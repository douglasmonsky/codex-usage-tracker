"""SQLite schema initialization and migrations for the aggregate usage store."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

import codex_usage_tracker.store.allowance_schema as allowance_schema
import codex_usage_tracker.store.compression_schema as compression_schema
import codex_usage_tracker.store.deduplication_schema as deduplication_schema
import codex_usage_tracker.store.recommendation_schema as recommendation_schema
import codex_usage_tracker.store.schema_query_indexes as schema_query_indexes
from codex_usage_tracker.core.schema import (
    USAGE_EVENT_COLUMN_NAMES,
    USAGE_EVENT_CREATE_COLUMNS_SQL,
    USAGE_EVENT_REPAIR_COLUMNS,
    USAGE_EVENT_SCHEMA_CHECKSUM,
)

SCHEMA_VERSION = 29
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
    11: "normalize observed allowance history",
    12: "persist source record provenance",
    13: "create normalized content index tables",
    14: "persist investigation run summaries",
    **compression_schema.MIGRATION_NAMES,
    **recommendation_schema.MIGRATION_NAMES,
    **schema_query_indexes.MIGRATION_NAMES,
    **deduplication_schema.MIGRATION_NAMES,
    **allowance_schema.MIGRATION_NAMES,
}
CALL_ORIGIN_REPAIR_COLUMNS: dict[str, str] = dict.fromkeys(
    ("call_initiator", "call_initiator_reason", "call_initiator_confidence"), "TEXT"
)
DASHBOARD_HELPER_REPAIR_COLUMNS = {
    "is_archived": "INTEGER NOT NULL DEFAULT 0",
    "thread_call_index": "INTEGER",
} | dict.fromkeys(("thread_key", "previous_record_id", "next_record_id"), "TEXT")
REQUIRED_USAGE_EVENT_COLUMNS = list(USAGE_EVENT_COLUMN_NAMES)


class SchemaMigrationError(RuntimeError):
    """Raised when a persisted aggregate schema cannot be repaired safely."""


def init_db(conn: sqlite3.Connection) -> None:
    """Create or repair the aggregate usage schema in-place."""

    user_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if _schema_is_current(conn, user_version):
        _validate_usage_events_schema(conn)
        return
    _ensure_migrations_table(conn)
    for version, migrate in _schema_migrations():
        _apply_schema_migration(
            conn,
            user_version=user_version,
            version=version,
            migrate=migrate,
        )
    _validate_usage_events_schema(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _schema_is_current(conn: sqlite3.Connection, user_version: int) -> bool:
    if user_version != SCHEMA_VERSION:
        return False
    migrations_table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if migrations_table is None:
        return False
    recorded_versions = {
        int(row[0]) for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    return all(version in recorded_versions for version, _ in _schema_migrations())


def _schema_migrations() -> tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...]:
    return (
        (1, _migrate_v1),
        (2, _migrate_v2),
        (3, _migrate_v3),
        (4, _migrate_v4),
        (5, _migrate_v5),
        (6, _migrate_v6),
        (7, _migrate_v7),
        (8, _migrate_v8),
        (9, _migrate_v9),
        (10, _migrate_v10),
        (11, _migrate_v11),
        (12, _migrate_v12),
        (13, _migrate_v13),
        (14, _migrate_v14),
        *compression_schema.schema_migrations(),
        (18, schema_query_indexes.migrate_source_file_line_index),
        (19, compression_schema.add_candidate_record_metadata),
        (20, recommendation_schema.create_recommendation_fact_tables),
        (21, recommendation_schema.add_recommendation_thread_summaries),
        (22, schema_query_indexes.add_diagnostic_lookup_index),
        (23, schema_query_indexes.add_diagnostic_aggregate_index),
        (24, deduplication_schema.migrate_usage_deduplication),
        (25, deduplication_schema.migrate_clone_rewritten_usage),
        (26, deduplication_schema.migrate_canonical_query_indexes),
        (27, allowance_schema.migrate_allowance_intelligence_v2),
        (28, allowance_schema.migrate_allowance_query_indexes_v3),
        (29, allowance_schema.add_allowance_plan_provenance),
    )


def _apply_schema_migration(
    conn: sqlite3.Connection,
    *,
    user_version: int,
    version: int,
    migrate: Callable[[sqlite3.Connection], None],
) -> None:
    recorded = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ?", (version,)
    ).fetchone()
    if user_version < version or recorded is None:
        migrate(conn)
        _record_migration(conn, version)
        return


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


def _migrate_v11(conn: sqlite3.Connection) -> None:
    _create_allowance_observations_table(conn)
    _backfill_allowance_observations(conn)


def _migrate_v12(conn: sqlite3.Connection) -> None:
    _create_source_records_table(conn)
    _backfill_source_records(conn)


def _migrate_v13(conn: sqlite3.Connection) -> None:
    _create_content_index_tables(conn)


def _migrate_v14(conn: sqlite3.Connection) -> None:
    from codex_usage_tracker.store.investigation_runs import create_investigation_run_tables

    create_investigation_run_tables(conn)


def _create_content_index_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS content_index_features (
            feature_key TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            detail TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_turns (
            turn_key TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn_id TEXT,
            turn_index INTEGER,
            role TEXT NOT NULL,
            event_timestamp TEXT,
            source_record_hash TEXT,
            source_file_id TEXT,
            line_start INTEGER,
            line_end INTEGER,
            content_hash TEXT,
            content_size_bytes INTEGER NOT NULL DEFAULT 0,
            indexed_content_included INTEGER NOT NULL DEFAULT 0,
            parser_adapter TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            parse_warnings_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_conversation_turns_record
        ON conversation_turns(record_id);

        CREATE INDEX IF NOT EXISTS idx_conversation_turns_session_time
        ON conversation_turns(session_id, event_timestamp);

        CREATE TABLE IF NOT EXISTS tool_calls (
            tool_call_key TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            turn_key TEXT,
            tool_name TEXT NOT NULL,
            call_id TEXT,
            status TEXT,
            started_at TEXT,
            ended_at TEXT,
            duration_ms INTEGER,
            argument_shape TEXT NOT NULL DEFAULT '',
            output_size_bytes INTEGER NOT NULL DEFAULT 0,
            source_file_id TEXT,
            line_start INTEGER,
            line_end INTEGER,
            parser_adapter TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            parse_warnings_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE,
            FOREIGN KEY(turn_key) REFERENCES conversation_turns(turn_key) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_tool_calls_record
        ON tool_calls(record_id);

        CREATE INDEX IF NOT EXISTS idx_tool_calls_tool_status
        ON tool_calls(tool_name, status);

        CREATE TABLE IF NOT EXISTS command_runs (
            command_run_key TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            turn_key TEXT,
            command_root TEXT NOT NULL,
            command_label TEXT NOT NULL DEFAULT '',
            exit_code INTEGER,
            status TEXT,
            duration_ms INTEGER,
            output_size_bytes INTEGER NOT NULL DEFAULT 0,
            failure_category TEXT,
            retry_group TEXT,
            source_file_id TEXT,
            line_start INTEGER,
            line_end INTEGER,
            parser_adapter TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            parse_warnings_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE,
            FOREIGN KEY(turn_key) REFERENCES conversation_turns(turn_key) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_command_runs_record
        ON command_runs(record_id);

        CREATE INDEX IF NOT EXISTS idx_command_runs_root_status
        ON command_runs(command_root, status);

        CREATE TABLE IF NOT EXISTS file_events (
            file_event_key TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            turn_key TEXT,
            operation TEXT NOT NULL,
            path_hash TEXT NOT NULL,
            path_basename TEXT NOT NULL DEFAULT '',
            path_extension TEXT NOT NULL DEFAULT '',
            path_identity TEXT NOT NULL DEFAULT '',
            source_file_id TEXT,
            line_start INTEGER,
            line_end INTEGER,
            parser_adapter TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            parse_warnings_json TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE,
            FOREIGN KEY(turn_key) REFERENCES conversation_turns(turn_key) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_file_events_record
        ON file_events(record_id);

        CREATE INDEX IF NOT EXISTS idx_file_events_operation_path
        ON file_events(operation, path_hash);

        CREATE TABLE IF NOT EXISTS content_fragments (
            fragment_rowid INTEGER PRIMARY KEY,
            fragment_id TEXT NOT NULL UNIQUE,
            record_id TEXT NOT NULL,
            turn_key TEXT,
            fragment_kind TEXT NOT NULL,
            role TEXT,
            safe_label TEXT NOT NULL DEFAULT '',
            content_hash TEXT NOT NULL,
            content_size_bytes INTEGER NOT NULL DEFAULT 0,
            fragment_text TEXT NOT NULL DEFAULT '',
            includes_raw_fragment INTEGER NOT NULL DEFAULT 0,
            source_file_id TEXT,
            line_start INTEGER,
            line_end INTEGER,
            token_link_record_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE,
            FOREIGN KEY(turn_key) REFERENCES conversation_turns(turn_key) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_content_fragments_record
        ON content_fragments(record_id);

        CREATE INDEX IF NOT EXISTS idx_content_fragments_kind_role
        ON content_fragments(fragment_kind, role);
        """
    )
    _create_content_fts_table(conn)


def _create_content_fts_table(conn: sqlite3.Connection) -> None:
    updated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS content_fts
            USING fts5(
                fragment_text,
                safe_label,
                fragment_kind,
                content='content_fragments',
                content_rowid='fragment_rowid'
            )
            """
        )
    except sqlite3.OperationalError as exc:
        conn.execute(
            """
            INSERT INTO content_index_features (feature_key, enabled, detail, updated_at)
            VALUES ('fts5', 0, ?, ?)
            ON CONFLICT(feature_key) DO UPDATE SET
                enabled = excluded.enabled,
                detail = excluded.detail,
                updated_at = excluded.updated_at
            """,
            (str(exc), updated_at),
        )
        return
    conn.execute(
        """
        INSERT INTO content_index_features (feature_key, enabled, detail, updated_at)
        VALUES ('fts5', 1, 'content_fts available', ?)
        ON CONFLICT(feature_key) DO UPDATE SET
            enabled = excluded.enabled,
            detail = excluded.detail,
            updated_at = excluded.updated_at
        """,
        (updated_at,),
    )


def _create_source_records_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_records (
            record_id TEXT PRIMARY KEY,
            source_file_id TEXT NOT NULL,
            source_file_hash TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            event_timestamp TEXT NOT NULL,
            source_record_hash TEXT NOT NULL,
            hash_basis TEXT NOT NULL DEFAULT 'source_file_id:line_number:record_id',
            raw_shape_label TEXT NOT NULL DEFAULT 'token_count',
            parser_adapter TEXT NOT NULL,
            parser_version TEXT NOT NULL,
            parse_warnings_json TEXT NOT NULL DEFAULT '[]',
            created_from TEXT NOT NULL DEFAULT 'usage_events',
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_source_records_source_line
        ON source_records(source_file_id, line_number);

        CREATE INDEX IF NOT EXISTS idx_source_records_shape_adapter
        ON source_records(raw_shape_label, parser_adapter, parser_version);

        CREATE INDEX IF NOT EXISTS idx_source_records_event_timestamp
        ON source_records(event_timestamp);
        """
    )


def _backfill_source_records(conn: sqlite3.Connection) -> None:
    if not _source_record_backfill_columns_available(conn):
        return
    from codex_usage_tracker.store.source_records import sync_source_records

    sync_source_records(conn)


def _source_record_backfill_columns_available(conn: sqlite3.Connection) -> bool:
    existing = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    required = {"record_id", "source_file", "line_number", "event_timestamp"}
    return required.issubset(existing)


def _create_allowance_observations_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS allowance_observations (
            observation_id TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            event_timestamp TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            source TEXT NOT NULL,
            window_key TEXT NOT NULL,
            window_kind TEXT NOT NULL,
            window_minutes INTEGER,
            used_percent REAL,
            remaining_percent REAL,
            resets_at INTEGER,
            plan_type TEXT,
            limit_id TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0,
            model TEXT,
            effort TEXT,
            input_tokens INTEGER NOT NULL DEFAULT 0,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            cumulative_total_tokens INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_allowance_observations_window_time
        ON allowance_observations(window_kind, event_timestamp);

        CREATE INDEX IF NOT EXISTS idx_allowance_observations_record
        ON allowance_observations(record_id);

        CREATE INDEX IF NOT EXISTS idx_allowance_observations_limit_window_time
        ON allowance_observations(limit_id, window_kind, event_timestamp);
        """
    )


def _backfill_allowance_observations(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM allowance_observations")
    _backfill_allowance_observation_window(conn, "primary")
    _backfill_allowance_observation_window(conn, "secondary")


def _backfill_allowance_observation_window(conn: sqlite3.Connection, window_key: str) -> None:
    used_col = f"rate_limit_{window_key}_used_percent"
    minutes_col = f"rate_limit_{window_key}_window_minutes"
    resets_col = f"rate_limit_{window_key}_resets_at"
    conn.execute(
        f"""
        INSERT INTO allowance_observations (
            observation_id,
            record_id,
            session_id,
            event_timestamp,
            line_number,
            source,
            window_key,
            window_kind,
            window_minutes,
            used_percent,
            remaining_percent,
            resets_at,
            plan_type,
            limit_id,
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
        )
        SELECT
            record_id || ':{window_key}',
            record_id,
            session_id,
            event_timestamp,
            line_number,
            'token_count.rate_limits',
            '{window_key}',
            CASE
                WHEN {minutes_col} = 300 THEN 'five_hour'
                WHEN {minutes_col} = 10080 THEN 'weekly'
                WHEN {minutes_col} IS NULL THEN 'unknown'
                ELSE 'custom'
            END,
            {minutes_col},
            {used_col},
            CASE
                WHEN {used_col} IS NULL THEN NULL
                ELSE 100.0 - {used_col}
            END,
            {resets_col},
            rate_limit_plan_type,
            rate_limit_limit_id,
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
        FROM usage_events
        WHERE {used_col} IS NOT NULL
            OR {minutes_col} IS NOT NULL
            OR {resets_col} IS NOT NULL
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


def _ensure_columns(conn: sqlite3.Connection, columns: dict[str, str]) -> None:
    _ensure_table_columns(conn, "usage_events", columns)


def _ensure_table_columns(
    conn: sqlite3.Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    existing = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})")}
    for column, column_type in columns.items():
        if column not in existing:
            try:
                conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column} {column_type}")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise


def _validate_usage_events_schema(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(usage_events)").fetchall()
    existing = {str(row["name"]) for row in rows}
    missing = [column for column in REQUIRED_USAGE_EVENT_COLUMNS if column not in existing]
    if missing:
        missing_text = ", ".join(missing)
        raise SchemaMigrationError(
            "usage_events schema is missing required columns: "
            f"{missing_text}. Run codex-usage-tracker rebuild-index after confirming your "
            "local aggregate index can be regenerated; raw Codex logs are not touched by "
            "rebuild-index."
        )
