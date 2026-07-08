"""MCP server exposing Codex usage, diagnostics, and local investigation tools."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
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
from codex_usage_tracker.reports.agentic_dogfood import (
    DEFAULT_AGENTIC_DOGFOOD_DIR,
    build_agentic_dogfood_report,
)
from codex_usage_tracker.reports.api import (
    build_action_brief_report,
    build_agentic_investigation_report,
    build_content_search_report,
    build_expensive_calls_report,
    build_hypothesis_test_report,
    build_investigation_suggestions_report,
    build_investigation_walk_report,
    build_large_low_output_report,
    build_local_evidence_export_report,
    build_pattern_scan_report,
    build_pricing_coverage_report,
    build_query_report,
    build_recommendations_report,
    build_repeated_file_rediscovery_report,
    build_shell_churn_report,
    build_source_coverage_report,
    build_summary_report,
    build_thread_trace_report,
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

_DOGFOOD_JOBS: dict[str, dict[str, Any]] = {}
_DOGFOOD_JOB_LOCK = threading.Lock()
_DOGFOOD_MAX_JOBS = 25


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_jsonable(value: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value))


def _prune_dogfood_jobs() -> None:
    if len(_DOGFOOD_JOBS) <= _DOGFOOD_MAX_JOBS:
        return
    removable = sorted(
        (
            job
            for job in _DOGFOOD_JOBS.values()
            if job.get("status") not in {"queued", "running"}
        ),
        key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""),
    )
    for job in removable[: max(0, len(_DOGFOOD_JOBS) - _DOGFOOD_MAX_JOBS)]:
        _DOGFOOD_JOBS.pop(str(job["job_id"]), None)


def _dogfood_job_status_payload(
    job_id: str,
    *,
    include_result: bool = False,
) -> dict[str, Any]:
    with _DOGFOOD_JOB_LOCK:
        job = _DOGFOOD_JOBS.get(job_id)
        if job is None:
            return {
                "schema": "codex-usage-tracker-async-job-status-v1",
                "job_id": job_id,
                "job_type": "agentic_dogfood",
                "status": "not_found",
                "percent_complete": 0,
                "error": "Unknown dogfood job_id. Jobs are in-process and cleared when the MCP server restarts.",
            }
        payload = {
            "schema": "codex-usage-tracker-async-job-status-v1",
            "job_id": job["job_id"],
            "job_type": job["job_type"],
            "status": job["status"],
            "percent_complete": job["percent_complete"],
            "current_stage": job.get("current_stage"),
            "stages": list(job.get("stages", [])),
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "started_at": job.get("started_at"),
            "completed_at": job.get("completed_at"),
            "error": job.get("error"),
            "filters": dict(job.get("filters", {})),
            "cache": dict(job.get("cache", {})),
            "artifacts": dict(job.get("artifacts", {})),
            "result_available": bool(job.get("result")),
            "polling_note": (
                "Poll usage_dogfood_status until status is completed or failed, then call usage_dogfood_result."
            ),
        }
        if include_result and job.get("result") is not None:
            payload["result"] = job["result"]
        return _copy_jsonable(payload)


def _update_dogfood_job(job_id: str, **updates: Any) -> None:
    with _DOGFOOD_JOB_LOCK:
        job = _DOGFOOD_JOBS[job_id]
        job.update(updates)
        job["updated_at"] = _utc_now()


def _append_dogfood_stage(job_id: str, stage: dict[str, Any]) -> None:
    with _DOGFOOD_JOB_LOCK:
        job = _DOGFOOD_JOBS[job_id]
        stages = list(job.get("stages", []))
        stages.append(stage)
        job["stages"] = stages
        job["current_stage"] = stage.get("stage")
        job["percent_complete"] = int(stage.get("percent") or job.get("percent_complete") or 0)
        if stage.get("cache_keys") is not None:
            job["cache"] = {
                "scope": "single_run_shared_reports",
                "cache_keys": list(stage["cache_keys"]),
            }
        job["updated_at"] = _utc_now()


def _run_dogfood_job(job_id: str, params: dict[str, Any]) -> None:
    _update_dogfood_job(
        job_id,
        status="running",
        percent_complete=1,
        current_stage="start",
        started_at=_utc_now(),
    )
    try:
        payload = build_agentic_dogfood_report(
            codex_home=params["codex_home"],
            db_path=params["db_path"],
            pricing_path=params["pricing_path"],
            allowance_path=params["allowance_path"],
            rate_card_path=params["rate_card_path"],
            projects_path=params["projects_path"],
            output_dir=params["output_dir"],
            since=params["since"],
            until=params["until"],
            thread=params["thread"],
            include_archived=params["include_archived"],
            evidence_limit=params["evidence_limit"],
            privacy_mode=params["privacy_mode"],
            refresh=params["refresh"],
            run_hypotheses=params["run_hypotheses"],
            run_deep_investigations=params["run_deep_investigations"],
            write_markdown=params["write_markdown"],
            progress_callback=lambda stage: _append_dogfood_stage(job_id, stage),
        )
    except Exception as exc:  # pragma: no cover - exercised through integration failure paths.
        _update_dogfood_job(
            job_id,
            status="failed",
            current_stage="failed",
            error=f"{type(exc).__name__}: {exc}",
            completed_at=_utc_now(),
        )
        return
    _update_dogfood_job(
        job_id,
        status="completed",
        percent_complete=100,
        current_stage="write_artifacts",
        completed_at=_utc_now(),
        result=payload,
        cache=payload.get("cache", {}),
        artifacts=payload.get("artifacts", {}),
    )


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
    include_archived: bool = False,
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
        include_archived=include_archived,
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
def usage_content_search(
    query: str,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 20,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Search explicit local content index snippets with aggregate call metadata."""

    return build_content_search_report(
        db_path=DEFAULT_DB_PATH,
        query=query,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        max_snippet_chars=max_snippet_chars,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_thread_trace(
    thread: str | None = None,
    thread_key: str | None = None,
    session_id: str | None = None,
    record_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
    offset: int = 0,
    max_snippet_chars: int | None = 800,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Return a local content-index call timeline for one thread/session."""

    return build_thread_trace_report(
        db_path=DEFAULT_DB_PATH,
        thread=thread,
        thread_key=thread_key,
        session_id=session_id,
        record_id=record_id,
        since=since,
        until=until,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
        max_snippet_chars=max_snippet_chars,
        privacy_mode=privacy_mode,
    ).payload


def _pattern_scan_payload(
    *,
    scan_type: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    min_occurrences: int,
    limit: int | None,
    privacy_mode: str,
) -> dict[str, Any]:
    return build_pattern_scan_report(
        db_path=DEFAULT_DB_PATH,
        scan_type=scan_type,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_repetition_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find repeated local content fragment hashes."""

    return _pattern_scan_payload(
        scan_type="repetition",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_command_loop_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find repeated command roots/labels and failing command loops."""

    return _pattern_scan_payload(
        scan_type="command_loop",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_file_churn_scan(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find repeated normalized file read/modify events."""

    return _pattern_scan_payload(
        scan_type="file_churn",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        privacy_mode=privacy_mode,
    )


@mcp.tool()
def usage_repeated_file_rediscovery(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Rank repeated safe file identities likely rediscovered across calls."""

    return build_repeated_file_rediscovery_report(
        db_path=DEFAULT_DB_PATH,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_shell_churn(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 3,
    limit: int | None = 20,
    sample_limit: int = 3,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Rank repeated shell command families and adjacent command loops."""

    return build_shell_churn_report(
        db_path=DEFAULT_DB_PATH,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_occurrences=min_occurrences,
        limit=limit,
        sample_limit=sample_limit,
        privacy_mode=privacy_mode,
    ).payload


@mcp.tool()
def usage_large_low_output_calls(
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_total_tokens: int = 20_000,
    max_output_tokens: int = 1_000,
    limit: int | None = 20,
    privacy_mode: str = "normal",
) -> dict[str, Any]:
    """Find high-token calls with low output as token-waste candidates."""

    return build_large_low_output_report(
        db_path=DEFAULT_DB_PATH,
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        min_total_tokens=min_total_tokens,
        max_output_tokens=max_output_tokens,
        limit=limit,
        privacy_mode=privacy_mode,
    ).payload


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
    }
    with _DOGFOOD_JOB_LOCK:
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
            },
            "cache": {},
            "artifacts": {},
            "result": None,
        }
        _prune_dogfood_jobs()
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
