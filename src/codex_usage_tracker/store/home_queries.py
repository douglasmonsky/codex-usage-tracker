"""Narrow, bounded reads for the Evidence Console Home surface."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.cache_repository import SQLiteCacheRepository
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.rows import row_to_dict

_MAX_HOME_FINDINGS = 3
_MAX_HOME_RECENT_EVIDENCE = 5
_HOME_USAGE_METRICS_KEY = "home_usage_metrics_v1"


def query_home_usage_metrics(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Return current active usage totals from canonical persisted facts."""
    with connect(db_path) as conn:
        state = conn.execute(
            """
            SELECT
                recommendation_fact_state.source_generation,
                recommendation_fact_state.record_count,
                compression_source_state.generation AS current_generation
            FROM recommendation_fact_state
            JOIN compression_source_state
                ON compression_source_state.singleton = 1
            WHERE recommendation_fact_state.singleton = 1
            """
        ).fetchone()
        if (
            state is None
            or int(state["source_generation"]) != int(state["current_generation"])
        ):
            return None
        cached = SQLiteCacheRepository(conn).get(_HOME_USAGE_METRICS_KEY)
        if cached is not None:
            try:
                payload = json.loads(cached)
            except json.JSONDecodeError:
                payload = None
            if (
                isinstance(payload, dict)
                and int(payload.get("source_generation") or -1)
                == int(state["source_generation"])
                and int(payload.get("materialized_calls") or -1)
                == int(state["record_count"])
                and payload.get("coverage_basis") == "tokens"
            ):
                return payload
        return persist_home_usage_metrics(
            conn,
            source_generation=int(state["source_generation"]),
            materialized_calls=int(state["record_count"]),
        )


def persist_home_usage_metrics(
    conn: sqlite3.Connection,
    *,
    source_generation: int,
    materialized_calls: int | None = None,
) -> dict[str, Any]:
    """Refresh the constant-size Home totals cache after fact materialization."""
    if materialized_calls is None:
        materialized_calls = int(
            conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[0]
        )
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS calls,
            coalesce(SUM(input_tokens), 0) AS input_tokens,
            coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
            coalesce(SUM(output_tokens), 0) AS output_tokens,
            coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
            coalesce(SUM(total_tokens), 0) AS total_tokens,
            coalesce(SUM(estimated_cost_usd), 0) AS estimated_cost_usd,
            coalesce(SUM(usage_credits), 0) AS usage_credits,
            coalesce(
                SUM(
                    CASE WHEN estimated_cost_usd IS NOT NULL
                         THEN total_tokens ELSE 0 END
                ),
                0
            ) AS priced_tokens,
            coalesce(
                SUM(
                    CASE WHEN usage_credits IS NOT NULL
                         THEN total_tokens ELSE 0 END
                ),
                0
            ) AS credited_tokens
        FROM recommendation_facts NOT INDEXED
        WHERE is_archived = 0
        """
    ).fetchone()
    if row is None:  # pragma: no cover - aggregate SELECT always returns one row
        raise RuntimeError("home usage aggregate returned no row")
    calls = int(row["calls"])
    total_tokens = int(row["total_tokens"])
    tier_row = conn.execute(
        """
        SELECT
            coalesce(
                SUM(
                    CASE WHEN service_tier IS NOT NULL AND trim(service_tier) != ''
                         THEN total_tokens ELSE 0 END
                ),
                0
            ) AS tier_tokens
        FROM usage_events INDEXED BY idx_canonical_usage_archived_timestamp
        WHERE is_archived = 0 AND is_duplicate = 0
        """
    ).fetchone()
    tier_tokens = int(tier_row["tier_tokens"] if tier_row is not None else 0)
    payload = {
        "calls": calls,
        "input_tokens": int(row["input_tokens"]),
        "cached_input_tokens": int(row["cached_input_tokens"]),
        "uncached_input_tokens": int(row["uncached_input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "reasoning_output_tokens": int(row["reasoning_output_tokens"]),
        "total_tokens": total_tokens,
        "estimated_cost_usd": float(row["estimated_cost_usd"]),
        "usage_credits": float(row["usage_credits"]),
        "pricing_coverage": int(row["priced_tokens"]) / total_tokens if total_tokens else 0.0,
        "credit_coverage": int(row["credited_tokens"]) / total_tokens if total_tokens else 0.0,
        "service_tier_coverage": tier_tokens / total_tokens if total_tokens else 0.0,
        "coverage_basis": "tokens",
        "source_generation": source_generation,
        "materialized_calls": materialized_calls,
    }
    SQLiteCacheRepository(conn).set_many(
        {
            _HOME_USAGE_METRICS_KEY: json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            )
        }
    )
    return payload


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
