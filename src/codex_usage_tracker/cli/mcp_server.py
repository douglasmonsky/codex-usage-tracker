"""MCP server exposing aggregate-only Codex usage tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from mcp.server.fastmcp import FastMCP

from codex_usage_tracker.allowance_intelligence import (
    build_allowance_diagnostics_report,
    build_allowance_export_report,
    build_allowance_history_report,
)
from codex_usage_tracker.context.api import (
    DEFAULT_CONTEXT_CHARS,
    DEFAULT_CONTEXT_ENTRIES,
    load_call_context,
)
from codex_usage_tracker.core.api_payloads import refresh_result_payload, session_payload
from codex_usage_tracker.core.formatting import (
    format_doctor,
    format_session,
)
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
from codex_usage_tracker.core.projects import apply_project_privacy_to_rows
from codex_usage_tracker.dashboard.api import generate_dashboard
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.pricing.allowance import write_allowance_template
from codex_usage_tracker.pricing.api import (
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.reports.api import (
    build_expensive_calls_report,
    build_pricing_coverage_report,
    build_query_report,
    build_recommendations_report,
    build_source_coverage_report,
    build_summary_report,
)
from codex_usage_tracker.server.call_detail import call_detail_payload
from codex_usage_tracker.server.call_lists import calls_payload
from codex_usage_tracker.server.live_queries import live_query_params
from codex_usage_tracker.server.live_rows import annotate_live_rows, query_live_call_rows
from codex_usage_tracker.server.recommendations import recommendations_payload
from codex_usage_tracker.server.reports import reports_pack_payload
from codex_usage_tracker.server.status import status_payload
from codex_usage_tracker.server.threads import threads_payload
from codex_usage_tracker.store.api import (
    export_usage_csv as export_csv,
)
from codex_usage_tracker.store.api import (
    query_session_usage,
)
from codex_usage_tracker.store.api import (
    refresh_usage_index as refresh_index,
)

mcp = FastMCP("codex-usage-tracker")


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


@mcp.tool()
def refresh_usage_index(include_archived: bool = False) -> dict[str, Any]:
    """Scan local Codex logs and upsert aggregate usage metrics into SQLite."""

    result = refresh_index(
        codex_home=DEFAULT_CODEX_HOME,
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
    )
    return refresh_result_payload(result, schema="codex-usage-tracker-refresh-v1")


@mcp.tool()
def usage_doctor(response_format: str = "markdown") -> str | dict[str, Any]:
    """Check the local plugin, MCP, database, dashboard, and pricing setup."""

    report = run_doctor(db_path=DEFAULT_DB_PATH, pricing_path=DEFAULT_PRICING_PATH)
    if response_format == "json":
        return report
    return format_doctor(report)


@mcp.tool()
def usage_summary(
    group_by: str = "thread",
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Summarize aggregate Codex token usage by date, model, effort, cwd, thread, session, parent thread, or subagent metadata."""

    report = build_summary_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        group_by=group_by,
        limit=limit,
        preset=preset,
        since=since,
        privacy_mode=privacy_mode,
    )
    if response_format == "json":
        return report.payload()
    return report.render()


@mcp.tool()
def session_usage(
    session_id: str | None = None,
    limit: int = 200,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Show aggregate per-call usage for one session, defaulting to the latest indexed session."""

    rows = apply_project_privacy_to_rows(
        query_session_usage(DEFAULT_DB_PATH, session_id=session_id, limit=limit),
        privacy_mode=privacy_mode,
    )
    if response_format == "json":
        return session_payload(
            rows,
            requested_session_id=session_id,
            limit=limit,
            privacy_mode=privacy_mode,
        )
    return format_session(rows)


@mcp.tool()
def usage_call_context(
    record_id: str,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    max_entries: int = DEFAULT_CONTEXT_ENTRIES,
    include_tool_output: bool = False,
    include_compaction_history: bool = False,
) -> str:
    """Load one model call's logged local context on demand from its source JSONL file."""

    if os.environ.get("CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT") != "1":
        return json.dumps(
            {
                "schema": "codex-usage-tracker-context-disabled-v1",
                "error": (
                    "Raw context loading through MCP is disabled. Set "
                    "CODEX_USAGE_TRACKER_ALLOW_RAW_CONTEXT=1 to opt in for this process."
                ),
                "raw_context_enabled": False,
                "record_id": record_id,
            },
            indent=2,
        )
    payload = load_call_context(
        record_id=record_id,
        db_path=DEFAULT_DB_PATH,
        max_chars=max_chars,
        max_entries=max_entries,
        include_tool_output=include_tool_output,
        include_compaction_history=include_compaction_history,
    )
    return json.dumps(payload, indent=2)


@mcp.tool()
def most_expensive_usage_calls(
    limit: int = 20,
    preset: str | None = None,
    since: str | None = None,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Show the highest last-call aggregate usage rows with efficiency signals."""

    report = build_expensive_calls_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        limit=limit,
        preset=preset,
        since=since,
        privacy_mode=privacy_mode,
    )
    if response_format == "json":
        return report.payload()
    return report.render()


@mcp.tool()
def usage_query(
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    pricing_status: str | None = None,
    credit_confidence: str | None = None,
    min_tokens: int | None = None,
    min_credits: float | None = None,
    limit: int = 100,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return stable JSON aggregate usage rows with filters for automation."""

    return build_query_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        project=project,
        pricing_status=pricing_status,
        credit_confidence=credit_confidence,
        min_tokens=min_tokens,
        min_credits=min_credits,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_recommendations(
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    project: str | None = None,
    min_score: float | None = None,
    limit: int = 20,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Rank aggregate usage rows and threads by recommendation severity."""

    report = build_recommendations_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        project=project,
        min_score=min_score,
        limit=limit,
        privacy_mode=privacy_mode,
    )
    if response_format == "json":
        return report.payload
    return report.render()


@mcp.tool()
def usage_pricing_coverage(
    limit: int = 20,
    since: str | None = None,
    response_format: str = "markdown",
) -> str | dict[str, Any]:
    """Show priced, estimated, and unpriced token coverage by model."""

    report = build_pricing_coverage_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        since=since,
    )
    if response_format == "json":
        return report.payload
    return report.render(limit=limit)


@mcp.tool()
def usage_source_coverage(
    include_archived: bool = False,
    limit: int = 20,
    response_format: str = "markdown",
) -> str | dict[str, Any]:
    """Show source provenance parser coverage aggregate-only."""

    report = build_source_coverage_report(
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
    )
    if response_format == "json":
        return report.payload
    return report.render(limit=limit)


@mcp.tool()
def usage_status(include_archived: bool = False) -> dict[str, Any]:
    """Return live dashboard status counts and parser freshness metadata."""

    return status_payload(
        _query_string(include_archived=include_archived),
        db_path=DEFAULT_DB_PATH,
        include_archived_default=include_archived,
    )


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
    return calls_payload(
        query,
        live_query_params=lambda params: _live_query_params(
            params,
            include_archived_default=include_archived,
            thread_key=thread_key,
        ),
        live_call_rows=lambda *,
        query_params,
        pricing_status,
        credit_confidence: _live_call_rows(
            query_params=query_params,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
            privacy_mode=privacy_mode,
        ),
    )


@mcp.tool()
def usage_call_detail(
    record_id: str,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return dashboard call investigator payload for one aggregate record."""

    return call_detail_payload(
        _query_string(record_id=record_id),
        db_path=DEFAULT_DB_PATH,
        annotate_rows=lambda rows: _annotate_dashboard_rows(
            rows,
            privacy_mode=privacy_mode,
        ),
    )


@mcp.tool()
def usage_threads(
    search: str | None = None,
    include_archived: bool = False,
    sort: str = "tokens",
    direction: str = "desc",
    limit: int | None = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return the dashboard Threads API payload as aggregate JSON rows."""

    return threads_payload(
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
        live_call_rows=lambda *,
        query_params,
        pricing_status,
        credit_confidence: _live_call_rows(
            query_params=query_params,
            pricing_status=pricing_status,
            credit_confidence=credit_confidence,
            privacy_mode=privacy_mode,
        ),
    )


@mcp.tool()
def usage_allowance_history(
    window_kind: str | None = None,
    limit: int = 1000,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Return normalized observed allowance history aggregate JSON."""

    return build_allowance_history_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_allowance_report_limit(limit),
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_allowance_diagnostics(
    window_kind: str | None = None,
    limit: int = 10000,
    include_archived: bool = False,
    privacy_mode: str = "strict",
) -> dict[str, Any]:
    """Diagnose allowance movement against local credit estimates."""

    return build_allowance_diagnostics_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_allowance_report_limit(limit),
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_allowance_export(
    window_kind: str | None = None,
    limit: int = 10000,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return strict-privacy allowance evidence bundle for manual sharing."""

    return build_allowance_export_report(
        db_path=DEFAULT_DB_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        include_archived=include_archived,
        window_kind=window_kind,
        limit=_allowance_report_limit(limit),
    ).payload


def _allowance_report_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


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

if __name__ == "__main__":
    mcp.run()
