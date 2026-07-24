"""SQLite schema for aggregate OpenTelemetry completion enrichment."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.store.connection import execute_script

MIGRATION_NAMES = {
    30: "persist OTel completion tier enrichment",
    31: "persist OTel cursor continuity anchors",
}

_USAGE_EVENT_TIER_COLUMNS = {
    "service_tier": "TEXT",
    "fast": "INTEGER",
    "service_tier_source": "TEXT",
    "service_tier_confidence": "TEXT",
}


def migrate_otel_completion_tiers(conn: sqlite3.Connection) -> None:
    """Add nullable tier fields plus aggregate-only OTel staging tables."""

    existing_usage_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    for column, column_type in _USAGE_EVENT_TIER_COLUMNS.items():
        if column not in existing_usage_columns:
            conn.execute(  # nosec B608 - fixed migration column names
                f"ALTER TABLE usage_events ADD COLUMN {column} {column_type}"
            )
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS otel_completion_sources (
            source_path TEXT PRIMARY KEY,
            device INTEGER NOT NULL,
            inode INTEGER NOT NULL,
            size INTEGER NOT NULL,
            parsed_offset INTEGER NOT NULL,
            parsed_line INTEGER NOT NULL,
            resume_anchor TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS otel_completion_events (
            fingerprint TEXT PRIMARY KEY,
            conversation_id TEXT,
            event_timestamp TEXT,
            input_tokens INTEGER,
            cached_input_tokens INTEGER,
            output_tokens INTEGER,
            reasoning_output_tokens INTEGER,
            model TEXT,
            effort TEXT,
            service_tier TEXT,
            fast INTEGER,
            service_tier_source TEXT,
            service_tier_confidence TEXT,
            app_version TEXT,
            source_path TEXT NOT NULL,
            source_line INTEGER NOT NULL,
            match_status TEXT NOT NULL CHECK (
                match_status IN ('pending', 'matched', 'ambiguous', 'conflict', 'invalid')
            ),
            matched_record_id TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_otel_completion_match_status
            ON otel_completion_events(match_status);
        CREATE INDEX IF NOT EXISTS idx_otel_completion_identity
            ON otel_completion_events(
                conversation_id,
                input_tokens,
                cached_input_tokens,
                output_tokens,
                reasoning_output_tokens
            );
        """,
    )


def add_otel_cursor_resume_anchor(conn: sqlite3.Connection) -> None:
    """Add a bounded-content continuity marker to existing OTel source cursors."""

    source_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(otel_completion_sources)").fetchall()
    }
    if "resume_anchor" not in source_columns:
        conn.execute("ALTER TABLE otel_completion_sources ADD COLUMN resume_anchor TEXT")
