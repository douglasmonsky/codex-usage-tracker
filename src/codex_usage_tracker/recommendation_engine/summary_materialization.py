"""Incremental materialization for exact recommendation thread summaries."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from typing import Any

_THREAD_KEY_BATCH_SIZE = 400
_RESET_SQL = """
    UPDATE thread_summaries
    SET recommendation_score = 0,
        recommendation_total_tokens = 0,
        recommendation_summary_json = NULL,
        max_recommendation_score = 0,
        primary_recommendation = NULL
"""


def sync_thread_recommendation_summaries(
    conn: sqlite3.Connection,
    *,
    thread_keys: Iterable[str] | None = None,
) -> int:
    """Refresh exact recommendation rollups for all or selected threads."""
    normalized = tuple(sorted({str(key) for key in thread_keys or () if key}))
    initialized = _summaries_are_complete(conn) or _summaries_have_materialized_rows(conn)
    selected = normalized if thread_keys is not None and initialized else None
    before = conn.total_changes
    _reset_summaries(conn, selected)
    for chunk in _thread_key_chunks(selected):
        rows = _aggregate_summaries(conn, chunk)
        signals = _aggregate_signals(conn, chunk)
        _persist_summaries(conn, rows, signals)
    _update_completeness(conn, selected)
    return conn.total_changes - before


def _reset_summaries(
    conn: sqlite3.Connection,
    thread_keys: tuple[str, ...] | None,
) -> None:
    if thread_keys is None:
        conn.execute(_RESET_SQL)
        return
    if not thread_keys:
        return
    placeholders = ", ".join("?" for _ in thread_keys)
    conn.execute(
        f"{_RESET_SQL} WHERE thread_key IN ({placeholders})",  # nosec B608
        thread_keys,
    )


def _thread_key_chunks(
    thread_keys: tuple[str, ...] | None,
) -> Iterable[tuple[str, ...] | None]:
    if thread_keys is None:
        yield None
        return
    for start in range(0, len(thread_keys), _THREAD_KEY_BATCH_SIZE):
        yield thread_keys[start : start + _THREAD_KEY_BATCH_SIZE]


def _aggregate_summaries(
    conn: sqlite3.Connection,
    thread_keys: tuple[str, ...] | None,
) -> list[sqlite3.Row]:
    filter_sql, params = _thread_filter("rf.thread_key", thread_keys)
    return conn.execute(
        f"""
        WITH scopes(scope, include_archived) AS (
            VALUES ('active', 0), ('all-history', 1)
        ),
        scoped AS (
            SELECT s.scope, rf.thread_key, rf.record_id, rf.event_timestamp,
                rf.total_tokens, rf.estimated_cost_usd, rf.usage_credits,
                rf.recommendation_score, rf.recommendations_json,
                rf.primary_recommendation_key, usage_events.session_id
            FROM recommendation_facts AS rf
            JOIN usage_events USING(record_id)
            JOIN scopes AS s ON s.include_archived = 1 OR rf.is_archived = 0
            WHERE json_array_length(rf.recommendations_json) > 0
            {filter_sql}
        ),
        ranked AS (
            SELECT scoped.*,
                row_number() OVER (
                    PARTITION BY scope, thread_key
                    ORDER BY recommendation_score DESC, total_tokens DESC,
                        event_timestamp ASC, record_id ASC
                ) AS recommendation_rank
            FROM scoped
        ),
        aggregate_rows AS (
            SELECT scope, thread_key,
                count(*) AS call_count,
                count(DISTINCT session_id) AS session_count,
                sum(total_tokens) AS total_tokens,
                sum(coalesce(estimated_cost_usd, 0)) AS estimated_cost_usd,
                sum(coalesce(usage_credits, 0)) AS usage_credits,
                sum(recommendation_score) AS recommendation_score,
                max(recommendation_score) AS max_recommendation_score,
                max(event_timestamp) AS latest_event
            FROM scoped
            GROUP BY scope, thread_key
        )
        SELECT aggregate_rows.*, ranked.recommendations_json,
            ranked.primary_recommendation_key
        FROM aggregate_rows
        JOIN ranked USING(scope, thread_key)
        WHERE ranked.recommendation_rank = 1
        """,  # nosec B608 - only generated placeholders; values remain bound
        params,
    ).fetchall()


def _aggregate_signals(
    conn: sqlite3.Connection,
    thread_keys: tuple[str, ...] | None,
) -> dict[tuple[str, str], set[str]]:
    filter_sql, params = _thread_filter("rf.thread_key", thread_keys)
    rows = conn.execute(
        f"""
        WITH scopes(scope, include_archived) AS (
            VALUES ('active', 0), ('all-history', 1)
        ),
        scoped AS (
            SELECT s.scope, rf.thread_key, rf.primary_recommendation_key,
                rf.secondary_recommendation_keys_json
            FROM recommendation_facts AS rf
            JOIN scopes AS s ON s.include_archived = 1 OR rf.is_archived = 0
            WHERE json_array_length(rf.recommendations_json) > 0
            {filter_sql}
        ),
        signals AS (
            SELECT scope, thread_key, primary_recommendation_key AS signal FROM scoped
            UNION
            SELECT scope, thread_key, json_each.value AS signal
            FROM scoped, json_each(scoped.secondary_recommendation_keys_json)
        )
        SELECT scope, thread_key, signal
        FROM signals
        WHERE signal IS NOT NULL AND signal != ''
        """,  # nosec B608 - only generated placeholders; values remain bound
        params,
    ).fetchall()
    result: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        result.setdefault((str(row["scope"]), str(row["thread_key"])), set()).add(
            str(row["signal"])
        )
    return result


def _persist_summaries(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    signals: dict[tuple[str, str], set[str]],
) -> None:
    updates = []
    for row in rows:
        key = (str(row["scope"]), str(row["thread_key"]))
        recommendations = json.loads(str(row["recommendations_json"]))
        primary = recommendations[0] if recommendations else None
        primary_key = primary.get("key") if isinstance(primary, dict) else None
        summary: dict[str, Any] = {
            "thread": _thread_label(key[1]),
            "call_count": int(row["call_count"]),
            "session_count": int(row["session_count"]),
            "total_tokens": int(row["total_tokens"]),
            "estimated_cost_usd": round(float(row["estimated_cost_usd"]), 6),
            "usage_credits": round(float(row["usage_credits"]), 6),
            "recommendation_score": round(float(row["recommendation_score"]), 2),
            "max_recommendation_score": round(float(row["max_recommendation_score"]), 2),
            "primary_recommendation": primary,
            "secondary_signals": sorted(
                signal for signal in signals.get(key, set()) if signal != primary_key
            ),
            "latest_event": row["latest_event"],
        }
        updates.append(
            (
                summary["recommendation_score"],
                summary["total_tokens"],
                json.dumps(summary, separators=(",", ":"), sort_keys=True),
                summary["max_recommendation_score"],
                primary_key,
                key[1],
                key[0],
            )
        )
    conn.executemany(
        """
        UPDATE thread_summaries
        SET recommendation_score = ?, recommendation_total_tokens = ?,
            recommendation_summary_json = ?, max_recommendation_score = ?,
            primary_recommendation = ?
        WHERE thread_key = ? AND is_archived_scope = ?
        """,
        updates,
    )


def _update_completeness(
    conn: sqlite3.Connection,
    thread_keys: tuple[str, ...] | None,
) -> None:
    current_row = conn.execute(
        "SELECT thread_summaries_complete FROM recommendation_fact_state WHERE singleton = 1"
    ).fetchone()
    current = bool(current_row and current_row[0])
    check_keys = thread_keys if current and thread_keys is not None else None
    filter_sql, params = _thread_filter("rf.thread_key", check_keys)
    noncanonical = conn.execute(
        f"""
        SELECT 1
        FROM recommendation_facts AS rf
        JOIN usage_events USING(record_id)
        WHERE json_array_length(rf.recommendations_json) > 0
            AND (
                nullif(usage_events.thread_name, '') IS NULL
                OR rf.thread_key != 'thread:' || usage_events.thread_name
            )
        {filter_sql}
        LIMIT 1
        """,  # nosec B608 - only generated placeholders; values remain bound
        params,
    ).fetchone()
    complete = noncanonical is None if check_keys is None else current and noncanonical is None
    conn.execute(
        """
        UPDATE recommendation_fact_state
        SET thread_summaries_complete = ?
        WHERE singleton = 1
        """,
        (int(complete),),
    )


def _thread_filter(
    column: str,
    thread_keys: tuple[str, ...] | None,
) -> tuple[str, list[str]]:
    if thread_keys is None:
        return "", []
    if not thread_keys:
        return "AND 0", []
    placeholders = ", ".join("?" for _ in thread_keys)
    return f"AND {column} IN ({placeholders})", list(thread_keys)


def _summaries_are_complete(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT thread_summaries_complete FROM recommendation_fact_state WHERE singleton = 1"
    ).fetchone()
    return bool(row and row[0])


def _summaries_have_materialized_rows(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM thread_summaries
        WHERE recommendation_summary_json IS NOT NULL
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _thread_label(thread_key: str) -> str:
    if thread_key.startswith("thread:"):
        return thread_key.removeprefix("thread:")
    return thread_key.removeprefix("session:")
