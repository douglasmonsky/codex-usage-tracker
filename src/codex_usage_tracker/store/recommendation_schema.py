"""SQLite schema objects for materialized recommendation facts."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.store.cache_repository import SQLiteCacheRepository
from codex_usage_tracker.store.connection import execute_script

MIGRATION_NAMES = {
    20: "persist versioned recommendation facts",
    21: "materialize recommendation thread summaries",
    33: "index recommendation facts by active time",
}

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_scope "
    "ON recommendation_facts(is_archived, recommendation_score DESC, "
    "event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_model_effort "
    "ON recommendation_facts(model, effort, is_archived, recommendation_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_thread "
    "ON recommendation_facts(thread_key, recommendation_score DESC, event_timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_thread_latest "
    "ON recommendation_facts(thread_key, event_timestamp DESC, total_tokens DESC, record_id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_time_model "
    "ON recommendation_facts(is_archived, event_timestamp, model)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_time_effort "
    "ON recommendation_facts(is_archived, event_timestamp, effort)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_primary "
    "ON recommendation_facts(primary_recommendation_key, recommendation_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_rank_all "
    "ON recommendation_facts(recommendation_score DESC, total_tokens DESC, "
    "event_timestamp, record_id) "
    "WHERE json_array_length(recommendations_json) > 0",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_rank_active "
    "ON recommendation_facts(recommendation_score DESC, total_tokens DESC, "
    "event_timestamp, record_id) "
    "WHERE is_archived = 0 AND json_array_length(recommendations_json) > 0",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_attention_sort "
    "ON recommendation_facts(recommendation_score DESC, event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_cost_sort "
    "ON recommendation_facts(coalesce(estimated_cost_usd, 0) DESC, "
    "event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_credits_sort "
    "ON recommendation_facts(coalesce(usage_credits, 0) DESC, "
    "event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_context_sort "
    "ON recommendation_facts(context_window_percent DESC, event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_pricing_coverage_scope "
    "ON recommendation_facts((pricing_model IS NOT NULL), pricing_estimated, is_archived, "
    "event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_pricing_estimated_scope "
    "ON recommendation_facts(pricing_estimated, is_archived, event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_credit_confidence_scope "
    "ON recommendation_facts(usage_credit_confidence, is_archived, "
    "event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_record_filter_cover "
    "ON recommendation_facts(record_id, pricing_model, pricing_estimated, "
    "usage_credit_confidence)",
)
_INDEX_DROP_STATEMENTS = tuple(
    statement.replace("CREATE INDEX IF NOT EXISTS ", "DROP INDEX IF EXISTS ").split(" ON ", 1)[0]
    for statement in _INDEX_STATEMENTS
)


def create_recommendation_fact_tables(conn: sqlite3.Connection) -> None:
    """Create versioned aggregate-only recommendation facts and state."""
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS recommendation_facts (
            record_id TEXT PRIMARY KEY,
            event_timestamp TEXT NOT NULL,
            is_archived INTEGER NOT NULL DEFAULT 0,
            thread_key TEXT NOT NULL DEFAULT '',
            model TEXT,
            effort TEXT,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            cumulative_total_tokens INTEGER NOT NULL DEFAULT 0,
            cache_ratio REAL NOT NULL DEFAULT 0,
            context_window_percent REAL NOT NULL DEFAULT 0,
            estimated_cost_usd REAL,
            pricing_model TEXT,
            pricing_estimated INTEGER NOT NULL DEFAULT 0,
            usage_credits REAL,
            usage_credit_confidence TEXT NOT NULL DEFAULT 'unpriced',
            primary_recommendation_key TEXT,
            secondary_recommendation_keys_json TEXT NOT NULL DEFAULT '[]',
            recommendation_score REAL NOT NULL DEFAULT 0,
            recommended_action_key TEXT NOT NULL,
            recommendations_json TEXT NOT NULL DEFAULT '[]',
            facts_version INTEGER NOT NULL,
            algorithm_version INTEGER NOT NULL,
            source_generation INTEGER NOT NULL,
            generation_fingerprint TEXT NOT NULL,
            config_fingerprint TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS recommendation_fact_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            facts_version INTEGER NOT NULL,
            algorithm_version INTEGER NOT NULL,
            source_generation INTEGER NOT NULL,
            generation_fingerprint TEXT NOT NULL,
            config_fingerprint TEXT NOT NULL,
            record_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """,
    )
    create_recommendation_fact_indexes(conn)


def add_recommendation_thread_summaries(conn: sqlite3.Connection) -> None:
    """Extend existing summary/state tables with exact recommendation rollups."""
    summary_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(thread_summaries)").fetchall()
    }
    for name, definition in (
        ("recommendation_score", "REAL NOT NULL DEFAULT 0"),
        ("recommendation_total_tokens", "INTEGER NOT NULL DEFAULT 0"),
        ("recommendation_summary_json", "TEXT"),
    ):
        if name not in summary_columns:
            conn.execute(f"ALTER TABLE thread_summaries ADD COLUMN {name} {definition}")

    state_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(recommendation_fact_state)").fetchall()
    }
    if "thread_summaries_complete" not in state_columns:
        conn.execute(
            """
            ALTER TABLE recommendation_fact_state
            ADD COLUMN thread_summaries_complete INTEGER NOT NULL DEFAULT 0
            """
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_thread_summaries_scope_recommendations
        ON thread_summaries(
            is_archived_scope,
            recommendation_score DESC,
            recommendation_total_tokens DESC,
            thread_key
        )
        """
    )
    create_recommendation_fact_indexes(conn)


def clear_recommendation_fact_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM recommendation_facts")
    conn.execute("DELETE FROM recommendation_fact_state")


def invalidate_recommendation_fact_tables(conn: sqlite3.Connection) -> None:
    """Prevent stale recommendation reads until the next derived-fact refresh."""

    clear_recommendation_fact_tables(conn)
    _reset_thread_recommendation_columns(conn)


def reconcile_recommendation_facts_with_canonical_usage(conn: sqlite3.Connection) -> None:
    """Drop newly noncanonical facts and force safe fact-page summary fallback."""

    conn.execute(
        "DELETE FROM recommendation_facts WHERE record_id NOT IN "
        "(SELECT record_id FROM canonical_usage_events)"
    )
    conn.execute(
        "UPDATE recommendation_fact_state SET record_count="
        "(SELECT COUNT(*) FROM recommendation_facts), thread_summaries_complete=0"
    )
    SQLiteCacheRepository(conn).delete("home_usage_metrics_v1")
    _reset_thread_recommendation_columns(conn)


def _reset_thread_recommendation_columns(conn: sqlite3.Connection) -> None:
    conn.execute(
        "UPDATE thread_summaries SET recommendation_score=0, "
        "recommendation_total_tokens=0, recommendation_summary_json=NULL, "
        "max_recommendation_score=0, primary_recommendation=NULL, "
        "estimated_cost_usd=NULL, usage_credits=NULL"
    )


def create_recommendation_fact_indexes(conn: sqlite3.Connection) -> None:
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)


def drop_recommendation_fact_indexes(conn: sqlite3.Connection) -> None:
    for statement in _INDEX_DROP_STATEMENTS:
        conn.execute(statement)
