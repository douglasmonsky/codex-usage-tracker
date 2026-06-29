"""Diagnostic fact per-call read queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.diagnostic_queries import append_diagnostic_fact_filters
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_offset,
    normalize_sort_direction,
    usage_where_clause,
)
from codex_usage_tracker.store.rows import usage_row_to_dict
from codex_usage_tracker.store.schema import init_db


def query_diagnostic_fact_calls(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    fact_type: str,
    fact_name: str,
    limit: int | None = 50,
    offset: int = 0,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = False,
    sort: str = "tokens",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return usage calls associated with one diagnostic fact."""

    where_clause, params = diagnostic_fact_call_where(
        fact_type=fact_type,
        fact_name=fact_name,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
    )
    order_expr = diagnostic_fact_call_order_expression(sort)
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
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                usage_events.*,
                previous_usage.event_timestamp AS previous_call_event_timestamp,
                previous_usage.session_id AS previous_call_session_id,
                previous_usage.turn_id AS previous_call_turn_id,
                f.fact_type,
                f.fact_name,
                f.fact_category,
                f.event_count AS diagnostic_event_count,
                f.confidence AS diagnostic_confidence,
                f.first_event_timestamp AS diagnostic_first_event_timestamp,
                f.last_event_timestamp AS diagnostic_last_event_timestamp,
                f.first_source_line AS diagnostic_first_source_line,
                f.last_source_line AS diagnostic_last_source_line,
                f.evidence_scope AS diagnostic_evidence_scope,
                f.raw_content_included AS raw_content_included
            FROM call_diagnostic_facts AS f
            JOIN usage_events ON usage_events.record_id = f.record_id
            LEFT JOIN usage_events AS previous_usage
            ON previous_usage.record_id = usage_events.previous_record_id
            {where_clause}
            ORDER BY {order_expr} {direction_sql},
                usage_events.event_timestamp DESC,
                usage_events.cumulative_total_tokens DESC
            {limit_clause}
            """,
            query_params,
        )
        return [usage_row_to_dict(row) for row in rows]


def query_diagnostic_fact_call_count(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    fact_type: str,
    fact_name: str,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    include_archived: bool = False,
) -> int:
    """Return the number of calls associated with one diagnostic fact."""

    where_clause, params = diagnostic_fact_call_where(
        fact_type=fact_type,
        fact_name=fact_name,
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT usage_events.record_id) AS row_count
            FROM call_diagnostic_facts AS f
            JOIN usage_events ON usage_events.record_id = f.record_id
            {where_clause}
            """,
            params,
        ).fetchone()
        return int(row["row_count"] if row is not None else 0)


def diagnostic_fact_call_where(
    *,
    fact_type: str,
    fact_name: str,
    since: str | None,
    until: str | None,
    model: str | None,
    effort: str | None,
    thread: str | None,
    min_tokens: int | None,
    include_archived: bool,
) -> tuple[str, list[Any]]:
    where_clause, params = usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        table_alias="usage_events",
        include_archived=include_archived,
    )
    return append_diagnostic_fact_filters(
        where_clause,
        params,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=None,
        table_alias="f",
    )


def diagnostic_fact_call_order_expression(sort: str) -> str:
    sort_map = {
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
    }
    try:
        return sort_map[sort]
    except KeyError as exc:
        allowed = ", ".join(sorted(sort_map))
        raise ValueError(f"sort must be one of: {allowed}") from exc
