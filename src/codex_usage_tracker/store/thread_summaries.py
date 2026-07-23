"""Materialized thread-summary maintenance for the usage store."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
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
    usage_where_clause,
)
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db

_THREAD_KEY_BATCH_SIZE = 500


def rebuild_thread_summaries(
    conn: sqlite3.Connection,
    *,
    thread_keys: Iterable[str] | None = None,
) -> int:
    """Rebuild materialized per-thread aggregate summaries."""

    before = conn.total_changes
    normalized_thread_keys = sorted({key for key in thread_keys or [] if key})
    recommendation_rows = _saved_recommendation_summaries(
        conn,
        thread_keys=normalized_thread_keys or None,
    )
    if not normalized_thread_keys:
        conn.execute("DELETE FROM thread_summaries")
        _insert_thread_summary_scopes(conn, updated_at=_summary_timestamp())
        _restore_recommendation_summaries(conn, recommendation_rows)
        return conn.total_changes - before
    updated_at = _summary_timestamp()
    for start in range(0, len(normalized_thread_keys), _THREAD_KEY_BATCH_SIZE):
        chunk = normalized_thread_keys[start : start + _THREAD_KEY_BATCH_SIZE]
        placeholders = ", ".join("?" for _key in chunk)
        conn.execute(
            f"DELETE FROM thread_summaries WHERE thread_key IN ({placeholders})",
            chunk,
        )
        _insert_thread_summary_scopes(conn, updated_at=updated_at, thread_keys=chunk)
    _restore_recommendation_summaries(conn, recommendation_rows)
    return conn.total_changes - before


def _saved_recommendation_summaries(
    conn: sqlite3.Connection,
    *,
    thread_keys: list[str] | None,
) -> list[sqlite3.Row]:
    conditions = ["recommendation_summary_json IS NOT NULL"]
    params: list[str] = []
    if thread_keys:
        placeholders = ", ".join("?" for _ in thread_keys)
        conditions.append(f"thread_key IN ({placeholders})")
        params.extend(thread_keys)
    where_clause = f"WHERE {' AND '.join(conditions)}"
    return conn.execute(
        f"""
        SELECT thread_key, is_archived_scope, recommendation_score,
            recommendation_total_tokens, recommendation_summary_json,
            max_recommendation_score, primary_recommendation
        FROM thread_summaries
        {where_clause}
        """,  # nosec B608 - only generated placeholders; values remain bound
        params,
    ).fetchall()


def _restore_recommendation_summaries(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
) -> None:
    conn.executemany(
        """
        UPDATE thread_summaries
        SET recommendation_score = ?, recommendation_total_tokens = ?,
            recommendation_summary_json = ?, max_recommendation_score = ?,
            primary_recommendation = ?
        WHERE thread_key = ? AND is_archived_scope = ?
        """,
        [
            (
                row["recommendation_score"],
                row["recommendation_total_tokens"],
                row["recommendation_summary_json"],
                row["max_recommendation_score"],
                row["primary_recommendation"],
                row["thread_key"],
                row["is_archived_scope"],
            )
            for row in rows
        ],
    )


def _summary_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _insert_thread_summary_scopes(
    conn: sqlite3.Connection,
    *,
    updated_at: str,
    thread_keys: Iterable[str] | None = None,
) -> None:
    _insert_thread_summary_scope(
        conn,
        scope="active",
        include_archived=False,
        updated_at=updated_at,
        thread_keys=thread_keys,
    )
    _insert_thread_summary_scope(
        conn,
        scope="all-history",
        include_archived=True,
        updated_at=updated_at,
        thread_keys=thread_keys,
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
            "CASE WHEN call_count > 0 "
            "THEN coalesce(estimated_cost_usd, 0) / call_count ELSE 0 END"
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
                "coalesce(avg_cache_ratio, 0) >= 0.25 "
                "AND coalesce(avg_cache_ratio, 0) < 0.45"
            ),
            "low": "coalesce(avg_cache_ratio, 0) >= 0.45",
        }
        try:
            clauses.append(risk_clauses[risk.lower()])
        except KeyError as exc:
            raise ValueError("risk must be one of: high, medium, low") from exc
    return "WHERE " + " AND ".join(f"({clause})" for clause in clauses), params


def _insert_thread_summary_scope(
    conn: sqlite3.Connection,
    *,
    scope: str,
    include_archived: bool,
    updated_at: str,
    thread_keys: Iterable[str] | None = None,
) -> None:
    where_clause, params = usage_where_clause(include_archived=include_archived)
    thread_key_expr = thread_key_expression()
    normalized_thread_keys = sorted({key for key in thread_keys or [] if key})
    if normalized_thread_keys:
        placeholders = ", ".join("?" for _key in normalized_thread_keys)
        thread_filter = f"{thread_key_expr} IN ({placeholders})"
        if where_clause:
            where_clause = f"{where_clause} AND ({thread_filter})"
        else:
            where_clause = f"WHERE {thread_filter}"
        params.extend(normalized_thread_keys)
    conn.execute(
        f"""
        INSERT INTO thread_summaries (
            thread_key,
            is_archived_scope,
            thread_label,
            first_event_timestamp,
            latest_event_timestamp,
            call_count,
            session_count,
            input_tokens,
            cached_input_tokens,
            uncached_input_tokens,
            output_tokens,
            reasoning_output_tokens,
            total_tokens,
            estimated_cost_usd,
            usage_credits,
            avg_cache_ratio,
            max_context_window_percent,
            max_recommendation_score,
            primary_recommendation,
            call_initiator_summary,
            archived_call_count,
            updated_at
        )
        SELECT
            {thread_key_expr} AS thread_key,
            ? AS is_archived_scope,
            coalesce(max(thread_name), max(parent_thread_name), max(session_id)) AS thread_label,
            MIN(event_timestamp) AS first_event_timestamp,
            MAX(event_timestamp) AS latest_event_timestamp,
            COUNT(*) AS call_count,
            COUNT(DISTINCT session_id) AS session_count,
            coalesce(SUM(input_tokens), 0) AS input_tokens,
            coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
            coalesce(SUM(output_tokens), 0) AS output_tokens,
            coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
            coalesce(SUM(total_tokens), 0) AS total_tokens,
            NULL AS estimated_cost_usd,
            NULL AS usage_credits,
            coalesce(AVG(cache_ratio), 0) AS avg_cache_ratio,
            coalesce(MAX(context_window_percent), 0) AS max_context_window_percent,
            coalesce(MAX(
                CASE
                    WHEN context_window_percent >= 0.90 THEN 100
                    WHEN cache_ratio < 0.20 AND input_tokens >= 50000 THEN 80
                    WHEN total_tokens >= 100000 THEN 70
                    ELSE 0
                END
            ), 0) AS max_recommendation_score,
            CASE
                WHEN MAX(context_window_percent) >= 0.90 THEN 'high_context_use'
                WHEN MIN(cache_ratio) < 0.20 AND MAX(input_tokens) >= 50000
                    THEN 'low_cache_reuse'
                WHEN MAX(total_tokens) >= 100000 THEN 'large_calls'
                ELSE NULL
            END AS primary_recommendation,
            CASE
                WHEN SUM(
                    CASE WHEN coalesce(call_initiator, 'unknown') = 'codex'
                    THEN 1 ELSE 0 END
                ) > SUM(
                    CASE WHEN coalesce(call_initiator, 'unknown') = 'user'
                    THEN 1 ELSE 0 END
                )
                    THEN 'mostly_codex'
                WHEN SUM(
                    CASE WHEN coalesce(call_initiator, 'unknown') = 'user'
                    THEN 1 ELSE 0 END
                ) > SUM(
                    CASE WHEN coalesce(call_initiator, 'unknown') = 'codex'
                    THEN 1 ELSE 0 END
                )
                    THEN 'mostly_user'
                WHEN SUM(
                    CASE WHEN coalesce(call_initiator, 'unknown') = 'unknown'
                    THEN 1 ELSE 0 END
                ) = COUNT(*)
                    THEN 'unknown'
                ELSE 'mixed'
            END AS call_initiator_summary,
            SUM(CASE WHEN coalesce(is_archived, 0) != 0 THEN 1 ELSE 0 END)
                AS archived_call_count,
            ? AS updated_at
        FROM canonical_usage_events
        {where_clause}
        GROUP BY {thread_key_expr}
        """,
        [scope, updated_at, *params],
    )
