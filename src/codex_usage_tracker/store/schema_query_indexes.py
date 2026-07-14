"""Additive query-index schema migrations."""

from __future__ import annotations

import sqlite3

MIGRATION_NAMES = {
    18: "index usage events by source file and line",
    22: "cover diagnostic fact lookups",
}


def migrate_source_file_line_index(conn: sqlite3.Connection) -> None:
    columns = {
        str(row["name"]) for row in conn.execute("PRAGMA table_info(usage_events)").fetchall()
    }
    if not {"source_file", "line_number"} <= columns:
        return
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_source_file_line "
        "ON usage_events(source_file, line_number)"
    )


def add_diagnostic_lookup_index(conn: sqlite3.Connection) -> None:
    """Cover correlated diagnostic lookups by type, name, and record."""

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_call_diagnostic_facts_lookup
        ON call_diagnostic_facts(fact_type, fact_name, record_id)
        """
    )
