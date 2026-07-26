"""Shared service-tier fields and retired telemetry cleanup."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.store.allowance_schema import (
    optimize_allowance_interval_revision_indexes,
)
from codex_usage_tracker.store.connection import execute_script

MIGRATION_NAMES = {
    30: "persist normalized service tier fields",
    31: "reserved schema checkpoint",
    38: "remove retired telemetry and low-selectivity allowance indexes",
}


def migrate_service_tier_fields(conn: sqlite3.Connection) -> None:
    """Add shared normalized tier fields without creating a sidecar."""

    tier_columns = {
        "service_tier": "TEXT",
        "fast": "INTEGER",
        "service_tier_source": "TEXT",
        "service_tier_confidence": "TEXT",
    }
    existing_columns = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    for column, column_type in tier_columns.items():
        if column not in existing_columns:
            conn.execute(  # nosec B608 - fixed migration column names.
                f"ALTER TABLE usage_events ADD COLUMN {column} {column_type}"
            )


def reserved_schema_checkpoint(_conn: sqlite3.Connection) -> None:
    """Preserve the monotonic migration ledger without legacy runtime objects."""


def drop_retired_telemetry_tables(conn: sqlite3.Connection) -> None:
    """Remove retired sidecar tables without touching shared usage facts."""

    execute_script(
        conn,
        """
        DROP TABLE IF EXISTS otel_completion_events;
        DROP TABLE IF EXISTS otel_completion_sources;
        """,
    )
    optimize_allowance_interval_revision_indexes(conn)
