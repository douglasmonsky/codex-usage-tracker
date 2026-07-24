from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.otel_schema import add_otel_cursor_resume_anchor
from codex_usage_tracker.store.schema import SCHEMA_VERSION, init_db


def test_schema_migration_creates_otel_sidecar_tables(tmp_path: Path) -> None:
    with connect(tmp_path / "usage.sqlite3") as conn:
        init_db(conn)
        source_columns = {
            str(row["name"]) for row in conn.execute("PRAGMA table_info(otel_completion_sources)")
        }
        event_columns = {
            str(row["name"]) for row in conn.execute("PRAGMA table_info(otel_completion_events)")
        }

    assert SCHEMA_VERSION == 35
    assert {
        "source_path",
        "device",
        "inode",
        "size",
        "parsed_offset",
        "parsed_line",
        "resume_anchor",
        "updated_at",
    } <= source_columns
    assert {
        "fingerprint",
        "conversation_id",
        "service_tier",
        "fast",
        "match_status",
        "matched_record_id",
    } <= event_columns


def test_cursor_anchor_migration_preserves_existing_source_state(tmp_path: Path) -> None:
    with connect(tmp_path / "usage.sqlite3") as conn:
        conn.execute(
            """
            CREATE TABLE otel_completion_sources (
                source_path TEXT PRIMARY KEY,
                device INTEGER NOT NULL,
                inode INTEGER NOT NULL,
                size INTEGER NOT NULL,
                parsed_offset INTEGER NOT NULL,
                parsed_line INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO otel_completion_sources (
                source_path, device, inode, size, parsed_offset, parsed_line, updated_at
            ) VALUES ('/tmp/synthetic-otel.jsonl', 1, 2, 100, 100, 1, '2026-07-16')
            """
        )

        add_otel_cursor_resume_anchor(conn)

        row = conn.execute(
            """
            SELECT parsed_offset, parsed_line, resume_anchor
            FROM otel_completion_sources
            WHERE source_path = '/tmp/synthetic-otel.jsonl'
            """
        ).fetchone()

    assert row is not None
    assert row["parsed_offset"] == 100
    assert row["parsed_line"] == 1
    assert row["resume_anchor"] is None
