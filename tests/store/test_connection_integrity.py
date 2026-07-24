from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.store.connection import connect, connect_read_only
from codex_usage_tracker.store.schema import init_db


def test_runtime_sqlite_connections_are_centralized_or_explicitly_configured() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src" / "codex_usage_tracker"
    direct_connection_files: set[str] = set()
    for source_path in source_root.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "sqlite3"
                and node.func.attr == "connect"
            ):
                direct_connection_files.add(source_path.relative_to(source_root).as_posix())

    assert direct_connection_files == {
        "application/allowance.py",
        "store/connection.py",
    }


def test_shared_connections_enable_foreign_keys_and_retain_wal(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    with connect(db_path) as connection:
        init_db(connection)
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"

    with connect_read_only(db_path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_read_only_connection_preserves_requested_short_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        init_db(connection)

    with connect_read_only(db_path, timeout=0.1) as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 100

    with connect_read_only(db_path, timeout=5.0, busy_timeout_ms=17) as connection:
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 17


def test_shared_connection_rolls_back_on_exception(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    with connect(db_path) as connection:
        connection.execute("CREATE TABLE rollback_probe (value TEXT NOT NULL)")

    with (
        pytest.raises(RuntimeError, match="synthetic rollback"),
        connect(db_path) as connection,
    ):
        connection.execute("INSERT INTO rollback_probe(value) VALUES ('pending')")
        raise RuntimeError("synthetic rollback")

    with connect_read_only(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM rollback_probe").fetchone()[0] == 0


def test_shared_connection_rejects_orphan_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"

    with connect(db_path) as connection:
        init_db(connection)
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            connection.execute(
                """
                INSERT INTO source_records (
                    record_id,
                    source_file_id,
                    source_file_hash,
                    line_number,
                    event_timestamp,
                    source_record_hash,
                    parser_adapter,
                    parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "orphan-record",
                    "synthetic-source",
                    "synthetic-hash",
                    1,
                    "2026-07-23T00:00:00Z",
                    "synthetic-record-hash",
                    "synthetic",
                    "1",
                ),
            )
