"""Bounded bulk persistence for parser-produced content rows."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager

from codex_usage_tracker.store.compression_revisions import touch_compression_revisions
from codex_usage_tracker.store.content_index_event_store import (
    PendingEventRows,
    upsert_pending_event_rows,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexPlan,
    ContentIndexProgressCallback,
    ContentIndexResult,
    _ExtractedContentRows,
)
from codex_usage_tracker.store.content_persistence import (
    CONTENT_INDEX_TABLES,
    _content_counts_for_source_file,
    _rebuild_content_fts,
    _sync_content_fts_for_source_file,
    _upsert_fragment_rows,
    _upsert_turn_rows,
    delete_content_index_rows_for_source_files,
)


def index_content_entries(
    conn: sqlite3.Connection,
    *,
    entries: Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]],
    total_sources: int,
    defer_full_fts_rebuild: bool,
    replacement_cleanup_done: bool,
    progress_callback: ContentIndexProgressCallback | None,
) -> ContentIndexResult:
    totals = ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    needs_full_fts_rebuild = False
    for index, (plan, extracted) in enumerate(entries, start=1):
        result = write_extracted_content_rows(
            conn,
            extracted=extracted,
            replace_existing=plan.replace_existing and not replacement_cleanup_done,
            sync_fts=not defer_full_fts_rebuild,
            start_line=0 if plan.replace_existing else plan.start_line,
        )
        needs_full_fts_rebuild |= plan.replace_existing and result.source_files > 0
        totals = add_content_index_result(totals, result)
        emit_content_index_progress(
            progress_callback,
            status="running" if index < total_sources else "completed",
            completed=index,
            total=total_sources,
            message="Indexed parser-produced content",
            content_fragments=totals.content_fragments,
            conversation_turns=totals.conversation_turns,
            workers=1,
        )
    if needs_full_fts_rebuild:
        _rebuild_content_fts(conn)
    if totals.source_files:
        touch_compression_revisions(conn, {"commands", "files", "fragments", "tools"})
    return totals


def write_extracted_content_rows(
    conn: sqlite3.Connection,
    *,
    extracted: _ExtractedContentRows,
    replace_existing: bool,
    sync_fts: bool,
    start_line: int,
) -> ContentIndexResult:
    if not extracted.has_usage_rows:
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    if replace_existing:
        delete_content_index_rows_for_source_files(
            conn,
            placeholders="?",
            source_files_to_replace=[extracted.source_path],
            sync_fts=sync_fts,
        )
    if extracted.turn_rows:
        _upsert_turn_rows(conn, extracted.turn_rows)
    if extracted.fragment_rows:
        _upsert_fragment_rows(conn, extracted.fragment_rows)
    upsert_pending_event_rows(conn, extracted.event_rows)
    _sync_extracted_fts(
        conn,
        source_path=extracted.source_path,
        replace_existing=replace_existing,
        sync_fts=sync_fts,
        start_line=start_line,
    )
    counts = _content_counts_for_source_file(conn, source_file=extracted.source_path)
    return ContentIndexResult(
        source_files=1,
        conversation_turns=counts["conversation_turns"],
        content_fragments=counts["content_fragments"],
        parse_warnings=extracted.parse_warnings,
    )


def index_precleaned_content_batches(
    conn: sqlite3.Connection,
    *,
    entries: Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]],
    total_sources: int,
    defer_full_fts_rebuild: bool,
    write_batch_sources: int,
    progress_callback: ContentIndexProgressCallback | None,
) -> ContentIndexResult:
    totals = ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    completed_sources = 0
    needs_full_fts_rebuild = False
    for batch in _batched_preextracted_entries(entries, size=write_batch_sources):
        result = _write_precleaned_content_batch(conn, batch)
        totals = add_content_index_result(totals, result)
        completed_sources += len(batch)
        needs_full_fts_rebuild = needs_full_fts_rebuild or any(
            plan.replace_existing and extracted.has_usage_rows for plan, extracted in batch
        )
        emit_content_index_progress(
            progress_callback,
            status="running" if completed_sources < total_sources else "completed",
            completed=completed_sources,
            total=total_sources,
            message="Indexed parser-produced content",
            content_fragments=totals.content_fragments,
            conversation_turns=totals.conversation_turns,
            workers=1,
        )
    if needs_full_fts_rebuild and defer_full_fts_rebuild:
        _rebuild_content_fts(conn)
    if totals.source_files:
        touch_compression_revisions(conn, {"commands", "files", "fragments", "tools"})
    return totals


@contextmanager
def deferred_content_indexes(
    conn: sqlite3.Connection,
    *,
    enabled: bool,
) -> Iterator[None]:
    if not enabled:
        yield
        return
    placeholders = ", ".join("?" for _table in CONTENT_INDEX_TABLES)
    indexes = [
        (str(row["name"]), str(row["sql"]))
        for row in conn.execute(
            f"""
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'index'
              AND tbl_name IN ({placeholders})
              AND sql IS NOT NULL
            ORDER BY name
            """,  # nosec B608 - fixed schema table list
            CONTENT_INDEX_TABLES,
        )
    ]
    for name, _sql in indexes:
        quoted_name = name.replace('"', '""')
        conn.execute(f'DROP INDEX "{quoted_name}"')  # nosec B608 - schema-owned name
    try:
        yield
    finally:
        for _name, sql in indexes:
            conn.execute(sql)


def add_content_index_result(
    left: ContentIndexResult,
    right: ContentIndexResult,
) -> ContentIndexResult:
    return ContentIndexResult(
        source_files=left.source_files + right.source_files,
        conversation_turns=left.conversation_turns + right.conversation_turns,
        content_fragments=left.content_fragments + right.content_fragments,
        parse_warnings=left.parse_warnings + right.parse_warnings,
    )


def emit_content_index_progress(
    progress_callback: ContentIndexProgressCallback | None,
    *,
    status: str,
    completed: int,
    total: int,
    message: str,
    **extra: object,
) -> None:
    if progress_callback is None:
        return
    percent = 100.0 if total <= 0 else round(min(100.0, (completed / total) * 100.0), 1)
    payload: dict[str, object] = {
        "schema": "codex-usage-tracker-refresh-progress-v1",
        "phase": "indexing_content",
        "status": status,
        "message": message,
        "completed": completed,
        "total": total,
        "percent": percent,
    }
    payload.update(extra)
    progress_callback(payload)


def _batched_preextracted_entries(
    entries: Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]],
    *,
    size: int,
) -> Iterator[list[tuple[ContentIndexPlan, _ExtractedContentRows]]]:
    batch: list[tuple[ContentIndexPlan, _ExtractedContentRows]] = []
    for entry in entries:
        batch.append(entry)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _write_precleaned_content_batch(
    conn: sqlite3.Connection,
    entries: list[tuple[ContentIndexPlan, _ExtractedContentRows]],
) -> ContentIndexResult:
    extracted_rows = [extracted for _plan, extracted in entries if extracted.has_usage_rows]
    turn_rows = _flatten_content_rows(extracted_rows, "turn_rows")
    fragment_rows = _flatten_content_rows(extracted_rows, "fragment_rows")
    event_rows = PendingEventRows(
        tool_call_rows=_flatten_event_rows(extracted_rows, "tool_call_rows"),
        command_run_rows=_flatten_event_rows(extracted_rows, "command_run_rows"),
        file_event_rows=_flatten_event_rows(extracted_rows, "file_event_rows"),
    )
    if turn_rows:
        _upsert_turn_rows(conn, turn_rows)
    if fragment_rows:
        _upsert_fragment_rows(conn, fragment_rows)
    upsert_pending_event_rows(conn, event_rows)
    return ContentIndexResult(
        source_files=len(extracted_rows),
        conversation_turns=len(turn_rows),
        content_fragments=len(fragment_rows),
        parse_warnings=sum(extracted.parse_warnings for extracted in extracted_rows),
    )


def _sync_extracted_fts(
    conn: sqlite3.Connection,
    *,
    source_path: str,
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
        source_file=source_path,
        min_line_start=start_line + 1,
    )


def _flatten_content_rows(
    extracted_rows: list[_ExtractedContentRows],
    attribute: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for extracted in extracted_rows:
        rows.extend(getattr(extracted, attribute))
    return rows


def _flatten_event_rows(
    extracted_rows: list[_ExtractedContentRows],
    attribute: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for extracted in extracted_rows:
        rows.extend(getattr(extracted.event_rows, attribute))
    return rows
