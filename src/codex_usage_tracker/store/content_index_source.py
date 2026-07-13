"""Serial source-file content indexing fallback."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_usage_tracker.store.content_extract import _decode_content_envelope
from codex_usage_tracker.store.content_index_models import ContentIndexResult
from codex_usage_tracker.store.content_index_stream import (
    _flush_pending_content_rows,
    _StreamingContentAccumulator,
)
from codex_usage_tracker.store.content_persistence import (
    _content_counts_for_source_file,
    _rebuild_content_fts,
    _sync_content_fts_for_source_file,
    delete_content_index_rows_for_source_files,
)
from codex_usage_tracker.store.content_provenance import _usage_rows_by_token_line


def index_content_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    replace_existing: bool = True,
    start_byte: int = 0,
    start_line: int = 0,
    sync_fts: bool = True,
) -> ContentIndexResult:
    usage_rows = _usage_rows_by_token_line(
        conn,
        source_file=str(source_path),
        min_line_number=None if replace_existing else start_line + 1,
    )
    if not usage_rows:
        return ContentIndexResult(0, 0, 0)
    start_byte, start_line = _prepare_source_rows(
        conn,
        source_path=source_path,
        replace_existing=replace_existing,
        sync_fts=sync_fts,
        start_byte=start_byte,
        start_line=start_line,
    )
    accumulator = _stream_content_rows(
        conn,
        source_path=source_path,
        start_byte=start_byte,
        start_line=start_line,
        usage_rows=usage_rows,
    )
    if accumulator is None:
        return ContentIndexResult(0, 0, 0)
    _flush_pending_content_rows(conn, accumulator.rows)
    _sync_source_fts(
        conn,
        source_path=source_path,
        replace_existing=replace_existing,
        sync_fts=sync_fts,
        start_line=start_line,
    )
    counts = _content_counts_for_source_file(conn, source_file=str(source_path))
    return ContentIndexResult(
        source_files=1,
        conversation_turns=counts["conversation_turns"],
        content_fragments=counts["content_fragments"],
        parse_warnings=accumulator.parse_warnings,
    )


def _prepare_source_rows(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    replace_existing: bool,
    sync_fts: bool,
    start_byte: int,
    start_line: int,
) -> tuple[int, int]:
    if not replace_existing:
        return start_byte, start_line
    delete_content_index_rows_for_source_files(
        conn,
        placeholders="?",
        source_files_to_replace=[str(source_path)],
        sync_fts=sync_fts,
    )
    return 0, 0


def _stream_content_rows(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    start_byte: int,
    start_line: int,
    usage_rows: dict[int, sqlite3.Row],
) -> _StreamingContentAccumulator | None:
    accumulator = _StreamingContentAccumulator()
    try:
        with source_path.open("rb") as handle:
            if start_byte > 0:
                handle.seek(start_byte)
            for line_number, raw_line in enumerate(handle, start_line + 1):
                decoded = _decode_content_envelope(raw_line)
                if decoded is None:
                    accumulator.parse_warnings += 1
                    continue
                envelope, payload = decoded
                accumulator.consume(
                    conn,
                    envelope=envelope,
                    payload=payload,
                    line_number=line_number,
                    usage_row=usage_rows.get(line_number),
                )
    except OSError:
        return None
    return accumulator


def _sync_source_fts(
    conn: sqlite3.Connection,
    *,
    source_path: Path,
    replace_existing: bool,
    sync_fts: bool,
    start_line: int,
) -> None:
    if not sync_fts:
        return
    if replace_existing:
        _rebuild_content_fts(conn)
        return
    _sync_content_fts_for_source_file(
        conn,
        source_file=str(source_path),
        min_line_start=start_line + 1,
    )
