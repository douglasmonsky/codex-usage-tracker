"""MCP server exposing aggregate-only Codex usage tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from codex_usage_tracker.allowance import write_allowance_template
from codex_usage_tracker.api_payloads import refresh_result_payload, session_payload
from codex_usage_tracker.context import DEFAULT_CONTEXT_CHARS, load_call_context
from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.formatting import (
    format_doctor,
    format_session,
)
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
)
from codex_usage_tracker.pricing import (
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.projects import apply_project_privacy_to_rows
from codex_usage_tracker.reports import (
    build_expensive_calls_report,
    build_pricing_coverage_report,
    build_query_report,
    build_recommendations_report,
    build_summary_report,
)
from codex_usage_tracker.store import (
    export_usage_csv as export_csv,
)
from codex_usage_tracker.store import (
    query_session_usage,
)
from codex_usage_tracker.store import (
    refresh_usage_index as refresh_index,
)

mcp = FastMCP("codex-usage-tracker")


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
    include_tool_output: bool = False,
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
        include_tool_output=include_tool_output,
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
