from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import SCHEMA_VERSION, init_db


def test_schema_migration_creates_otel_sidecar_tables(tmp_path: Path) -> None:
    with connect(tmp_path / "usage.sqlite3") as conn:
        init_db(conn)
        source_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(otel_completion_sources)")
        }
        event_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(otel_completion_events)")
        }

    assert SCHEMA_VERSION == 30
    assert {
        "source_path",
        "device",
        "inode",
        "size",
        "parsed_offset",
        "parsed_line",
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
