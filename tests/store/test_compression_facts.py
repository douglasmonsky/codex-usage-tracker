from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.store.api import refresh_usage_index, reset_usage_database
from codex_usage_tracker.store.compression_fact_contract import call_revision_identity
from codex_usage_tracker.store.compression_facts import backfill_compression_detector_facts
from codex_usage_tracker.store.compression_schema import (
    read_compression_source_generation,
)
from codex_usage_tracker.store.connection import connect
from tests.store_dashboard_helpers import (
    _entry,
    _make_codex_home,
    _token_event,
)


def test_content_refresh_updates_detector_fact_exposure(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        fact_row = conn.execute(
            """
            SELECT SUM(content_exposure_tokens) AS content_exposure_tokens
            FROM compression_record_facts
            """
        ).fetchone()
        fact_state = conn.execute(
            "SELECT source_generation FROM compression_fact_state WHERE singleton = 1"
        ).fetchone()
        source_generation = read_compression_source_generation(conn)

    assert fact_row is not None
    assert fact_row["content_exposure_tokens"] > 0
    assert fact_state is not None
    assert fact_state["source_generation"] == source_generation


def test_direct_ingestion_facts_match_legacy_backfill(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        direct = _fact_table_snapshot(conn)
        backfill_compression_detector_facts(conn)
        legacy = _fact_table_snapshot(conn)

    assert direct == legacy


def test_append_refresh_does_not_rebuild_historical_detector_facts(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    source_path = next((codex_home / "sessions").glob("**/*.jsonl"))

    with connect(db_path) as conn:
        initial_count = int(
            conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        )
        conn.executescript(
            """
            CREATE TABLE protected_compression_facts (
                record_id TEXT PRIMARY KEY
            );
            INSERT INTO protected_compression_facts
            SELECT record_id FROM compression_record_facts;
            CREATE TRIGGER protect_historical_compression_facts
            BEFORE DELETE ON compression_record_facts
            WHEN OLD.record_id IN (SELECT record_id FROM protected_compression_facts)
            BEGIN
                SELECT RAISE(ABORT, 'historical fact was rebuilt');
            END;
            """
        )

    with source_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                _entry(
                    "response_item",
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "APPENDED FACT"}],
                    },
                )
            )
            + "\n"
        )
        handle.write(json.dumps(_token_event(8_000, 400)) + "\n")

    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        final_count = int(
            conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        )
        fact_state = conn.execute(
            "SELECT source_generation FROM compression_fact_state WHERE singleton = 1"
        ).fetchone()
        source_generation = read_compression_source_generation(conn)
    assert final_count == initial_count + 1
    assert fact_state is not None
    assert fact_state["source_generation"] == source_generation


def test_reset_clears_all_detector_fact_tables(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    reset_usage_database(db_path=db_path)

    with connect(db_path) as conn:
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "compression_record_facts",
                "compression_sequence_facts",
                "compression_thread_facts",
                "compression_fact_state",
            )
        }
    assert set(counts.values()) == {0}


def test_failed_full_backfill_rolls_back_rows_and_indexes(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    with connect(db_path) as conn:
        original_count = int(
            conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        )

    def fail_after_record_facts(stage: str) -> None:
        if stage == "record_facts":
            raise RuntimeError("stop after record facts")

    with (
        pytest.raises(RuntimeError, match="stop after record facts"),
        connect(db_path) as conn,
    ):
        backfill_compression_detector_facts(
            conn,
            stage_callback=fail_after_record_facts,
        )

    with connect(db_path) as conn:
        restored_count = int(
            conn.execute("SELECT COUNT(*) FROM compression_record_facts").fetchone()[0]
        )
        indexes = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'idx_compression_%_facts_%'"
            )
        }
    assert restored_count == original_count
    assert "idx_compression_record_facts_scope" in indexes
    assert "idx_compression_sequence_facts_scope" in indexes


def _fact_table_snapshot(conn) -> dict[str, list[tuple[object, ...]]]:
    snapshots: dict[str, list[tuple[object, ...]]] = {}
    for table in (
        "compression_record_facts",
        "compression_sequence_facts",
        "compression_thread_facts",
    ):
        columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]
        order_columns = ", ".join(str(index + 1) for index in range(len(columns)))
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY {order_columns}"  # nosec B608
        ).fetchall()
        snapshots[table] = [tuple(row) for row in rows]
    return snapshots


def test_call_revision_identity_ignores_derived_thread_links() -> None:
    unlinked = (
        "record",
        "session",
        "thread",
        "2026-01-01T00:00:00Z",
        "model",
        "high",
        0,
        None,
        None,
        10,
        20,
        30,
        40,
        0.5,
        75.0,
    )
    linked = (*unlinked[:7], 3, "previous-record", *unlinked[9:])

    assert call_revision_identity(unlinked) == call_revision_identity(linked)
