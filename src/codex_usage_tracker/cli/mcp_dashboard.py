"""Dashboard API and local export/config MCP tools."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.core.dashboard_targets import build_dashboard_target
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.dashboard.api import generate_dashboard
from codex_usage_tracker.dashboard_service import DashboardServiceStatus, dashboard_service_status
from codex_usage_tracker.diagnostics.dedupe import build_dedupe_diagnostics
from codex_usage_tracker.pricing.allowance import write_allowance_template
from codex_usage_tracker.pricing.api import (
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.server.call_detail import call_detail_payload
from codex_usage_tracker.server.call_lists import calls_payload
from codex_usage_tracker.server.live_queries import live_query_params
from codex_usage_tracker.server.live_rows import annotate_live_rows, query_live_call_rows
from codex_usage_tracker.server.recommendations import recommendations_payload
from codex_usage_tracker.server.reports import reports_pack_payload
from codex_usage_tracker.server.status import status_payload
from codex_usage_tracker.server.threads import threads_payload
from codex_usage_tracker.store.api import export_usage_csv as export_csv


def _query_string(**values: object) -> str:
    query: dict[str, str] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, bool):
            query[key] = "true" if value else "false"
        else:
            query[key] = str(value)
    return urlencode(query)


def _live_query_params(
    params: dict[str, list[str]],
    *,
    include_archived_default: bool = False,
    thread_key: str | None = None,
) -> dict[str, Any]:
    return live_query_params(
        params,
        include_archived_default=include_archived_default,
        thread_key=thread_key,
    )


def _annotate_dashboard_rows(
    rows: list[dict[str, Any]],
    *,
    privacy_mode: str,
) -> list[dict[str, Any]]:
    return annotate_live_rows(
        rows,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        thresholds_path=DEFAULT_THRESHOLDS_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        privacy_mode=privacy_mode,
    )


def _live_call_rows(
    *,
    query_params: dict[str, Any],
    pricing_status: str | None,
    credit_confidence: str | None,
    privacy_mode: str,
) -> tuple[list[dict[str, Any]], int]:
    return query_live_call_rows(
        db_path=DEFAULT_DB_PATH,
        query_params=query_params,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        thresholds_path=DEFAULT_THRESHOLDS_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        privacy_mode=privacy_mode,
    )


def attach_dashboard_targets(
    payload: dict[str, Any],
    *,
    privacy_mode: str = "normal",
    history: str = "active",
) -> dict[str, Any]:
    """Attach additive evidence links without changing the source payload contract."""

    try:
        service_status: DashboardServiceStatus | None = dashboard_service_status(home=Path.home())
    except Exception:  # A local annotation failure must not break an MCP result.
        service_status = None

    def target(*, target_history: str = history, **values: Any) -> dict[str, Any] | None:
        try:
            return build_dashboard_target(
                privacy_mode=privacy_mode,
                service_status=service_status,
                history=target_history,
                **values,
            )
        except ValueError:
            return None

    def attach_row(row: object) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        record_id = row.get("record_id")
        thread_key = row.get("thread_key")
        archived = row.get("is_archived")
        row_history = (
            "all" if archived is True or isinstance(archived, int) and archived == 1 else history
        )
        row_target = (
            target(view="call", record_id=record_id, target_history=row_history)
            if isinstance(record_id, str)
            else target(view="threads", thread_key=thread_key, target_history=row_history)
            if isinstance(thread_key, str)
            else None
        )
        if row_target is not None:
            row["dashboard_target"] = row_target
        return row_target

    schema = payload.get("schema")
    if schema == "codex-usage-tracker-status-v1":
        payload["dashboard_target"] = target(view="overview")
    elif schema == "codex-usage-tracker-calls-v1":
        for row in payload.get("rows", []):
            attach_row(row)
    elif schema == "codex-usage-tracker-call-v1":
        record = payload.get("record")
        detail_target = attach_row(record)
        for key in ("previous_record", "next_record"):
            attach_row(payload.get(key))
        for row in payload.get("adjacent_records", []):
            attach_row(row)
        if detail_target is not None:
            payload["dashboard_target"] = detail_target
    elif schema == "codex-usage-tracker-threads-v1":
        for row in payload.get("rows", []):
            attach_row(row)

    findings = payload.get("findings")
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            evidence = finding.get("evidence")
            if isinstance(evidence, list):
                finding_target = None
                for row in evidence:
                    evidence_target = attach_row(row)
                    if finding_target is None and evidence_target is not None:
                        finding_target = evidence_target
                if finding_target is not None:
                    finding["dashboard_target"] = deepcopy(finding_target)
    return payload


@mcp.tool()
def usage_status(include_archived: bool = False) -> dict[str, Any]:
    """Return live dashboard status counts and parser freshness metadata."""
    return attach_dashboard_targets(
        status_payload(
            _query_string(include_archived=include_archived),
            codex_home=DEFAULT_CODEX_HOME,
            db_path=DEFAULT_DB_PATH,
            pricing_path=DEFAULT_PRICING_PATH,
            allowance_path=DEFAULT_ALLOWANCE_PATH,
            rate_card_path=DEFAULT_RATE_CARD_PATH,
            include_archived_default=include_archived,
        ),
        history="all" if include_archived else "active",
    )


@mcp.tool()
def usage_dedupe_diagnostics(limit: int = 100) -> dict[str, Any]:
    """Return dedupe totals and bounded physical provenance for excluded clone copies."""

    return build_dedupe_diagnostics(db_path=DEFAULT_DB_PATH, limit=limit)


@mcp.tool()
def usage_calls(
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    include_archived: bool = False,
    sort: str = "time",
    direction: str = "desc",
    limit: int | None = 100,
    offset: int = 0,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return the dashboard Calls API payload as aggregate JSON rows."""
    query = _query_string(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    return attach_dashboard_targets(
        calls_payload(
            query,
            live_query_params=lambda params: _live_query_params(
                params,
                include_archived_default=include_archived,
                thread_key=thread_key,
            ),
            live_call_rows=lambda *, query_params, pricing_status, credit_confidence: (
                _live_call_rows(
                    query_params=query_params,
                    pricing_status=pricing_status,
                    credit_confidence=credit_confidence,
                    privacy_mode=privacy_mode,
                )
            ),
        ),
        privacy_mode=privacy_mode,
        history="all" if include_archived else "active",
    )


@mcp.tool()
def usage_call_detail(
    record_id: str,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return dashboard call investigator payload for one aggregate record."""
    return attach_dashboard_targets(
        call_detail_payload(
            _query_string(record_id=record_id),
            db_path=DEFAULT_DB_PATH,
            annotate_rows=lambda rows: _annotate_dashboard_rows(
                rows,
                privacy_mode=privacy_mode,
            ),
        ),
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_threads(
    search: str | None = None,
    include_archived: bool = False,
    sort: str = "tokens",
    direction: str = "desc",
    limit: int | None = 100,
    offset: int = 0,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return the dashboard Threads API payload as aggregate JSON rows."""
    return attach_dashboard_targets(
        threads_payload(
            _query_string(
                search=search,
                include_archived=include_archived,
                sort=sort,
                direction=direction,
                limit=limit,
                offset=offset,
            ),
            db_path=DEFAULT_DB_PATH,
            include_archived_default=include_archived,
        ),
        privacy_mode=privacy_mode,
        history="all" if include_archived else "active",
    )


@mcp.tool()
def usage_dashboard_recommendations(
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    min_score: float | None = None,
    limit: int = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return the dashboard recommendations payload in structured JSON."""
    return recommendations_payload(
        _query_string(
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            project=project,
            min_score=min_score,
            limit=limit,
        ),
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_report_pack(
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    report_key: str | None = None,
    evidence_limit: int = 10,
    include_archived: bool = False,
    sort: str = "time",
    direction: str = "desc",
    limit: int | None = 100,
    offset: int = 0,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return aggregate dashboard report cards and evidence rows."""
    query = _query_string(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        report_key=report_key,
        evidence_limit=evidence_limit,
        include_archived=include_archived,
        sort=sort,
        direction=direction,
        limit=limit,
        offset=offset,
    )
    return reports_pack_payload(
        query,
        live_query_params=lambda params: _live_query_params(
            params,
            include_archived_default=include_archived,
            thread_key=thread_key,
        ),
        live_call_rows=lambda *, query_params, pricing_status, credit_confidence: _live_call_rows(
            query_params=query_params,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
            privacy_mode=privacy_mode,
        ),
    )


@mcp.tool()
def generate_usage_dashboard(
    output_path: str | None = None,
    limit: int = 5000,
    since: str | None = None,
    privacy_mode: str = "normal",
    include_archived: bool = False,
) -> dict[str, Any]:
    """Generate a local hoverable HTML dashboard from aggregate-only usage metrics."""
    output = Path(output_path).expanduser() if output_path else DEFAULT_DASHBOARD_PATH
    generated = generate_dashboard(
        DEFAULT_DB_PATH,
        output_path=output,
        limit=limit,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        since=since,
        privacy_mode=privacy_mode,
        include_archived=include_archived,
    )
    return {
        "schema": "codex-usage-tracker-dashboard-v1",
        "dashboard_path": str(generated),
        "file_url": generated.resolve().as_uri(),
        "opened": False,
        "limit": None if limit <= 0 else limit,
        "since": since,
        "privacy_mode": privacy_mode,
        "include_archived": include_archived,
    }


@mcp.tool()
def export_usage_csv(
    output_path: str,
    limit: int | None = None,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Export aggregate Codex token usage rows to a local CSV file."""
    output = Path(output_path).expanduser()
    rows = export_csv(
        output_path=output,
        db_path=DEFAULT_DB_PATH,
        limit=limit,
        privacy_mode=privacy_mode,
    )
    return {
        "schema": "codex-usage-tracker-export-v1",
        "rows": rows,
        "csv_path": str(output),
        "limit": limit,
        "privacy_mode": privacy_mode,
    }


@mcp.tool()
def init_usage_pricing_config(force: bool = False) -> dict[str, Any]:
    """Write a local pricing template for optional cost estimates."""
    output = write_pricing_template(DEFAULT_PRICING_PATH, force=force)
    return {
        "schema": "codex-usage-tracker-init-pricing-v1",
        "pricing_path": str(output),
        "created": True,
    }


@mcp.tool()
def init_usage_allowance_config(force: bool = False) -> dict[str, Any]:
    """Write a local template for optional Codex allowance windows."""
    output = write_allowance_template(DEFAULT_ALLOWANCE_PATH, force=force)
    return {
        "schema": "codex-usage-tracker-init-allowance-v1",
        "allowance_path": str(output),
        "created": True,
    }


@mcp.tool()
def update_usage_pricing_config(
    tier: str = "standard", include_estimates: bool = True
) -> dict[str, Any]:
    """Fetch OpenAI-published text-token pricing into the local pricing config."""
    result = update_pricing_from_openai_docs(
        DEFAULT_PRICING_PATH,
        tier=tier,
        include_estimates=include_estimates,
    )
    return {
        "schema": "codex-usage-tracker-update-pricing-v1",
        "pricing_path": str(result.path),
        "source_url": result.source_url,
        "tier": result.tier,
        "fetched_at": result.fetched_at,
        "model_count": result.model_count,
        "estimated_model_count": result.estimated_model_count,
        "backup_path": str(result.backup_path) if result.backup_path else None,
    }
