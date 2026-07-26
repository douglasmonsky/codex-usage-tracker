from __future__ import annotations

import inspect
import json
import sqlite3
from pathlib import Path

from codex_usage_tracker.store import service_tier_schema
from codex_usage_tracker.store.api import refresh_usage_index, upsert_usage_events
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import SCHEMA_VERSION, init_db
from tests.store_dashboard_helpers import _usage_event


def test_current_schema_and_refresh_surface_exclude_retired_telemetry(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    with connect(db_path) as conn:
        init_db(conn)
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert SCHEMA_VERSION == 38
    assert "otel_completion_sources" not in tables
    assert "otel_completion_events" not in tables
    assert "otel_dir" not in inspect.signature(refresh_usage_index).parameters


def test_telemetry_removal_preserves_shared_service_tier_data() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE usage_events (
            record_id TEXT PRIMARY KEY,
            service_tier TEXT,
            fast INTEGER,
            service_tier_source TEXT,
            service_tier_confidence TEXT
        );
        INSERT INTO usage_events VALUES (
            'synthetic-record',
            'priority',
            1,
            'primary_event',
            'exact'
        );
        CREATE TABLE otel_completion_sources (
            source_path TEXT PRIMARY KEY
        );
        CREATE TABLE otel_completion_events (
            fingerprint TEXT PRIMARY KEY
        );
        """
    )

    service_tier_schema.drop_retired_telemetry_tables(conn)

    row = conn.execute(
        """
        SELECT service_tier, fast, service_tier_source, service_tier_confidence
        FROM usage_events
        WHERE record_id = 'synthetic-record'
        """
    ).fetchone()
    tables = {
        str(item["name"])
        for item in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }

    assert row is not None
    assert tuple(row) == ("priority", 1, "primary_event", "exact")
    assert "otel_completion_sources" not in tables
    assert "otel_completion_events" not in tables


def test_schema_37_migration_removes_telemetry_and_preserves_usage_row(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="synthetic-tier-record",
                session_id="synthetic-tier-session",
                thread_key="thread:synthetic-tier",
                event_timestamp="2026-07-25T12:00:00Z",
                cumulative_total_tokens=110,
            )
        ],
        db_path,
    )
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE usage_events
            SET service_tier = 'priority',
                fast = 1,
                service_tier_source = 'primary_event',
                service_tier_confidence = 'exact'
            WHERE record_id = 'synthetic-tier-record'
            """
        )
        conn.executescript(
            """
            CREATE TABLE otel_completion_sources (
                source_path TEXT PRIMARY KEY
            );
            CREATE TABLE otel_completion_events (
                fingerprint TEXT PRIMARY KEY
            );
            """
        )
        conn.execute("DELETE FROM schema_migrations WHERE version = 38")
        conn.execute("PRAGMA user_version = 37")
        before_row = conn.execute(
            "SELECT * FROM usage_events WHERE record_id = 'synthetic-tier-record'"
        ).fetchone()
        assert before_row is not None
        before_bytes = json.dumps(
            tuple(before_row),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()

    with connect(db_path) as conn:
        init_db(conn)
        after_row = conn.execute(
            "SELECT * FROM usage_events WHERE record_id = 'synthetic-tier-record'"
        ).fetchone()
        assert after_row is not None
        after_bytes = json.dumps(
            tuple(after_row),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        tables = {
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        applied = conn.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 38"
        ).fetchone()
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION

    assert after_bytes == before_bytes
    assert applied is not None and int(applied[0]) == 1
    assert "otel_completion_sources" not in tables
    assert "otel_completion_events" not in tables


def test_refresh_progress_and_metadata_do_not_report_retired_phases(tmp_path: Path) -> None:
    progress: list[dict[str, object]] = []

    result = refresh_usage_index(
        codex_home=tmp_path / "codex",
        db_path=tmp_path / "usage.sqlite3",
        progress_callback=progress.append,
    )

    assert all(item.get("phase") != "otel" for item in progress)
    assert all(not key.startswith("otel_") for key in result.parser_diagnostics)
