from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.database import (
    initialize_analytical_database,
    open_read_snapshot,
    short_writer_transaction,
    validate_analytical_database,
)
from codex_usage_tracker.kernel.schema import (
    ANALYTICAL_TABLES,
    APPLICATION_ID,
    MAX_INDEX_COUNT,
    SCHEMA_VERSION,
)


def _schema_dump(path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            """
            SELECT type, name, sql
            FROM sqlite_schema
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()


def test_fresh_analytical_cache_has_only_approved_schema(tmp_path: Path) -> None:
    path = tmp_path / "kernel.sqlite3"

    initialize_analytical_database(path)

    with open_read_snapshot(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table'"
            )
        }
        indexes = connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_schema
            WHERE type = 'index' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert connection.execute("PRAGMA application_id").fetchone()[0] == APPLICATION_ID
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    assert tables == ANALYTICAL_TABLES
    assert indexes <= MAX_INDEX_COUNT
    assert validate_analytical_database(path) == []


def test_schema_dump_is_deterministic_and_has_no_full_path_column(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.sqlite3"
    second = tmp_path / "second.sqlite3"

    initialize_analytical_database(first)
    initialize_analytical_database(second)

    assert _schema_dump(first) == _schema_dump(second)
    schema_text = "\n".join(sql or "" for _, _, sql in _schema_dump(first)).lower()
    for forbidden in (
        "full_path",
        "raw_path",
        "prompt_text",
        "reasoning_text",
        "tool_output",
    ):
        assert forbidden not in schema_text


def test_foreign_keys_reject_orphan_facts(tmp_path: Path) -> None:
    path = tmp_path / "kernel.sqlite3"
    initialize_analytical_database(path)

    with short_writer_transaction(path) as connection:
        connection.execute(
            """
            INSERT INTO generations(
                generation, source_revision_digest, created_at,
                high_water_digest, inserted_count, updated_count,
                deleted_count, canonical_count, excluded_count,
                parser_versions, integrity_status
            )
            VALUES (1, 'sha256:source', '2026-01-01T00:00:00Z',
                    'sha256:water', 0, 0, 0, 0, 0, 'parser-v1', 'valid')
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO threads(
                    thread_id, source_id, session_identity_hash, display_label,
                    archive_state, first_generation, last_generation,
                    identity_basis, identity_confidence
                )
                VALUES ('thr_1', 'src_missing', 'session', 'Thread',
                        'active', 1, 1, 'upstream', 'exact')
                """
            )
