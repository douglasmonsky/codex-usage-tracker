"""Live usage API read queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_offset,
    normalize_sort_direction,
    render_sql_template,
    usage_api_sort_expression,
    usage_api_where_clause,
)
from codex_usage_tracker.store.rows import usage_row_to_dict
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.usage_timing import (
    USAGE_TIMING_JOIN_SQL,
    USAGE_TIMING_SELECT_SQL,
    usage_parent_select_sql,
)


class _UsageApiFilterKwargs(TypedDict):
    search: str | None
    since: str | None
    until: str | None
    model: str | None
    effort: str | None
    thread: str | None
    thread_key: str | None
    include_archived: bool
    table_alias: str | None


class _UsageApiCountFilterKwargs(TypedDict):
    search: str | None
    since: str | None
    until: str | None
    model: str | None
    effort: str | None
    thread: str | None
    thread_key: str | None
    include_archived: bool


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

    filter_kwargs: _UsageApiFilterKwargs = {
        "search": search,
        "since": since,
        "until": until,
        "model": model,
        "effort": effort,
        "thread": thread,
        "thread_key": thread_key,
        "include_archived": include_archived,
        "table_alias": "usage_events",
    }
    order_expr = usage_api_sort_expression(sort)
    direction_sql = normalize_sort_direction(direction)
    normalized_limit = normalize_limit(limit)
    normalized_offset = normalize_offset(offset)
    limit_clause = ""
    if thread_key and normalized_limit is not None:
        candidate_limit = normalized_limit + normalized_offset
        indexed_where, indexed_params = usage_api_where_clause(
            **filter_kwargs,
            thread_key_mode="indexed",
        )
        legacy_where, legacy_params = usage_api_where_clause(
            **filter_kwargs,
            thread_key_mode="legacy",
        )
        where_clause = render_sql_template(
            """
            WHERE usage_events.record_id IN (
                SELECT record_id FROM (
                    SELECT usage_events.record_id
                    FROM usage_events
                    $timing_join
                    $indexed_where
                    ORDER BY $order_expr $direction,
                        usage_events.event_timestamp DESC,
                        usage_events.cumulative_total_tokens DESC
                    LIMIT ?
                ) AS indexed_thread_rows
                UNION ALL
                SELECT record_id FROM (
                    SELECT usage_events.record_id
                    FROM usage_events
                    $timing_join
                    $legacy_where
                    ORDER BY $order_expr $direction,
                        usage_events.event_timestamp DESC,
                        usage_events.cumulative_total_tokens DESC
                    LIMIT ?
                ) AS legacy_thread_rows
            )
            """,
            {
                "timing_join": USAGE_TIMING_JOIN_SQL,
                "indexed_where": indexed_where,
                "legacy_where": legacy_where,
                "order_expr": order_expr,
                "direction": direction_sql,
            },
        )
        query_params = [
            *indexed_params,
            candidate_limit,
            *legacy_params,
            candidate_limit,
        ]
    else:
        where_clause, params = usage_api_where_clause(**filter_kwargs)
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

    with connect(db_path) as conn:
        init_db(conn)
        query = render_sql_template(
            """
            SELECT
                usage_events.*,
                $timing_select,
                $parent_select
            FROM usage_events
            $timing_join
            $where_clause
            ORDER BY $order_expr $direction,
                usage_events.event_timestamp DESC,
                usage_events.cumulative_total_tokens DESC
            $limit_clause
            """,
            {
                "timing_select": USAGE_TIMING_SELECT_SQL,
                "parent_select": usage_parent_select_sql(include_archived=include_archived),
                "timing_join": USAGE_TIMING_JOIN_SQL,
                "where_clause": where_clause,
                "order_expr": order_expr,
                "direction": direction_sql,
                "limit_clause": limit_clause,
            },
        )
        rows = conn.execute(query, query_params).fetchall()
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

    filter_kwargs: _UsageApiCountFilterKwargs = {
        "search": search,
        "since": since,
        "until": until,
        "model": model,
        "effort": effort,
        "thread": thread,
        "thread_key": thread_key,
        "include_archived": include_archived,
    }
    with connect(db_path) as conn:
        init_db(conn)
        if thread_key:
            total = 0
            for mode in ("indexed", "legacy"):
                where_clause, params = usage_api_where_clause(
                    **filter_kwargs,
                    thread_key_mode=mode,
                )
                row = conn.execute(
                    f"SELECT COUNT(*) AS row_count FROM usage_events {where_clause}",
                    params,
                ).fetchone()
                total += int(row["row_count"] if row is not None else 0)
            return total
        where_clause, params = usage_api_where_clause(**filter_kwargs)
        row = conn.execute(
            f"SELECT COUNT(*) AS row_count FROM usage_events {where_clause}",
            params,
        ).fetchone()
    return int(row["row_count"] if row is not None else 0)
