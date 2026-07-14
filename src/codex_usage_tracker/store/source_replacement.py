"""Batch-safe cleanup helpers for replaced source logs."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

from codex_usage_tracker.store.compression_fact_sync import (
    delete_compression_facts_for_source_files,
)
from codex_usage_tracker.store.content_index import (
    _clear_content_fts,
    _rebuild_content_fts,
    delete_content_index_rows_for_source_files,
)

_SOURCE_FILE_SQL_BATCH_SIZE = 400


def source_file_strings(replace_source_files: Iterable[Path] | None) -> list[str]:
    return list(dict.fromkeys(str(path) for path in replace_source_files or []))


def delete_usage_events_for_source_files(
    conn: sqlite3.Connection,
    source_files_to_replace: list[str],
    *,
    sync_content_fts: bool = True,
) -> None:
    if not source_files_to_replace:
        return
    if sync_content_fts:
        _clear_content_fts(conn)
    for source_batch in _source_file_batches(source_files_to_replace):
        _delete_source_batch(conn, source_batch)
    if sync_content_fts:
        _rebuild_content_fts(conn)


def thread_keys_for_source_files(
    conn: sqlite3.Connection,
    source_files_to_replace: list[str],
) -> set[str]:
    thread_keys: set[str] = set()
    for source_batch in _source_file_batches(source_files_to_replace):
        placeholders = ", ".join("?" for _source in source_batch)
        rows = conn.execute(
            f"""
            SELECT thread_key, session_id
            FROM usage_events
            WHERE source_file IN ({placeholders})
            """,  # nosec B608 - generated placeholders
            source_batch,
        ).fetchall()
        thread_keys.update(thread_keys_for_usage_rows(rows))
    return thread_keys


def thread_keys_for_usage_rows(
    rows: Iterable[Mapping[str, object] | sqlite3.Row],
) -> set[str]:
    keys: set[str] = set()
    for row in rows:
        session_id = _usage_row_value(row, "session_id")
        thread_key = _usage_row_value(row, "thread_key") or (
            f"session:{session_id}" if session_id else None
        )
        if thread_key:
            keys.add(str(thread_key))
    return keys


def _delete_source_batch(conn: sqlite3.Connection, source_batch: list[str]) -> None:
    placeholders = ", ".join("?" for _source in source_batch)
    delete_content_index_rows_for_source_files(
        conn,
        placeholders=placeholders,
        source_files_to_replace=source_batch,
        sync_fts=False,
    )
    delete_compression_facts_for_source_files(conn, source_files=source_batch)
    for table_name in (
        "allowance_observations",
        "source_records",
        "call_diagnostic_facts",
        "recommendation_facts",
    ):
        conn.execute(
            f"""
            DELETE FROM {table_name}
            WHERE record_id IN (
                SELECT record_id
                FROM usage_events
                WHERE source_file IN ({placeholders})
            )
            """,  # nosec B608 - fixed table names and generated placeholders
            source_batch,
        )
    conn.execute(
        f"DELETE FROM usage_events WHERE source_file IN ({placeholders})",  # nosec B608
        source_batch,
    )


def _source_file_batches(source_files: list[str]) -> Iterator[list[str]]:
    for start in range(0, len(source_files), _SOURCE_FILE_SQL_BATCH_SIZE):
        yield source_files[start : start + _SOURCE_FILE_SQL_BATCH_SIZE]


def _usage_row_value(
    row: Mapping[str, object] | sqlite3.Row,
    key: str,
) -> object | None:
    if isinstance(row, sqlite3.Row):
        try:
            return row[key]
        except (IndexError, KeyError, TypeError):
            return None
    return row.get(key)
