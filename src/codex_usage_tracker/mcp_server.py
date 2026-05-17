"""MCP server exposing aggregate-only Codex usage tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from datetime import date, timedelta

from mcp.server.fastmcp import FastMCP

from codex_usage_tracker.dashboard import generate_dashboard
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.formatting import (
    format_calls,
    format_doctor,
    format_pricing_coverage,
    format_session,
    format_summary,
)
from codex_usage_tracker.paths import (
    DEFAULT_CODEX_HOME,
    DEFAULT_DASHBOARD_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
)
from codex_usage_tracker.pricing import (
    annotate_rows_with_efficiency,
    load_pricing_config,
    summarize_pricing_coverage,
    update_pricing_from_openai_docs,
    write_pricing_template,
)
from codex_usage_tracker.store import (
    export_usage_csv as export_csv,
    query_most_expensive_calls,
    query_session_usage,
    query_summary,
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
    return {
        "scanned_files": result.scanned_files,
        "parsed_events": result.parsed_events,
        "inserted_or_updated_events": result.inserted_or_updated_events,
        "db_path": result.db_path,
    }


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
) -> str:
    """Summarize aggregate Codex token usage by date, model, effort, cwd, thread, or session."""

    group_by, since_filter = _resolve_summary_options(group_by, preset, since)
    pricing = load_pricing_config(DEFAULT_PRICING_PATH)
    if preset == "expensive":
        rows = query_most_expensive_calls(DEFAULT_DB_PATH, limit=limit, since=since_filter)
        return format_calls(annotate_rows_with_efficiency(rows, pricing))
    rows = query_summary(
        DEFAULT_DB_PATH, group_by=group_by, limit=limit, since=since_filter
    )
    if group_by == "model":
        rows = annotate_rows_with_efficiency(rows, pricing, model_field="group_key")
    return format_summary(rows, group_by)


@mcp.tool()
def session_usage(session_id: str | None = None, limit: int = 200) -> str:
    """Show aggregate per-call usage for one session, defaulting to the latest indexed session."""

    rows = query_session_usage(DEFAULT_DB_PATH, session_id=session_id, limit=limit)
    return format_session(rows)


@mcp.tool()
def most_expensive_usage_calls(
    limit: int = 20, preset: str | None = None, since: str | None = None
) -> str:
    """Show the highest last-call aggregate usage rows with efficiency signals."""

    pricing = load_pricing_config(DEFAULT_PRICING_PATH)
    rows = query_most_expensive_calls(
        DEFAULT_DB_PATH, limit=limit, since=_resolve_since(preset, since)
    )
    return format_calls(annotate_rows_with_efficiency(rows, pricing))


@mcp.tool()
def usage_pricing_coverage(
    limit: int = 20,
    since: str | None = None,
    response_format: str = "markdown",
) -> str | dict[str, Any]:
    """Show priced, estimated, and unpriced token coverage by model."""

    pricing = load_pricing_config(DEFAULT_PRICING_PATH)
    rows = query_summary(DEFAULT_DB_PATH, group_by="model", limit=1000, since=since)
    report = summarize_pricing_coverage(rows, pricing=pricing)
    if response_format == "json":
        return report
    return format_pricing_coverage(report, limit=limit)


@mcp.tool()
def generate_usage_dashboard(
    output_path: str | None = None, limit: int = 5000, since: str | None = None
) -> dict[str, Any]:
    """Generate a local hoverable HTML dashboard from aggregate-only usage metrics."""

    output = Path(output_path).expanduser() if output_path else DEFAULT_DASHBOARD_PATH
    generated = generate_dashboard(
        DEFAULT_DB_PATH,
        output_path=output,
        limit=limit,
        pricing_path=DEFAULT_PRICING_PATH,
        since=since,
    )
    return {"dashboard_path": str(generated), "file_url": generated.resolve().as_uri()}


@mcp.tool()
def export_usage_csv(output_path: str, limit: int | None = None) -> dict[str, Any]:
    """Export aggregate Codex token usage rows to a local CSV file."""

    output = Path(output_path).expanduser()
    rows = export_csv(output_path=output, db_path=DEFAULT_DB_PATH, limit=limit)
    return {"rows": rows, "csv_path": str(output)}


@mcp.tool()
def init_usage_pricing_config(force: bool = False) -> dict[str, Any]:
    """Write a local pricing template for optional cost estimates."""

    output = write_pricing_template(DEFAULT_PRICING_PATH, force=force)
    return {"pricing_path": str(output)}


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
        "pricing_path": str(result.path),
        "source_url": result.source_url,
        "tier": result.tier,
        "fetched_at": result.fetched_at,
        "model_count": result.model_count,
        "estimated_model_count": result.estimated_model_count,
        "backup_path": str(result.backup_path) if result.backup_path else None,
    }


def _resolve_summary_options(
    group_by: str, preset: str | None, since: str | None
) -> tuple[str, str | None]:
    if preset == "by-model":
        group_by = "model"
    elif preset == "by-cwd":
        group_by = "cwd"
    elif preset == "by-thread":
        group_by = "thread"
    return group_by, _resolve_since(preset, since)


def _resolve_since(preset: str | None, since: str | None) -> str | None:
    if since:
        return since
    if preset == "today":
        return date.today().isoformat()
    if preset == "last-7-days":
        return (date.today() - timedelta(days=6)).isoformat()
    return None


if __name__ == "__main__":
    mcp.run()
