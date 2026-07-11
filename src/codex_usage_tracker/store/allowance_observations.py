"""Normalized observed Codex allowance snapshots."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.rows import row_to_dict
from codex_usage_tracker.store.schema import init_db

ALLOWANCE_OBSERVATION_COLUMNS = (
    "observation_id",
    "record_id",
    "session_id",
    "event_timestamp",
    "line_number",
    "source",
    "window_key",
    "window_kind",
    "window_minutes",
    "used_percent",
    "remaining_percent",
    "resets_at",
    "plan_type",
    "limit_id",
    "is_archived",
    "model",
    "effort",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "cumulative_total_tokens",
)
ALLOWANCE_SYNC_BATCH_SIZE = 500


def sync_allowance_observations_for_record_ids(
    conn: sqlite3.Connection,
    record_ids: list[str],
) -> int:
    """Refresh normalized allowance rows for newly upserted usage records."""

    unique_record_ids = list(dict.fromkeys(record_ids))
    if not unique_record_ids:
        return 0
    inserted = 0
    for start in range(0, len(unique_record_ids), ALLOWANCE_SYNC_BATCH_SIZE):
        chunk = unique_record_ids[start : start + ALLOWANCE_SYNC_BATCH_SIZE]
        placeholders = ", ".join("?" for _record_id in chunk)
        conn.execute(
            f"DELETE FROM allowance_observations WHERE record_id IN ({placeholders})",
            chunk,
        )
        record_filter = f"AND record_id IN ({placeholders})"
        for window_key in ("primary", "secondary"):
            inserted += conn.execute(
                _insert_observation_sql(window_key, record_filter=record_filter),
                chunk,
            ).rowcount
    return inserted


def query_allowance_observations(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    include_archived: bool = False,
    window_kind: str | None = None,
    limit: int | None = 1000,
) -> list[dict[str, Any]]:
    """Return normalized allowance observations ordered chronologically."""

    with connect(db_path) as conn:
        init_db(conn)
        where: list[str] = []
        params: list[Any] = []
        if not include_archived:
            where.append("is_archived = 0")
        if window_kind:
            where.append("window_kind = ?")
            params.append(window_kind)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = "LIMIT ?"
            params.append(max(int(limit), 0))
        rows = conn.execute(
            f"""
            SELECT {", ".join(ALLOWANCE_OBSERVATION_COLUMNS)}
            FROM allowance_observations
            {where_sql}
            ORDER BY event_timestamp ASC, cumulative_total_tokens ASC, window_key ASC
            {limit_sql}
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def _insert_observation_sql(window_key: str, *, record_filter: str = "") -> str:
    used_col = f"rate_limit_{window_key}_used_percent"
    minutes_col = f"rate_limit_{window_key}_window_minutes"
    resets_col = f"rate_limit_{window_key}_resets_at"
    columns = ", ".join(ALLOWANCE_OBSERVATION_COLUMNS)
    return f"""
        INSERT INTO allowance_observations ({columns})
        SELECT
            record_id || ':{window_key}' AS observation_id,
            record_id,
            session_id,
            event_timestamp,
            line_number,
            'token_count.rate_limits' AS source,
            '{window_key}' AS window_key,
            {_window_kind_sql(minutes_col)} AS window_kind,
            {minutes_col} AS window_minutes,
            {used_col} AS used_percent,
            CASE
                WHEN {used_col} IS NULL THEN NULL
                ELSE 100.0 - {used_col}
            END AS remaining_percent,
            {resets_col} AS resets_at,
            rate_limit_plan_type AS plan_type,
            rate_limit_limit_id AS limit_id,
            is_archived,
            model,
            effort,
            input_tokens,
            cached_input_tokens,
            uncached_input_tokens,
            output_tokens,
            reasoning_output_tokens,
            total_tokens,
            cumulative_total_tokens
        FROM usage_events
        WHERE (
            {used_col} IS NOT NULL
            OR {minutes_col} IS NOT NULL
            OR {resets_col} IS NOT NULL
        )
        {record_filter}
    """


def _window_kind_sql(minutes_col: str) -> str:
    return f"""
        CASE
            WHEN {minutes_col} = 300 THEN 'five_hour'
            WHEN {minutes_col} = 10080 THEN 'weekly'
            WHEN {minutes_col} IS NULL THEN 'unknown'
            ELSE 'custom'
        END
    """
