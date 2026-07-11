"""Aggregate summary read queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import (
    group_expression,
    normalize_limit,
    since_where_clause,
)
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db


def query_summary(
    db_path: Path = DEFAULT_DB_PATH,
    group_by: str = "thread",
    limit: int | None = 20,
    since: str | None = None,
    include_archived: bool = True,
) -> list[dict[str, Any]]:
    """Return aggregate usage grouped by a supported summary dimension."""

    group_expr = group_expression(group_by)
    where_clause, raw_params = since_where_clause(
        since,
        include_archived=include_archived,
    )
    params: list[Any] = list(raw_params)
    normalized_limit = normalize_limit(limit)
    limit_clause = "LIMIT ?" if normalized_limit is not None else ""
    sql = f"""
        SELECT
            {group_expr} AS group_key,
            COUNT(*) AS model_calls,
            COUNT(DISTINCT session_id) AS sessions,
            COUNT(DISTINCT turn_id) AS turns,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(uncached_input_tokens) AS uncached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            AVG(cache_ratio) AS avg_cache_ratio,
            AVG(reasoning_output_ratio) AS avg_reasoning_output_ratio,
            AVG(context_window_percent) AS avg_context_window_percent,
            MAX(event_timestamp) AS latest_event
        FROM usage_events
        {where_clause}
        GROUP BY group_key
        ORDER BY total_tokens DESC
        {limit_clause}
    """
    if normalized_limit is not None:
        params.append(normalized_limit)
    with connect(db_path) as conn:
        init_db(conn)
        return [row_to_dict(row) for row in conn.execute(sql, params)]
