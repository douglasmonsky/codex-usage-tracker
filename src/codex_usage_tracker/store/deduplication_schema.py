"""Migration for canonical usage identity."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.core.usage_identity import usage_identity_from_values


def migrate_usage_deduplication(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(usage_events)")}
    if not {"record_id", "event_timestamp", "source_file", "line_number"} <= existing:
        return
    columns = {
        "upstream_usage_id": "TEXT",
        "usage_fingerprint": "TEXT",
        "canonical_record_id": "TEXT",
        "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
        "duplicate_reason": "TEXT",
    }
    for name, declaration in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE usage_events ADD COLUMN {name} {declaration}")
    for row in conn.execute("SELECT * FROM usage_events").fetchall():
        identity = usage_identity_from_values(dict(row), upstream_usage_id=row["upstream_usage_id"])
        conn.execute(
            "UPDATE usage_events SET upstream_usage_id=?, usage_fingerprint=?, canonical_record_id=?, is_duplicate=1, duplicate_reason='copied_usage_fingerprint' WHERE record_id=?",
            (
                identity.upstream_usage_id,
                identity.usage_fingerprint,
                identity.canonical_record_id,
                row["record_id"],
            ),
        )
    conn.execute(
        "UPDATE usage_events SET is_duplicate=0, duplicate_reason=NULL WHERE record_id IN (SELECT record_id FROM (SELECT record_id, ROW_NUMBER() OVER (PARTITION BY usage_fingerprint ORDER BY event_timestamp, source_file, line_number, record_id) AS n FROM usage_events) WHERE n=1)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_fingerprint ON usage_events(usage_fingerprint)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_canonical_record_id ON usage_events(canonical_record_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_duplicate ON usage_events(is_duplicate)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_duplicate_reason "
        "ON usage_events(is_duplicate, duplicate_reason)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_canonical_fingerprint ON usage_events(usage_fingerprint) WHERE is_duplicate=0"
    )
    conn.execute("DROP VIEW IF EXISTS canonical_usage_events")
    conn.execute(
        "CREATE VIEW canonical_usage_events AS SELECT * FROM usage_events WHERE is_duplicate=0"
    )
