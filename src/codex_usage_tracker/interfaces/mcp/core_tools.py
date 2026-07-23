"""Stable adapters for the core MCP tool profile."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.application.allowance import AllowanceAnalysisRuntime, get_allowance
from codex_usage_tracker.application.allowance_models import AllowanceRequest
from codex_usage_tracker.application.container import ApplicationContainer
from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.evidence import get_evidence
from codex_usage_tracker.application.job_status import JobStatusService, get_job_status
from codex_usage_tracker.application.refresh import REFRESH_SCHEMA, refresh_usage
from codex_usage_tracker.application.requests import (
    ExecutionMode,
    HistoryScope,
    JobStatusRequest,
    RefreshRequest,
    RequestScope,
    StatusRequest,
)
from codex_usage_tracker.application.status import STATUS_SCHEMA, _build_status
from codex_usage_tracker.core.contracts import (
    MessageV1,
    NextActionV1,
    enforce_payload_budget,
    envelope_payload,
)
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.evidence.models import EvidenceRequest
from codex_usage_tracker.interfaces.mcp.models import McpProfile
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import (
    build_usage_analyze as build_usage_analyze,
)
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import (
    build_usage_query as build_usage_query,
)
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import (
    usage_analyze as usage_analyze,
)
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import (
    usage_query as usage_query,
)
from codex_usage_tracker.jobs.service import JobService

MAX_STATUS_PAYLOAD_BYTES = 16 * 1024
MAX_REFRESH_PAYLOAD_BYTES = 64 * 1024
MAX_EVIDENCE_PAYLOAD_BYTES = 128 * 1024
MAX_ALLOWANCE_PAYLOAD_BYTES = 128 * 1024


def usage_status() -> dict[str, object]:
    """Return McpEnvelopeV1 containing status.v2."""
    return build_usage_status()


def usage_refresh(
    history: str = "active",
    aggregate_only: bool = True,
    execution: str = "auto",
) -> dict[str, object]:
    """Refresh bounded work synchronously or return a generic refresh job."""
    return build_usage_refresh(
        history=history,
        aggregate_only=aggregate_only,
        execution=execution,
    )


def usage_job_status(job_id: str, include_result: bool = False) -> dict[str, object]:
    """Poll one registered generic job through the shared core service."""
    return build_usage_job_status(job_id=job_id, include_result=include_result)


def usage_evidence(
    selector_kind: str,
    selector_id: str,
    section: str = "summary",
    limit: int = 20,
    cursor: str | None = None,
    history: str = "active",
    analysis_id: str | None = None,
) -> dict[str, object]:
    """Open exact canonical aggregate evidence selected by a prior tool result."""
    return build_usage_evidence(
        selector_kind=selector_kind,
        selector_id=selector_id,
        section=section,
        limit=limit,
        cursor=cursor,
        history=history,
        analysis_id=analysis_id,
    )


def usage_allowance(
    operation: str,
    window: str = "weekly",
    range: str = "8w",  # noqa: A002 - public roadmap field name.
    cursor: str | None = None,
    limit: int = 50,
    analysis_id: str | None = None,
    execution: str = "auto",
) -> dict[str, object]:
    """Read bounded allowance state or run its persisted aggregate analysis."""
    return build_usage_allowance(
        operation=operation,
        window=window,
        range_preset=range,
        cursor=cursor,
        limit=limit,
        analysis_id=analysis_id,
        execution=execution,
    )


def build_usage_allowance(
    *,
    operation: str,
    window: str = "weekly",
    range_preset: str = "8w",
    cursor: str | None = None,
    limit: int = 50,
    analysis_id: str | None = None,
    execution: str = "auto",
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    now: datetime | None = None,
    job_service: JobService | None = None,
    runtime: AllowanceAnalysisRuntime | None = None,
    container: ApplicationContainer | None = None,
) -> dict[str, object]:
    if container is not None:
        db_path = container.paths.db_path
        pricing_path = container.paths.pricing_path
        now = now or container.clock.now()
        job_service = job_service or container.jobs
    request = AllowanceRequest(
        operation=cast(Any, operation),
        window=cast(Any, window),
        range=range_preset,
        cursor=cursor,
        limit=limit,
        analysis_id=analysis_id,
        execution=cast(Any, execution),
    )
    result = get_allowance(
        request,
        db_path=db_path,
        now=now,
        job_service=job_service,
        runtime=runtime,
    )
    context = (
        container.request_context(RequestScope(privacy_mode="strict"))
        if container is not None
        else build_request_context(
            db_path=db_path,
            pricing_path=pricing_path,
            scope=RequestScope(privacy_mode="strict"),
        )
    )
    state = result.payload.get("state")
    job_id = result.payload.get("job_id")
    next_actions = ()
    if (
        result.result_schema == "codex-usage-tracker.job.v1"
        and state in {"queued", "running"}
        and isinstance(job_id, str)
    ):
        next_actions = (
            NextActionV1(
                code="job.poll",
                label="Poll allowance analysis job",
                tool="usage_job_status",
                arguments={"job_id": job_id, "include_result": True},
            ),
        )
    payload = envelope_payload(
        tool="usage_allowance",
        result_schema=result.result_schema,
        result=result.payload,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="aggregate",
        dashboard_targets=(result.dashboard_target,),
        next_actions=next_actions,
    )
    enforce_payload_budget(payload, MAX_ALLOWANCE_PAYLOAD_BYTES, "usage_allowance")
    return payload


def build_usage_evidence(
    *,
    selector_kind: str,
    selector_id: str,
    section: str = "summary",
    limit: int = 20,
    cursor: str | None = None,
    history: str = "active",
    analysis_id: str | None = None,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    job_service: JobService | None = None,
    container: ApplicationContainer | None = None,
) -> dict[str, object]:
    if container is not None:
        db_path = container.paths.db_path
        pricing_path = container.paths.pricing_path
        allowance_path = container.paths.allowance_path
        job_service = job_service or container.jobs
    request = EvidenceRequest(
        selector_kind=cast(Any, selector_kind),
        selector_id=selector_id,
        section=section,
        limit=limit,
        cursor=cursor,
        history=cast(Any, history),
        analysis_id=analysis_id,
    )
    scope = RequestScope(
        history=cast(HistoryScope, request.history),
        thread_key=request.selector_id if request.selector_kind == "thread" else None,
    )
    context = (
        container.request_context(scope)
        if container is not None
        else build_request_context(db_path=db_path, pricing_path=pricing_path, scope=scope)
    )
    result = get_evidence(
        request,
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        job_service=job_service,
        context=context,
    )
    payload = envelope_payload(
        tool="usage_evidence",
        result_schema=result.schema,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="aggregate",
        dashboard_targets=(result.dashboard_target,),
    )
    enforce_payload_budget(payload, MAX_EVIDENCE_PAYLOAD_BYTES, "usage_evidence")
    return payload


def build_usage_status(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    codex_home: Path = DEFAULT_CODEX_HOME,
    home: Path | None = None,
    profile: str = "core",
    container: ApplicationContainer | None = None,
) -> dict[str, object]:
    """Build the core status envelope with explicit testable local dependencies."""
    if container is not None:
        db_path = container.paths.db_path
        pricing_path = container.paths.pricing_path
        codex_home = container.paths.codex_home
        home = home or codex_home.parent
    request = StatusRequest(
        db_path=db_path,
        pricing_path=pricing_path,
        codex_home=codex_home,
        home=home or Path.home(),
        mcp_profile=cast(McpProfile, profile),
    )
    if container is None:
        result, context = _build_status(request)
    else:
        context = container.request_context(
            request.scope,
            prefer_materialized_active=True,
        )
        result, context = _build_status(
            request,
            context=context,
            clock=container.clock,
            pricing_provider=container.pricing,
        )
    next_action = cast(dict[str, object], result["next_action"])
    payload = envelope_payload(
        tool="usage_status",
        result_schema=STATUS_SCHEMA,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="administrative",
        limitations=(
            MessageV1(
                code="mcp.current_task_exposure_unverified",
                severity="info",
                message="Current-task MCP tool exposure is not verified by this status call.",
            ),
        ),
        next_actions=(
            NextActionV1(
                code=cast(str, next_action["code"]),
                label=cast(str, next_action["label"]),
                tool=cast(str | None, next_action["tool"]),
                arguments=cast(dict[str, object], next_action["arguments"]),
            ),
        ),
    )
    enforce_payload_budget(payload, MAX_STATUS_PAYLOAD_BYTES, "usage_status")
    return payload


def build_usage_refresh(
    *,
    history: str = "active",
    aggregate_only: bool = True,
    execution: str = "auto",
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    codex_home: Path = DEFAULT_CODEX_HOME,
    container: ApplicationContainer | None = None,
) -> dict[str, object]:
    if container is not None:
        db_path = container.paths.db_path
        pricing_path = container.paths.pricing_path
        codex_home = container.paths.codex_home
    request = RefreshRequest(
        history=cast(HistoryScope, history),
        aggregate_only=aggregate_only,
        execution=cast(ExecutionMode, execution),
    )
    outcome = refresh_usage(
        request,
        db_path=db_path,
        pricing_path=pricing_path,
        codex_home=codex_home,
        source_repository=(None if container is None else container.repositories.sources),
        job_service=None if container is None else container.jobs,
    )
    context = (
        container.request_context(RequestScope(history=request.history))
        if container is not None
        else build_request_context(
            db_path=db_path,
            pricing_path=pricing_path,
            scope=RequestScope(history=request.history),
        )
    )
    if outcome.result is not None:
        result_schema = REFRESH_SCHEMA
        result: object = outcome.result
        next_actions: tuple[NextActionV1, ...] = ()
    else:
        if outcome.job is None:
            raise RuntimeError("refresh outcome contained neither a result nor a job")
        job = outcome.job
        result_schema = "codex-usage-tracker.job.v1"
        result = job.to_payload()
        next_actions = (
            NextActionV1(
                code="job.poll",
                label="Poll refresh job",
                tool="usage_job_status",
                arguments={"job_id": job.job_id},
            ),
        )
    payload = envelope_payload(
        tool="usage_refresh",
        result_schema=result_schema,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="administrative",
        next_actions=next_actions,
    )
    enforce_payload_budget(payload, MAX_REFRESH_PAYLOAD_BYTES, "usage_refresh")
    return payload


def build_usage_job_status(
    *,
    job_id: str,
    include_result: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    job_service: JobStatusService | None = None,
    container: ApplicationContainer | None = None,
) -> dict[str, object]:
    if container is not None:
        db_path = container.paths.db_path
        pricing_path = container.paths.pricing_path
        job_service = job_service or container.jobs
    request = JobStatusRequest(job_id=job_id, include_result=include_result)
    status = get_job_status(request, job_service=job_service)
    context = (
        container.request_context(RequestScope())
        if container is not None
        else build_request_context(
            db_path=db_path,
            pricing_path=pricing_path,
            scope=RequestScope(),
        )
    )
    payload = envelope_payload(
        tool="usage_job_status",
        result_schema="codex-usage-tracker.job.v1",
        result=status.to_payload(),
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="administrative",
        next_actions=(
            ()
            if status.state in {"completed", "failed", "cancelled"}
            else (
                NextActionV1(
                    code="job.poll",
                    label="Poll job again",
                    tool="usage_job_status",
                    arguments={"job_id": status.job_id, "include_result": include_result},
                ),
            )
        ),
    )
    enforce_payload_budget(
        payload,
        MAX_REFRESH_PAYLOAD_BYTES if include_result else MAX_STATUS_PAYLOAD_BYTES,
        "usage_job_status",
    )
    return payload
