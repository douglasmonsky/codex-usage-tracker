"""MCP server exposing Codex usage, diagnostics, and local investigation tools."""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from codex_usage_tracker.cli.mcp_allowance import (
    usage_allowance_diagnostics as usage_allowance_diagnostics,
)
from codex_usage_tracker.cli.mcp_allowance import (
    usage_allowance_export as usage_allowance_export,
)
from codex_usage_tracker.cli.mcp_allowance import (
    usage_allowance_history as usage_allowance_history,
)
from codex_usage_tracker.cli.mcp_discovery import (
    _pattern_scan_payload,
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
from codex_usage_tracker.cli.mcp_runtime import mcp
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
from codex_usage_tracker.reports.agentic_dogfood import (
    DEFAULT_AGENTIC_DOGFOOD_DIR,
)
from codex_usage_tracker.reports.api import (
    build_action_brief_report,
    build_agentic_investigation_report,
    build_expensive_calls_report,
    build_hypothesis_test_report,
    build_investigation_suggestions_report,
    build_investigation_walk_report,
    build_local_evidence_export_report,
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
from codex_usage_tracker.server.usage_refresh import RefreshJobRegistry
from codex_usage_tracker.store.api import (
    export_usage_csv as export_csv,
)
from codex_usage_tracker.store.api import (
    query_session_usage,
)
from codex_usage_tracker.store.api import (
    refresh_usage_index as refresh_index,
)

_REFRESH_JOB_REGISTRY = RefreshJobRegistry()
_REFRESH_JOB_LOCK = threading.Lock()


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
def refresh_usage_index(
    include_archived: bool = False,
    aggregate_only: bool = False,
) -> dict[str, Any]:
    """Scan local Codex logs into SQLite usage and content indexes."""

    result = refresh_index(
        codex_home=DEFAULT_CODEX_HOME,
        db_path=DEFAULT_DB_PATH,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
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
def usage_suggest_investigations(
    goal: str | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 10,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Suggest goal-led usage investigations and next MCP tools."""

    return build_investigation_suggestions_report(
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_investigate(
    goal: str = "token_waste",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    detail_mode: str = "compact",
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Run a goal-led aggregate usage investigation."""

    return build_agentic_investigation_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        detail_mode=detail_mode,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_action_brief(
    goal: str = "token_waste",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return compact aggregate remediation brief with concrete next actions."""

    return build_action_brief_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        goal=goal,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload


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


@mcp.tool()
def usage_test_hypotheses(
    question: str,
    hypotheses: list[str] | None = None,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Test usage hypotheses against aggregate/local-index diagnostics."""
    return build_hypothesis_test_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        question=question,
        hypotheses=hypotheses,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_context_bloat_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find high-token threads with local content/event density."""

    return _pattern_scan_payload(
        scan_type="context_bloat",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_investigation_walk(
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Run a bounded local hypothesis walk over normalized usage evidence."""

    return build_investigation_walk_report(
        db_path=DEFAULT_DB_PATH,
        question=question,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        evidence_limit=evidence_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_local_evidence_export(
    question: str,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    evidence_limit: int = 5,
) -> dict[str, Any]:
    """Return a strict shareable local evidence summary without raw content."""

    return build_local_evidence_export_report(
        db_path=DEFAULT_DB_PATH,
        question=question,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        evidence_limit=evidence_limit,
    ).payload


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
        live_call_rows=lambda *, query_params, pricing_status, credit_confidence: _live_call_rows(
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


if __name__ == "__main__":
    mcp.run()
