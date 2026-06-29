from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_usage_tracker.parser_state import (
    PARSER_ADAPTER_VERSION,
    ParserState,
    parser_state_to_json,
)
from codex_usage_tracker.store_schema import init_db
from codex_usage_tracker.store_sources import source_logs_requiring_parse


def test_source_logs_requiring_parse_classifies_new_unchanged_and_append_only(
    tmp_path: Path,
) -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_db(conn)
    new_path = tmp_path / "new.jsonl"
    unchanged_path = tmp_path / "unchanged.jsonl"
    grown_path = tmp_path / "grown.jsonl"
    new_path.write_text("{}\n", encoding="utf-8")
    unchanged_path.write_text("{}\n", encoding="utf-8")
    grown_path.write_text("{}\n{}\n", encoding="utf-8")
    state = ParserState(session_id="session")
    _insert_source_metadata(conn, unchanged_path, state=state)
    _insert_source_metadata(
        conn,
        grown_path,
        size_bytes=len("{}\n"),
        parsed_until_byte=len("{}\n"),
        parsed_until_line=1,
        state=state,
    )

    plans = source_logs_requiring_parse(
        conn, [new_path, unchanged_path, grown_path, tmp_path / "missing.jsonl"]
    )

    by_path = {plan.path: plan for plan in plans}
    assert set(by_path) == {new_path, grown_path}
    assert by_path[new_path].replace_existing is True
    assert by_path[grown_path].replace_existing is False
    assert by_path[grown_path].start_byte == len("{}\n")
    assert by_path[grown_path].start_line == 1
    assert by_path[grown_path].initial_state == state


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
