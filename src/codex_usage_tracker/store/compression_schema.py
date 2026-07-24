"""Schema objects owned by the Compression Lab repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

from codex_usage_tracker.store.connection import execute_script

MIGRATION_NAMES = {
    15: "persist compression analysis runs",
    16: "persist compression detector facts",
    17: "persist compression revision state",
    19: "snapshot compression candidate evidence metadata",
}


def schema_migrations() -> tuple[tuple[int, Callable[[sqlite3.Connection], None]], ...]:
    """Return schema migrations owned by the compression domain."""
    return (
        (15, create_compression_run_tables),
        (16, create_compression_fact_tables),
        (17, create_compression_revision_tables),
    )


_COMPRESSION_FACT_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_compression_record_facts_scope "
    "ON compression_record_facts(is_archived, event_timestamp, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_compression_record_facts_thread "
    "ON compression_record_facts(thread_key, thread_call_index, event_timestamp, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_compression_sequence_facts_scope "
    "ON compression_sequence_facts(fact_kind, thread_key, record_id, fact_key)",
    "CREATE INDEX IF NOT EXISTS idx_compression_sequence_facts_category "
    "ON compression_sequence_facts(fact_kind, category, thread_key, record_id)",
    "CREATE INDEX IF NOT EXISTS idx_compression_thread_facts_activity "
    "ON compression_thread_facts(last_event_at DESC, manifest_key)",
)
_COMPRESSION_FACT_INDEX_DROP_STATEMENTS = (
    "DROP INDEX IF EXISTS idx_compression_record_facts_scope",
    "DROP INDEX IF EXISTS idx_compression_record_facts_thread",
    "DROP INDEX IF EXISTS idx_compression_sequence_facts_scope",
    "DROP INDEX IF EXISTS idx_compression_sequence_facts_category",
    "DROP INDEX IF EXISTS idx_compression_thread_facts_activity",
)


def create_compression_fact_tables(conn: sqlite3.Connection) -> None:
    """Create detector-ready record, sequence, and thread fact tables."""
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS compression_record_facts (
            record_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            session_id TEXT NOT NULL,
            thread_key TEXT NOT NULL DEFAULT '',
            event_timestamp TEXT NOT NULL,
            model TEXT,
            effort TEXT,
            is_archived INTEGER NOT NULL DEFAULT 0,
            thread_call_index INTEGER,
            previous_record_id TEXT,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL,
            usage_credits REAL,
            cache_ratio REAL NOT NULL DEFAULT 0,
            context_window_percent REAL NOT NULL DEFAULT 0,
            turn_count INTEGER NOT NULL DEFAULT 0,
            indexed_call INTEGER NOT NULL DEFAULT 0,
            tool_call_count INTEGER NOT NULL DEFAULT 0,
            command_run_count INTEGER NOT NULL DEFAULT 0,
            file_event_count INTEGER NOT NULL DEFAULT 0,
            content_fragment_count INTEGER NOT NULL DEFAULT 0,
            compaction_count INTEGER NOT NULL DEFAULT 0,
            source_record_count INTEGER NOT NULL DEFAULT 0,
            parser_warning_record_count INTEGER NOT NULL DEFAULT 0,
            parser_adapter TEXT,
            parser_version TEXT,
            content_exposure_tokens INTEGER NOT NULL DEFAULT 0,
            tool_output_exposure_tokens INTEGER NOT NULL DEFAULT 0,
            manifest_count INTEGER NOT NULL DEFAULT 0,
            manifest_sum_hex TEXT NOT NULL DEFAULT '',
            manifest_xor_hex TEXT NOT NULL DEFAULT '',
            facts_version INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS compression_sequence_facts (
            fact_key TEXT PRIMARY KEY,
            record_id TEXT NOT NULL,
            thread_key TEXT NOT NULL DEFAULT '',
            turn_key TEXT,
            source_order INTEGER NOT NULL,
            fact_kind TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT,
            duration_ms INTEGER,
            output_size_bytes INTEGER NOT NULL DEFAULT 0,
            command_label TEXT,
            exit_code INTEGER,
            retry_group TEXT,
            path_identity TEXT,
            exposure_tokens INTEGER NOT NULL DEFAULT 0,
            facts_version INTEGER NOT NULL,
            FOREIGN KEY(record_id) REFERENCES usage_events(record_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS compression_thread_facts (
            manifest_key TEXT PRIMARY KEY,
            thread_key TEXT NOT NULL DEFAULT '',
            record_id TEXT NOT NULL DEFAULT '',
            call_count INTEGER NOT NULL DEFAULT 0,
            first_event_at TEXT,
            last_event_at TEXT,
            cached_input_tokens INTEGER NOT NULL DEFAULT 0,
            uncached_input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            reasoning_output_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd REAL,
            usage_credits REAL,
            cache_break_count INTEGER NOT NULL DEFAULT 0,
            manifest_count INTEGER NOT NULL DEFAULT 0,
            manifest_sum_hex TEXT NOT NULL DEFAULT '',
            manifest_xor_hex TEXT NOT NULL DEFAULT '',
            manifest_revision TEXT NOT NULL DEFAULT '',
            facts_version INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS compression_fact_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            facts_version INTEGER NOT NULL,
            source_generation INTEGER NOT NULL,
            record_count INTEGER NOT NULL DEFAULT 0,
            sequence_count INTEGER NOT NULL DEFAULT 0,
            thread_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """,
    )
    create_compression_fact_indexes(conn)


def create_compression_fact_indexes(conn: sqlite3.Connection) -> None:
    """Create secondary indexes used by detector-ready fact queries."""
    for statement in _COMPRESSION_FACT_INDEX_STATEMENTS:
        conn.execute(statement)


def drop_compression_fact_indexes(conn: sqlite3.Connection) -> None:
    """Drop secondary fact indexes before an explicit full rebuild."""
    for statement in _COMPRESSION_FACT_INDEX_DROP_STATEMENTS:
        conn.execute(statement)


def create_compression_run_tables(conn: sqlite3.Connection) -> None:
    """Create persistent run, candidate, and component-claim tables."""
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS compression_runs (
            run_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            source_revision TEXT NOT NULL,
            scope_hash TEXT NOT NULL,
            detector_set_version TEXT NOT NULL,
            estimator_version TEXT NOT NULL,
            compression_schema_version INTEGER NOT NULL,
            scope_json TEXT NOT NULL,
            filters_json TEXT NOT NULL DEFAULT '{}',
            coverage_json TEXT NOT NULL DEFAULT '{}',
            progress_percent REAL NOT NULL DEFAULT 0,
            stage TEXT NOT NULL DEFAULT 'pending',
            current_detector TEXT,
            completed_detectors INTEGER NOT NULL DEFAULT 0,
            total_detectors INTEGER NOT NULL DEFAULT 0,
            records_examined INTEGER NOT NULL DEFAULT 0,
            candidate_count INTEGER NOT NULL DEFAULT 0,
            cache_reused INTEGER NOT NULL DEFAULT 0,
            timing_json TEXT NOT NULL DEFAULT '{}',
            error_summary_json TEXT NOT NULL DEFAULT '{}',
            aggregate_profile_json TEXT NOT NULL DEFAULT '{}',
            public_profile_json TEXT NOT NULL DEFAULT '{}',
            source_generation INTEGER NOT NULL DEFAULT 0,
            revision_key TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            last_accessed_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_compression_runs_cache_lookup
        ON compression_runs(
            source_revision,
            scope_hash,
            detector_set_version,
            estimator_version,
            compression_schema_version,
            status,
            completed_at DESC
        );

        CREATE INDEX IF NOT EXISTS idx_compression_runs_last_accessed
        ON compression_runs(last_accessed_at);

        CREATE TABLE IF NOT EXISTS compression_candidates (
            candidate_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            family TEXT NOT NULL,
            pattern TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            rank INTEGER NOT NULL,
            confidence_grade TEXT NOT NULL,
            confidence_score REAL NOT NULL,
            observation_count INTEGER NOT NULL,
            observed_exposure_tokens INTEGER NOT NULL,
            observed_exposure_json TEXT NOT NULL,
            gross_low INTEGER NOT NULL,
            gross_likely INTEGER NOT NULL,
            gross_high INTEGER NOT NULL,
            adjusted_low INTEGER NOT NULL,
            adjusted_likely INTEGER NOT NULL,
            adjusted_high INTEGER NOT NULL,
            detector_version TEXT NOT NULL,
            estimator_version TEXT NOT NULL,
            estimator_tier TEXT NOT NULL,
            estimator_name TEXT NOT NULL,
            confidence_reasons_json TEXT NOT NULL,
            estimator_assumptions_json TEXT NOT NULL,
            evidence_handles_json TEXT NOT NULL,
            intervention_json TEXT NOT NULL,
            verification_json TEXT NOT NULL,
            warnings_json TEXT NOT NULL,
            overlaps_json TEXT NOT NULL,
            thread_keys_json TEXT NOT NULL,
            first_seen TEXT,
            last_seen TEXT,
            FOREIGN KEY(run_id) REFERENCES compression_runs(run_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_compression_candidates_run_rank
        ON compression_candidates(run_id, rank, candidate_id);

        CREATE INDEX IF NOT EXISTS idx_compression_candidates_run_family_savings
        ON compression_candidates(run_id, family, adjusted_likely DESC);

        CREATE INDEX IF NOT EXISTS idx_compression_candidates_run_confidence
        ON compression_candidates(run_id, confidence_grade, confidence_score DESC);

        CREATE TABLE IF NOT EXISTS compression_candidate_records (
            candidate_id TEXT NOT NULL,
            record_id TEXT NOT NULL,
            component TEXT NOT NULL,
            exposure_tokens INTEGER NOT NULL,
            estimate_low INTEGER NOT NULL,
            estimate_likely INTEGER NOT NULL,
            estimate_high INTEGER NOT NULL,
            evidence_role TEXT NOT NULL,
            trace_handle_json TEXT NOT NULL,
            model TEXT,
            thread_key TEXT,
            event_timestamp TEXT,
            PRIMARY KEY(candidate_id, record_id, component),
            FOREIGN KEY(candidate_id)
                REFERENCES compression_candidates(candidate_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS compression_source_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            generation INTEGER NOT NULL
        );

        INSERT OR IGNORE INTO compression_source_state(singleton, generation)
        VALUES (1, 0);
        """,
    )


def create_compression_revision_tables(conn: sqlite3.Connection) -> None:
    """Create bounded source checkpoints and detector dependency revisions."""
    source_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(source_files)").fetchall()
    }
    source_additions = {
        "parsed_prefix_tail_hash": "TEXT NOT NULL DEFAULT ''",
        "parsed_row_count": "INTEGER NOT NULL DEFAULT 0",
        "source_generation": "INTEGER NOT NULL DEFAULT 0",
        "source_device": "INTEGER NOT NULL DEFAULT 0",
        "source_inode": "INTEGER NOT NULL DEFAULT 0",
    }
    for column, definition in source_additions.items():
        if column not in source_columns:
            conn.execute(f"ALTER TABLE source_files ADD COLUMN {column} {definition}")

    run_columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(compression_runs)").fetchall()
    }
    if "revision_key" not in run_columns:
        conn.execute(
            "ALTER TABLE compression_runs ADD COLUMN revision_key TEXT NOT NULL DEFAULT ''"
        )
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS compression_revision_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            generation INTEGER NOT NULL DEFAULT 0,
            call_generation INTEGER NOT NULL DEFAULT 0,
            thread_generation INTEGER NOT NULL DEFAULT 0,
            tool_generation INTEGER NOT NULL DEFAULT 0,
            command_generation INTEGER NOT NULL DEFAULT 0,
            file_generation INTEGER NOT NULL DEFAULT 0,
            fragment_generation INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO compression_revision_state(singleton) VALUES (1);
        UPDATE compression_revision_state
        SET generation = (SELECT generation FROM compression_source_state WHERE singleton = 1),
            call_generation = (SELECT generation FROM compression_source_state WHERE singleton = 1),
            thread_generation = (SELECT generation FROM compression_source_state WHERE singleton = 1),
            tool_generation = (SELECT generation FROM compression_source_state WHERE singleton = 1),
            command_generation = (SELECT generation FROM compression_source_state WHERE singleton = 1),
            file_generation = (SELECT generation FROM compression_source_state WHERE singleton = 1),
            fragment_generation = (SELECT generation FROM compression_source_state WHERE singleton = 1)
        WHERE generation = 0
          AND call_generation = 0
          AND thread_generation = 0
          AND tool_generation = 0
          AND command_generation = 0
          AND file_generation = 0
          AND fragment_generation = 0;
        CREATE INDEX IF NOT EXISTS idx_compression_runs_revision_cache
        ON compression_runs(
            revision_key,
            scope_hash,
            detector_set_version,
            estimator_version,
            compression_schema_version,
            status,
            completed_at DESC
        );
        """,
    )


def read_compression_source_generation(conn: sqlite3.Connection) -> int:
    _ensure_compression_storage(conn)
    row = conn.execute(
        "SELECT generation FROM compression_source_state WHERE singleton = 1"
    ).fetchone()
    return int(row["generation"] if row is not None else 0)


def touch_compression_source_generation(conn: sqlite3.Connection) -> int:
    """Invalidate exact compression caches once per aggregate write transaction."""
    from codex_usage_tracker.store.compression_revision_state import touch_compression_revisions

    _ensure_compression_storage(conn)
    return touch_compression_revisions(conn)


def stamp_compression_fact_state(
    conn: sqlite3.Connection,
    *,
    facts_version: int,
) -> None:
    """Record fact-table integrity counts at the current source generation."""
    counts = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM compression_record_facts),
            (SELECT COUNT(*) FROM compression_sequence_facts),
            (SELECT COUNT(*) FROM compression_thread_facts),
            (SELECT COALESCE(MAX(updated_at), '') FROM compression_record_facts)
        """
    ).fetchone()
    conn.execute(
        """
        INSERT INTO compression_fact_state (
            singleton, facts_version, source_generation,
            record_count, sequence_count, thread_count, updated_at
        ) VALUES (1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(singleton) DO UPDATE SET
            facts_version = excluded.facts_version,
            source_generation = excluded.source_generation,
            record_count = excluded.record_count,
            sequence_count = excluded.sequence_count,
            thread_count = excluded.thread_count,
            updated_at = excluded.updated_at
        """,
        (
            facts_version,
            read_compression_source_generation(conn),
            int(counts[0]),
            int(counts[1]),
            int(counts[2]),
            str(counts[3] or ""),
        ),
    )


def _ensure_compression_storage(conn: sqlite3.Connection) -> None:
    conn.execute("DROP INDEX IF EXISTS idx_compression_candidate_records_record")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS compression_source_state (
            singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
            generation INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO compression_source_state(singleton, generation)
        VALUES (1, 0)
        """
    )
    columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(compression_runs)").fetchall()
    }
    if "public_profile_json" not in columns:
        conn.execute(
            "ALTER TABLE compression_runs ADD COLUMN public_profile_json TEXT NOT NULL DEFAULT '{}'"
        )
    if "source_generation" not in columns:
        conn.execute(
            "ALTER TABLE compression_runs ADD COLUMN source_generation INTEGER NOT NULL DEFAULT 0"
        )


def add_candidate_record_metadata(conn: sqlite3.Connection) -> None:
    """Persist stable model/thread/time facts with each candidate claim."""
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(compression_candidate_records)").fetchall()
    }
    for column in ("model", "thread_key", "event_timestamp"):
        if column not in columns:
            conn.execute(f"ALTER TABLE compression_candidate_records ADD COLUMN {column} TEXT")
    conn.execute(
        """
        UPDATE compression_candidate_records
        SET model = COALESCE(model, (
                SELECT u.model FROM usage_events AS u
                WHERE u.record_id = compression_candidate_records.record_id
            )),
            thread_key = COALESCE(thread_key, (
                SELECT COALESCE(u.thread_key, u.thread_name, u.session_id)
                FROM usage_events AS u
                WHERE u.record_id = compression_candidate_records.record_id
            )),
            event_timestamp = COALESCE(event_timestamp, (
                SELECT u.event_timestamp FROM usage_events AS u
                WHERE u.record_id = compression_candidate_records.record_id
            ))
        WHERE model IS NULL OR thread_key IS NULL OR event_timestamp IS NULL
        """
    )
