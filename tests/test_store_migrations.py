from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.store import (
    EVENT_COLUMNS,
    SchemaMigrationError,
    connect,
    export_usage_csv,
    init_db,
    query_dashboard_event_count,
    query_session_usage,
    refresh_metadata,
    refresh_usage_index,
    schema_state,
)

LEGACY_SESSION_ID = "019e3810-78be-7f32-a7d7-884d9bdba1fd"
NEW_SESSION_ID = "019e3811-5715-7018-a7bb-2232b46a5671"


def test_init_db_migrates_legacy_aggregate_table_without_data_loss(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path)

    with connect(db_path) as conn:
        init_db(conn)

    rows = query_session_usage(db_path=db_path, session_id=LEGACY_SESSION_ID)
    state = schema_state(db_path)
    metadata = refresh_metadata(db_path)

    assert len(rows) == 1
    assert rows[0]["record_id"] == "legacy-record"
    assert rows[0]["source_file"] == "/tmp/synthetic-session.jsonl"
    assert rows[0]["thread_source"] is None
    assert rows[0]["parent_thread_name"] is None
    assert rows[0]["model_context_window"] is None
    assert metadata["parsed_events"] == "legacy"
    assert metadata["parser_invalid_integer"] == "2"
    assert state["schema_version"] == 2
    assert state["checksum_matches"] is True
    assert [row["version"] for row in state["migrations"]] == [1, 2]


def test_refresh_is_idempotent_after_legacy_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    codex_home = _make_codex_home(tmp_path)
    _write_legacy_usage_database(db_path)

    first = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    first_count = query_dashboard_event_count(db_path=db_path)
    second = refresh_usage_index(codex_home=codex_home, db_path=db_path)
    second_count = query_dashboard_event_count(db_path=db_path)
    legacy_rows = query_session_usage(db_path=db_path, session_id=LEGACY_SESSION_ID)
    new_rows = query_session_usage(db_path=db_path, session_id=NEW_SESSION_ID)
    metadata = refresh_metadata(db_path)

    assert first.parsed_events == 1
    assert second.parsed_events == 1
    assert first_count == 2
    assert second_count == 2
    assert legacy_rows[0]["record_id"] == "legacy-record"
    assert new_rows[0]["thread_name"] == "Synthetic migration thread"
    assert metadata["schema_version"] == "2"
    assert metadata["parsed_events"] == "1"
    assert metadata["inserted_or_updated_events"] == "1"


def test_csv_export_keeps_current_columns_after_legacy_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage.csv"
    _write_legacy_usage_database(db_path)

    exported = export_usage_csv(csv_path, db_path=db_path)

    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert exported == 1
    assert rows[0]["record_id"] == "legacy-record"
    assert list(rows[0]) == EVENT_COLUMNS


def test_malformed_legacy_schema_reports_actionable_error_without_data_loss(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path, omit_source_file=True)

    with pytest.raises(SchemaMigrationError, match="missing required columns: source_file"), connect(
        db_path
    ) as conn:
        init_db(conn)

    raw = sqlite3.connect(db_path)
    try:
        row_count = raw.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        user_version = raw.execute("PRAGMA user_version").fetchone()[0]
    finally:
        raw.close()

    assert row_count == 1
    assert user_version == 1


def test_doctor_reports_malformed_legacy_schema_without_traceback(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _write_legacy_usage_database(db_path, omit_source_file=True)

    report = run_doctor(codex_home=tmp_path / ".codex", db_path=db_path)
    schema_check = _check_named(report, "Database schema")
    parser_check = _check_named(report, "Parser diagnostics")

    assert report["status"] == "fail"
    assert schema_check["status"] == "fail"
    assert "source_file" in schema_check["detail"]
    assert "rebuild-index" in str(schema_check["remediation"])
    assert parser_check["status"] == "fail"
    assert "database migration failed" in parser_check["detail"]


def _write_legacy_usage_database(db_path: Path, *, omit_source_file: bool = False) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        ("record_id", "TEXT PRIMARY KEY"),
        ("session_id", "TEXT NOT NULL"),
        ("event_timestamp", "TEXT NOT NULL"),
        ("source_file", "TEXT NOT NULL"),
        ("line_number", "INTEGER NOT NULL"),
        ("input_tokens", "INTEGER NOT NULL"),
        ("cached_input_tokens", "INTEGER NOT NULL"),
        ("output_tokens", "INTEGER NOT NULL"),
        ("reasoning_output_tokens", "INTEGER NOT NULL"),
        ("total_tokens", "INTEGER NOT NULL"),
        ("cumulative_input_tokens", "INTEGER NOT NULL"),
        ("cumulative_cached_input_tokens", "INTEGER NOT NULL"),
        ("cumulative_output_tokens", "INTEGER NOT NULL"),
        ("cumulative_reasoning_output_tokens", "INTEGER NOT NULL"),
        ("cumulative_total_tokens", "INTEGER NOT NULL"),
        ("uncached_input_tokens", "INTEGER NOT NULL"),
        ("cache_ratio", "REAL NOT NULL"),
        ("reasoning_output_ratio", "REAL NOT NULL"),
        ("context_window_percent", "REAL NOT NULL"),
    ]
    if omit_source_file:
        columns = [column for column in columns if column[0] != "source_file"]
    column_names = [name for name, _declaration in columns]
    values = {
        "record_id": "legacy-record",
        "session_id": LEGACY_SESSION_ID,
        "event_timestamp": "2026-05-17T18:58:27.000Z",
        "source_file": "/tmp/synthetic-session.jsonl",
        "line_number": 12,
        "input_tokens": 90,
        "cached_input_tokens": 20,
        "output_tokens": 10,
        "reasoning_output_tokens": 5,
        "total_tokens": 100,
        "cumulative_input_tokens": 90,
        "cumulative_cached_input_tokens": 20,
        "cumulative_output_tokens": 10,
        "cumulative_reasoning_output_tokens": 5,
        "cumulative_total_tokens": 100,
        "uncached_input_tokens": 70,
        "cache_ratio": 20 / 90,
        "reasoning_output_ratio": 0.5,
        "context_window_percent": 0.0,
    }
    raw = sqlite3.connect(db_path)
    try:
        raw.execute(f"CREATE TABLE usage_events ({_columns_sql(columns)})")
        raw.execute("CREATE TABLE refresh_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        raw.executemany(
            "INSERT INTO refresh_meta (key, value) VALUES (?, ?)",
            [
                ("parsed_events", "legacy"),
                ("parser_invalid_integer", "2"),
            ],
        )
        placeholders = ", ".join("?" for _name in column_names)
        raw.execute(
            f"INSERT INTO usage_events ({', '.join(column_names)}) VALUES ({placeholders})",
            [values[name] for name in column_names],
        )
        raw.execute("PRAGMA user_version = 1")
        raw.commit()
    finally:
        raw.close()


def _columns_sql(columns: list[tuple[str, str]]) -> str:
    return ", ".join(f"{name} {declaration}" for name, declaration in columns)


def _check_named(report: dict[str, object], name: str) -> dict[str, object]:
    checks = report["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check["name"] == name:
            return check
    raise AssertionError(f"missing doctor check: {name}")


def _make_codex_home(tmp_path: Path) -> Path:
    codex_home = tmp_path / ".codex"
    log_path = (
        codex_home
        / "sessions"
        / "2026"
        / "05"
        / "17"
        / f"rollout-2026-05-17T18-58-27-{NEW_SESSION_ID}.jsonl"
    )
    _write_jsonl(
        codex_home / "session_index.jsonl",
        [
            {
                "id": NEW_SESSION_ID,
                "thread_name": "Synthetic migration thread",
                "updated_at": "2026-05-17T19:00:00Z",
            }
        ],
    )
    _write_jsonl(
        log_path,
        [
            _entry("session_meta", {"id": NEW_SESSION_ID}),
            _entry("turn_context", {"turn_id": "turn-a", "model": "gpt-5.5"}),
            _token_event(200, 200),
        ],
    )
    return codex_home


def _token_event(cumulative_total: int, last_total: int) -> dict[str, object]:
    return _entry(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": cumulative_total - 20,
                    "cached_input_tokens": 40,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 5,
                    "total_tokens": cumulative_total,
                },
                "last_token_usage": {
                    "input_tokens": last_total - 20,
                    "cached_input_tokens": 10,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 5,
                    "total_tokens": last_total,
                },
                "model_context_window": 258400,
            },
        },
    )


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": "2026-05-17T18:58:27.000Z",
        "type": entry_type,
        "payload": payload,
    }


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
