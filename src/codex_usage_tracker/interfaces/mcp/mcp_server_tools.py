"""Legacy full-profile MCP implementation tools."""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from codex_usage_tracker.context.api import (
    DEFAULT_CONTEXT_CHARS,
    DEFAULT_CONTEXT_ENTRIES,
    load_call_context,
)
from codex_usage_tracker.core.api_payloads import refresh_result_payload, session_payload
from codex_usage_tracker.core.formatting import format_doctor, format_session
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_CODEX_HOME,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import apply_project_privacy_to_rows
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.interfaces.mcp import mcp_allowance as _mcp_allowance
from codex_usage_tracker.interfaces.mcp import mcp_compression as mcp_compression
from codex_usage_tracker.interfaces.mcp import mcp_dogfood as _mcp_dogfood
from codex_usage_tracker.interfaces.mcp import mcp_visualization as mcp_visualization
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_call_detail as usage_call_detail,
)
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_calls as usage_calls,
)
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_dashboard_recommendations as usage_dashboard_recommendations,
)
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_dedupe_diagnostics as usage_dedupe_diagnostics,
)
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_report_pack as usage_report_pack,
)
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_status as usage_status,
)
from codex_usage_tracker.interfaces.mcp.mcp_dashboard import (
    usage_threads as usage_threads,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_command_loop_scan as usage_command_loop_scan,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_content_search as usage_content_search,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_file_churn_scan as usage_file_churn_scan,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_large_low_output_calls as usage_large_low_output_calls,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_pricing_coverage as usage_pricing_coverage,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_query as usage_query,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_recommendations as usage_recommendations,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_repeated_file_rediscovery as usage_repeated_file_rediscovery,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_repetition_scan as usage_repetition_scan,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_shell_churn as usage_shell_churn,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_source_coverage as usage_source_coverage,
)
from codex_usage_tracker.interfaces.mcp.mcp_discovery import (
    usage_thread_trace as usage_thread_trace,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood_tools import (
    usage_dogfood_result as usage_dogfood_result,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood_tools import (
    usage_dogfood_start as usage_dogfood_start,
)
from codex_usage_tracker.interfaces.mcp.mcp_dogfood_tools import (
    usage_dogfood_status as usage_dogfood_status,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_action_brief as usage_action_brief,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_context_bloat_scan as usage_context_bloat_scan,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_investigate as usage_investigate,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_investigation_walk as usage_investigation_walk,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_local_evidence_export as usage_local_evidence_export,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_suggest_investigations as usage_suggest_investigations,
)
from codex_usage_tracker.interfaces.mcp.mcp_investigations import (
    usage_test_hypotheses as usage_test_hypotheses,
)
from codex_usage_tracker.interfaces.mcp.mcp_local_operations import (
    export_usage_csv as export_usage_csv,
)
from codex_usage_tracker.interfaces.mcp.mcp_local_operations import (
    generate_usage_dashboard as generate_usage_dashboard,
)
from codex_usage_tracker.interfaces.mcp.mcp_local_operations import (
    init_usage_allowance_config as init_usage_allowance_config,
)
from codex_usage_tracker.interfaces.mcp.mcp_local_operations import (
    init_usage_pricing_config as init_usage_pricing_config,
)
from codex_usage_tracker.interfaces.mcp.mcp_local_operations import (
    update_usage_pricing_config as update_usage_pricing_config,
)
from codex_usage_tracker.interfaces.mcp.mcp_subagents import subagent_usage as subagent_usage
from codex_usage_tracker.interfaces.mcp.serialization import pretty_json
from codex_usage_tracker.recommendation_engine import api as recommendation_api
from codex_usage_tracker.reports.api import build_expensive_calls_report, build_summary_report
from codex_usage_tracker.server.usage_refresh import RefreshJobRegistry
from codex_usage_tracker.store import api as store_api

_REFRESH_JOB_REGISTRY, _REFRESH_JOB_LOCK = RefreshJobRegistry(), threading.Lock()
_DOGFOOD_JOB_LOCK = _mcp_dogfood.DOGFOOD_JOB_LOCK
_DOGFOOD_JOBS = _mcp_dogfood.DOGFOOD_JOBS
_dogfood_cache_key = _mcp_dogfood.cache_key
_dogfood_job_status_payload = _mcp_dogfood.job_status_payload
_load_cached_dogfood_result = _mcp_dogfood.load_cached_result
_prune_dogfood_jobs = _mcp_dogfood.prune_jobs
_register_dogfood_job = _mcp_dogfood.register_job
_run_dogfood_job = _mcp_dogfood.run_job
_utc_now = _mcp_dogfood.utc_now
usage_allowance_diagnostics = _mcp_allowance.usage_allowance_diagnostics
usage_allowance_export = _mcp_allowance.usage_allowance_export
usage_allowance_history = _mcp_allowance.usage_allowance_history
usage_allowance_status = _mcp_allowance.usage_allowance_status
usage_allowance_series = _mcp_allowance.usage_allowance_series
usage_allowance_evidence = _mcp_allowance.usage_allowance_evidence
usage_allowance_analysis = _mcp_allowance.usage_allowance_analysis
usage_allowance_analysis_status = _mcp_allowance.usage_allowance_analysis_status


def refresh_usage_index(
    include_archived: bool = False,
    aggregate_only: bool = False,
) -> dict[str, Any]:
    """Scan local Codex logs into SQLite usage and content indexes."""

    result = recommendation_api.refresh_usage_index(
        codex_home=DEFAULT_CODEX_HOME,
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        rate_card_path=DEFAULT_RATE_CARD_PATH,
        thresholds_path=DEFAULT_THRESHOLDS_PATH,
    )
    return refresh_result_payload(result, schema="codex-usage-tracker-refresh-v1")


def usage_refresh_start(
    include_archived: bool = False,
    aggregate_only: bool = False,
) -> dict[str, Any]:
    """Start an async local usage refresh job and return a pollable job_id."""

    return _REFRESH_JOB_REGISTRY.start_refresh(
        codex_home=DEFAULT_CODEX_HOME,
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
        refresh_lock=_REFRESH_JOB_LOCK,
    )


def usage_refresh_status(job_id: str) -> dict[str, Any]:
    """Poll an async local usage refresh job for phase progress and result."""

    return _REFRESH_JOB_REGISTRY.status(job_id)


def usage_doctor(response_format: str = "markdown") -> str | dict[str, Any]:
    """Check the local plugin, MCP, database, dashboard, and pricing setup."""

    report = run_doctor(db_path=DEFAULT_DB_PATH, pricing_path=DEFAULT_PRICING_PATH)
    if response_format == "json":
        return report
    return format_doctor(report)


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


def session_usage(
    session_id: str | None = None,
    limit: int = 200,
    response_format: str = "markdown",
    privacy_mode: str = "normal",
) -> str | dict[str, Any]:
    """Show aggregate per-call usage for one session, defaulting to the latest indexed session."""

    rows = apply_project_privacy_to_rows(
        store_api.query_session_usage(DEFAULT_DB_PATH, session_id=session_id, limit=limit),
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
    return pretty_json(payload)


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


def main() -> None:
    """Run the compatibility profile through the selected-profile server."""
    from codex_usage_tracker.interfaces.mcp.server import main as run_server

    run_server("full")


if __name__ == "__main__":
    main()
