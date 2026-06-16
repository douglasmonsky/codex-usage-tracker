"""Materialized thread-summary maintenance for the usage store."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone

from codex_usage_tracker.store_query_sql import (
    _thread_key_expression,
    _usage_where_clause,
)


def rebuild_thread_summaries(
    conn: sqlite3.Connection,
    *,
    thread_keys: Iterable[str] | None = None,
) -> int:
    """Rebuild materialized per-thread aggregate summaries."""

    before = conn.total_changes
    normalized_thread_keys = sorted({key for key in thread_keys or [] if key})
    if thread_keys is None:
        conn.execute("DELETE FROM thread_summaries")
    elif not normalized_thread_keys:
        return 0
    else:
        placeholders = ", ".join("?" for _key in normalized_thread_keys)
        conn.execute(
            f"DELETE FROM thread_summaries WHERE thread_key IN ({placeholders})",
            normalized_thread_keys,
        )
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _insert_thread_summary_scope(
        conn,
        scope="active",
        include_archived=False,
        updated_at=updated_at,
        thread_keys=normalized_thread_keys if thread_keys is not None else None,
    )
    _insert_thread_summary_scope(
        conn,
        scope="all-history",
        include_archived=True,
        updated_at=updated_at,
        thread_keys=normalized_thread_keys if thread_keys is not None else None,
    )
    return conn.total_changes - before


def _insert_thread_summary_scope(
    conn: sqlite3.Connection,
    *,
    scope: str,
    include_archived: bool,
    updated_at: str,
    thread_keys: list[str] | None = None,
) -> None:
    where_clause, params = _usage_where_clause(include_archived=include_archived)
    thread_key_expr = _thread_key_expression()
    clauses: list[str] = []
    if where_clause:
        clauses.append(where_clause.removeprefix("WHERE "))
    if thread_keys is not None:
        placeholders = ", ".join("?" for _key in thread_keys)
        clauses.append(f"{thread_key_expr} IN ({placeholders})")
        params = [*params, *thread_keys]
    scoped_where_clause = "WHERE " + " AND ".join(f"({clause})" for clause in clauses)
    if not clauses:
        scoped_where_clause = ""
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
        FROM usage_events
        {scoped_where_clause}
        GROUP BY {thread_key_expr}
        """,
        [scope, updated_at, *params],
    )
