"""Additive source-location indexes for usage events."""

from __future__ import annotations

import sqlite3


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
