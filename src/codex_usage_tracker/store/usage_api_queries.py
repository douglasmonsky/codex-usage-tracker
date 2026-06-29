"""Live usage API read queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_offset,
    normalize_sort_direction,
    usage_api_sort_expression,
    usage_api_where_clause,
    usage_where_clause,
)
from codex_usage_tracker.store.rows import usage_row_to_dict
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.usage_timing import (
    USAGE_TIMING_JOIN_SQL,
    USAGE_TIMING_SELECT_SQL,
)


def query_usage_api_events(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 100,
    offset: int = 0,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
    sort: str = "time",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return SQL-backed live dashboard call API rows."""

    where_clause, params = usage_api_where_clause(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        thread_key=thread_key,
        include_archived=include_archived,
        table_alias="usage_events",
    )
    order_expr = usage_api_sort_expression(sort)
    direction_sql = normalize_sort_direction(direction)
    normalized_limit = normalize_limit(limit)
    normalized_offset = normalize_offset(offset)
    limit_clause = ""
    query_params = list(params)
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
        if normalized_offset:
            limit_clause += " OFFSET ?"
            query_params.append(normalized_offset)
    elif normalized_offset:
        limit_clause = "LIMIT -1 OFFSET ?"
        query_params.append(normalized_offset)

    parent_where_clause, parent_params = usage_where_clause(include_archived=include_archived)
    parent_thread_filter = (
        f"{parent_where_clause} AND thread_name IS NOT NULL"
        if parent_where_clause
        else "WHERE thread_name IS NOT NULL"
    )
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                {USAGE_TIMING_SELECT_SQL},
                coalesce(
                    usage_events.parent_thread_name,
                    parent_threads.thread_name
                ) AS resolved_parent_thread_name,
                coalesce(
                    usage_events.parent_session_updated_at,
                    parent_threads.session_updated_at
                ) AS resolved_parent_session_updated_at
            FROM usage_events
            {USAGE_TIMING_JOIN_SQL}
            LEFT JOIN (
                SELECT
                    session_id,
                    max(thread_name) AS thread_name,
                    max(session_updated_at) AS session_updated_at
                FROM usage_events
                {parent_thread_filter}
                GROUP BY session_id
            ) AS parent_threads
            ON usage_events.parent_session_id = parent_threads.session_id
            {where_clause}
            ORDER BY {order_expr} {direction_sql},
                usage_events.event_timestamp DESC,
                usage_events.cumulative_total_tokens DESC
            {limit_clause}
            """,
            [*parent_params, *query_params],
        ).fetchall()
    return [usage_row_to_dict(row) for row in rows]


def query_usage_api_event_count(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    thread_key: str | None = None,
    include_archived: bool = False,
) -> int:
    """Return count for SQL-backed live dashboard call APIs."""

    where_clause, params = usage_api_where_clause(
        search=search,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        thread_key=thread_key,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"SELECT COUNT(*) AS row_count FROM usage_events {where_clause}",
            params,
        ).fetchone()
    return int(row["row_count"] if row is not None else 0)
