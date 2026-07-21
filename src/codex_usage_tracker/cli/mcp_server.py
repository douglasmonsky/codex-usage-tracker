from __future__ import annotations

import json
import os
import threading
import uuid
from typing import Any

from codex_usage_tracker.cli import mcp_allowance as _mcp_allowance
from codex_usage_tracker.cli import mcp_compression as mcp_compression
from codex_usage_tracker.cli import mcp_visualization as mcp_visualization
from codex_usage_tracker.cli.mcp_dashboard import (
    export_usage_csv as export_usage_csv,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    generate_usage_dashboard as generate_usage_dashboard,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    init_usage_allowance_config as init_usage_allowance_config,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    init_usage_pricing_config as init_usage_pricing_config,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    update_usage_pricing_config as update_usage_pricing_config,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_call_detail as usage_call_detail,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_calls as usage_calls,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_dashboard_recommendations as usage_dashboard_recommendations,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_dedupe_diagnostics as usage_dedupe_diagnostics,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_report_pack as usage_report_pack,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_status as usage_status,
)
from codex_usage_tracker.cli.mcp_dashboard import (
    usage_threads as usage_threads,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_command_loop_scan as usage_command_loop_scan,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_content_search as usage_content_search,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_file_churn_scan as usage_file_churn_scan,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_large_low_output_calls as usage_large_low_output_calls,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_pricing_coverage as usage_pricing_coverage,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_query as usage_query,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_recommendations as usage_recommendations,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_repeated_file_rediscovery as usage_repeated_file_rediscovery,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_repetition_scan as usage_repetition_scan,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_shell_churn as usage_shell_churn,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_source_coverage as usage_source_coverage,
)
from codex_usage_tracker.cli.mcp_discovery import (
    usage_thread_trace as usage_thread_trace,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    DOGFOOD_JOB_LOCK as _DOGFOOD_JOB_LOCK,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    DOGFOOD_JOBS as _DOGFOOD_JOBS,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    cache_key as _dogfood_cache_key,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    job_status_payload as _dogfood_job_status_payload,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    load_cached_result as _load_cached_dogfood_result,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    prune_jobs as _prune_dogfood_jobs,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    run_job as _run_dogfood_job,
)
from codex_usage_tracker.cli.mcp_dogfood import (
    utc_now as _utc_now,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_action_brief as usage_action_brief,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_context_bloat_scan as usage_context_bloat_scan,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_investigate as usage_investigate,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_investigation_walk as usage_investigation_walk,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_local_evidence_export as usage_local_evidence_export,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_suggest_investigations as usage_suggest_investigations,
)
from codex_usage_tracker.cli.mcp_investigations import (
    usage_test_hypotheses as usage_test_hypotheses,
)
from codex_usage_tracker.cli.mcp_runtime import mcp
from codex_usage_tracker.cli.mcp_subagents import subagent_usage as subagent_usage
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
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.core.projects import apply_project_privacy_to_rows
from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.recommendation_engine import api as recommendation_api
from codex_usage_tracker.reports.agentic_dogfood import (
    DEFAULT_AGENTIC_DOGFOOD_DIR,
)
from codex_usage_tracker.reports.api import (
    build_expensive_calls_report,
    build_summary_report,
)
from codex_usage_tracker.server.usage_refresh import RefreshJobRegistry
from codex_usage_tracker.store import api as store_api

_REFRESH_JOB_REGISTRY, _REFRESH_JOB_LOCK = RefreshJobRegistry(), threading.Lock()
usage_allowance_diagnostics = _mcp_allowance.usage_allowance_diagnostics
usage_allowance_export = _mcp_allowance.usage_allowance_export
usage_allowance_history = _mcp_allowance.usage_allowance_history
usage_allowance_status = _mcp_allowance.usage_allowance_status
usage_allowance_series = _mcp_allowance.usage_allowance_series
usage_allowance_evidence = _mcp_allowance.usage_allowance_evidence
usage_allowance_analysis = _mcp_allowance.usage_allowance_analysis
usage_allowance_analysis_status = _mcp_allowance.usage_allowance_analysis_status


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
def usage_refresh_status(job_id: str) -> dict[str, Any]:
    """Poll an async local usage refresh job for phase progress and result."""

    return _REFRESH_JOB_REGISTRY.status(job_id)


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
def usage_dogfood_start(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "strict",
    refresh: bool = True,
    run_hypotheses: bool = False,
    run_deep_investigations: bool = False,
    write_markdown: bool = True,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Start async aggregate dogfood diagnostics and return a polling job id."""
    job_id = uuid.uuid4().hex
    now = _utc_now()
    params = {
        "codex_home": DEFAULT_CODEX_HOME,
        "db_path": DEFAULT_DB_PATH,
        "pricing_path": DEFAULT_PRICING_PATH,
        "allowance_path": DEFAULT_ALLOWANCE_PATH,
        "rate_card_path": DEFAULT_RATE_CARD_PATH,
        "projects_path": DEFAULT_PROJECTS_PATH,
        "output_dir": DEFAULT_AGENTIC_DOGFOOD_DIR / "jobs" / job_id,
        "since": since,
        "until": until,
        "thread": thread,
        "include_archived": include_archived,
        "evidence_limit": max(1, evidence_limit),
        "privacy_mode": privacy_mode,
        "refresh": refresh,
        "run_hypotheses": run_hypotheses,
        "run_deep_investigations": run_deep_investigations,
        "write_markdown": write_markdown,
        "use_cache": use_cache,
        "cache_root": DEFAULT_AGENTIC_DOGFOOD_DIR / "cache",
    }
    cache_key = _dogfood_cache_key(params)
    cache_hit_payload: dict[str, Any] | None = None
    cache_source = "disabled"
    if use_cache and not refresh:
        cache_hit_payload, cache_source = _load_cached_dogfood_result(params, cache_key)
    with _DOGFOOD_JOB_LOCK:
        if cache_hit_payload is not None:
            _DOGFOOD_JOBS[job_id] = {
                "job_id": job_id,
                "job_type": "agentic_dogfood",
                "status": "completed",
                "percent_complete": 100,
                "current_stage": "result_cache",
                "stages": [
                    {
                        "stage": "result_cache",
                        "percent": 100,
                        "status": "completed",
                        "source": cache_source,
                    }
                ],
                "created_at": now,
                "updated_at": now,
                "started_at": now,
                "completed_at": now,
                "error": None,
                "filters": {
                    "since": since,
                    "until": until,
                    "thread": thread,
                    "include_archived": include_archived,
                    "evidence_limit": max(1, evidence_limit),
                    "privacy_mode": privacy_mode,
                    "refresh": refresh,
                    "run_hypotheses": run_hypotheses,
                    "run_deep_investigations": run_deep_investigations,
                    "use_cache": use_cache,
                },
                "cache": cache_hit_payload.get("cache", {}),
                "result_cache": {
                    "enabled": use_cache,
                    "cacheable": True,
                    "hit": True,
                    "source": cache_source,
                    "cache_key": cache_key,
                },
                "artifacts": cache_hit_payload.get("artifacts", {}),
                "result": cache_hit_payload,
            }
            _prune_dogfood_jobs()
        else:
            _DOGFOOD_JOBS[job_id] = {
                "job_id": job_id,
                "job_type": "agentic_dogfood",
                "status": "queued",
                "percent_complete": 0,
                "current_stage": "queued",
                "stages": [],
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
                "error": None,
                "filters": {
                    "since": since,
                    "until": until,
                    "thread": thread,
                    "include_archived": include_archived,
                    "evidence_limit": max(1, evidence_limit),
                    "privacy_mode": privacy_mode,
                    "refresh": refresh,
                    "run_hypotheses": run_hypotheses,
                    "run_deep_investigations": run_deep_investigations,
                    "use_cache": use_cache,
                },
                "cache": {},
                "result_cache": {
                    "enabled": use_cache,
                    "cacheable": True,
                    "hit": False,
                    "source": cache_source if use_cache and not refresh else None,
                    "cache_key": cache_key,
                    "miss_reason": cache_source
                    if use_cache and not refresh
                    else "refresh_requested"
                    if use_cache
                    else "disabled",
                },
                "artifacts": {},
                "result": None,
            }
        _prune_dogfood_jobs()
    if cache_hit_payload is not None:
        return _dogfood_job_status_payload(job_id)
    worker = threading.Thread(
        target=_run_dogfood_job,
        args=(job_id, params),
        name=f"codex-usage-dogfood-{job_id[:8]}",
        daemon=True,
    )
    worker.start()
    return _dogfood_job_status_payload(job_id)


@mcp.tool()
def usage_dogfood_status(job_id: str, include_result: bool = False) -> dict[str, Any]:
    """Poll async dogfood progress percent, stage, cache keys, and completion state."""
    return _dogfood_job_status_payload(job_id, include_result=include_result)


@mcp.tool()
def usage_dogfood_result(job_id: str) -> dict[str, Any]:
    """Return completed async dogfood payload or current status when still running."""
    status = _dogfood_job_status_payload(job_id, include_result=True)
    if status.get("status") != "completed":
        return status
    result = status.get("result")
    return result if isinstance(result, dict) else status


if __name__ == "__main__":
    mcp.run()
