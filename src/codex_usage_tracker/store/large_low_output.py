"""Large low-output call diagnostics over aggregate usage rows."""

from __future__ import annotations

import sqlite3
from typing import Any


def query_large_low_output_calls(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_total_tokens: int = 20_000,
    max_output_tokens: int = 1_000,
    limit: int | None = 20,
) -> dict[str, Any]:
    """Return large aggregate-token calls that produced little output."""

    normalized_min_total = max(0, min_total_tokens)
    normalized_max_output = max(0, max_output_tokens)
    normalized_limit = _normalize_limit(limit)
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        extra_clauses=[
            "u.total_tokens >= ?",
            "u.output_tokens <= ?",
        ],
        extra_params=[normalized_min_total, normalized_max_output],
    )

    rows = conn.execute(
        f"""
        WITH tool_counts AS (
            SELECT
                record_id,
                COUNT(*) AS tool_call_count,
                COALESCE(SUM(output_size_bytes), 0) AS tool_output_size_bytes
            FROM tool_calls
            GROUP BY record_id
        ),
        command_counts AS (
            SELECT
                record_id,
                COUNT(*) AS command_run_count,
                COALESCE(SUM(output_size_bytes), 0) AS command_output_size_bytes,
                SUM(CASE WHEN status != 'completed' THEN 1 ELSE 0 END) AS failed_command_count
            FROM command_runs
            GROUP BY record_id
        ),
        file_counts AS (
            SELECT
                record_id,
                COUNT(*) AS file_event_count,
                SUM(CASE WHEN operation = 'read' THEN 1 ELSE 0 END) AS file_read_count,
                SUM(CASE WHEN operation IN ('modify', 'edit', 'write') THEN 1 ELSE 0 END) AS file_write_count
            FROM file_events
            GROUP BY record_id
        )
        SELECT
            u.record_id,
            u.session_id,
            u.thread_key,
            u.thread_name,
            u.parent_thread_name,
            u.event_timestamp,
            u.model,
            u.effort,
            u.call_initiator,
            u.call_initiator_confidence,
            u.total_tokens,
            u.input_tokens,
            u.cached_input_tokens,
            u.uncached_input_tokens,
            u.output_tokens,
            u.reasoning_output_tokens,
            u.model_context_window,
            u.context_window_percent,
            COALESCE(tc.tool_call_count, 0) AS tool_call_count,
            COALESCE(tc.tool_output_size_bytes, 0) AS tool_output_size_bytes,
            COALESCE(cc.command_run_count, 0) AS command_run_count,
            COALESCE(cc.command_output_size_bytes, 0) AS command_output_size_bytes,
            COALESCE(cc.failed_command_count, 0) AS failed_command_count,
            COALESCE(fc.file_event_count, 0) AS file_event_count,
            COALESCE(fc.file_read_count, 0) AS file_read_count,
            COALESCE(fc.file_write_count, 0) AS file_write_count
        FROM usage_events u
        LEFT JOIN tool_counts tc ON tc.record_id = u.record_id
        LEFT JOIN command_counts cc ON cc.record_id = u.record_id
        LEFT JOIN file_counts fc ON fc.record_id = u.record_id
        {where_sql}
        ORDER BY u.total_tokens DESC, u.uncached_input_tokens DESC, u.event_timestamp DESC, u.record_id ASC
        """,
        params,
    ).fetchall()

    candidates = [_candidate(row) for row in rows]
    sliced = candidates if normalized_limit is None else candidates[:normalized_limit]
    return {
        "rows": sliced,
        "total_candidates": len(candidates),
    }


def _candidate(row: sqlite3.Row) -> dict[str, Any]:
    input_tokens = int(row["input_tokens"] or 0)
    cached_input_tokens = int(row["cached_input_tokens"] or 0)
    uncached_input_tokens = int(row["uncached_input_tokens"] or 0)
    output_tokens = int(row["output_tokens"] or 0)
    total_tokens = int(row["total_tokens"] or 0)
    context_window_percent = float(row["context_window_percent"] or 0.0)
    tool_output_size_bytes = int(row["tool_output_size_bytes"] or 0)
    command_output_size_bytes = int(row["command_output_size_bytes"] or 0)
    tool_call_count = int(row["tool_call_count"] or 0)
    command_run_count = int(row["command_run_count"] or 0)
    file_event_count = int(row["file_event_count"] or 0)
    explanation, reasons = _candidate_explanation(
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        uncached_input_tokens=uncached_input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        context_window_percent=context_window_percent,
        tool_output_size_bytes=tool_output_size_bytes,
        command_output_size_bytes=command_output_size_bytes,
        tool_call_count=tool_call_count,
        command_run_count=command_run_count,
        file_event_count=file_event_count,
    )
    return {
        "record_id": row["record_id"],
        "session_id": row["session_id"],
        "thread_key": row["thread_key"],
        "thread_name": row["thread_name"],
        "parent_thread_name": row["parent_thread_name"],
        "event_timestamp": row["event_timestamp"],
        "model": row["model"],
        "effort": row["effort"],
        "call_initiator": row["call_initiator"],
        "call_initiator_confidence": row["call_initiator_confidence"],
        "total_tokens": total_tokens,
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": int(row["reasoning_output_tokens"] or 0),
        "cache_ratio": _ratio(cached_input_tokens, input_tokens),
        "uncached_input_ratio": _ratio(uncached_input_tokens, input_tokens),
        "model_context_window": row["model_context_window"],
        "context_window_percent": context_window_percent,
        "tool_call_count": tool_call_count,
        "command_run_count": command_run_count,
        "file_event_count": file_event_count,
        "nearby_activity": {
            "tool_call_count": tool_call_count,
            "command_run_count": command_run_count,
            "failed_command_count": int(row["failed_command_count"] or 0),
            "file_event_count": file_event_count,
            "file_read_count": int(row["file_read_count"] or 0),
            "file_write_count": int(row["file_write_count"] or 0),
            "tool_output_size_bytes": tool_output_size_bytes,
            "command_output_size_bytes": command_output_size_bytes,
        },
        "candidate_explanation": explanation,
        "explanation_reasons": reasons,
        "next_tool": "usage_thread_trace",
    }


def _candidate_explanation(
    *,
    input_tokens: int,
    cached_input_tokens: int,
    uncached_input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    context_window_percent: float,
    tool_output_size_bytes: int,
    command_output_size_bytes: int,
    tool_call_count: int,
    command_run_count: int,
    file_event_count: int,
) -> tuple[str, list[str]]:
    cache_ratio = _ratio(cached_input_tokens, input_tokens)
    uncached_ratio = _ratio(uncached_input_tokens, input_tokens)
    activity_count = tool_call_count + command_run_count + file_event_count
    output_bytes = tool_output_size_bytes + command_output_size_bytes
    reasons: list[str] = []

    if input_tokens and uncached_input_tokens >= 10_000 and uncached_ratio >= 0.65 and cache_ratio <= 0.35:
        reasons.append("large_uncached_input")
    if context_window_percent >= 0.60:
        reasons.append("high_context_window_share")
    if output_bytes >= 50_000 or activity_count >= 8:
        reasons.append("tool_or_file_activity_pressure")
    if total_tokens and output_tokens <= max(250, int(total_tokens * 0.02)):
        reasons.append("very_low_output_share")

    if "large_uncached_input" in reasons:
        return "cold_resume_or_cache_miss", reasons
    if "tool_or_file_activity_pressure" in reasons:
        return "tool_output_pressure", reasons
    if "high_context_window_share" in reasons:
        return "stale_thread_low_value_continuation", reasons
    return "large_context_low_output", reasons


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


def _usage_filters(
    alias: str,
    *,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    extra_clauses: list[str] | None = None,
    extra_params: list[object] | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if not include_archived:
        clauses.append(f"{alias}.is_archived = 0")
    if since:
        clauses.append(f"{alias}.event_timestamp >= ?")
        params.append(since)
    if until:
        clauses.append(f"{alias}.event_timestamp <= ?")
        params.append(until)
    if thread:
        clauses.append(f"({alias}.thread_name = ? OR {alias}.thread_key = ? OR {alias}.session_id = ?)")
        params.extend([thread, thread, thread])
    if extra_clauses:
        clauses.extend(extra_clauses)
    if extra_params:
        params.extend(extra_params)
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params
