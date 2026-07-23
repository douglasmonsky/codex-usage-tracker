"""Application orchestration for canonical aggregate evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from codex_usage_tracker.application.context import RequestContext, build_request_context
from codex_usage_tracker.application.errors import RequestContextError
from codex_usage_tracker.application.query import query_usage
from codex_usage_tracker.application.query_models import QueryFilters, QueryRequest
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.core.contracts import EvidenceV1
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH, DEFAULT_PRICING_PATH
from codex_usage_tracker.evidence.models import (
    EvidenceHistoryMismatchError,
    EvidenceRequest,
    EvidenceResult,
)
from codex_usage_tracker.evidence.service import EvidenceRepository, resolve_evidence
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.store.allowance_intelligence import query_allowance_evidence_record
from codex_usage_tracker.store.api import connect
from codex_usage_tracker.store.thread_summaries import query_thread_summary
from codex_usage_tracker.store.usage_record_queries import query_usage_record

_CALL_METRICS = (
    "total_tokens",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "cache_ratio",
    "context_window_percent",
)
_THREAD_METRICS = (
    "call_count",
    "total_tokens",
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "avg_cache_ratio",
    "max_context_window_percent",
)
_ALLOWANCE_METRICS = (
    "window_kind",
    "cohort_key",
    "point_kind",
    "credits_per_percent",
    "percent_delta",
    "credits_delta",
    "end_observed_at",
    "quality_grade",
)


def get_evidence(
    request: EvidenceRequest,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    job_service: JobService | None = None,
    context: RequestContext | None = None,
) -> EvidenceResult:
    """Resolve one request with a single scope/revision context."""
    scope = RequestScope(
        history=request.history,
        thread_key=request.selector_id if request.selector_kind == "thread" else None,
    )
    if context is not None and context.scope != scope.to_contract():
        raise RequestContextError("evidence context scope does not match the request")
    if context is None and _requires_request_context(request):
        context = build_request_context(db_path=db_path, pricing_path=pricing_path, scope=scope)
    repository = _LocalEvidenceRepository(db_path, context, job_service)
    return resolve_evidence(request, repository)


def _requires_request_context(request: EvidenceRequest) -> bool:
    """Only cursor- or revision-aware evidence needs global accounting context."""
    return request.selector_kind in {"finding", "analysis"} or (
        request.selector_kind == "thread" and request.section == "calls"
    )


class _LocalEvidenceRepository(EvidenceRepository):
    def __init__(
        self, db_path: Path, context: RequestContext | None, job_service: JobService | None
    ) -> None:
        self.db_path = db_path
        self.context = context
        if job_service is None:
            from codex_usage_tracker.application.refresh import default_job_service

            job_service = default_job_service()
        self.job_service = job_service

    def source_revision(self) -> str | None:
        if self.context is None:
            raise RuntimeError("source revision requires request context")
        return self.context.source_revision

    def call(self, selector_id: str, history: str) -> EvidenceV1 | None:
        row = query_usage_record(self.db_path, selector_id, include_archived=history == "all")
        if (
            row is None
            and history == "active"
            and query_usage_record(self.db_path, selector_id, include_archived=True) is not None
        ):
            raise EvidenceHistoryMismatchError(f"call is archived: {selector_id}")
        return (
            None
            if row is None
            else _record(
                "call",
                selector_id,
                {"record_id": selector_id},
                row,
                _CALL_METRICS,
                "canonical_usage.v2",
            )
        )

    def thread_summary(self, selector_id: str, history: str) -> EvidenceV1 | None:
        row = query_thread_summary(
            self.db_path, thread_key=selector_id, include_archived=history == "all"
        )
        if row is None and history == "active":
            archived = query_thread_summary(
                self.db_path, thread_key=selector_id, include_archived=True
            )
            if archived is not None:
                raise EvidenceHistoryMismatchError(f"thread is archived: {selector_id}")
        return (
            None
            if row is None
            else _record(
                "thread",
                selector_id,
                {"thread_key": selector_id},
                row,
                _THREAD_METRICS,
                "thread_summaries.v1",
            )
        )

    def thread_calls(
        self, selector_id: str, history: str, limit: int, cursor: str | None
    ) -> tuple[tuple[EvidenceV1, ...], str | None]:
        if self.context is None:
            raise RuntimeError("thread call evidence requires request context")
        result = query_usage(
            QueryRequest(
                entity="call",
                measures=("tokens", "cached_tokens", "output_tokens"),
                filters=QueryFilters(thread_key=selector_id),
                order_by="tokens",
                limit=limit,
                cursor=cursor,
                history=cast(Any, history),
            ),
            db_path=self.db_path,
            context=self.context,
        )
        records = tuple(
            _record(
                "call",
                str(row["record_id"]),
                {"record_id": str(row["record_id"]), "thread_key": selector_id},
                row,
                ("tokens", "cached_tokens", "output_tokens"),
                "codex-usage-tracker.query.v2",
            )
            for row in result.rows
        )
        if not records and cursor is None:
            self.thread_summary(selector_id, history)
        return records, result.next_cursor

    def allowance(self, selector_id: str, history: str) -> EvidenceV1 | None:
        with connect(self.db_path) as connection:
            row = query_allowance_evidence_record(
                connection, interval_id=selector_id, include_archived=history == "all"
            )
            if row is None and history == "active":
                archived = query_allowance_evidence_record(
                    connection, interval_id=selector_id, include_archived=True
                )
                if archived is not None:
                    raise EvidenceHistoryMismatchError(
                        f"allowance evidence is archived: {selector_id}"
                    )
        return (
            None
            if row is None
            else _record(
                "allowance_cycle",
                selector_id,
                {"interval_id": selector_id},
                row,
                _ALLOWANCE_METRICS,
                "allowance_intervals.v1",
            )
        )

    def completed_analyses(self) -> tuple[Mapping[str, object], ...]:
        if self.context is None:
            raise RuntimeError("analysis evidence requires request context")
        results = self.job_service.completed_results(
            kind="analysis",
            result_schema="codex-usage-tracker.analysis.v2",
            source_revision=self.context.source_revision,
        )
        return tuple(_typed_analysis(result) for result in results)


def _record(
    kind: str,
    evidence_id: str,
    selectors: dict[str, str],
    row: Mapping[str, object],
    fields: tuple[str, ...],
    source_schema: str,
) -> EvidenceV1:
    return EvidenceV1(
        evidence_id=f"{kind}:{evidence_id}",
        kind=cast(Any, kind),
        label=evidence_id,
        selectors=selectors,
        metrics={key: cast(Any, row.get(key)) for key in fields if key in row},
        source_schema=source_schema,
        dashboard_target=None,
    )


def _typed_analysis(result: Mapping[str, object]) -> Mapping[str, object]:
    raw_evidence = result.get("evidence")
    evidence = (
        tuple(_typed_evidence(item) for item in raw_evidence if isinstance(item, Mapping))
        if isinstance(raw_evidence, (list, tuple))
        else ()
    )
    return {**result, "evidence": evidence}


def _typed_evidence(value: Mapping[str, object]) -> EvidenceV1:
    return EvidenceV1(
        evidence_id=cast(str, value["evidence_id"]),
        kind=cast(Any, value["kind"]),
        label=cast(str, value["label"]),
        selectors=cast(Mapping[str, str], value["selectors"]),
        metrics=cast(Any, value["metrics"]),
        source_schema=cast(str, value["source_schema"]),
        dashboard_target=cast(Mapping[str, object] | None, value.get("dashboard_target")),
    )
