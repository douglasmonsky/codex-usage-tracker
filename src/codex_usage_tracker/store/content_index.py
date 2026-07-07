"""Normalized local content indexing for Codex JSONL source logs."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION, optional_str
from codex_usage_tracker.store.query_sql import usage_where_clause

MAX_FRAGMENT_CHARS = 4000
DEFAULT_SEARCH_SNIPPET_CHARS = 800
PARSER_ADAPTER_NAME = "codex-jsonl"
CONTENT_INDEX_TABLES = (
    "content_fragments",
    "file_events",
    "command_runs",
    "tool_calls",
    "conversation_turns",
)


@dataclass(frozen=True)
class ContentIndexResult:
    """Content indexing counts for one refresh operation."""

    source_files: int
    conversation_turns: int
    content_fragments: int
    parse_warnings: int = 0


@dataclass(frozen=True)
class _PendingFragment:
    role: str
    fragment_kind: str
    safe_label: str
    text: str
    line_start: int
    line_end: int
    turn_id: str | None
    turn_index: int
    event_timestamp: str | None


@dataclass(frozen=True)
class ContentSearchResult:
    """Content-index search result rows and paging metadata."""

    rows: list[dict[str, object]]
    total_matched_rows: int
    search_mode: str


@dataclass(frozen=True)
class ContentTraceResult:
    """Thread/session trace result rows and paging metadata."""

    calls: list[dict[str, object]]
    total_matched_calls: int


def index_content_for_source_files(
    conn: sqlite3.Connection,
    *,
    source_files: Iterable[Path],
) -> ContentIndexResult:
    """Populate normalized bounded local content rows for source files."""

    source_paths = list(dict.fromkeys(source_files))
    totals = ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    for source_path in source_paths:
        result = _index_content_for_source_file(conn, source_path=source_path)
        totals = ContentIndexResult(
            source_files=totals.source_files + result.source_files,
            conversation_turns=totals.conversation_turns + result.conversation_turns,
            content_fragments=totals.content_fragments + result.content_fragments,
            parse_warnings=totals.parse_warnings + result.parse_warnings,
        )
    return totals


def clear_content_index_rows(conn: sqlite3.Connection) -> None:
    """Clear normalized content index rows while tolerating unavailable FTS5."""

    _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(f"DELETE FROM {table_name}")


def delete_content_index_rows_for_source_files(
    conn: sqlite3.Connection,
    *,
    placeholders: str,
    source_files_to_replace: list[str],
) -> None:
    """Delete normalized content rows linked to source files."""

    record_subquery = (
        "SELECT record_id FROM usage_events " f"WHERE source_file IN ({placeholders})"
    )
    _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(
            f"DELETE FROM {table_name} WHERE record_id IN ({record_subquery})",
            source_files_to_replace,
        )
    _rebuild_content_fts(conn)


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
        f"SELECT COUNT(*) AS call_count FROM usage_events AS u {where_clause}",
        params,
    ).fetchone()
    total_matched = int(count_row["call_count"] if count_row is not None else 0)
    rows = conn.execute(
        f"""
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
        """,
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
            assert isinstance(fragments, list)
            fragments.append(
                _trace_fragment_row(row, max_snippet_chars=max_snippet_chars)
            )
    for call in calls_by_id.values():
        fragments = call["fragments"]
        assert isinstance(fragments, list)
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
        "(lower(cf.fragment_text) LIKE ? OR lower(cf.safe_label) LIKE ?)"
        for _term in terms
    ]
    like_params: list[object] = []
    for term in terms:
        pattern = f"%{term.lower()}%"
        like_params.extend([pattern, pattern])
    from_sql = f"""
        FROM content_fragments AS cf
        JOIN usage_events AS u ON u.record_id = cf.record_id
        WHERE {' AND '.join(like_clauses)}
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


def _snippet(
    text: str,
    *,
    query: str,
    max_chars: int | None,
) -> tuple[str, bool]:
    if max_chars is None or max_chars <= 0 or len(text) <= max_chars:
        return text, False
    terms = _search_terms(query)
    lower_text = text.lower()
    positions = [lower_text.find(term.lower()) for term in terms]
    match_positions = [position for position in positions if position >= 0]
    center = min(match_positions) if match_positions else 0
    start = max(0, center - max_chars // 3)
    end = min(len(text), start + max_chars)
    if end - start < max_chars:
        start = max(0, end - max_chars)
    excerpt = text[start:end].strip()
    prefix = "... " if start > 0 else ""
    suffix = " ..." if end < len(text) else ""
    return f"{prefix}{excerpt}{suffix}", True


def _search_terms(query: str) -> list[str]:
    return [term for term in re.findall(r"[\w-]+", query) if term]


def _fts_match_query(query: str) -> str:
    terms = _search_terms(query)
    if not terms:
        return _fts_quote(query)
    return " ".join(_fts_quote(term) for term in terms)


def _fts_quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _normalize_search_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return limit


def _normalize_search_offset(offset: int) -> int:
    return max(0, offset)


def _limit_clause(limit: int | None) -> str:
    if limit is None:
        return ""
    return "LIMIT ? OFFSET ?"


def _limit_params(limit: int | None, offset: int) -> list[int]:
    if limit is None:
        return []
    return [limit, offset]


def _index_content_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
) -> ContentIndexResult:
    usage_rows = _usage_rows_by_token_line(conn, source_file=str(source_path))
    if not usage_rows:
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)

    delete_content_index_rows_for_source_files(
        conn,
        placeholders="?",
        source_files_to_replace=[str(source_path)],
    )
    pending: list[_PendingFragment] = []
    turn_id: str | None = None
    turn_index = 0
    parse_warnings = 0
    try:
        with source_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                try:
                    envelope = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parse_warnings += 1
                    continue
                if not isinstance(envelope, dict):
                    parse_warnings += 1
                    continue
                payload = envelope.get("payload")
                if not isinstance(payload, dict):
                    parse_warnings += 1
                    continue
                entry_type = envelope.get("type")
                timestamp = optional_str(envelope.get("timestamp"))
                if entry_type == "turn_context":
                    turn_id = optional_str(payload.get("turn_id"))
                    turn_index += 1
                    continue
                if _is_token_count(entry_type, payload):
                    usage_row = usage_rows.get(line_number)
                    if usage_row is not None:
                        _flush_pending_fragments(
                            conn,
                            pending=pending,
                            usage_row=usage_row,
                        )
                    pending = []
                    continue
                pending.extend(
                    _extract_pending_fragments(
                        envelope=envelope,
                        payload=payload,
                        line_number=line_number,
                        timestamp=timestamp,
                        turn_id=turn_id,
                        turn_index=turn_index,
                    )
                )
    except OSError:
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)

    _rebuild_content_fts(conn)
    counts = _content_counts_for_source_file(conn, source_file=str(source_path))
    return ContentIndexResult(
        source_files=1,
        conversation_turns=counts["conversation_turns"],
        content_fragments=counts["content_fragments"],
        parse_warnings=parse_warnings,
    )


def _usage_rows_by_token_line(
    conn: sqlite3.Connection,
    *,
    source_file: str,
) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT
            u.record_id,
            u.session_id,
            u.turn_id,
            u.event_timestamp,
            u.source_file,
            u.line_number,
            sr.source_file_id,
            sr.source_record_hash,
            sr.parser_adapter,
            sr.parser_version
        FROM usage_events AS u
        JOIN source_records AS sr ON sr.record_id = u.record_id
        WHERE u.source_file = ?
        ORDER BY u.line_number
        """,
        (source_file,),
    ).fetchall()
    return {int(row["line_number"]): row for row in rows}


def _extract_pending_fragments(
    *,
    envelope: dict[str, Any],
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    entry_type = envelope.get("type")
    payload_type = optional_str(payload.get("type")) or ""
    if entry_type == "response_item":
        return _response_item_fragments(
            payload=payload,
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    if entry_type == "compacted":
        return _compaction_fragments(
            payload=payload,
            payload_type="compacted",
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    if entry_type == "event_msg" and payload_type == "context_compacted":
        return _compaction_fragments(
            payload=payload,
            payload_type="context_compacted",
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    return []


def _response_item_fragments(
    *,
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    payload_type = optional_str(payload.get("type")) or "response_item"
    role = optional_str(payload.get("role")) or _role_from_payload_type(payload_type)
    fragments: list[_PendingFragment] = []
    for index, text in enumerate(_content_texts(payload.get("content"))):
        fragments.append(
            _pending_fragment(
                role=role,
                fragment_kind="message",
                safe_label=f"response_item.{payload_type}.{role}.{index}",
                text=text,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    for index, text in enumerate(_reasoning_summary_texts(payload.get("summary"))):
        fragments.append(
            _pending_fragment(
                role="reasoning",
                fragment_kind="reasoning_summary",
                safe_label=f"response_item.{payload_type}.reasoning_summary.{index}",
                text=text,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    return fragments


def _compaction_fragments(
    *,
    payload: dict[str, Any],
    payload_type: str,
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    fragments: list[_PendingFragment] = []
    message = optional_str(payload.get("message"))
    if message:
        fragments.append(
            _pending_fragment(
                role="system",
                fragment_kind="compaction",
                safe_label=f"{payload_type}.message",
                text=message,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    for index, item in enumerate(_message_history(payload.get("replacement_history"))):
        role = optional_str(item.get("role")) or "unknown"
        for content_index, text in enumerate(_content_texts(item.get("content"))):
            fragments.append(
                _pending_fragment(
                    role=role,
                    fragment_kind="compaction_history",
                    safe_label=f"{payload_type}.replacement_history.{role}.{index}.{content_index}",
                    text=text,
                    line_number=line_number,
                    timestamp=timestamp,
                    turn_id=turn_id,
                    turn_index=turn_index,
                )
            )
    return fragments


def _pending_fragment(
    *,
    role: str,
    fragment_kind: str,
    safe_label: str,
    text: str,
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> _PendingFragment:
    return _PendingFragment(
        role=role,
        fragment_kind=fragment_kind,
        safe_label=safe_label,
        text=text[:MAX_FRAGMENT_CHARS],
        line_start=line_number,
        line_end=line_number,
        turn_id=turn_id,
        turn_index=turn_index,
        event_timestamp=timestamp,
    )


def _flush_pending_fragments(
    conn: sqlite3.Connection,
    *,
    pending: list[_PendingFragment],
    usage_row: sqlite3.Row,
) -> None:
    if not pending:
        return
    turn_rows: list[dict[str, object]] = []
    fragment_rows: list[dict[str, object]] = []
    for index, fragment in enumerate(pending):
        turn_key = _stable_hash(
            f"turn:{usage_row['record_id']}:{fragment.line_start}:{fragment.role}:{index}"
        )
        turn_rows.append(_turn_row(turn_key=turn_key, fragment=fragment, usage_row=usage_row))
        fragment_rows.append(
            _fragment_row(
                fragment_id=_stable_hash(
                    f"fragment:{turn_key}:{index}:{_stable_hash(fragment.text)}"
                ),
                turn_key=turn_key,
                fragment=fragment,
                usage_row=usage_row,
            )
        )
    _upsert_turn_rows(conn, turn_rows)
    _upsert_fragment_rows(conn, fragment_rows)


def _turn_row(
    *,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: sqlite3.Row,
) -> dict[str, object]:
    return {
        "turn_key": turn_key,
        "record_id": str(usage_row["record_id"]),
        "session_id": str(usage_row["session_id"]),
        "turn_id": fragment.turn_id or usage_row["turn_id"],
        "turn_index": fragment.turn_index,
        "role": fragment.role,
        "event_timestamp": fragment.event_timestamp or usage_row["event_timestamp"],
        "source_record_hash": usage_row["source_record_hash"],
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "content_hash": _stable_hash(fragment.text),
        "content_size_bytes": len(fragment.text.encode("utf-8")),
        "indexed_content_included": 1,
        "parser_adapter": usage_row["parser_adapter"] or PARSER_ADAPTER_NAME,
        "parser_version": usage_row["parser_version"] or PARSER_ADAPTER_VERSION,
        "parse_warnings_json": "[]",
    }


def _fragment_row(
    *,
    fragment_id: str,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: sqlite3.Row,
) -> dict[str, object]:
    return {
        "fragment_id": fragment_id,
        "record_id": str(usage_row["record_id"]),
        "turn_key": turn_key,
        "fragment_kind": fragment.fragment_kind,
        "role": fragment.role,
        "safe_label": fragment.safe_label,
        "content_hash": _stable_hash(fragment.text),
        "content_size_bytes": len(fragment.text.encode("utf-8")),
        "fragment_text": fragment.text,
        "includes_raw_fragment": 1,
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "token_link_record_id": str(usage_row["record_id"]),
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _upsert_turn_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "turn_key",
        "record_id",
        "session_id",
        "turn_id",
        "turn_index",
        "role",
        "event_timestamp",
        "source_record_hash",
        "source_file_id",
        "line_start",
        "line_end",
        "content_hash",
        "content_size_bytes",
        "indexed_content_included",
        "parser_adapter",
        "parser_version",
        "parse_warnings_json",
    )
    conn.executemany(
        _upsert_sql("conversation_turns", columns, "turn_key"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_fragment_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "fragment_id",
        "record_id",
        "turn_key",
        "fragment_kind",
        "role",
        "safe_label",
        "content_hash",
        "content_size_bytes",
        "fragment_text",
        "includes_raw_fragment",
        "source_file_id",
        "line_start",
        "line_end",
        "token_link_record_id",
        "created_at",
    )
    conn.executemany(
        _upsert_sql("content_fragments", columns, "fragment_id"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_sql(table_name: str, columns: tuple[str, ...], primary_key: str) -> str:
    placeholders = ", ".join("?" for _column in columns)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column != primary_key
    )
    return (
        f"INSERT INTO {table_name} ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT({primary_key}) DO UPDATE SET {update_clause}"
    )


def _rebuild_content_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
        conn.execute(
            """
            INSERT INTO content_fts(rowid, fragment_text, safe_label, fragment_kind)
            SELECT fragment_rowid, fragment_text, safe_label, fragment_kind
            FROM content_fragments
            WHERE fragment_text != ''
            """
        )
    except sqlite3.DatabaseError:
        return


def _clear_content_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
    except sqlite3.DatabaseError:
        return


def _content_counts_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_file: str,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT
            (SELECT COUNT(*)
             FROM conversation_turns
             WHERE record_id IN (
                 SELECT record_id FROM usage_events WHERE source_file = ?
             )) AS conversation_turns,
            (SELECT COUNT(*)
             FROM content_fragments
             WHERE record_id IN (
                 SELECT record_id FROM usage_events WHERE source_file = ?
             )) AS content_fragments
        """,
        (source_file, source_file),
    ).fetchone()
    if rows is None:
        return {"conversation_turns": 0, "content_fragments": 0}
    return {
        "conversation_turns": int(rows["conversation_turns"] or 0),
        "content_fragments": int(rows["content_fragments"] or 0),
    }


def _content_texts(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            text = optional_str(item.get("text"))
            if text:
                texts.append(text)
    return texts


def _reasoning_summary_texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = optional_str(item.get("text")) or optional_str(item.get("summary_text"))
            if text:
                texts.append(text)
    return texts


def _message_history(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _role_from_payload_type(payload_type: str) -> str:
    if payload_type == "reasoning":
        return "reasoning"
    if payload_type in {"function_call", "function_call_output"}:
        return "tool"
    return "unknown"


def _is_token_count(entry_type: object, payload: dict[str, Any]) -> bool:
    return entry_type == "event_msg" and payload.get("type") == "token_count"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
