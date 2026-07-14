"""SQLite schema objects for materialized recommendation facts."""

from __future__ import annotations

import sqlite3

MIGRATION_NAMES = {20: "persist versioned recommendation facts"}

_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_scope "
    "ON recommendation_facts(is_archived, recommendation_score DESC, "
    "event_timestamp DESC, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_model_effort "
    "ON recommendation_facts(model, effort, is_archived, recommendation_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_thread "
    "ON recommendation_facts(thread_key, recommendation_score DESC, event_timestamp DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendation_facts_primary "
    "ON recommendation_facts(primary_recommendation_key, recommendation_score DESC)",
)
_INDEX_DROP_STATEMENTS = tuple(
    statement.replace("CREATE INDEX IF NOT EXISTS ", "DROP INDEX IF EXISTS ").split(" ON ", 1)[0]
    for statement in _INDEX_STATEMENTS
)


def create_recommendation_fact_tables(conn: sqlite3.Connection) -> None:
    """Create versioned aggregate-only recommendation facts and state."""
    conn.executescript(
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
        """
    )
    create_recommendation_fact_indexes(conn)


def clear_recommendation_fact_tables(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM recommendation_facts")
    conn.execute("DELETE FROM recommendation_fact_state")


def create_recommendation_fact_indexes(conn: sqlite3.Connection) -> None:
    for statement in _INDEX_STATEMENTS:
        conn.execute(statement)


def drop_recommendation_fact_indexes(conn: sqlite3.Connection) -> None:
    for statement in _INDEX_DROP_STATEMENTS:
        conn.execute(statement)
