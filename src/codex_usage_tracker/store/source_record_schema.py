"""Schema ownership for persisted source-record provenance."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.store.connection import execute_script


def create_source_records_table(conn: sqlite3.Connection) -> None:
    """Create source-record provenance storage and its query indexes."""

    execute_script(
        conn,
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
        """,
    )
