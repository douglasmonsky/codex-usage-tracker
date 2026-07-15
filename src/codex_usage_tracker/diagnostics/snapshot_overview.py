"""Stored and computed diagnostic overview payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.diagnostics.snapshot_constants import DIAGNOSTIC_OVERVIEW_SECTION
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    history_scope as history_scope_label,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    int_value,
    missing_payload,
    snapshot_metadata,
)
from codex_usage_tracker.store.api import connect, query_diagnostic_snapshot
from codex_usage_tracker.store.schema import init_db


def diagnostic_overview_payload(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the latest persisted overview snapshot without recomputing it."""

    history_scope = history_scope_label(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
    )
    if stored is None:
        return missing_payload(history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload


def _compute_overview(
    *,
    db_path: Path,
    include_archived: bool,
) -> tuple[dict[str, Any], int]:
    usage_where = "" if include_archived else "WHERE is_archived = 0"
    source_where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        usage_query = f"""
            SELECT
                COUNT(*) AS usage_rows,
                COUNT(DISTINCT session_id) AS session_count,
                COUNT(DISTINCT thread_key) AS thread_count,
                COUNT(DISTINCT model) AS model_count,
                MIN(event_timestamp) AS first_event_timestamp,
                MAX(event_timestamp) AS latest_event_timestamp,
                coalesce(SUM(input_tokens), 0) AS input_tokens,
                coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                coalesce(SUM(output_tokens), 0) AS output_tokens,
                coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                coalesce(SUM(total_tokens), 0) AS total_tokens,
                AVG(cache_ratio) AS avg_cache_ratio
            FROM canonical_usage_events
            {usage_where}
            """  # nosec B608
        usage_row = conn.execute(usage_query).fetchone()
        facts_query = f"""
            SELECT COUNT(*) AS diagnostic_fact_rows
            FROM call_diagnostic_facts AS facts
            JOIN canonical_usage_events AS usage_events ON usage_events.record_id = facts.record_id
            {usage_where}
            """  # nosec B608
        facts_row = conn.execute(facts_query).fetchone()
        source_row = conn.execute(
            f"SELECT COUNT(*) AS source_logs_scanned FROM source_files {source_where}"  # nosec B608
        ).fetchone()
    input_tokens = int_value(usage_row["input_tokens"])
    cached_input_tokens = int_value(usage_row["cached_input_tokens"])
    overview = {
        "usage_rows": int_value(usage_row["usage_rows"]),
        "session_count": int_value(usage_row["session_count"]),
        "thread_count": int_value(usage_row["thread_count"]),
        "model_count": int_value(usage_row["model_count"]),
        "first_event_timestamp": usage_row["first_event_timestamp"],
        "latest_event_timestamp": usage_row["latest_event_timestamp"],
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": int_value(usage_row["uncached_input_tokens"]),
        "output_tokens": int_value(usage_row["output_tokens"]),
        "reasoning_output_tokens": int_value(usage_row["reasoning_output_tokens"]),
        "total_tokens": int_value(usage_row["total_tokens"]),
        "cache_ratio": cached_input_tokens / input_tokens if input_tokens else 0.0,
        "avg_call_cache_ratio": float(usage_row["avg_cache_ratio"] or 0),
        "diagnostic_fact_rows": int_value(facts_row["diagnostic_fact_rows"]),
    }
    return overview, int_value(source_row["source_logs_scanned"])
