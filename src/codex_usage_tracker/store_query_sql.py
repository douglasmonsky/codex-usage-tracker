"""SQL helper expressions for aggregate usage queries."""

from __future__ import annotations

from typing import Any

_ARCHIVED_SOURCE_PATTERNS = (
    "%/archived_sessions/%",
    "archived_sessions/%",
    "%\\archived_sessions\\%",
    "archived_sessions\\%",
)
API_USAGE_SORTS = {
    "time": "usage_events.event_timestamp",
    "tokens": "usage_events.total_tokens",
    "input": "usage_events.input_tokens",
    "cached": "usage_events.cached_input_tokens",
    "uncached": "usage_events.uncached_input_tokens",
    "output": "usage_events.output_tokens",
    "reasoning": "usage_events.reasoning_output_tokens",
    "cache": "usage_events.cache_ratio",
    "model": "usage_events.model",
    "effort": "usage_events.effort",
    "thread": "coalesce(usage_events.thread_name, usage_events.parent_thread_name, usage_events.session_id)",
    "initiator": "coalesce(usage_events.call_initiator, 'unknown')",
    "duration": """
        coalesce(
            (
                julianday(usage_events.event_timestamp)
                - julianday(
                    CASE
                        WHEN previous_usage.record_id IS NOT NULL
                            AND previous_usage.session_id = usage_events.session_id
                            AND coalesce(previous_usage.turn_id, '') = coalesce(usage_events.turn_id, '')
                            AND coalesce(usage_events.turn_id, '') != ''
                        THEN previous_usage.event_timestamp
                        ELSE usage_events.turn_timestamp
                    END
                )
            ) * 86400.0,
            -1
        )
    """,
    "gap": """
        coalesce(
            (julianday(usage_events.event_timestamp) - julianday(previous_usage.event_timestamp))
                * 86400.0,
            -1
        )
    """,
}


def _group_expression(group_by: str) -> str:
    mapping = {
        "date": "substr(event_timestamp, 1, 10)",
        "model": "coalesce(model, 'Unknown model')",
        "effort": "coalesce(effort, 'Unknown effort')",
        "cwd": "coalesce(cwd, 'Unknown cwd')",
        "thread": "coalesce(thread_name, parent_thread_name, session_id)",
        "session": "session_id",
        "thread_source": "coalesce(thread_source, 'user')",
        "subagent_type": "coalesce(subagent_type, 'not subagent')",
        "agent_role": "coalesce(agent_role, 'not agent role')",
        "parent_session": "coalesce(parent_session_id, 'no parent session')",
        "parent_thread": "coalesce(parent_thread_name, 'no parent thread')",
    }
    try:
        return mapping[group_by]
    except KeyError as exc:
        allowed = ", ".join(sorted(mapping))
        raise ValueError(f"group_by must be one of: {allowed}") from exc


def _since_where_clause(since: str | None) -> tuple[str, list[Any]]:
    return _usage_where_clause(since=since)


def _thread_key_expression(prefix: str = "") -> str:
    return (
        f"coalesce(nullif({prefix}thread_key, ''), "
        f"CASE WHEN {prefix}thread_name IS NOT NULL "
        f"THEN 'thread:' || {prefix}thread_name "
        f"ELSE 'session:' || {prefix}session_id END)"
    )


def _usage_where_clause(
    *,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    table_alias: str | None = None,
    include_archived: bool = True,
) -> tuple[str, list[Any]]:
    prefix = f"{table_alias}." if table_alias else ""
    clauses: list[str] = []
    params: list[Any] = []
    _extend_basic_usage_filters(
        clauses,
        params,
        prefix=prefix,
        since=since,
        until=until,
        model=model,
        effort=effort,
    )
    _extend_thread_filter(clauses, params, prefix=prefix, thread=thread)
    _extend_min_tokens_filter(clauses, params, prefix=prefix, min_tokens=min_tokens)
    _extend_archive_filter(clauses, params, prefix=prefix, include_archived=include_archived)
    return _where_clause(clauses, params)


def _extend_basic_usage_filters(
    clauses: list[str],
    params: list[Any],
    *,
    prefix: str,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
) -> None:
    for value, clause in (
        (since, f"{prefix}event_timestamp >= ?"),
        (until, f"{prefix}event_timestamp <= ?"),
        (model, f"{prefix}model = ?"),
        (effort, f"{prefix}effort = ?"),
    ):
        if value:
            clauses.append(clause)
            params.append(value)


def _extend_thread_filter(
    clauses: list[str],
    params: list[Any],
    *,
    prefix: str,
    thread: str | None,
) -> None:
    if not thread:
        return
    clauses.append(
        "("
        f"{prefix}thread_name = ? OR "
        f"{prefix}parent_thread_name = ? OR "
        f"{prefix}session_id = ?"
        ")"
    )
    params.extend([thread, thread, thread])


def _extend_min_tokens_filter(
    clauses: list[str],
    params: list[Any],
    *,
    prefix: str,
    min_tokens: int | None,
) -> None:
    if min_tokens is None:
        return
    clauses.append(f"{prefix}total_tokens >= ?")
    params.append(min_tokens)


def _extend_archive_filter(
    clauses: list[str],
    params: list[Any],
    *,
    prefix: str,
    include_archived: bool,
) -> None:
    if include_archived:
        return
    archived_path_clause = " OR ".join(
        f"{prefix}source_file LIKE ?" for _pattern in _ARCHIVED_SOURCE_PATTERNS
    )
    clauses.append(
        f"(coalesce({prefix}is_archived, 0) = 0 AND NOT ({archived_path_clause}))"
    )
    params.extend(_ARCHIVED_SOURCE_PATTERNS)


def _where_clause(clauses: list[str], params: list[Any]) -> tuple[str, list[Any]]:
    if not clauses:
        return "", []
    return "WHERE " + " AND ".join(clauses), params


def _usage_api_where_clause(
    *,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = True,
    table_alias: str | None = None,
) -> tuple[str, list[Any]]:
    prefix = f"{table_alias}." if table_alias else ""
    base_where, params = _usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
        table_alias=table_alias,
    )
    clauses = [base_where.removeprefix("WHERE ")] if base_where else []
    if search:
        like = f"%{search}%"
        clauses.append(
            "("
            f"{prefix}thread_name LIKE ? OR "
            f"{prefix}parent_thread_name LIKE ? OR "
            f"{prefix}cwd LIKE ? OR "
            f"{prefix}model LIKE ? OR "
            f"{prefix}session_id LIKE ?"
            ")"
        )
        params.extend([like, like, like, like, like])
    if thread_key:
        clauses.append(
            "("
            f"{prefix}thread_key = ? OR "
            f"'thread:' || {prefix}thread_name = ? OR "
            f"'session:' || {prefix}session_id = ? OR "
            f"{prefix}session_id = ?"
            ")"
        )
        params.extend([thread_key, thread_key, thread_key, thread_key])
    if not clauses:
        return "", []
    return "WHERE " + " AND ".join(f"({clause})" for clause in clauses), params


def _usage_api_sort_expression(sort: str) -> str:
    try:
        return API_USAGE_SORTS[sort]
    except KeyError as exc:
        allowed = ", ".join(sorted(API_USAGE_SORTS))
        raise ValueError(f"sort must be one of: {allowed}") from exc


def _normalize_sort_direction(direction: str) -> str:
    normalized = direction.lower()
    if normalized == "asc":
        return "ASC"
    if normalized == "desc":
        return "DESC"
    raise ValueError("direction must be one of: asc, desc")


def _normalize_limit(limit: int | None) -> int | None:
    if limit is None or limit <= 0:
        return None
    return int(limit)


def _normalize_offset(offset: int | None) -> int:
    if offset is None or offset <= 0:
        return 0
    return int(offset)


group_expression = _group_expression
normalize_limit = _normalize_limit
normalize_offset = _normalize_offset
normalize_sort_direction = _normalize_sort_direction
since_where_clause = _since_where_clause
thread_key_expression = _thread_key_expression
usage_api_sort_expression = _usage_api_sort_expression
usage_api_where_clause = _usage_api_where_clause
usage_where_clause = _usage_where_clause
