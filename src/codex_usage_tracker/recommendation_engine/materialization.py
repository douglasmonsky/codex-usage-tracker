"""Incremental materialization of aggregate recommendation facts."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
    DEFAULT_THRESHOLDS_PATH,
)
from codex_usage_tracker.recommendation_engine.fact_config import (
    RECOMMENDATION_ALGORITHM_VERSION,
    RECOMMENDATION_FACTS_VERSION,
    RecommendationFactConfig,
    annotate_rows_for_recommendation_facts,
    load_recommendation_fact_config,
    recommendation_generation_fingerprint,
)
from codex_usage_tracker.recommendation_engine.summary_materialization import (
    sync_thread_recommendation_summaries,
)
from codex_usage_tracker.store.compression_schema import read_compression_source_generation
from codex_usage_tracker.store.recommendation_schema import (
    create_recommendation_fact_indexes,
    drop_recommendation_fact_indexes,
)
from codex_usage_tracker.store.rows import row_to_dict

_FACT_BATCH_SIZE = 1_000


def backfill_recommendation_facts(
    conn: sqlite3.Connection,
    *,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
) -> int:
    """Rebuild all recommendation facts from normalized SQLite rows only."""
    config = load_recommendation_fact_config(
        pricing_path=pricing_path,
        allowance_path=allowance_path,
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
    )
    generation = _generation(conn, config)
    drop_recommendation_fact_indexes(conn)
    try:
        conn.execute("DELETE FROM recommendation_facts")
        cursor = conn.execute("SELECT * FROM usage_events ORDER BY record_id")
        count = _insert_cursor_facts(conn, cursor, config=config, generation=generation)
    finally:
        create_recommendation_fact_indexes(conn)
    _stamp_state(conn, config=config, generation=generation)
    sync_thread_recommendation_summaries(conn)
    return count


def sync_recommendation_facts(
    conn: sqlite3.Connection,
    *,
    record_ids: Iterable[str],
    thread_keys: Iterable[str] | None = None,
) -> int:
    """Replace facts only for changed normalized usage records."""
    targets = tuple(dict.fromkeys(str(record_id) for record_id in record_ids if record_id))
    config = load_recommendation_fact_config()
    generation = _generation(conn, config)
    _populate_targets(conn, targets)
    affected_thread_keys = {
        str(row[0])
        for row in conn.execute(
            """
            SELECT thread_key FROM recommendation_facts
            WHERE record_id IN (SELECT record_id FROM recommendation_fact_targets)
            UNION
            SELECT thread_key FROM usage_events
            WHERE record_id IN (SELECT record_id FROM recommendation_fact_targets)
            """
        ).fetchall()
        if row[0]
    }
    affected_thread_keys.update(str(key) for key in thread_keys or () if key)
    conn.execute(
        """
        DELETE FROM recommendation_facts
        WHERE record_id IN (SELECT record_id FROM recommendation_fact_targets)
        """
    )
    cursor = conn.execute(
        """
        SELECT usage_events.*
        FROM usage_events
        JOIN recommendation_fact_targets USING(record_id)
        ORDER BY usage_events.record_id
        """
    )
    count = _insert_cursor_facts(conn, cursor, config=config, generation=generation)
    _stamp_state(conn, config=config, generation=generation)
    sync_thread_recommendation_summaries(conn, thread_keys=affected_thread_keys)
    return count


def sync_refresh_recommendation_facts(
    conn: sqlite3.Connection,
    record_ids: tuple[str, ...],
    thread_keys: frozenset[str],
    full_rebuild: bool,
) -> None:
    if full_rebuild:
        backfill_recommendation_facts(conn)
    else:
        sync_recommendation_facts(
            conn,
            record_ids=record_ids,
            thread_keys=thread_keys,
        )


def _generation(
    conn: sqlite3.Connection,
    config: RecommendationFactConfig,
) -> tuple[int, str, str]:
    source_generation = read_compression_source_generation(conn)
    fingerprint = recommendation_generation_fingerprint(
        source_generation=source_generation,
        config_fingerprint=config.fingerprint,
    )
    updated_at = datetime.now(timezone.utc).isoformat()
    return source_generation, fingerprint, updated_at


def _populate_targets(conn: sqlite3.Connection, record_ids: tuple[str, ...]) -> None:
    conn.execute(
        "CREATE TEMP TABLE IF NOT EXISTS recommendation_fact_targets (record_id TEXT PRIMARY KEY)"
    )
    conn.execute("DELETE FROM recommendation_fact_targets")
    conn.executemany(
        "INSERT OR IGNORE INTO recommendation_fact_targets(record_id) VALUES (?)",
        ((record_id,) for record_id in record_ids),
    )


def _insert_cursor_facts(
    conn: sqlite3.Connection,
    cursor: sqlite3.Cursor,
    *,
    config: RecommendationFactConfig,
    generation: tuple[int, str, str],
) -> int:
    inserted = 0
    while rows := cursor.fetchmany(_FACT_BATCH_SIZE):
        facts = list(_fact_rows(rows, config=config, generation=generation))
        conn.executemany(_FACT_INSERT_SQL, facts)
        inserted += len(facts)
    return inserted


def _fact_rows(
    rows: list[sqlite3.Row],
    *,
    config: RecommendationFactConfig,
    generation: tuple[int, str, str],
) -> Iterator[tuple[Any, ...]]:
    source_generation, generation_fingerprint, updated_at = generation
    values = [row_to_dict(row) for row in rows]
    values = annotate_rows_for_recommendation_facts(values, config)
    for row in values:
        recommendations = row["action_recommendations"]
        yield (
            row["record_id"],
            row["event_timestamp"],
            int(row.get("is_archived") or 0),
            str(row.get("thread_key") or ""),
            row.get("model"),
            row.get("effort"),
            _integer(row.get("input_tokens")),
            _integer(row.get("cached_input_tokens")),
            _integer(row.get("uncached_input_tokens")),
            _integer(row.get("output_tokens")),
            _integer(row.get("reasoning_output_tokens")),
            _integer(row.get("total_tokens")),
            _integer(row.get("cumulative_total_tokens")),
            _number(row.get("cache_ratio")),
            _number(row.get("context_window_percent")),
            row.get("estimated_cost_usd"),
            row.get("pricing_model"),
            int(bool(row.get("pricing_estimated"))),
            row.get("usage_credits"),
            str(row.get("usage_credit_confidence") or "unpriced"),
            row.get("primary_signal"),
            _json(row.get("secondary_signals") or []),
            _number(row.get("recommendation_score")),
            row["recommended_action_key"],
            _json(recommendations),
            RECOMMENDATION_FACTS_VERSION,
            RECOMMENDATION_ALGORITHM_VERSION,
            source_generation,
            generation_fingerprint,
            config.fingerprint,
            updated_at,
        )


def _stamp_state(
    conn: sqlite3.Connection,
    *,
    config: RecommendationFactConfig,
    generation: tuple[int, str, str],
) -> None:
    source_generation, generation_fingerprint, updated_at = generation
    count = int(conn.execute("SELECT COUNT(*) FROM recommendation_facts").fetchone()[0])
    conn.execute(
        """
        INSERT INTO recommendation_fact_state (
            singleton, facts_version, algorithm_version, source_generation,
            generation_fingerprint, config_fingerprint, record_count, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(singleton) DO UPDATE SET
            facts_version = excluded.facts_version,
            algorithm_version = excluded.algorithm_version,
            source_generation = excluded.source_generation,
            generation_fingerprint = excluded.generation_fingerprint,
            config_fingerprint = excluded.config_fingerprint,
            record_count = excluded.record_count,
            updated_at = excluded.updated_at
        """,
        (
            RECOMMENDATION_FACTS_VERSION,
            RECOMMENDATION_ALGORITHM_VERSION,
            source_generation,
            generation_fingerprint,
            config.fingerprint,
            count,
            updated_at,
        ),
    )


def _integer(value: Any) -> int:
    return int(value or 0)


def _number(value: Any) -> float:
    return float(value or 0)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)


_FACT_INSERT_SQL = """
    INSERT INTO recommendation_facts (
        record_id, event_timestamp, is_archived, thread_key, model, effort,
        input_tokens, cached_input_tokens, uncached_input_tokens, output_tokens,
        reasoning_output_tokens, total_tokens, cumulative_total_tokens, cache_ratio,
        context_window_percent, estimated_cost_usd, pricing_model, pricing_estimated,
        usage_credits, usage_credit_confidence, primary_recommendation_key,
        secondary_recommendation_keys_json, recommendation_score,
        recommended_action_key, recommendations_json, facts_version,
        algorithm_version, source_generation, generation_fingerprint,
        config_fingerprint, updated_at
    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
"""
