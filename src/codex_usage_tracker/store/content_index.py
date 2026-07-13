"""Normalized local content indexing for Codex JSONL source logs."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from codex_usage_tracker.store.compression_revisions import touch_compression_revisions
from codex_usage_tracker.store.content_extract import (
    MAX_FRAGMENT_CHARS as MAX_FRAGMENT_CHARS,
)
from codex_usage_tracker.store.content_index_bulk import (
    add_content_index_result as _add_content_index_result,
)
from codex_usage_tracker.store.content_index_bulk import (
    deferred_content_indexes as _deferred_content_indexes,
)
from codex_usage_tracker.store.content_index_bulk import (
    emit_content_index_progress as _emit_content_index_progress,
)
from codex_usage_tracker.store.content_index_bulk import (
    index_content_entries as _index_content_entries,
)
from codex_usage_tracker.store.content_index_bulk import (
    index_precleaned_content_batches as _index_precleaned_content_batches,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexPlan as ContentIndexPlan,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexProgressCallback,
    _ExtractedContentRows,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexResult as ContentIndexResult,
)
from codex_usage_tracker.store.content_index_parallel import (
    index_content_for_source_plans_parallel as _index_content_for_source_plans_parallel,
)
from codex_usage_tracker.store.content_index_parallel import (
    parallel_content_index_worker_count as _parallel_content_index_worker_count,
)
from codex_usage_tracker.store.content_index_source import (
    index_content_for_source_file as _index_content_for_source_file,
)
from codex_usage_tracker.store.content_persistence import (
    CONTENT_INDEX_TABLES as CONTENT_INDEX_TABLES,
)
from codex_usage_tracker.store.content_persistence import (
    _clear_content_fts as _clear_content_fts,
)
from codex_usage_tracker.store.content_persistence import (
    _rebuild_content_fts as _rebuild_content_fts,
)
from codex_usage_tracker.store.content_persistence import (
    _upsert_sql as _upsert_sql,
)
from codex_usage_tracker.store.content_persistence import (
    clear_content_index_rows as clear_content_index_rows,
)
from codex_usage_tracker.store.content_persistence import (
    delete_content_index_rows_for_source_files as delete_content_index_rows_for_source_files,
)
from codex_usage_tracker.store.content_query import (
    DEFAULT_SEARCH_SNIPPET_CHARS as DEFAULT_SEARCH_SNIPPET_CHARS,
)
from codex_usage_tracker.store.content_rows import (
    PARSER_ADAPTER_NAME as PARSER_ADAPTER_NAME,
)
from codex_usage_tracker.store.content_search import (
    ContentSearchResult as ContentSearchResult,
)
from codex_usage_tracker.store.content_search import (
    search_content_fragments as search_content_fragments,
)
from codex_usage_tracker.store.content_trace import (
    ContentTraceResult as ContentTraceResult,
)
from codex_usage_tracker.store.content_trace import (
    trace_thread_content as trace_thread_content,
)


def index_content_for_source_files(
    conn: sqlite3.Connection,
    *,
    source_files: Iterable[Path],
) -> ContentIndexResult:
    """Populate normalized bounded local content rows for source files."""

    source_paths = list(dict.fromkeys(source_files))
    return index_content_for_source_plans(
        conn,
        plans=(
            ContentIndexPlan(source_path=source_path, replace_existing=True)
            for source_path in source_paths
        ),
    )


def index_content_for_source_plans(
    conn: sqlite3.Connection,
    *,
    plans: Iterable[ContentIndexPlan],
    progress_callback: ContentIndexProgressCallback | None = None,
    force_serial: bool = False,
) -> ContentIndexResult:
    """Populate normalized bounded local content rows using refresh parse plans."""

    source_plans = list(_dedupe_content_index_plans(plans))
    total_sources = len(source_plans)
    _emit_content_index_progress(
        progress_callback,
        status="running" if total_sources else "completed",
        completed=0,
        total=total_sources,
        message="Indexing local content",
        content_fragments=0,
    )
    defer_full_fts_rebuild = any(plan.replace_existing for plan in source_plans)
    worker_count = 1 if force_serial else _parallel_content_index_worker_count(source_plans)
    if worker_count > 1:
        result = _index_content_for_source_plans_parallel(
            conn,
            source_plans=source_plans,
            sync_fts=not defer_full_fts_rebuild,
            progress_callback=progress_callback,
            worker_count=worker_count,
        )
    else:
        result = _index_content_for_source_plans_serial(
            conn,
            source_plans=source_plans,
            sync_fts=not defer_full_fts_rebuild,
            progress_callback=progress_callback,
        )
    if source_plans:
        touch_compression_revisions(conn, {"commands", "files", "fragments", "tools"})
    return result


def index_preextracted_content_rows(
    conn: sqlite3.Connection,
    *,
    entries: Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]],
    progress_callback: ContentIndexProgressCallback | None = None,
    total_sources: int | None = None,
    defer_full_fts_rebuild: bool | None = None,
    replacement_cleanup_done: bool = False,
    write_batch_sources: int = 1,
    defer_secondary_indexes: bool = False,
) -> ContentIndexResult:
    """Persist parser-produced content rows with one deterministic SQLite writer."""
    extracted_entries, total_sources, defer_full_fts_rebuild = _normalize_preextracted_entries(
        entries,
        total_sources=total_sources,
        defer_full_fts_rebuild=defer_full_fts_rebuild,
    )
    _emit_content_index_progress(
        progress_callback,
        status="running" if total_sources else "completed",
        completed=0,
        total=total_sources,
        message="Indexing parser-produced content",
        content_fragments=0,
    )
    if _use_precleaned_bulk(
        replacement_cleanup_done=replacement_cleanup_done,
        write_batch_sources=write_batch_sources,
        defer_full_fts_rebuild=defer_full_fts_rebuild,
    ):
        return _index_precleaned_with_indexes(
            conn,
            entries=extracted_entries,
            total_sources=total_sources,
            defer_full_fts_rebuild=defer_full_fts_rebuild,
            write_batch_sources=write_batch_sources,
            defer_secondary_indexes=defer_secondary_indexes,
            progress_callback=progress_callback,
        )
    return _index_content_entries(
        conn,
        entries=extracted_entries,
        total_sources=total_sources,
        defer_full_fts_rebuild=defer_full_fts_rebuild,
        replacement_cleanup_done=replacement_cleanup_done,
        progress_callback=progress_callback,
    )


def _index_content_for_source_plans_serial(
    conn: sqlite3.Connection,
    *,
    source_plans: list[ContentIndexPlan],
    sync_fts: bool,
    progress_callback: ContentIndexProgressCallback | None,
) -> ContentIndexResult:
    totals = ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    needs_full_fts_rebuild = False
    total_sources = len(source_plans)
    for index, plan in enumerate(source_plans, start=1):
        result = _index_content_for_source_file(
            conn,
            source_path=plan.source_path,
            replace_existing=plan.replace_existing,
            start_byte=plan.start_byte,
            start_line=plan.start_line,
            sync_fts=sync_fts,
        )
        needs_full_fts_rebuild |= _replaced_source_with_rows(plan, result)
        totals = _add_content_index_result(totals, result)
        _emit_content_index_progress(
            progress_callback,
            status=_progress_status(index, total_sources),
            completed=index,
            total=total_sources,
            message="Indexed local content",
            content_fragments=totals.content_fragments,
            conversation_turns=totals.conversation_turns,
        )
    if needs_full_fts_rebuild:
        _rebuild_content_fts(conn)
    return totals


def _normalize_preextracted_entries(
    entries: Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]],
    *,
    total_sources: int | None,
    defer_full_fts_rebuild: bool | None,
) -> tuple[Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]], int, bool]:
    if total_sources is not None and defer_full_fts_rebuild is not None:
        return entries, total_sources, defer_full_fts_rebuild
    buffered_entries = list(entries)
    return (
        buffered_entries,
        len(buffered_entries),
        any(plan.replace_existing for plan, _rows in buffered_entries),
    )


def _use_precleaned_bulk(
    *,
    replacement_cleanup_done: bool,
    write_batch_sources: int,
    defer_full_fts_rebuild: bool,
) -> bool:
    return replacement_cleanup_done and write_batch_sources > 1 and defer_full_fts_rebuild


def _index_precleaned_with_indexes(
    conn: sqlite3.Connection,
    *,
    entries: Iterable[tuple[ContentIndexPlan, _ExtractedContentRows]],
    total_sources: int,
    defer_full_fts_rebuild: bool,
    write_batch_sources: int,
    defer_secondary_indexes: bool,
    progress_callback: ContentIndexProgressCallback | None,
) -> ContentIndexResult:
    with _deferred_content_indexes(conn, enabled=defer_secondary_indexes):
        return _index_precleaned_content_batches(
            conn,
            entries=entries,
            total_sources=total_sources,
            defer_full_fts_rebuild=defer_full_fts_rebuild,
            write_batch_sources=write_batch_sources,
            progress_callback=progress_callback,
        )


def _replaced_source_with_rows(
    plan: ContentIndexPlan,
    result: ContentIndexResult,
) -> bool:
    return plan.replace_existing and result.source_files > 0


def _progress_status(completed: int, total: int) -> str:
    return "running" if completed < total else "completed"


def _dedupe_content_index_plans(
    plans: Iterable[ContentIndexPlan],
) -> Iterable[ContentIndexPlan]:
    by_path: dict[Path, ContentIndexPlan] = {}
    for plan in plans:
        existing = by_path.get(plan.source_path)
        if existing is None or plan.replace_existing or plan.start_byte < existing.start_byte:
            by_path[plan.source_path] = plan
    return by_path.values()
