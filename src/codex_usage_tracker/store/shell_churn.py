"""Shell churn diagnostics over normalized command runs."""

from __future__ import annotations

import sqlite3
from typing import Any

SHELL_CHURN_ROOTS = {
    "sed",
    "rg",
    "grep",
    "git",
    "gh",
    "nl",
    "cat",
    "pytest",
    "npm",
    "pnpm",
    "yarn",
    "pip",
    "python",
    "python3",
    "node",
}


def query_shell_churn(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 3,
    limit: int | None = 20,
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Return repeated shell command families without raw command output."""

    normalized_min = max(1, min_occurrences)
    normalized_limit = _normalize_limit(limit)
    normalized_sample_limit = max(1, sample_limit)
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    rows = conn.execute(
        f"""
        WITH filtered AS (
            SELECT
                cr.command_run_key,
                cr.record_id,
                cr.command_root,
                cr.command_label,
                cr.status,
                cr.exit_code,
                cr.retry_group,
                cr.failure_category,
                cr.output_size_bytes,
                cr.line_start,
                u.thread_key,
                u.thread_name,
                u.session_id,
                u.event_timestamp,
                u.total_tokens
            FROM command_runs cr
            JOIN usage_events u ON u.record_id = cr.record_id
            {where_sql}
        ),
        sequenced AS (
            SELECT
                filtered.*,
                LAG(command_root) OVER (
                    PARTITION BY COALESCE(thread_key, session_id)
                    ORDER BY event_timestamp, line_start, record_id, command_run_key
                ) AS previous_command_root,
                LAG(command_label) OVER (
                    PARTITION BY COALESCE(thread_key, session_id)
                    ORDER BY event_timestamp, line_start, record_id, command_run_key
                ) AS previous_command_label
            FROM filtered
        )
        SELECT
            command_root,
            MIN(command_label) AS sample_command_label,
            COUNT(DISTINCT command_label) AS distinct_label_count,
            COUNT(*) AS occurrences,
            COUNT(DISTINCT record_id) AS call_count,
            COUNT(DISTINCT thread_key) AS thread_count,
            COUNT(DISTINCT session_id) AS session_count,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(output_size_bytes), 0) AS output_size_bytes,
            SUM(CASE WHEN COALESCE(exit_code, 0) = 0 THEN 1 ELSE 0 END) AS success_count,
            SUM(CASE WHEN COALESCE(exit_code, 0) != 0 THEN 1 ELSE 0 END) AS failure_count,
            SUM(CASE WHEN command_root = previous_command_root THEN 1 ELSE 0 END)
                AS adjacent_root_repeat_count,
            SUM(CASE WHEN command_label = previous_command_label THEN 1 ELSE 0 END)
                AS adjacent_label_repeat_count,
            COUNT(DISTINCT retry_group) AS retry_group_count,
            MIN(event_timestamp) AS first_seen_at,
            MAX(event_timestamp) AS last_seen_at
        FROM sequenced
        GROUP BY command_root
        HAVING COUNT(*) >= ?
        ORDER BY
            failure_count DESC,
            adjacent_root_repeat_count DESC,
            occurrences DESC,
            total_tokens DESC,
            last_seen_at DESC
        """,
        [*params, normalized_min],
    ).fetchall()
    candidates = [
        _shell_churn_candidate(
            row,
            top_labels=_top_labels_for_root(
                conn,
                command_root=str(row["command_root"]),
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_sample_limit,
            ),
            trace_handles=_trace_handles_for_root(
                conn,
                command_root=str(row["command_root"]),
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_sample_limit,
            ),
        )
        for row in rows
    ]
    candidates.sort(key=_candidate_sort_key, reverse=True)
    sliced = candidates if normalized_limit is None else candidates[:normalized_limit]
    return {
        "rows": sliced,
        "total_candidates": len(candidates),
    }


def _shell_churn_candidate(
    row: sqlite3.Row,
    *,
    top_labels: list[dict[str, Any]],
    trace_handles: list[dict[str, Any]],
) -> dict[str, Any]:
    command_root = str(row["command_root"] or "unknown")
    occurrences = int(row["occurrences"] or 0)
    failure_count = int(row["failure_count"] or 0)
    adjacent_root_count = int(row["adjacent_root_repeat_count"] or 0)
    adjacent_label_count = int(row["adjacent_label_repeat_count"] or 0)
    total_tokens = int(row["total_tokens"] or 0)
    output_size_bytes = int(row["output_size_bytes"] or 0)
    return {
        "command_root": command_root,
        "command_label": row["sample_command_label"],
        "command_family": _command_family(command_root),
        "churn_kind": _churn_kind(failure_count, adjacent_root_count),
        "occurrences": occurrences,
        "call_count": int(row["call_count"] or 0),
        "thread_count": int(row["thread_count"] or 0),
        "session_count": int(row["session_count"] or 0),
        "total_tokens": total_tokens,
        "output_size_bytes": output_size_bytes,
        "success_count": int(row["success_count"] or 0),
        "failure_count": failure_count,
        "distinct_label_count": int(row["distinct_label_count"] or 0),
        "adjacent_root_repeat_count": adjacent_root_count,
        "adjacent_label_repeat_count": adjacent_label_count,
        "retry_group_count": int(row["retry_group_count"] or 0),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "top_labels": top_labels,
        "recommendation": _recommendation(command_root, failure_count, adjacent_root_count),
        "trace_handles": trace_handles,
    }


def _top_labels_for_root(
    conn: sqlite3.Connection,
    *,
    command_root: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    limit: int,
) -> list[dict[str, Any]]:
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        extra_clauses=["cr.command_root = ?"],
        extra_params=[command_root],
    )
    rows = conn.execute(
        f"""
        SELECT
            cr.command_label,
            cr.status,
            cr.exit_code,
            cr.retry_group,
            COUNT(*) AS occurrences,
            COALESCE(SUM(cr.output_size_bytes), 0) AS output_size_bytes
        FROM command_runs cr
        JOIN usage_events u ON u.record_id = cr.record_id
        {where_sql}
        GROUP BY cr.command_label, cr.status, cr.exit_code, cr.retry_group
        ORDER BY occurrences DESC, output_size_bytes DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        {
            "command_label": row["command_label"],
            "status": row["status"],
            "exit_code": row["exit_code"],
            "retry_group": row["retry_group"],
            "occurrences": int(row["occurrences"] or 0),
            "output_size_bytes": int(row["output_size_bytes"] or 0),
        }
        for row in rows
    ]


def _trace_handles_for_root(
    conn: sqlite3.Connection,
    *,
    command_root: str,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    limit: int,
) -> list[dict[str, Any]]:
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
        extra_clauses=["cr.command_root = ?"],
        extra_params=[command_root],
    )
    rows = conn.execute(
        f"""
        SELECT
            u.thread_key,
            COALESCE(NULLIF(u.thread_name, ''), u.session_id) AS thread_name,
            u.session_id,
            COUNT(DISTINCT u.record_id) AS call_count,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            MIN(u.event_timestamp) AS first_seen_at,
            MAX(u.event_timestamp) AS last_seen_at
        FROM command_runs cr
        JOIN usage_events u ON u.record_id = cr.record_id
        {where_sql}
        GROUP BY u.thread_key, thread_name, u.session_id
        ORDER BY call_count DESC, total_tokens DESC, last_seen_at DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        {
            "thread_key": row["thread_key"],
            "thread": row["thread_name"],
            "session_id": row["session_id"],
            "call_count": int(row["call_count"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "next_tool": "usage_thread_trace",
        }
        for row in rows
    ]


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
        clauses.append(f"COALESCE({alias}.is_archived, 0) = 0")
    if since:
        clauses.append(f"{alias}.event_timestamp >= ?")
        params.append(since)
    if until:
        clauses.append(f"{alias}.event_timestamp <= ?")
        params.append(until)
    if thread:
        clauses.append(
            f"({alias}.thread_key = ? OR {alias}.thread_name = ? OR {alias}.session_id = ?)"
        )
        params.extend([thread, thread, thread])
    if extra_clauses:
        clauses.extend(extra_clauses)
    if extra_params:
        params.extend(extra_params)
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _candidate_sort_key(row: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(row["failure_count"]),
        int(row["adjacent_root_repeat_count"]),
        int(row["occurrences"]),
        int(row["total_tokens"]),
    )


def _command_family(command_root: str) -> str:
    if command_root in {"sed", "rg", "grep", "nl", "cat"}:
        return "file_discovery"
    if command_root in {"git", "gh"}:
        return "vcs"
    if command_root in {"pytest"}:
        return "test"
    if command_root in {"npm", "pnpm", "yarn", "pip"}:
        return "package"
    if command_root in {"python", "python3", "node"}:
        return "runtime"
    if command_root in SHELL_CHURN_ROOTS:
        return "known_shell"
    return "unknown"


def _churn_kind(failure_count: int, adjacent_root_repeat_count: int) -> str:
    if failure_count:
        return "failure_retry_churn"
    if adjacent_root_repeat_count:
        return "successful_loop_churn"
    return "repeated_command_family"


def _recommendation(
    command_root: str,
    failure_count: int,
    adjacent_root_repeat_count: int,
) -> str:
    if failure_count:
        return "Stop and summarize the failure mode before retrying commands."
    if command_root in {"sed", "rg", "grep", "nl", "cat"}:
        return "Cache query results or inspect a broader file slice once."
    if command_root in {"git", "gh"}:
        return "Summarize repository state once before continuing."
    if adjacent_root_repeat_count:
        return "Replace repeated shell probing with a small script or saved notes."
    return "Review whether repeated shell calls can be batched."


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit
