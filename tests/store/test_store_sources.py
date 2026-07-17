from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from codex_usage_tracker.parser.state import (
    PARSER_ADAPTER_VERSION,
    ParserState,
)
from codex_usage_tracker.store.schema import init_db
from codex_usage_tracker.store.sources import (
    source_logs_requiring_parse,
    upsert_source_file_metadata,
)
from tests.store_dashboard_helpers import _usage_event


class _AutoClosingConnection:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def __del__(self) -> None:
        with suppress(Exception):
            self.close()


def _memory_db() -> _AutoClosingConnection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return _AutoClosingConnection(conn)


def test_source_logs_requiring_parse_classifies_new_unchanged_and_append_only(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    new_path = tmp_path / "new.jsonl"
    unchanged_path = tmp_path / "unchanged.jsonl"
    grown_path = tmp_path / "grown.jsonl"
    new_path.write_text("{}\n", encoding="utf-8")
    unchanged_path.write_text("{}\n", encoding="utf-8")
    grown_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[
            (unchanged_path, [], {}, state),
            (grown_path, [], {}, state),
        ],
    )
    with grown_path.open("a", encoding="utf-8") as handle:
        handle.write("{}\n")

    plans = source_logs_requiring_parse(
        conn.connection,
        [new_path, unchanged_path, grown_path, tmp_path / "missing.jsonl"],
    )

    by_path = {plan.path: plan for plan in plans}
    assert set(by_path) == {new_path, grown_path}
    assert by_path[new_path].replace_existing is True
    assert by_path[grown_path].replace_existing is False
    assert by_path[grown_path].start_byte == len("{}\n")
    assert by_path[grown_path].start_line == 1
    assert by_path[grown_path].initial_state == state


def test_source_logs_requiring_parse_rejects_larger_replacement(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "rotated.jsonl"
    source_path.write_text("first\n", encoding="utf-8")
    state = ParserState(session_id="session")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    source_path.write_text("second\nreplacement\n", encoding="utf-8")

    plans = source_logs_requiring_parse(conn.connection, [source_path])

    assert len(plans) == 1
    assert plans[0].replace_existing is True
    assert plans[0].start_byte == 0
    assert plans[0].start_line == 0


def test_source_logs_requiring_parse_reparses_malformed_filesystem_identity(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    conn.execute(
        "UPDATE source_files SET source_inode = ? WHERE source_file = ?",
        ("not-a-filesystem-id", str(source_path)),
    )

    plans = source_logs_requiring_parse(conn.connection, [source_path])

    assert len(plans) == 1
    assert plans[0].replace_existing is True
    assert plans[0].start_byte == 0
    assert plans[0].start_line == 0


def test_source_logs_requiring_parse_preserves_legacy_integer_identity(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    stat = source_path.stat()
    conn.execute(
        """
        UPDATE source_files
        SET source_device = ?, source_inode = ?
        WHERE source_file = ?
        """,
        (stat.st_dev, stat.st_ino, str(source_path)),
    )

    assert source_logs_requiring_parse(conn.connection, [source_path]) == []

    with source_path.open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    plans = source_logs_requiring_parse(conn.connection, [source_path])

    assert len(plans) == 1
    assert plans[0].replace_existing is False
    assert plans[0].start_byte == len("{}\n")
    assert plans[0].start_line == 1


def test_upsert_source_file_metadata_persists_large_filesystem_ids_as_text(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    actual_stat = source_path.stat()
    original_stat = Path.stat
    large_device = (1 << 127) + 123
    large_inode = (1 << 127) + 456

    def large_stat(path: Path, *, follow_symlinks: bool = True) -> Any:
        if path == source_path:
            return SimpleNamespace(
                st_size=actual_stat.st_size,
                st_mtime_ns=actual_stat.st_mtime_ns,
                st_dev=large_device,
                st_ino=large_inode,
            )
        return original_stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", large_stat)

    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )

    row = conn.execute(
        """
        SELECT source_device, source_inode,
               typeof(source_device) AS source_device_type,
               typeof(source_inode) AS source_inode_type
        FROM source_files
        WHERE source_file = ?
        """,
        (str(source_path),),
    ).fetchone()
    assert dict(row) == {
        "source_device": f"fsid-v1:{large_device}",
        "source_inode": f"fsid-v1:{large_inode}",
        "source_device_type": "text",
        "source_inode_type": "text",
    }


def test_source_metadata_generation_advances_only_for_new_checkpoint(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(session_id="session")

    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    first = conn.execute(
        "SELECT source_generation FROM source_files WHERE source_file = ?",
        (str(source_path),),
    ).fetchone()
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    unchanged = conn.execute(
        "SELECT source_generation FROM source_files WHERE source_file = ?",
        (str(source_path),),
    ).fetchone()
    with source_path.open("a", encoding="utf-8") as handle:
        handle.write("{}\n")
    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )
    appended = conn.execute(
        "SELECT source_generation FROM source_files WHERE source_file = ?",
        (str(source_path),),
    ).fetchone()

    assert first["source_generation"] == 1
    assert unchanged["source_generation"] == 1
    assert appended["source_generation"] == 2


def test_upsert_source_file_metadata_records_latest_event_and_parser_state(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "events.jsonl"
    source_path.write_text("{}\n{}\n", encoding="utf-8")
    state = ParserState(
        session_id="session",
        latest_record_id="fallback-record",
        latest_event_timestamp="2026-06-01T09:00:00Z",
    )
    earlier = _usage_event(
        record_id="record-earlier",
        session_id="session",
        thread_key="thread:one",
        event_timestamp="2026-06-01T10:00:00Z",
        cumulative_total_tokens=100,
    )
    latest = _usage_event(
        record_id="record-latest",
        session_id="session",
        thread_key="thread:one",
        event_timestamp="2026-06-01T10:01:00Z",
        cumulative_total_tokens=110,
    )

    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [earlier, latest], {"malformed_json": 1}, state)],
    )

    row = conn.execute(
        "SELECT * FROM source_files WHERE source_file = ?", (str(source_path),)
    ).fetchone()
    assert row["latest_record_id"] == "record-latest"
    assert row["latest_event_timestamp"] == "2026-06-01T10:01:00Z"
    assert row["parsed_until_line"] == 2
    assert row["parsed_until_byte"] == source_path.stat().st_size
    assert row["parsed_row_count"] == 2
    assert row["source_device"] == f"fsid-v1:{source_path.stat().st_dev}"
    assert row["source_inode"] == f"fsid-v1:{source_path.stat().st_ino}"
    assert len(row["parsed_prefix_tail_hash"]) == 64
    assert row["source_generation"] == 1
    assert row["parser_adapter"] == PARSER_ADAPTER_VERSION
    assert json.loads(row["parser_state_json"])["session_id"] == "session"


def test_upsert_source_file_metadata_uses_parser_state_when_no_events(
    tmp_path: Path,
) -> None:
    conn = _memory_db()
    source_path = tmp_path / "empty.jsonl"
    source_path.write_text("{}\n", encoding="utf-8")
    state = ParserState(
        session_id="session",
        latest_record_id="state-record",
        latest_event_timestamp="2026-06-01T09:00:00Z",
    )

    upsert_source_file_metadata(
        conn.connection,
        parsed_files=[(source_path, [], {}, state)],
    )

    row = conn.execute(
        "SELECT latest_record_id, latest_event_timestamp FROM source_files WHERE source_file = ?",
        (str(source_path),),
    ).fetchone()
    assert dict(row) == {
        "latest_record_id": "state-record",
        "latest_event_timestamp": "2026-06-01T09:00:00Z",
    }
