"""Store-local synchronization of normalized Codex allowance snapshots."""

from __future__ import annotations

import sqlite3

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


def rebuild_allowance_observations(conn: sqlite3.Connection) -> int:
    """Rebuild normalized allowance rows from canonical usage only."""

    conn.execute("DELETE FROM allowance_observations")
    record_ids = [
        str(row[0])
        for row in conn.execute(
            "SELECT record_id FROM canonical_usage_events WHERE "
            "rate_limit_primary_used_percent IS NOT NULL OR "
            "rate_limit_primary_window_minutes IS NOT NULL OR "
            "rate_limit_primary_resets_at IS NOT NULL OR "
            "rate_limit_secondary_used_percent IS NOT NULL OR "
            "rate_limit_secondary_window_minutes IS NOT NULL OR "
            "rate_limit_secondary_resets_at IS NOT NULL"
        )
    ]
    return sync_allowance_observations_for_record_ids(conn, record_ids)


def sync_allowance_observations_for_record_ids(
    conn: sqlite3.Connection,
    record_ids: list[str],
) -> int:
    """Refresh normalized allowance rows for newly upserted usage records."""

    unique_record_ids = list(dict.fromkeys(record_ids))
    if not unique_record_ids:
        return 0
    has_allowance_source = conn.execute(
        """
        SELECT 1
        FROM canonical_usage_events
        WHERE rate_limit_primary_used_percent IS NOT NULL
           OR rate_limit_primary_window_minutes IS NOT NULL
           OR rate_limit_primary_resets_at IS NOT NULL
           OR rate_limit_secondary_used_percent IS NOT NULL
           OR rate_limit_secondary_window_minutes IS NOT NULL
           OR rate_limit_secondary_resets_at IS NOT NULL
        LIMIT 1
        """
    ).fetchone()
    if has_allowance_source is None:
        has_existing_observation = conn.execute(
            "SELECT 1 FROM allowance_observations LIMIT 1"
        ).fetchone()
        if has_existing_observation is None:
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
        FROM canonical_usage_events
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
