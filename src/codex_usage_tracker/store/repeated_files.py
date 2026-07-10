"""Repeated safe file-identity diagnostics over the local content index."""

from __future__ import annotations

import sqlite3
from typing import Any

from codex_usage_tracker.store.row_values import row_int


def query_repeated_file_rediscovery(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
    sample_limit: int = 3,
) -> dict[str, Any]:
    """Return repeated safe file identities without exposing full paths."""

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
                fe.file_event_key,
                fe.record_id,
                fe.operation,
                fe.path_hash,
                fe.path_basename,
                fe.path_extension,
                fe.path_identity,
                u.thread_key,
                u.thread_name,
                u.session_id,
                u.event_timestamp,
                u.total_tokens
            FROM file_events fe
            JOIN usage_events u ON u.record_id = fe.record_id
            {where_sql}
        ),
        sequenced AS (
            SELECT
                filtered.*,
                LAG(path_hash) OVER (
                    PARTITION BY COALESCE(thread_key, session_id)
                    ORDER BY event_timestamp, record_id, file_event_key
                ) AS previous_path_hash
            FROM filtered
        )
        SELECT
            path_hash,
            MIN(path_identity) AS path_identity,
            MIN(path_basename) AS path_basename,
            MIN(path_extension) AS path_extension,
            COUNT(*) AS occurrences,
            SUM(CASE WHEN operation = 'read' THEN 1 ELSE 0 END) AS read_count,
            SUM(CASE WHEN operation IN ('modify', 'edit', 'write') THEN 1 ELSE 0 END)
                AS write_count,
            SUM(CASE WHEN operation NOT IN ('read', 'modify', 'edit', 'write') THEN 1 ELSE 0 END)
                AS other_operation_count,
            COUNT(DISTINCT record_id) AS call_count,
            COUNT(DISTINCT thread_key) AS thread_count,
            COUNT(DISTINCT session_id) AS session_count,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            SUM(CASE WHEN previous_path_hash = path_hash THEN 1 ELSE 0 END)
                AS adjacent_retouch_count,
            MIN(event_timestamp) AS first_seen_at,
            MAX(event_timestamp) AS last_seen_at
        FROM sequenced
        GROUP BY path_hash
        HAVING COUNT(*) >= ?
        ORDER BY
            read_count DESC,
            adjacent_retouch_count DESC,
            occurrences DESC,
            total_tokens DESC,
            last_seen_at DESC
        """,
        [*params, normalized_min],
    ).fetchall()

    sorted_rows = sorted(rows, key=_candidate_row_sort_key, reverse=True)
    sliced_rows = sorted_rows if normalized_limit is None else sorted_rows[:normalized_limit]
    candidates = [
        _file_candidate(
            row,
            trace_handles=_trace_handles_for_path(
                conn,
                path_hash=str(row["path_hash"]),
                since=since,
                until=until,
                thread=thread,
                include_archived=include_archived,
                limit=normalized_sample_limit,
            ),
        )
        for row in sliced_rows
    ]
    return {
        "rows": candidates,
        "total_candidates": len(sorted_rows),
    }


def _file_candidate(
    row: sqlite3.Row,
    *,
    trace_handles: list[dict[str, Any]],
) -> dict[str, Any]:
    read_count = row_int(row, "read_count")
    write_count = row_int(row, "write_count")
    other_count = row_int(row, "other_operation_count")
    occurrences = row_int(row, "occurrences")
    call_count = row_int(row, "call_count")
    adjacent_count = row_int(row, "adjacent_retouch_count")
    total_tokens = row_int(row, "total_tokens")
    candidate_kind = _file_candidate_kind(read_count, write_count, other_count)
    return {
        "path_hash": row["path_hash"],
        "path_identity": row["path_identity"],
        "path_basename": row["path_basename"],
        "path_extension": row["path_extension"],
        "candidate_kind": candidate_kind,
        "occurrences": occurrences,
        "call_count": call_count,
        "thread_count": row_int(row, "thread_count"),
        "session_count": row_int(row, "session_count"),
        "total_tokens": total_tokens,
        "avg_tokens_per_call": _average_tokens(total_tokens, call_count),
        "adjacent_retouch_count": adjacent_count,
        "operation_mix": {
            "read": read_count,
            "write": write_count,
            "other": other_count,
        },
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "recommendation": _recommendation(
            candidate_kind,
            adjacent_count,
            path_basename=str(row["path_basename"] or "file"),
            path_extension=str(row["path_extension"] or ""),
            read_count=read_count,
            write_count=write_count,
            other_count=other_count,
        ),
        "trace_handles": trace_handles,
    }


def _file_candidate_kind(read_count: int, write_count: int, other_count: int) -> str:
    if read_count >= max(write_count + other_count, 1):
        return "repeated_read_rediscovery"
    return "edit_or_write_churn"


def _average_tokens(total_tokens: int, call_count: int) -> float:
    if not call_count:
        return 0.0
    return round(total_tokens / call_count, 2)


def _trace_handles_for_path(
    conn: sqlite3.Connection,
    *,
    path_hash: str,
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
        extra_clauses=["fe.path_hash = ?"],
        extra_params=[path_hash],
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
        FROM file_events fe
        JOIN usage_events u ON u.record_id = fe.record_id
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


def _candidate_row_sort_key(row: sqlite3.Row) -> tuple[int, int, int, int]:
    return (
        int(row["read_count"] or 0),
        int(row["adjacent_retouch_count"] or 0),
        int(row["occurrences"] or 0),
        int(row["total_tokens"] or 0),
    )


def _recommendation(
    candidate_kind: str,
    adjacent_retouch_count: int,
    *,
    path_basename: str,
    path_extension: str,
    read_count: int,
    write_count: int,
    other_count: int,
) -> str:
    file_label = path_basename or f"{path_extension or 'file'} file"
    operation_mix = f"{read_count} reads, {write_count} writes, {other_count} other events"
    if candidate_kind == "repeated_read_rediscovery":
        if adjacent_retouch_count:
            return (
                f"Cache or summarize {file_label} once before continuing; "
                f"{adjacent_retouch_count} adjacent retouches and {operation_mix} suggest rediscovery."
            )
        return f"Use thread handoff notes for {file_label}; operation mix is {operation_mix}."
    return (
        f"Batch edits for {file_label} or inspect thread trace; operation mix is {operation_mix}."
    )


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit
