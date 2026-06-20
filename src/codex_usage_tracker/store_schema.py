"""SQLite schema initialization and migrations for the aggregate usage store."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from codex_usage_tracker.schema import (
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_CREATE_COLUMNS_SQL,
    USAGE_EVENT_REPAIR_COLUMNS,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)

SCHEMA_VERSION = 10
MIGRATION_NAMES = {
    1: "create usage_events aggregate fact table",
    2: "track schema migration checksum metadata",
    3: "persist aggregate call-origin metadata",
    4: "persist dashboard query helper fields",
    5: "materialize thread summaries",
    6: "track source file refresh metadata",
    7: "persist source file parser cursors",
    8: "persist observed Codex usage snapshots",
    9: "persist aggregate diagnostic facts",
    10: "persist on-demand diagnostic report snapshots",
}
CALL_ORIGIN_REPAIR_COLUMNS = {
    "call_initiator": "TEXT",
    "call_initiator_reason": "TEXT",
    "call_initiator_confidence": "TEXT",
}
DASHBOARD_HELPER_REPAIR_COLUMNS = {
    "is_archived": "INTEGER NOT NULL DEFAULT 0",
    "thread_key": "TEXT",
    "thread_call_index": "INTEGER",
    "previous_record_id": "TEXT",
    "next_record_id": "TEXT",
}
REQUIRED_USAGE_EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)


class SchemaMigrationError(RuntimeError):
    """Raised when a persisted aggregate schema cannot be repaired safely."""


def init_db(conn: sqlite3.Connection) -> None:
    """Create or repair the aggregate usage schema in-place."""

    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    _ensure_migrations_table(conn)
    if user_version < 1:
        _migrate_v1(conn)
        _record_migration(conn, 1)
    else:
        _migrate_v1(conn)
        _record_migration_if_missing(conn, 1)
    if user_version < 2:
        _migrate_v2(conn)
        _record_migration(conn, 2)
    else:
        _migrate_v2(conn)
        _record_migration_if_missing(conn, 2)
    if user_version < 3:
        _migrate_v3(conn)
        _record_migration(conn, 3)
    else:
        _migrate_v3(conn)
        _record_migration_if_missing(conn, 3)
    if user_version < 4:
        _migrate_v4(conn)
        _record_migration(conn, 4)
    else:
        _migrate_v4(conn)
        _record_migration_if_missing(conn, 4)
    if user_version < 5:
        _migrate_v5(conn)
        _record_migration(conn, 5)
    else:
        _migrate_v5(conn)
        _record_migration_if_missing(conn, 5)
    if user_version < 6:
        _migrate_v6(conn)
        _record_migration(conn, 6)
    else:
        _migrate_v6(conn)
        _record_migration_if_missing(conn, 6)
    if user_version < 7:
        _migrate_v7(conn)
        _record_migration(conn, 7)
    else:
        _migrate_v7(conn)
        _record_migration_if_missing(conn, 7)
    if user_version < 8:
        _migrate_v8(conn)
        _record_migration(conn, 8)
    else:
        _migrate_v8(conn)
        _record_migration_if_missing(conn, 8)
    if user_version < 9:
        _migrate_v9(conn)
        _record_migration(conn, 9)
    else:
        _migrate_v9(conn)
        _record_migration_if_missing(conn, 9)
    if user_version < 10:
        _migrate_v10(conn)
        _record_migration(conn, 10)
    else:
        _migrate_v10(conn)
        _record_migration_if_missing(conn, 10)
    _validate_usage_events_schema(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def _migrate_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS usage_events (
            {USAGE_EVENT_CREATE_COLUMNS_SQL}
        );

        CREATE TABLE IF NOT EXISTS refresh_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    _ensure_columns(conn, USAGE_EVENT_REPAIR_COLUMNS)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_session ON usage_events(session_id);
        CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_events(event_timestamp);
        CREATE INDEX IF NOT EXISTS idx_usage_model_effort ON usage_events(model, effort);
        CREATE INDEX IF NOT EXISTS idx_usage_thread ON usage_events(thread_name);
        CREATE INDEX IF NOT EXISTS idx_usage_parent_thread ON usage_events(parent_thread_name);
        CREATE INDEX IF NOT EXISTS idx_usage_parent_session ON usage_events(parent_session_id);
        CREATE INDEX IF NOT EXISTS idx_usage_total_tokens ON usage_events(total_tokens);
        """
    )


def _migrate_v2(conn: sqlite3.Connection) -> None:
    _ensure_migrations_table(conn)


def _migrate_v3(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, CALL_ORIGIN_REPAIR_COLUMNS)


def _migrate_v4(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, DASHBOARD_HELPER_REPAIR_COLUMNS)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_archived_timestamp
            ON usage_events(is_archived, event_timestamp);
        CREATE INDEX IF NOT EXISTS idx_usage_archived_model_effort
            ON usage_events(is_archived, model, effort);
        CREATE INDEX IF NOT EXISTS idx_usage_thread_key_timestamp
            ON usage_events(thread_key, event_timestamp, cumulative_total_tokens);
        """
    )


def _migrate_v5(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS thread_summaries (
            thread_key TEXT NOT NULL,
            is_archived_scope TEXT NOT NULL,
            thread_label TEXT,
            first_event_timestamp TEXT,
            latest_event_timestamp TEXT,
            call_count INTEGER NOT NULL DEFAULT 0,
            session_count INTEGER NOT NULL DEFAULT 0,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL,
            usage_credits REAL,
            avg_cache_ratio REAL NOT NULL DEFAULT 0,
            max_context_window_percent REAL NOT NULL DEFAULT 0,
            max_recommendation_score REAL,
            primary_recommendation TEXT,
            call_initiator_summary TEXT,
            archived_call_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (thread_key, is_archived_scope)
        );

        CREATE INDEX IF NOT EXISTS idx_thread_summaries_scope_tokens
            ON thread_summaries(is_archived_scope, total_tokens);
        CREATE INDEX IF NOT EXISTS idx_thread_summaries_scope_latest
            ON thread_summaries(is_archived_scope, latest_event_timestamp);
        """
    )


def _migrate_v6(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_files (
            source_file_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL UNIQUE,
            source_file_hash TEXT NOT NULL,
            is_archived INTEGER NOT NULL DEFAULT 0,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            mtime_ns INTEGER NOT NULL DEFAULT 0,
            parsed_until_line INTEGER NOT NULL DEFAULT 0,
            parsed_until_byte INTEGER NOT NULL DEFAULT 0,
            latest_record_id TEXT,
            latest_event_timestamp TEXT,
            parser_adapter TEXT NOT NULL,
            parser_diagnostics_json TEXT NOT NULL DEFAULT '{}',
            last_indexed_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_source_files_archived
            ON source_files(is_archived);
        CREATE INDEX IF NOT EXISTS idx_source_files_mtime
            ON source_files(mtime_ns, size_bytes);
        """
    )


def _migrate_v7(conn: sqlite3.Connection) -> None:
    _ensure_table_columns(
        conn,
        "source_files",
        {"parser_state_json": "TEXT NOT NULL DEFAULT ''"},
    )


def _migrate_v8(conn: sqlite3.Connection) -> None:
    _ensure_columns(conn, USAGE_EVENT_REPAIR_COLUMNS)
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_usage_observed_rate_limit_timestamp
            ON usage_events(event_timestamp)
            WHERE rate_limit_primary_used_percent IS NOT NULL
               OR rate_limit_secondary_used_percent IS NOT NULL;
        """
    )


def _migrate_v9(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS call_diagnostic_facts (
            record_id TEXT NOT NULL,
            fact_type TEXT NOT NULL,
            fact_name TEXT NOT NULL,
            fact_category TEXT,
            event_count INTEGER NOT NULL DEFAULT 1,
            confidence TEXT NOT NULL DEFAULT 'medium',
            first_event_timestamp TEXT,
            last_event_timestamp TEXT,
            first_source_line INTEGER,
            last_source_line INTEGER,
            evidence_scope TEXT NOT NULL DEFAULT 'between_token_counts',
            raw_content_included INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (record_id, fact_type, fact_name),
            FOREIGN KEY (record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_call_diagnostic_facts_type_name
            ON call_diagnostic_facts(fact_type, fact_name);
        CREATE INDEX IF NOT EXISTS idx_call_diagnostic_facts_record
            ON call_diagnostic_facts(record_id);
        """
    )


def _migrate_v10(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS diagnostic_snapshots (
            section TEXT NOT NULL,
            history_scope TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            computed_at TEXT NOT NULL,
            source_logs_scanned INTEGER NOT NULL DEFAULT 0,
            usage_rows_scanned INTEGER NOT NULL DEFAULT 0,
            raw_content_included INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (section, history_scope)
        );

        CREATE INDEX IF NOT EXISTS idx_diagnostic_snapshots_computed_at
            ON diagnostic_snapshots(computed_at);
        """
    )


def _record_migration(conn: sqlite3.Connection, version: int) -> None:
    conn.execute(
        """
        INSERT INTO schema_migrations (version, name, checksum, applied_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(version) DO UPDATE SET
            name = excluded.name,
            checksum = excluded.checksum
        """,
        (
            version,
            MIGRATION_NAMES[version],
            USAGE_EVENT_SCHEMA_CHECKSUM,
            datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        ),
    )


def _record_migration_if_missing(conn: sqlite3.Connection, version: int) -> None:
    exists = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?",
        (version,),
    ).fetchone()
    if exists is None:
        _record_migration(conn, version)


def _ensure_columns(conn: sqlite3.Connection, columns: dict[str, str]) -> None:
    _ensure_table_columns(conn, "usage_events", columns)


def _ensure_table_columns(
    conn: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    for column, column_type in columns.items():
        if column not in existing:
            try:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise


def _validate_usage_events_schema(conn: sqlite3.Connection) -> None:
    existing = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    missing = [column for column in REQUIRED_USAGE_EVENT_COLUMNS if column not in existing]
    if missing:
        missing_text = ", ".join(missing)
        raise SchemaMigrationError(
            "usage_events schema is missing required columns: "
            f"{missing_text}. Run codex-usage-tracker rebuild-index after confirming your "
            "local aggregate index can be regenerated; raw Codex logs are not touched by "
            "rebuild-index."
        )
