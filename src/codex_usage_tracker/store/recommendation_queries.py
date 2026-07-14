"""Indexed read services for materialized recommendation facts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import normalize_limit, usage_where_clause
from codex_usage_tracker.store.rows import usage_row_to_dict
from codex_usage_tracker.store.usage_timing import (
    USAGE_TIMING_JOIN_SQL,
    USAGE_TIMING_SELECT_SQL,
    usage_parent_select_sql,
)


@dataclass(frozen=True)
class RecommendationFactPage:
    """Ordered recommendation rows plus the count before response limiting."""

    rows: list[dict[str, Any]]
    total_count: int


def query_recommendation_fact_page(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    since: str | None = None,
    until: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    thread: str | None = None,
    include_archived: bool = False,
    min_score: float | None = None,
    limit: int | None = 20,
) -> RecommendationFactPage:
    """Return actionable facts in the legacy recommendation order."""

    where_clause, params = usage_where_clause(
        since=since,
        until=until,
        model=model,
        effort=effort,
        thread=thread,
        table_alias="usage_events",
        include_archived=include_archived,
    )
    where_clause = _extend_fact_filters(where_clause, params, min_score=min_score)
    normalized_limit = normalize_limit(limit)
    limit_clause = "" if normalized_limit is None else " LIMIT ?"
    row_params = [*params] if normalized_limit is None else [*params, normalized_limit]
    from_clause = "recommendation_facts rf JOIN usage_events USING (record_id)"
    count_query = f"SELECT COUNT(*) FROM {from_clause} {where_clause}"  # nosec B608 - internal SQL templates; values remain bound
    row_query = f"""
        SELECT
            usage_events.*,
            {USAGE_TIMING_SELECT_SQL},
            {usage_parent_select_sql(include_archived=include_archived)},
            rf.recommendation_score AS fact_recommendation_score,
            rf.primary_recommendation_key AS fact_primary_recommendation_key,
            rf.secondary_recommendation_keys_json
                AS fact_secondary_recommendation_keys_json,
            rf.recommended_action_key AS fact_recommended_action_key,
            rf.recommendations_json AS fact_recommendations_json
        FROM {from_clause}
        {USAGE_TIMING_JOIN_SQL}
        {where_clause}
        ORDER BY
            rf.recommendation_score DESC,
            rf.total_tokens DESC,
            rf.event_timestamp ASC,
            rf.record_id ASC
        {limit_clause}
    """  # nosec B608 - clauses are internal templates and values remain bound

    with connect(db_path) as conn:
        total_count = int(conn.execute(count_query, params).fetchone()[0])
        rows = conn.execute(row_query, row_params).fetchall()
    return RecommendationFactPage(
        rows=[usage_row_to_dict(row) for row in rows],
        total_count=total_count,
    )


def _extend_fact_filters(
    where_clause: str,
    params: list[Any],
    *,
    min_score: float | None,
) -> str:
    clauses = ["json_array_length(rf.recommendations_json) > 0"]
    if min_score is not None:
        clauses.append("rf.recommendation_score >= ?")
        params.append(min_score)
    separator = " AND " if where_clause else " WHERE "
    return f"{where_clause}{separator}{' AND '.join(clauses)}"
