"""Diagnostic fact aggregate read queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_sort_direction,
    usage_where_clause,
)
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db


def query_diagnostic_facts(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 50,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    fact_type: str | None = None,
    fact_name: str | None = None,
    fact_category: str | None = None,
    include_archived: bool = False,
    sort: str = "uncached",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return aggregate diagnostic fact summaries joined to usage events."""

    sort_map = {
        "uncached": "associated_uncached_input_tokens",
        "tokens": "associated_total_tokens",
        "cached": "associated_cached_input_tokens",
        "output": "associated_output_tokens",
        "cache": "avg_cache_ratio",
        "largest": "largest_call_tokens",
        "calls": "associated_calls",
        "occurrences": "occurrences",
        "time": "latest_event_timestamp",
        "fact": "f.fact_name",
    }
    if sort not in sort_map:
        allowed = ", ".join(sorted(sort_map))
        raise ValueError(f"sort must be one of: {allowed}")
    direction_sql = normalize_sort_direction(direction)
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
    where_clause, params = append_diagnostic_fact_filters(
        where_clause,
        params,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=fact_category,
        table_alias="f",
    )
    sub_where_clause, sub_params = usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        min_tokens=min_tokens,
        table_alias="u2",
        include_archived=include_archived,
    )
    sub_where_clause, sub_params = append_diagnostic_fact_filters(
        sub_where_clause,
        sub_params,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=fact_category,
        table_alias="f2",
    )
    sub_conditions = [
        "f2.fact_type = f.fact_type",
        "f2.fact_name = f.fact_name",
    ]
    if sub_where_clause:
        sub_conditions.append(sub_where_clause.removeprefix("WHERE "))
    sub_where_sql = "WHERE " + " AND ".join(f"({condition})" for condition in sub_conditions)
    normalized_limit = normalize_limit(limit)
    limit_clause = ""
    query_params: list[Any] = [*sub_params, *params]
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            SELECT
                f.fact_type,
                f.fact_name,
                f.fact_category,
                coalesce(SUM(f.event_count), 0) AS occurrences,
                COUNT(DISTINCT usage_events.record_id) AS associated_calls,
                coalesce(SUM(usage_events.input_tokens), 0) AS associated_input_tokens,
                coalesce(SUM(usage_events.cached_input_tokens), 0)
                    AS associated_cached_input_tokens,
                coalesce(SUM(usage_events.uncached_input_tokens), 0)
                    AS associated_uncached_input_tokens,
                coalesce(SUM(usage_events.output_tokens), 0) AS associated_output_tokens,
                coalesce(SUM(usage_events.reasoning_output_tokens), 0)
                    AS associated_reasoning_output_tokens,
                coalesce(SUM(usage_events.total_tokens), 0) AS associated_total_tokens,
                AVG(usage_events.cache_ratio) AS avg_cache_ratio,
                MAX(usage_events.total_tokens) AS largest_call_tokens,
                MAX(usage_events.event_timestamp) AS latest_event_timestamp,
                MIN(f.first_source_line) AS first_source_line,
                MAX(f.last_source_line) AS last_source_line,
                MAX(f.raw_content_included) AS raw_content_included,
                (
                    SELECT u2.record_id
                    FROM call_diagnostic_facts AS f2
                    JOIN usage_events AS u2 ON u2.record_id = f2.record_id
                    {sub_where_sql}
                    ORDER BY u2.total_tokens DESC, u2.event_timestamp DESC, u2.record_id
                    LIMIT 1
                ) AS largest_record_id
            FROM call_diagnostic_facts AS f
            JOIN usage_events ON usage_events.record_id = f.record_id
            {where_clause}
            GROUP BY f.fact_type, f.fact_name, f.fact_category
            ORDER BY {sort_map[sort]} {direction_sql},
                associated_total_tokens DESC,
                f.fact_type,
                f.fact_name
            {limit_clause}
            """,
            query_params,
        )
        return [row_to_dict(row) for row in rows]


def query_diagnostic_summary(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 20,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    min_tokens: int | None = None,
    fact_type: str | None = None,
    fact_name: str | None = None,
    fact_category: str | None = None,
    include_archived: bool = False,
    sort: str = "uncached",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return aggregate diagnostic summaries grouped by fact type."""

    sort_map = {
        "uncached": "associated_uncached_input_tokens",
        "tokens": "associated_total_tokens",
        "cached": "associated_cached_input_tokens",
        "output": "associated_output_tokens",
        "cache": "avg_cache_ratio",
        "largest": "largest_call_tokens",
        "calls": "associated_calls",
        "occurrences": "occurrences",
        "time": "latest_event_timestamp",
        "fact": "type_counts.fact_type",
    }
    if sort not in sort_map:
        allowed = ", ".join(sorted(sort_map))
        raise ValueError(f"sort must be one of: {allowed}")
    direction_sql = normalize_sort_direction(direction)
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
    where_clause, params = append_diagnostic_fact_filters(
        where_clause,
        params,
        fact_type=fact_type,
        fact_name=fact_name,
        fact_category=fact_category,
        table_alias="f",
    )
    normalized_limit = normalize_limit(limit)
    limit_clause = ""
    query_params: list[Any] = list(params)
    if normalized_limit is not None:
        limit_clause = "LIMIT ?"
        query_params.append(normalized_limit)
    with connect(db_path) as conn:
        init_db(conn)
        rows = conn.execute(
            f"""
            WITH scoped AS (
                SELECT
                    f.fact_type,
                    f.fact_name,
                    f.event_count,
                    usage_events.record_id,
                    usage_events.input_tokens,
                    usage_events.cached_input_tokens,
                    usage_events.uncached_input_tokens,
                    usage_events.output_tokens,
                    usage_events.reasoning_output_tokens,
                    usage_events.total_tokens,
                    usage_events.cache_ratio,
                    usage_events.event_timestamp
                FROM call_diagnostic_facts AS f
                JOIN usage_events ON usage_events.record_id = f.record_id
                {where_clause}
            ),
            type_counts AS (
                SELECT
                    fact_type,
                    coalesce(SUM(event_count), 0) AS occurrences,
                    COUNT(DISTINCT record_id) AS associated_calls,
                    COUNT(DISTINCT fact_name) AS fact_names
                FROM scoped
                GROUP BY fact_type
            ),
            distinct_calls AS (
                SELECT
                    fact_type,
                    record_id,
                    MAX(input_tokens) AS input_tokens,
                    MAX(cached_input_tokens) AS cached_input_tokens,
                    MAX(uncached_input_tokens) AS uncached_input_tokens,
                    MAX(output_tokens) AS output_tokens,
                    MAX(reasoning_output_tokens) AS reasoning_output_tokens,
                    MAX(total_tokens) AS total_tokens,
                    MAX(cache_ratio) AS cache_ratio,
                    MAX(event_timestamp) AS event_timestamp
                FROM scoped
                GROUP BY fact_type, record_id
            ),
            call_sums AS (
                SELECT
                    fact_type,
                    coalesce(SUM(input_tokens), 0) AS associated_input_tokens,
                    coalesce(SUM(cached_input_tokens), 0) AS associated_cached_input_tokens,
                    coalesce(SUM(uncached_input_tokens), 0)
                        AS associated_uncached_input_tokens,
                    coalesce(SUM(output_tokens), 0) AS associated_output_tokens,
                    coalesce(SUM(reasoning_output_tokens), 0)
                        AS associated_reasoning_output_tokens,
                    coalesce(SUM(total_tokens), 0) AS associated_total_tokens,
                    AVG(cache_ratio) AS avg_cache_ratio,
                    MAX(total_tokens) AS largest_call_tokens,
                    MAX(event_timestamp) AS latest_event_timestamp
                FROM distinct_calls
                GROUP BY fact_type
            )
            SELECT
                type_counts.fact_type,
                type_counts.occurrences,
                type_counts.associated_calls,
                type_counts.fact_names,
                call_sums.associated_input_tokens,
                call_sums.associated_cached_input_tokens,
                call_sums.associated_uncached_input_tokens,
                call_sums.associated_output_tokens,
                call_sums.associated_reasoning_output_tokens,
                call_sums.associated_total_tokens,
                call_sums.avg_cache_ratio,
                call_sums.largest_call_tokens,
                call_sums.latest_event_timestamp,
                (
                    SELECT s2.fact_name
                    FROM scoped AS s2
                    WHERE s2.fact_type = type_counts.fact_type
                    GROUP BY s2.fact_name
                    ORDER BY SUM(s2.event_count) DESC, SUM(s2.uncached_input_tokens) DESC
                    LIMIT 1
                ) AS top_fact_name
            FROM type_counts
            JOIN call_sums ON call_sums.fact_type = type_counts.fact_type
            ORDER BY {sort_map[sort]} {direction_sql},
                associated_total_tokens DESC,
                type_counts.fact_type
            {limit_clause}
            """,
            query_params,
        )
        return [row_to_dict(row) for row in rows]


def append_diagnostic_fact_filters(
    where_clause: str,
    params: list[Any],
    *,
    fact_type: str | None,
    fact_name: str | None,
    fact_category: str | None,
    table_alias: str,
) -> tuple[str, list[Any]]:
    clauses = _existing_fact_filter_clauses(where_clause)
    updated_params = list(params)
    prefix = f"{table_alias}."
    for field, value in (
        ("fact_type", fact_type),
        ("fact_name", fact_name),
        ("fact_category", fact_category),
    ):
        if value:
            clauses.append(f"{prefix}{field} = ?")
            updated_params.append(value)
    return _diagnostic_where_clause(clauses), updated_params


def _existing_fact_filter_clauses(where_clause: str) -> list[str]:
    if not where_clause:
        return []
    return [where_clause.removeprefix("WHERE ")]


def _diagnostic_where_clause(clauses: list[str]) -> str:
    if not clauses:
        return ""
    return "WHERE " + " AND ".join(f"({clause})" for clause in clauses)
