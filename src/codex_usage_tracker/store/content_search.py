"""Search queries for the normalized local content index."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from codex_usage_tracker.store.content_query import (
    DEFAULT_SEARCH_SNIPPET_CHARS,
    _fts_match_query,
    _limit_clause,
    _limit_params,
    _normalize_search_limit,
    _normalize_search_offset,
    _search_terms,
    _snippet,
)
from codex_usage_tracker.store.query_sql import usage_where_clause


@dataclass(frozen=True)
class ContentSearchResult:
    """Content-index search result rows and paging metadata."""

    rows: list[dict[str, object]]
    total_matched_rows: int
    search_mode: str


def search_content_fragments(
    conn: sqlite3.Connection,
    *,
    query: str,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    limit: int | None = 20,
    offset: int = 0,
    max_snippet_chars: int | None = DEFAULT_SEARCH_SNIPPET_CHARS,
) -> ContentSearchResult:
    """Search the local content index and return bounded local snippets."""

    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query is required")
    normalized_limit = _normalize_search_limit(limit)
    normalized_offset = _normalize_search_offset(offset)
    try:
        return _search_content_fts(
            conn,
            query=normalized_query,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
            limit=normalized_limit,
            offset=normalized_offset,
            max_snippet_chars=max_snippet_chars,
        )
    except sqlite3.DatabaseError:
        return _search_content_like(
            conn,
            query=normalized_query,
            since=since,
            until=until,
            model=model,
            effort=effort,
            thread=thread,
            include_archived=include_archived,
            limit=normalized_limit,
            offset=normalized_offset,
            max_snippet_chars=max_snippet_chars,
        )


def _search_content_fts(
    conn: sqlite3.Connection,
    *,
    query: str,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    include_archived: bool,
    limit: int | None,
    offset: int,
    max_snippet_chars: int | None,
) -> ContentSearchResult:
    usage_clause, usage_params = _search_usage_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
    )
    match_query = _fts_match_query(query)
    from_sql = f"""
        FROM content_fts
        JOIN content_fragments AS cf ON cf.fragment_rowid = content_fts.rowid
        JOIN usage_events AS u ON u.record_id = cf.record_id
        WHERE content_fts MATCH ?
        {usage_clause}
    """
    params: list[object] = [match_query, *usage_params]
    total_matched = _search_count(conn, from_sql=from_sql, params=params)
    rows = conn.execute(
        f"""
        SELECT
            bm25(content_fts) AS search_rank,
            cf.fragment_id,
            cf.record_id,
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
            cf.token_link_record_id,
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
            u.is_archived
        {from_sql}
        ORDER BY search_rank ASC, u.event_timestamp DESC, cf.line_start ASC
        {_limit_clause(limit)}
        """,
        [*params, *_limit_params(limit, offset)],
    ).fetchall()
    return ContentSearchResult(
        rows=[
            _content_search_row(
                row,
                query=query,
                max_snippet_chars=max_snippet_chars,
            )
            for row in rows
        ],
        total_matched_rows=total_matched,
        search_mode="fts5",
    )


def _search_content_like(
    conn: sqlite3.Connection,
    *,
    query: str,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    include_archived: bool,
    limit: int | None,
    offset: int,
    max_snippet_chars: int | None,
) -> ContentSearchResult:
    usage_clause, usage_params = _search_usage_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        include_archived=include_archived,
    )
    terms = _search_terms(query) or [query]
    like_clauses = [
        "(lower(cf.fragment_text) LIKE ? OR lower(cf.safe_label) LIKE ?)" for _term in terms
    ]
    like_params: list[object] = []
    for term in terms:
        pattern = f"%{term.lower()}%"
        like_params.extend([pattern, pattern])
    from_sql = f"""
        FROM content_fragments AS cf
        JOIN usage_events AS u ON u.record_id = cf.record_id
        WHERE {" AND ".join(like_clauses)}
        {usage_clause}
    """
    params = [*like_params, *usage_params]
    total_matched = _search_count(conn, from_sql=from_sql, params=params)
    rows = conn.execute(
        f"""
        SELECT
            NULL AS search_rank,
            cf.fragment_id,
            cf.record_id,
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
            cf.token_link_record_id,
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
            u.is_archived
        {from_sql}
        ORDER BY u.event_timestamp DESC, cf.line_start ASC
        {_limit_clause(limit)}
        """,
        [*params, *_limit_params(limit, offset)],
    ).fetchall()
    return ContentSearchResult(
        rows=[
            _content_search_row(
                row,
                query=query,
                max_snippet_chars=max_snippet_chars,
            )
            for row in rows
        ],
        total_matched_rows=total_matched,
        search_mode="like",
    )


def _search_usage_clause(
    *,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    include_archived: bool,
) -> tuple[str, list[object]]:
    where_clause, params = usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        table_alias="u",
        include_archived=include_archived,
    )
    if not where_clause:
        return "", []
    return f"AND {where_clause.removeprefix('WHERE ')}", params


def _search_count(
    conn: sqlite3.Connection,
    *,
    from_sql: str,
    params: list[object],
) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS row_count {from_sql}", params).fetchone()
    return int(row["row_count"] if row is not None else 0)


def _content_search_row(
    row: sqlite3.Row,
    *,
    query: str,
    max_snippet_chars: int | None,
) -> dict[str, object]:
    fragment_text = str(row["fragment_text"] or "")
    snippet, truncated = _snippet(
        fragment_text,
        query=query,
        max_chars=max_snippet_chars,
    )
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
        "search_rank": row["search_rank"],
    }
