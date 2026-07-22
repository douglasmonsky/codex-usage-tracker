"""Narrow, bounded reads for the Evidence Console Home surface."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.rows import row_to_dict

_MAX_HOME_FINDINGS = 3
_MAX_HOME_RECENT_EVIDENCE = 5


def query_home_finding_rows(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    min_score: float = 80,
    limit: int = _MAX_HOME_FINDINGS,
) -> list[dict[str, Any]]:
    """Return only the persisted fields needed for bounded Home findings."""
    bounded_limit = _bounded_limit(limit, maximum=_MAX_HOME_FINDINGS)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                usage_events.record_id,
                rf.primary_recommendation_key AS fact_primary_recommendation_key,
                rf.recommendations_json AS fact_recommendations_json
            FROM recommendation_facts AS rf
            JOIN canonical_usage_events AS usage_events
                ON usage_events.record_id = rf.record_id
            WHERE usage_events.is_archived = 0
                AND rf.is_archived = 0
                AND rf.recommendation_score >= ?
                AND json_array_length(rf.recommendations_json) > 0
            ORDER BY
                rf.recommendation_score DESC,
                rf.total_tokens DESC,
                rf.event_timestamp ASC,
                rf.record_id ASC
            LIMIT ?
            """,
            (float(min_score), bounded_limit),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def query_home_recent_evidence_rows(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    limit: int = _MAX_HOME_RECENT_EVIDENCE,
) -> list[dict[str, Any]]:
    """Return a safe-column projection for the most recent active canonical calls."""
    bounded_limit = _bounded_limit(limit, maximum=_MAX_HOME_RECENT_EVIDENCE)
    with connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                record_id,
                event_timestamp,
                thread_name,
                session_id,
                model,
                total_tokens
            FROM canonical_usage_events
            WHERE is_archived = 0
            ORDER BY event_timestamp DESC, cumulative_total_tokens DESC, record_id ASC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def _bounded_limit(value: int, *, maximum: int) -> int:
    try:
        return min(max(int(value), 0), maximum)
    except (TypeError, ValueError):
        return maximum
