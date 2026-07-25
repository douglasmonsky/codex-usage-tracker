"""Narrow, bounded reads for the Evidence Console Home surface."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.core.usage_identity import FINGERPRINT_VERSION
from codex_usage_tracker.store.cache_repository import SQLiteCacheRepository
from codex_usage_tracker.store.connection import connect_read_only

_HOME_USAGE_METRICS_KEY = "home_usage_metrics_v1"
_HOME_DEDUPE_STATUS_KEY = "home_dedupe_status_v1"


def query_home_refresh_metadata(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, str]:
    """Return committed refresh metadata without schema initialization."""
    if not db_path.exists():
        return {}
    with connect_read_only(db_path, timeout=1.0) as conn:
        try:
            rows = conn.execute("SELECT key, value FROM refresh_meta").fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            rows = []
    return {str(row["key"]): str(row["value"]) for row in rows}


def _empty_home_status_counts() -> dict[str, Any]:
    return {
        "dedupe_enabled": True,
        "fingerprint_version": FINGERPRINT_VERSION,
        "total_rows": 0,
        "active_rows": 0,
        "total_max_event_timestamp": None,
        "active_max_event_timestamp": None,
        "physical_rows": 0,
        "canonical_rows": 0,
        "excluded_copied_rows": 0,
        "duplicate_fingerprint_groups": 0,
        "physical_total_tokens": 0,
        "canonical_total_tokens": 0,
        "excluded_total_tokens": 0,
        "duplicate_reasons": {},
    }


def query_home_status_counts(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """Return exact Home row counts from compact maintained summaries."""
    if not db_path.exists():
        return _empty_home_status_counts()
    with connect_read_only(db_path, timeout=1.0) as conn:
        row = conn.execute(
            """
            SELECT
                coalesce(SUM(
                    CASE WHEN is_archived_scope = 'all-history' THEN call_count ELSE 0 END
                ), 0) AS total_rows,
                coalesce(SUM(
                    CASE WHEN is_archived_scope = 'active' THEN call_count ELSE 0 END
                ), 0) AS active_rows,
                MAX(
                    CASE WHEN is_archived_scope = 'all-history'
                         THEN latest_event_timestamp END
                ) AS total_max_event_timestamp,
                MAX(
                    CASE WHEN is_archived_scope = 'active'
                         THEN latest_event_timestamp END
                ) AS active_max_event_timestamp,
                coalesce(SUM(
                    CASE WHEN is_archived_scope = 'all-history' THEN total_tokens ELSE 0 END
                ), 0) AS canonical_total_tokens,
                (SELECT generation
                 FROM compression_source_state
                 WHERE singleton = 1) AS source_generation
            FROM thread_summaries
            """
        ).fetchone()
        duplicate_row = conn.execute(
            """
            SELECT COUNT(*) AS excluded_copied_rows
            FROM usage_events INDEXED BY idx_usage_duplicate_reason
            WHERE is_duplicate = 1
            """
        ).fetchone()
        cached_dedupe = SQLiteCacheRepository(conn).get(_HOME_DEDUPE_STATUS_KEY)
    total_rows = int(row["total_rows"] if row is not None else 0)
    active_rows = int(row["active_rows"] if row is not None else 0)
    excluded = int(duplicate_row["excluded_copied_rows"] if duplicate_row is not None else 0)
    canonical_total_tokens = int(row["canonical_total_tokens"] if row is not None else 0)
    source_generation = int((row["source_generation"] if row is not None else 0) or 0)
    dedupe_snapshot = _cached_dedupe_status(
        cached_dedupe,
        source_generation=source_generation,
    )
    excluded_total_tokens = int(dedupe_snapshot.get("excluded_total_tokens") or 0)
    return {
        "dedupe_enabled": True,
        "fingerprint_version": FINGERPRINT_VERSION,
        "total_rows": total_rows,
        "active_rows": active_rows,
        "total_max_event_timestamp": (
            row["total_max_event_timestamp"] if row is not None else None
        ),
        "active_max_event_timestamp": (
            row["active_max_event_timestamp"] if row is not None else None
        ),
        "physical_rows": total_rows + excluded,
        "canonical_rows": total_rows,
        "excluded_copied_rows": excluded,
        "duplicate_fingerprint_groups": int(
            dedupe_snapshot.get("duplicate_fingerprint_groups") or 0
        ),
        "physical_total_tokens": canonical_total_tokens + excluded_total_tokens,
        "canonical_total_tokens": canonical_total_tokens,
        "excluded_total_tokens": excluded_total_tokens,
        "duplicate_reasons": dict(dedupe_snapshot.get("duplicate_reasons") or {}),
    }


def _cached_dedupe_status(
    cached: str | None,
    *,
    source_generation: int,
) -> dict[str, Any]:
    if cached is None:
        return {}
    try:
        payload = json.loads(cached)
    except json.JSONDecodeError:
        return {}
    if (
        not isinstance(payload, dict)
        or int(payload.get("source_generation") or -1) != source_generation
    ):
        return {}
    return payload


def query_home_usage_metrics(
    db_path: Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """Return current active usage totals without waiting for recommendations."""
    if not db_path.exists():
        return None
    with connect_read_only(db_path, timeout=1.0) as conn:
        state = conn.execute(
            """
            SELECT
                recommendation_fact_state.source_generation,
                recommendation_fact_state.record_count,
                compression_source_state.generation AS current_generation
            FROM compression_source_state
            LEFT JOIN recommendation_fact_state
                ON recommendation_fact_state.singleton = 1
            WHERE compression_source_state.singleton = 1
            """
        ).fetchone()
        if state is None:
            return None
        current_generation = int(state["current_generation"])
        recommendation_generation = state["source_generation"]
        if (
            recommendation_generation is not None
            and int(recommendation_generation) == current_generation
        ):
            cached = SQLiteCacheRepository(conn).get(_HOME_USAGE_METRICS_KEY)
            if cached is not None:
                try:
                    payload = json.loads(cached)
                except json.JSONDecodeError:
                    payload = None
                if (
                    isinstance(payload, dict)
                    and int(payload.get("source_generation") or -1) == current_generation
                    and int(payload.get("materialized_calls") or -1) == int(state["record_count"])
                    and payload.get("coverage_basis") == "tokens"
                ):
                    return payload
            return _thread_summary_usage_metrics(
                conn,
                source_generation=current_generation,
                materialized_calls=int(state["record_count"] or 0),
            )
        return _thread_summary_usage_metrics(
            conn,
            source_generation=current_generation,
            materialized_calls=int(state["record_count"] or 0),
        )


def _thread_summary_usage_metrics(
    conn: sqlite3.Connection,
    *,
    source_generation: int,
    materialized_calls: int,
) -> dict[str, Any]:
    """Build exact token totals from the incrementally maintained active summaries."""
    row = conn.execute(
        """
        SELECT
            coalesce(SUM(call_count), 0) AS calls,
            coalesce(SUM(input_tokens), 0) AS input_tokens,
            coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
            coalesce(SUM(output_tokens), 0) AS output_tokens,
            coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
            coalesce(SUM(total_tokens), 0) AS total_tokens
        FROM thread_summaries
        WHERE is_archived_scope = 'active'
        """
    ).fetchone()
    if row is None:  # pragma: no cover - aggregate SELECT always returns one row
        raise RuntimeError("home thread summary aggregate returned no row")
    calls = int(row["calls"])
    return {
        "calls": calls,
        "input_tokens": int(row["input_tokens"]),
        "cached_input_tokens": int(row["cached_input_tokens"]),
        "uncached_input_tokens": int(row["uncached_input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "reasoning_output_tokens": int(row["reasoning_output_tokens"]),
        "total_tokens": int(row["total_tokens"]),
        "estimated_cost_usd": 0.0,
        "usage_credits": 0.0,
        "pricing_coverage": 0.0,
        "credit_coverage": 0.0,
        "service_tier_coverage": 0.0,
        "coverage_basis": "tokens",
        "source_generation": source_generation,
        "materialized_calls": materialized_calls,
    }


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
    dedupe_payload = _materialized_dedupe_status(
        conn,
        source_generation=source_generation,
    )
    SQLiteCacheRepository(conn).set_many(
        {
            _HOME_USAGE_METRICS_KEY: json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ),
            _HOME_DEDUPE_STATUS_KEY: json.dumps(
                dedupe_payload,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
    )
    return payload


def _materialized_dedupe_status(
    conn: sqlite3.Connection,
    *,
    source_generation: int,
) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS excluded_copied_rows,
            COUNT(DISTINCT usage_fingerprint) AS duplicate_fingerprint_groups,
            coalesce(SUM(total_tokens), 0) AS excluded_total_tokens
        FROM usage_events INDEXED BY idx_usage_duplicate_reason
        WHERE is_duplicate = 1
        """
    ).fetchone()
    reasons = {
        str(reason_row["duplicate_reason"]): int(reason_row["row_count"])
        for reason_row in conn.execute(
            """
            SELECT duplicate_reason, COUNT(*) AS row_count
            FROM usage_events INDEXED BY idx_usage_duplicate_reason
            WHERE is_duplicate = 1 AND duplicate_reason IS NOT NULL
            GROUP BY duplicate_reason
            ORDER BY duplicate_reason
            """
        )
    }
    return {
        "source_generation": source_generation,
        "excluded_copied_rows": int(row["excluded_copied_rows"] if row is not None else 0),
        "duplicate_fingerprint_groups": int(
            row["duplicate_fingerprint_groups"] if row is not None else 0
        ),
        "excluded_total_tokens": int(row["excluded_total_tokens"] if row is not None else 0),
        "duplicate_reasons": reasons,
    }
