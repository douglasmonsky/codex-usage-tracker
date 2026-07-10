"""Thread trace queries for the normalized local content index."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from codex_usage_tracker.store.content_query import (
    DEFAULT_SEARCH_SNIPPET_CHARS,
    _limit_clause,
    _limit_params,
    _normalize_search_limit,
    _normalize_search_offset,
    _snippet,
)
from codex_usage_tracker.store.query_sql import usage_where_clause


@dataclass(frozen=True)
class ContentTraceResult:
    """Thread/session trace result rows and paging metadata."""

    calls: list[dict[str, object]]
    total_matched_calls: int


def trace_thread_content(
    conn: sqlite3.Connection,
    *,
    thread: str | None = None,
    thread_key: str | None = None,
    session_id: str | None = None,
    record_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_archived: bool = False,
    limit: int | None = 100,
    offset: int = 0,
    max_snippet_chars: int | None = DEFAULT_SEARCH_SNIPPET_CHARS,
) -> ContentTraceResult:
    """Return a paged aggregate call trace with attached content fragments."""

    where_clause, params = _trace_where_clause(
        thread=thread,
        thread_key=thread_key,
        session_id=session_id,
        record_id=record_id,
        since=since,
        until=until,
        include_archived=include_archived,
    )
    normalized_limit = _normalize_search_limit(limit)
    normalized_offset = _normalize_search_offset(offset)
    count_row = conn.execute(
        f"SELECT COUNT(*) AS call_count FROM usage_events AS u {where_clause}",  # nosec B608 - internal clause builder with bound values
        params,
    ).fetchone()
    total_matched = int(count_row["call_count"] if count_row is not None else 0)
    trace_query = f"""
        SELECT
            u.record_id,
            u.session_id,
            u.thread_name,
            u.parent_thread_name,
            u.thread_key,
            u.event_timestamp,
            u.model,
            u.effort,
            u.total_tokens,
            u.input_tokens,
            u.cached_input_tokens,
            u.uncached_input_tokens,
            u.output_tokens,
            u.reasoning_output_tokens,
            u.is_archived,
            cf.fragment_id,
            cf.turn_key,
            cf.fragment_kind,
            cf.role,
            cf.safe_label,
            cf.content_hash,
            cf.content_size_bytes,
            cf.fragment_text,
            cf.includes_raw_fragment,
            cf.source_file_id,
            cf.line_start,
            cf.line_end,
            cf.token_link_record_id
        FROM (
            SELECT *
            FROM usage_events AS u
            {where_clause}
            ORDER BY u.event_timestamp ASC, u.cumulative_total_tokens ASC
            {_limit_clause(normalized_limit)}
        ) AS u
        LEFT JOIN content_fragments AS cf ON cf.record_id = u.record_id
        ORDER BY u.event_timestamp ASC, u.cumulative_total_tokens ASC, cf.line_start ASC
        """  # nosec B608 - internal clause builder with bound values
    rows = conn.execute(
        trace_query,
        [*params, *_limit_params(normalized_limit, normalized_offset)],
    ).fetchall()
    return ContentTraceResult(
        calls=_trace_calls(rows, max_snippet_chars=max_snippet_chars),
        total_matched_calls=total_matched,
    )


def _trace_where_clause(
    *,
    thread: str | None,
    thread_key: str | None,
    session_id: str | None,
    record_id: str | None,
    since: str | None,
    until: str | None,
    include_archived: bool,
) -> tuple[str, list[object]]:
    usage_clause, params = usage_where_clause(
        since=since,
        until=until,
        table_alias="u",
        include_archived=include_archived,
    )
    clauses: list[str] = []
    if usage_clause:
        clauses.append(usage_clause.removeprefix("WHERE "))
    identity_clauses: list[str] = []
    identity_params: list[object] = []
    if thread:
        identity_clauses.append(
            "(u.thread_name = ? OR u.parent_thread_name = ? OR u.session_id = ?)"
        )
        identity_params.extend([thread, thread, thread])
    if thread_key:
        identity_clauses.append("u.thread_key = ?")
        identity_params.append(thread_key)
    if session_id:
        identity_clauses.append("u.session_id = ?")
        identity_params.append(session_id)
    if record_id:
        identity_clauses.append(
            """
            (
                u.record_id = ?
                OR u.session_id = (
                    SELECT session_id FROM usage_events WHERE record_id = ?
                )
                OR (
                    u.thread_key IS NOT NULL
                    AND u.thread_key = (
                        SELECT thread_key FROM usage_events WHERE record_id = ?
                    )
                )
            )
            """
        )
        identity_params.extend([record_id, record_id, record_id])
    if not identity_clauses:
        raise ValueError("thread, thread_key, session_id, or record_id is required")
    clauses.append("(" + " OR ".join(identity_clauses) + ")")
    return "WHERE " + " AND ".join(clauses), [*params, *identity_params]


def _trace_calls(
    rows: list[sqlite3.Row],
    *,
    max_snippet_chars: int | None,
) -> list[dict[str, object]]:
    calls_by_id: dict[str, dict[str, object]] = {}
    for row in rows:
        record_id = str(row["record_id"])
        call = calls_by_id.setdefault(record_id, _trace_call_row(row))
        if row["fragment_id"] is not None:
            fragments = call["fragments"]
            if not isinstance(fragments, list):
                raise TypeError("trace fragments must be a list")
            fragments.append(_trace_fragment_row(row, max_snippet_chars=max_snippet_chars))
    for call in calls_by_id.values():
        fragments = call["fragments"]
        if not isinstance(fragments, list):
            raise TypeError("trace fragments must be a list")
        call["fragment_count"] = len(fragments)
    return list(calls_by_id.values())


def _trace_call_row(row: sqlite3.Row) -> dict[str, object]:
    return {
        "record_id": row["record_id"],
        "session_id": row["session_id"],
        "thread_name": row["thread_name"],
        "parent_thread_name": row["parent_thread_name"],
        "thread_key": row["thread_key"],
        "event_timestamp": row["event_timestamp"],
        "model": row["model"],
        "effort": row["effort"],
        "total_tokens": int(row["total_tokens"] or 0),
        "input_tokens": int(row["input_tokens"] or 0),
        "cached_input_tokens": int(row["cached_input_tokens"] or 0),
        "uncached_input_tokens": int(row["uncached_input_tokens"] or 0),
        "output_tokens": int(row["output_tokens"] or 0),
        "reasoning_output_tokens": int(row["reasoning_output_tokens"] or 0),
        "is_archived": bool(row["is_archived"]),
        "fragment_count": 0,
        "fragments": [],
    }


def _trace_fragment_row(
    row: sqlite3.Row,
    *,
    max_snippet_chars: int | None,
) -> dict[str, object]:
    snippet, truncated = _snippet(
        str(row["fragment_text"] or ""),
        query="",
        max_chars=max_snippet_chars,
    )
    return {
        "fragment_id": row["fragment_id"],
        "turn_key": row["turn_key"],
        "fragment_kind": row["fragment_kind"],
        "role": row["role"],
        "safe_label": row["safe_label"],
        "content_hash": row["content_hash"],
        "content_size_bytes": int(row["content_size_bytes"] or 0),
        "snippet": snippet,
        "snippet_truncated": truncated,
        "includes_raw_fragment": bool(row["includes_raw_fragment"]),
        "source_file_id": row["source_file_id"],
        "line_start": row["line_start"],
        "line_end": row["line_end"],
        "token_link_record_id": row["token_link_record_id"],
    }
