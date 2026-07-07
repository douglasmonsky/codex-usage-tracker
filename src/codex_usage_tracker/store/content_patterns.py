"""Pattern scans over the normalized local content index."""

from __future__ import annotations

import sqlite3
from typing import Any

PATTERN_SCAN_TYPES = ("repetition", "command_loop", "file_churn", "context_bloat")


def query_local_pattern_scan(
    conn: sqlite3.Connection,
    *,
    scan_type: str = "all",
    since: str | None = None,
    until: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_occurrences: int = 2,
    limit: int | None = 20,
) -> dict[str, Any]:
    """Return normalized local index pattern rows."""

    scan_types = _scan_types(scan_type)
    normalized_limit = _normalize_limit(limit)
    normalized_min = max(1, min_occurrences)
    rows: list[dict[str, Any]] = []
    for name in scan_types:
        if name == "repetition":
            rows.extend(
                _content_repetition_rows(
                    conn,
                    since=since,
                    until=until,
                    thread=thread,
                    include_archived=include_archived,
                    min_occurrences=normalized_min,
                    limit=normalized_limit,
                )
            )
        elif name == "command_loop":
            rows.extend(
                _command_loop_rows(
                    conn,
                    since=since,
                    until=until,
                    thread=thread,
                    include_archived=include_archived,
                    min_occurrences=normalized_min,
                    limit=normalized_limit,
                )
            )
        elif name == "file_churn":
            rows.extend(
                _file_churn_rows(
                    conn,
                    since=since,
                    until=until,
                    thread=thread,
                    include_archived=include_archived,
                    min_occurrences=normalized_min,
                    limit=normalized_limit,
                )
            )
        elif name == "context_bloat":
            rows.extend(
                _context_bloat_rows(
                    conn,
                    since=since,
                    until=until,
                    thread=thread,
                    include_archived=include_archived,
                    min_occurrences=normalized_min,
                    limit=normalized_limit,
                )
            )
    rows.sort(key=_pattern_sort_key)
    if normalized_limit is not None:
        rows = rows[:normalized_limit]
    return {
        "scan_types": scan_types,
        "patterns": rows,
        "total_patterns": len(rows),
    }


def _content_repetition_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    min_occurrences: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    rows = conn.execute(
        f"""
        SELECT
            cf.content_hash AS pattern_key,
            cf.fragment_kind AS fragment_kind,
            cf.role AS role,
            MIN(cf.safe_label) AS safe_label,
            COUNT(*) AS occurrences,
            COUNT(DISTINCT cf.record_id) AS call_count,
            COUNT(DISTINCT u.thread_key) AS thread_count,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            MIN(u.event_timestamp) AS first_seen_at,
            MAX(u.event_timestamp) AS last_seen_at
        FROM content_fragments cf
        JOIN usage_events u ON u.record_id = cf.record_id
        {where_sql}
        GROUP BY cf.content_hash, cf.fragment_kind, cf.role
        HAVING COUNT(*) >= ?
        ORDER BY occurrences DESC, total_tokens DESC, last_seen_at DESC
        {_limit_clause(limit)}
        """,
        [*params, min_occurrences, *_limit_params(limit)],
    ).fetchall()
    return [
        {
            "scan_type": "repetition",
            "pattern_key": row["pattern_key"],
            "evidence_kind": "content_fragment_hash",
            "summary": f"Repeated {row['fragment_kind']} fragment hash",
            "occurrences": int(row["occurrences"]),
            "call_count": int(row["call_count"]),
            "thread_count": int(row["thread_count"]),
            "total_tokens": int(row["total_tokens"] or 0),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "details": {
                "fragment_kind": row["fragment_kind"],
                "role": row["role"],
                "safe_label": row["safe_label"],
            },
        }
        for row in rows
    ]


def _command_loop_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    min_occurrences: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    rows = conn.execute(
        f"""
        SELECT
            cr.command_root AS command_root,
            cr.command_label AS command_label,
            cr.status AS status,
            cr.exit_code AS exit_code,
            COUNT(*) AS occurrences,
            COUNT(DISTINCT cr.record_id) AS call_count,
            COUNT(DISTINCT u.thread_key) AS thread_count,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            COALESCE(SUM(cr.output_size_bytes), 0) AS output_size_bytes,
            MIN(u.event_timestamp) AS first_seen_at,
            MAX(u.event_timestamp) AS last_seen_at
        FROM command_runs cr
        JOIN usage_events u ON u.record_id = cr.record_id
        {where_sql}
        GROUP BY cr.command_root, cr.command_label, cr.status, cr.exit_code
        HAVING COUNT(*) >= ? OR COALESCE(cr.exit_code, 0) != 0
        ORDER BY
            CASE WHEN COALESCE(cr.exit_code, 0) != 0 THEN 1 ELSE 0 END DESC,
            occurrences DESC,
            total_tokens DESC
        {_limit_clause(limit)}
        """,
        [*params, min_occurrences, *_limit_params(limit)],
    ).fetchall()
    return [
        {
            "scan_type": "command_loop",
            "pattern_key": _command_pattern_key(row),
            "evidence_kind": "command_run",
            "summary": f"Repeated command pattern: {row['command_label']}",
            "occurrences": int(row["occurrences"]),
            "call_count": int(row["call_count"]),
            "thread_count": int(row["thread_count"]),
            "total_tokens": int(row["total_tokens"] or 0),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "details": {
                "command_root": row["command_root"],
                "command_label": row["command_label"],
                "status": row["status"],
                "exit_code": row["exit_code"],
                "output_size_bytes": int(row["output_size_bytes"] or 0),
            },
        }
        for row in rows
    ]


def _file_churn_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    min_occurrences: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    rows = conn.execute(
        f"""
        SELECT
            fe.operation AS operation,
            fe.path_hash AS path_hash,
            fe.path_basename AS path_basename,
            fe.path_extension AS path_extension,
            COUNT(*) AS occurrences,
            COUNT(DISTINCT fe.record_id) AS call_count,
            COUNT(DISTINCT u.thread_key) AS thread_count,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            MIN(u.event_timestamp) AS first_seen_at,
            MAX(u.event_timestamp) AS last_seen_at
        FROM file_events fe
        JOIN usage_events u ON u.record_id = fe.record_id
        {where_sql}
        GROUP BY fe.operation, fe.path_hash, fe.path_basename, fe.path_extension
        HAVING COUNT(*) >= ?
        ORDER BY occurrences DESC, total_tokens DESC, last_seen_at DESC
        {_limit_clause(limit)}
        """,
        [*params, min_occurrences, *_limit_params(limit)],
    ).fetchall()
    return [
        {
            "scan_type": "file_churn",
            "pattern_key": f"{row['operation']}:{row['path_hash']}",
            "evidence_kind": "file_event",
            "summary": f"Repeated {row['operation']} events for {row['path_basename']}",
            "occurrences": int(row["occurrences"]),
            "call_count": int(row["call_count"]),
            "thread_count": int(row["thread_count"]),
            "total_tokens": int(row["total_tokens"] or 0),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "details": {
                "operation": row["operation"],
                "path_hash": row["path_hash"],
                "path_basename": row["path_basename"],
                "path_extension": row["path_extension"],
            },
        }
        for row in rows
    ]


def _context_bloat_rows(
    conn: sqlite3.Connection,
    *,
    since: str | None,
    until: str | None,
    thread: str | None,
    include_archived: bool,
    min_occurrences: int,
    limit: int | None,
) -> list[dict[str, Any]]:
    where_sql, params = _usage_filters(
        "u",
        since=since,
        until=until,
        thread=thread,
        include_archived=include_archived,
    )
    rows = conn.execute(
        f"""
        SELECT
            u.thread_key AS thread_key,
            COALESCE(NULLIF(u.thread_name, ''), u.session_id) AS thread_name,
            COUNT(DISTINCT u.record_id) AS call_count,
            COALESCE(SUM(u.total_tokens), 0) AS total_tokens,
            COALESCE(AVG(u.total_tokens), 0) AS avg_tokens,
            COALESCE(MAX(u.total_tokens), 0) AS max_tokens,
            COUNT(DISTINCT cf.fragment_id) AS fragment_count,
            COUNT(DISTINCT tc.tool_call_key) AS tool_call_count,
            COUNT(DISTINCT cr.command_run_key) AS command_run_count,
            COUNT(DISTINCT fe.file_event_key) AS file_event_count,
            MIN(u.event_timestamp) AS first_seen_at,
            MAX(u.event_timestamp) AS last_seen_at
        FROM usage_events u
        LEFT JOIN content_fragments cf ON cf.record_id = u.record_id
        LEFT JOIN tool_calls tc ON tc.record_id = u.record_id
        LEFT JOIN command_runs cr ON cr.record_id = u.record_id
        LEFT JOIN file_events fe ON fe.record_id = u.record_id
        {where_sql}
        GROUP BY u.thread_key, thread_name
        HAVING COUNT(DISTINCT u.record_id) >= ?
        ORDER BY total_tokens DESC, max_tokens DESC, call_count DESC
        {_limit_clause(limit)}
        """,
        [*params, min_occurrences, *_limit_params(limit)],
    ).fetchall()
    return [
        {
            "scan_type": "context_bloat",
            "pattern_key": row["thread_key"],
            "evidence_kind": "thread_usage_shape",
            "summary": f"High aggregate usage thread: {row['thread_name']}",
            "occurrences": int(row["call_count"]),
            "call_count": int(row["call_count"]),
            "thread_count": 1,
            "total_tokens": int(row["total_tokens"] or 0),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "details": {
                "thread_key": row["thread_key"],
                "thread_name": row["thread_name"],
                "avg_tokens": float(row["avg_tokens"] or 0),
                "max_tokens": int(row["max_tokens"] or 0),
                "fragment_count": int(row["fragment_count"] or 0),
                "tool_call_count": int(row["tool_call_count"] or 0),
                "command_run_count": int(row["command_run_count"] or 0),
                "file_event_count": int(row["file_event_count"] or 0),
            },
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
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _scan_types(scan_type: str) -> tuple[str, ...]:
    normalized = scan_type.strip().lower().replace("-", "_") if scan_type else "all"
    if normalized == "all":
        return PATTERN_SCAN_TYPES
    if normalized not in PATTERN_SCAN_TYPES:
        allowed = ", ".join(("all", *PATTERN_SCAN_TYPES))
        raise ValueError(f"unknown pattern scan type {scan_type!r}; expected one of {allowed}")
    return (normalized,)


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


def _limit_clause(limit: int | None) -> str:
    return "" if _normalize_limit(limit) is None else "LIMIT ?"


def _limit_params(limit: int | None) -> list[int]:
    normalized = _normalize_limit(limit)
    return [] if normalized is None else [normalized]


def _command_pattern_key(row: sqlite3.Row) -> str:
    status = row["status"] or "unknown"
    exit_code = "none" if row["exit_code"] is None else str(row["exit_code"])
    return f"{row['command_root']}:{row['command_label']}:{status}:{exit_code}"


def _pattern_sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
    return (-int(row["total_tokens"]), -int(row["occurrences"]), str(row["scan_type"]))
