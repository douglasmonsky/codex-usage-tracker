"""Migration for canonical usage identity."""

from __future__ import annotations

import sqlite3

from codex_usage_tracker.core.usage_identity import usage_identity_from_values

MIGRATION_NAMES = {
    24: "add canonical usage identity and deduplication",
    25: "recognize clone-rewritten usage timestamps",
}

_IDENTITY_COLUMNS = {
    "upstream_usage_id": "TEXT",
    "usage_fingerprint": "TEXT",
    "canonical_record_id": "TEXT",
    "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
    "duplicate_reason": "TEXT",
}


def migrate_usage_deduplication(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(usage_events)")}
    if not {"record_id", "event_timestamp", "source_file", "line_number"} <= existing:
        return
    _ensure_identity_columns(conn, existing)
    _backfill_usage_identity(conn)
    _create_dedupe_indexes(conn)
    _create_canonical_view(conn)


def migrate_clone_rewritten_usage(conn: sqlite3.Connection) -> None:
    """Reclassify v1 identities and rebuild canonical derived state."""

    migrate_usage_deduplication(conn)
    canonical_view = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='view' AND name='canonical_usage_events'"
    ).fetchone()
    if canonical_view is not None:
        _rebuild_canonical_derivatives(conn)


def _ensure_identity_columns(conn: sqlite3.Connection, existing: set[str]) -> None:
    for name, declaration in _IDENTITY_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE usage_events ADD COLUMN {name} {declaration}")


def _backfill_usage_identity(conn: sqlite3.Connection) -> None:
    conn.execute("DROP INDEX IF EXISTS idx_usage_canonical_fingerprint")
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


def _create_dedupe_indexes(conn: sqlite3.Connection) -> None:
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


def _create_canonical_view(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS canonical_usage_events")
    conn.execute(
        "CREATE VIEW canonical_usage_events AS SELECT * FROM usage_events WHERE is_duplicate=0"
    )


def _rebuild_canonical_derivatives(conn: sqlite3.Connection) -> None:
    from codex_usage_tracker.store.allowance_observations import (
        rebuild_allowance_observations,
    )
    from codex_usage_tracker.store.recommendation_schema import (
        reconcile_recommendation_facts_with_canonical_usage,
    )
    from codex_usage_tracker.store.thread_summaries import rebuild_thread_summaries

    rebuild_allowance_observations(conn)
    reconcile_recommendation_facts_with_canonical_usage(conn)
    rebuild_thread_summaries(conn)
