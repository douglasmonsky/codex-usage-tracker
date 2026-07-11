from __future__ import annotations

import json
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Any

from codex_usage_tracker.parser.state import (
    PARSER_ADAPTER_VERSION,
    ParserState,
    parser_state_to_json,
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
    grown_path.write_text("{}\n{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    _insert_source_metadata(conn.connection, unchanged_path, state=state)
    _insert_source_metadata(
        conn.connection,
        grown_path,
        size_bytes=len("{}\n"),
        parsed_until_byte=len("{}\n"),
        parsed_until_line=1,
        state=state,
    )

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


def _insert_source_metadata(
    conn: sqlite3.Connection,
    path: Path,
    *,
    state: ParserState,
    size_bytes: int | None = None,
    parsed_until_byte: int | None = None,
    parsed_until_line: int = 0,
) -> None:
    stat = path.stat()
    size = int(stat.st_size if size_bytes is None else size_bytes)
    parsed_byte = int(size if parsed_until_byte is None else parsed_until_byte)
    conn.execute(
        """
        INSERT INTO source_files (
            source_file_id,
            source_file,
            source_file_hash,
            is_archived,
            size_bytes,
            mtime_ns,
            parsed_until_line,
            parsed_until_byte,
            latest_record_id,
            latest_event_timestamp,
            parser_adapter,
            parser_diagnostics_json,
            parser_state_json,
            last_indexed_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            path.name,
            str(path),
            f"hash-{path.name}",
            0,
            size,
            int(stat.st_mtime_ns),
            parsed_until_line,
            parsed_byte,
            state.latest_record_id,
            state.latest_event_timestamp,
            PARSER_ADAPTER_VERSION,
            "{}",
            parser_state_to_json(state),
            "2026-06-01T00:00:00+00:00",
        ),
    )
