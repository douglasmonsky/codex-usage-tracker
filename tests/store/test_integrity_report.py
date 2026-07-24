from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from codex_usage_tracker.diagnostics.api import run_doctor
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.integrity import check_database_integrity
from codex_usage_tracker.store.schema import init_db


def test_integrity_report_passes_for_a_valid_database(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)

    report = check_database_integrity(db_path)

    assert report == {
        "schema": "codex-usage-tracker.database-integrity.v1",
        "state": "pass",
        "readable": True,
        "foreign_keys_enabled": True,
        "integrity_error_count": 0,
        "foreign_key_violation_count": 0,
        "affected_tables": [],
        "affected_tables_truncated": False,
        "error": None,
    }


def test_integrity_report_is_unknown_for_missing_or_unreadable_database(tmp_path: Path) -> None:
    missing = check_database_integrity(tmp_path / "missing.sqlite3")
    assert missing["state"] == "unknown"
    assert missing["readable"] is False
    assert missing["error"] == "database_missing"

    invalid_path = tmp_path / "invalid.sqlite3"
    invalid_path.write_text("not a sqlite database", encoding="utf-8")
    invalid = check_database_integrity(invalid_path)
    assert invalid["state"] == "unknown"
    assert invalid["readable"] is False
    assert invalid["error"] == "database_unreadable"


def test_integrity_report_counts_orphans_without_exposing_row_content(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)

    raw = sqlite3.connect(db_path)
    try:
        raw.execute("PRAGMA foreign_keys = OFF")
        raw.execute(
            """
            INSERT INTO source_records (
                record_id, source_file_id, source_file_hash, line_number,
                event_timestamp, source_record_hash, parser_adapter, parser_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "private-row-id-must-not-appear",
                "synthetic-source",
                "synthetic-hash",
                1,
                "2026-07-23T00:00:00Z",
                "synthetic-record-hash",
                "synthetic",
                "1",
            ),
        )
        raw.commit()
    finally:
        raw.close()

    report = check_database_integrity(db_path)

    assert report["state"] == "fail"
    assert report["integrity_error_count"] == 0
    assert report["foreign_key_violation_count"] == 1
    assert report["affected_tables"] == ["source_records"]
    assert "private-row-id-must-not-appear" not in json.dumps(report)


def test_doctor_reports_database_integrity_without_repairing(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)

    report = run_doctor(codex_home=tmp_path / ".codex", db_path=db_path)
    check = next(item for item in report["checks"] if item["name"] == "Database integrity")

    assert check["status"] == "pass"
    assert "integrity_check=ok" in check["detail"]
