"""Materialized thread-summary maintenance for the usage store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.query_sql import (
    normalize_limit,
    normalize_offset,
    normalize_sort_direction,
    render_sql_template,
    thread_key_expression,
)
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.thread_summary_rebuild import (
    rebuild_thread_summaries as rebuild_thread_summaries,
)


def _latest_record_id_expression(*, include_archived: bool) -> str:
    active_fact_filter = "" if include_archived else "AND rf.is_archived = 0"
    active_usage_filter = _active_usage_filter(include_archived)
    legacy_thread_key = thread_key_expression("u.")
    return render_sql_template(
        """
        coalesce(
            (
                SELECT rf.record_id
                FROM recommendation_facts AS rf
                    INDEXED BY idx_recommendation_facts_thread_latest
                WHERE rf.thread_key = t.thread_key
                    AND rf.event_timestamp = t.latest_event_timestamp
                    $active_fact_filter
                ORDER BY
                    rf.total_tokens DESC,
                    rf.record_id DESC
                LIMIT 1
            ),
            (
                SELECT u.record_id
                FROM canonical_usage_events AS u
                WHERE u.thread_key = t.thread_key
                $active_usage_filter
                ORDER BY
                    u.event_timestamp DESC,
                    u.cumulative_total_tokens DESC,
                    u.record_id DESC
                LIMIT 1
            ),
            (
                SELECT u.record_id
                FROM canonical_usage_events AS u
                WHERE (u.thread_key IS NULL OR u.thread_key = '')
                    AND $legacy_thread_key = t.thread_key
                $active_usage_filter
                ORDER BY
                    u.event_timestamp DESC,
                    u.cumulative_total_tokens DESC,
                    u.record_id DESC
                LIMIT 1
            )
        )
        """,
        {
            "active_fact_filter": active_fact_filter,
            "active_usage_filter": active_usage_filter,
            "legacy_thread_key": legacy_thread_key,
        },
    )


def query_thread_summaries(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int | None = 100,
    offset: int = 0,
    search: str | None = None,
    risk: str | None = None,
    include_archived: bool = False,
    sort: str = "tokens",
    direction: str = "desc",
) -> list[dict[str, Any]]:
    """Return materialized thread summaries for live dashboard APIs."""

    where_clause, params = _thread_summary_where_clause(
        search=search,
        risk=risk,
        include_archived=include_archived,
    )
    sort_column = _thread_summary_sort_column(sort)
    direction_sql = normalize_sort_direction(direction)
    normalized_limit = normalize_limit(limit)
    normalized_offset = normalize_offset(offset)
    limit_clause, query_params = _thread_summary_limit_clause(
        normalized_limit,
        normalized_offset,
        params,
    )
    latest_record_id = _latest_record_id_expression(include_archived=include_archived)
    with connect(db_path) as conn:
        init_db(conn)
        query = render_sql_template(
            """
            SELECT
                t.*,
                $latest_record_id AS latest_record_id
            FROM thread_summaries AS t
            $where_clause
            ORDER BY $sort_column $direction, latest_event_timestamp DESC
            $limit_clause
            """,
            {
                "latest_record_id": latest_record_id,
                "where_clause": where_clause,
                "sort_column": sort_column,
                "direction": direction_sql,
                "limit_clause": limit_clause,
            },
        )
        rows = conn.execute(query, query_params).fetchall()
    return [row_to_dict(row) for row in rows]


def query_thread_summary(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    thread_key: str,
    include_archived: bool = False,
) -> dict[str, Any] | None:
    """Return one exact aggregate thread summary in the selected history scope."""
    scope = "all-history" if include_archived else "active"
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT t.*
            FROM thread_summaries AS t
            WHERE t.thread_key = ?
              AND t.is_archived_scope = ?
            LIMIT 1
            """,  # nosec B608 - fixed archive predicate only.
            (thread_key, scope),
        ).fetchone()
    return row_to_dict(row) if row is not None else None


def _thread_summary_sort_column(sort: str) -> str:
    sort_map = {
        "tokens": "total_tokens",
        "time": "latest_event_timestamp",
        "calls": "call_count",
        "cache": "avg_cache_ratio",
        "thread": "thread_label",
        "cost": "coalesce(estimated_cost_usd, 0)",
        "credits": "coalesce(usage_credits, 0)",
        "context": "coalesce(max_context_window_percent, 0)",
        "risk": "coalesce(avg_cache_ratio, 0)",
        "cost_per_call": (
            "CASE WHEN call_count > 0 THEN coalesce(estimated_cost_usd, 0) / call_count ELSE 0 END"
        ),
    }
    if sort not in sort_map:
        allowed = ", ".join(sorted(sort_map))
        raise ValueError(f"sort must be one of: {allowed}")
    return sort_map[sort]


def _thread_summary_limit_clause(
    limit: int | None,
    offset: int,
    params: list[Any],
) -> tuple[str, list[Any]]:
    query_params = list(params)
    if limit is not None:
        query_params.append(limit)
        if offset:
            query_params.append(offset)
            return "LIMIT ? OFFSET ?", query_params
        return "LIMIT ?", query_params
    if offset:
        query_params.append(offset)
        return "LIMIT -1 OFFSET ?", query_params
    return "", query_params


def _active_usage_filter(include_archived: bool) -> str:
    if include_archived:
        return ""
    return "AND coalesce(u.is_archived, 0) = 0"


def query_thread_summary_count(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    search: str | None = None,
    risk: str | None = None,
    include_archived: bool = False,
) -> int:
    """Return the number of thread summaries matching list filters."""

    where_clause, params = _thread_summary_where_clause(
        search=search,
        risk=risk,
        include_archived=include_archived,
    )
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            f"SELECT COUNT(*) AS row_count FROM thread_summaries {where_clause}",
            params,
        ).fetchone()
    return int(row["row_count"] if row is not None else 0)


def _thread_summary_where_clause(
    *,
    search: str | None,
    risk: str | None,
    include_archived: bool,
) -> tuple[str, list[Any]]:
    clauses = ["is_archived_scope = ?"]
    params: list[Any] = ["all-history" if include_archived else "active"]
    if search:
        like = f"%{search}%"
        clauses.append("(thread_key LIKE ? OR thread_label LIKE ?)")
        params.extend([like, like])
    if risk is not None:
        risk_clauses = {
            "high": "coalesce(avg_cache_ratio, 0) < 0.25",
            "medium": (
                "coalesce(avg_cache_ratio, 0) >= 0.25 AND coalesce(avg_cache_ratio, 0) < 0.45"
            ),
            "low": "coalesce(avg_cache_ratio, 0) >= 0.45",
        }
        try:
            clauses.append(risk_clauses[risk.lower()])
        except KeyError as exc:
            raise ValueError("risk must be one of: high, medium, low") from exc
    return "WHERE " + " AND ".join(f"({clause})" for clause in clauses), params
