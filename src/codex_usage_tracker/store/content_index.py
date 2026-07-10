"""Normalized local content indexing for Codex JSONL source logs."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from codex_usage_tracker.parser.state import optional_str
from codex_usage_tracker.store.content_extract import (
    MAX_FRAGMENT_CHARS as MAX_FRAGMENT_CHARS,
)
from codex_usage_tracker.store.content_extract import (
    _extract_content_rows_for_source_file,
    _extract_pending_fragments,
    _is_token_count,
)
from codex_usage_tracker.store.content_index_event_store import upsert_pending_event_rows
from codex_usage_tracker.store.content_index_events import (
    PendingCommandRun,
    PendingFileEvent,
    PendingToolCall,
    extract_pending_local_events,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexPlan as ContentIndexPlan,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexProgressCallback,
    _ExtractedContentRows,
    _PendingContentRows,
    _PendingFragment,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexResult as ContentIndexResult,
)
from codex_usage_tracker.store.content_provenance import (
    _content_usage_rows_for_plans,
    _usage_rows_by_token_line,
)
from codex_usage_tracker.store.content_query import (
    DEFAULT_SEARCH_SNIPPET_CHARS as DEFAULT_SEARCH_SNIPPET_CHARS,
)
from codex_usage_tracker.store.content_rows import (
    PARSER_ADAPTER_NAME as PARSER_ADAPTER_NAME,
)
from codex_usage_tracker.store.content_rows import (
    _append_pending_content_rows,
    _empty_pending_content_rows,
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

_CONTENT_WRITE_BATCH_RECORDS = 250
_PARALLEL_CONTENT_INDEX_WORKERS_ENV = "CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS"
_PARALLEL_CONTENT_INDEX_MIN_FILES = 4
_PARALLEL_CONTENT_INDEX_MAX_WORKERS = 8
CONTENT_INDEX_TABLES = (
    "content_fragments",
    "file_events",
    "command_runs",
    "tool_calls",
    "conversation_turns",
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
) -> ContentIndexResult:
    """Populate normalized bounded local content rows using refresh parse plans."""

    source_plans = list(_dedupe_content_index_plans(plans))
    total_sources = len(source_plans)
    _emit_content_index_progress(
        progress_callback,
        status="running",
        completed=0,
        total=total_sources,
        message="Indexing local content",
        content_fragments=0,
    )
    defer_full_fts_rebuild = any(plan.replace_existing for plan in source_plans)
    worker_count = _parallel_content_index_worker_count(len(source_plans))
    if worker_count > 1:
        return _index_content_for_source_plans_parallel(
            conn,
            source_plans=source_plans,
            sync_fts=not defer_full_fts_rebuild,
            progress_callback=progress_callback,
            worker_count=worker_count,
        )
    return _index_content_for_source_plans_serial(
        conn,
        source_plans=source_plans,
        sync_fts=not defer_full_fts_rebuild,
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
        needs_full_fts_rebuild = needs_full_fts_rebuild or (
            plan.replace_existing and result.source_files > 0
        )
        totals = _add_content_index_result(totals, result)
        _emit_content_index_progress(
            progress_callback,
            status="running" if index < total_sources else "completed",
            completed=index,
            total=total_sources,
            message="Indexed local content",
            content_fragments=totals.content_fragments,
            conversation_turns=totals.conversation_turns,
        )
    if needs_full_fts_rebuild:
        _rebuild_content_fts(conn)
    return totals


def _index_content_for_source_plans_parallel(
    conn: sqlite3.Connection,
    *,
    source_plans: list[ContentIndexPlan],
    sync_fts: bool,
    progress_callback: ContentIndexProgressCallback | None,
    worker_count: int,
) -> ContentIndexResult:
    usage_rows_by_path = _content_usage_rows_for_plans(conn, source_plans=source_plans)
    totals = ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)
    needs_full_fts_rebuild = False
    completed = 0
    total_sources = len(source_plans)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _extract_content_rows_for_source_file,
                source_path=plan.source_path,
                usage_rows=usage_rows_by_path.get(str(plan.source_path), {}),
                start_byte=0 if plan.replace_existing else plan.start_byte,
                start_line=0 if plan.replace_existing else plan.start_line,
            ): plan
            for plan in source_plans
        }
        for future in as_completed(futures):
            plan = futures[future]
            extracted = future.result()
            result = _write_extracted_content_rows(
                conn,
                extracted=extracted,
                replace_existing=plan.replace_existing,
                sync_fts=sync_fts,
                start_line=0 if plan.replace_existing else plan.start_line,
            )
            needs_full_fts_rebuild = needs_full_fts_rebuild or (
                plan.replace_existing and result.source_files > 0
            )
            totals = _add_content_index_result(totals, result)
            completed += 1
            _emit_content_index_progress(
                progress_callback,
                status="running" if completed < total_sources else "completed",
                completed=completed,
                total=total_sources,
                message="Indexed local content",
                content_fragments=totals.content_fragments,
                conversation_turns=totals.conversation_turns,
                workers=worker_count,
            )
    if needs_full_fts_rebuild:
        _rebuild_content_fts(conn)
    return totals


def _add_content_index_result(
    left: ContentIndexResult,
    right: ContentIndexResult,
) -> ContentIndexResult:
    return ContentIndexResult(
        source_files=left.source_files + right.source_files,
        conversation_turns=left.conversation_turns + right.conversation_turns,
        content_fragments=left.content_fragments + right.content_fragments,
        parse_warnings=left.parse_warnings + right.parse_warnings,
    )


def _emit_content_index_progress(
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


def _dedupe_content_index_plans(
    plans: Iterable[ContentIndexPlan],
) -> Iterable[ContentIndexPlan]:
    by_path: dict[Path, ContentIndexPlan] = {}
    for plan in plans:
        existing = by_path.get(plan.source_path)
        if existing is None or plan.replace_existing or plan.start_byte < existing.start_byte:
            by_path[plan.source_path] = plan
    return by_path.values()


def clear_content_index_rows(conn: sqlite3.Connection) -> None:
    """Clear normalized content index rows while tolerating unavailable FTS5."""

    _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(f"DELETE FROM {table_name}")


def delete_content_index_rows_for_source_files(
    conn: sqlite3.Connection,
    *,
    placeholders: str,
    source_files_to_replace: list[str],
    sync_fts: bool = True,
) -> None:
    """Delete normalized content rows linked to source files."""

    record_subquery = f"SELECT record_id FROM usage_events WHERE source_file IN ({placeholders})"
    if sync_fts:
        _clear_content_fts(conn)
    for table_name in CONTENT_INDEX_TABLES:
        conn.execute(
            f"DELETE FROM {table_name} WHERE record_id IN ({record_subquery})",
            source_files_to_replace,
        )
    if sync_fts:
        _rebuild_content_fts(conn)


def _write_extracted_content_rows(
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

    if sync_fts:
        if replace_existing:
            _rebuild_content_fts(conn)
        else:
            _sync_content_fts_for_source_file(
                conn,
                source_file=extracted.source_path,
                min_line_start=start_line + 1,
            )
    counts = _content_counts_for_source_file(conn, source_file=extracted.source_path)
    return ContentIndexResult(
        source_files=1,
        conversation_turns=counts["conversation_turns"],
        content_fragments=counts["content_fragments"],
        parse_warnings=extracted.parse_warnings,
    )


def _parallel_content_index_worker_count(plan_count: int) -> int:
    if plan_count < _PARALLEL_CONTENT_INDEX_MIN_FILES:
        return 1
    configured = _configured_parallel_content_index_workers()
    if configured is not None:
        return min(plan_count, configured)
    return min(plan_count, max(1, os.cpu_count() or 1), _PARALLEL_CONTENT_INDEX_MAX_WORKERS)


def _configured_parallel_content_index_workers() -> int | None:
    raw_value = os.environ.get(_PARALLEL_CONTENT_INDEX_WORKERS_ENV)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        return max(1, int(raw_value))
    except ValueError:
        return None


def _index_content_for_source_file(
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
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)

    if replace_existing:
        start_byte = 0
        start_line = 0
        delete_content_index_rows_for_source_files(
            conn,
            placeholders="?",
            source_files_to_replace=[str(source_path)],
            sync_fts=sync_fts,
        )
    pending: list[_PendingFragment] = []
    pending_tool_calls: list[PendingToolCall] = []
    pending_command_runs: list[PendingCommandRun] = []
    pending_file_events: list[PendingFileEvent] = []
    pending_rows = _empty_pending_content_rows()
    turn_id: str | None = None
    turn_index = 0
    parse_warnings = 0
    try:
        with source_path.open("rb") as handle:
            if start_byte > 0:
                handle.seek(start_byte)
            for line_number, raw_line in enumerate(handle, start_line + 1):
                try:
                    envelope = json.loads(raw_line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    parse_warnings += 1
                    continue
                if not isinstance(envelope, dict):
                    parse_warnings += 1
                    continue
                payload = envelope.get("payload")
                if not isinstance(payload, dict):
                    parse_warnings += 1
                    continue
                entry_type = envelope.get("type")
                timestamp = optional_str(envelope.get("timestamp"))
                if entry_type == "turn_context":
                    turn_id = optional_str(payload.get("turn_id"))
                    turn_index += 1
                    continue
                if _is_token_count(entry_type, payload):
                    usage_row = usage_rows.get(line_number)
                    if usage_row is not None:
                        _append_pending_content_rows(
                            pending_rows,
                            pending=pending,
                            tool_calls=pending_tool_calls,
                            command_runs=pending_command_runs,
                            file_events=pending_file_events,
                            usage_row=usage_row,
                        )
                        if pending_rows.linked_records >= _CONTENT_WRITE_BATCH_RECORDS:
                            _flush_pending_content_rows(conn, pending_rows)
                        pending = []
                        pending_tool_calls = []
                        pending_command_runs = []
                        pending_file_events = []
                    continue
                pending.extend(
                    _extract_pending_fragments(
                        envelope=envelope,
                        payload=payload,
                        line_number=line_number,
                        timestamp=timestamp,
                        turn_id=turn_id,
                        turn_index=turn_index,
                    )
                )
                events = extract_pending_local_events(
                    envelope=envelope,
                    payload=payload,
                    line_number=line_number,
                    timestamp=timestamp,
                )
                pending_tool_calls.extend(events.tool_calls)
                pending_command_runs.extend(events.command_runs)
                pending_file_events.extend(events.file_events)
    except OSError:
        return ContentIndexResult(source_files=0, conversation_turns=0, content_fragments=0)

    _flush_pending_content_rows(conn, pending_rows)

    if sync_fts:
        if replace_existing:
            _rebuild_content_fts(conn)
        else:
            _sync_content_fts_for_source_file(
                conn,
                source_file=str(source_path),
                min_line_start=start_line + 1,
            )
    counts = _content_counts_for_source_file(conn, source_file=str(source_path))
    return ContentIndexResult(
        source_files=1,
        conversation_turns=counts["conversation_turns"],
        content_fragments=counts["content_fragments"],
        parse_warnings=parse_warnings,
    )


def _flush_pending_content_rows(
    conn: sqlite3.Connection,
    batch: _PendingContentRows,
) -> None:
    if batch.turn_rows:
        _upsert_turn_rows(conn, batch.turn_rows)
    if batch.fragment_rows:
        _upsert_fragment_rows(conn, batch.fragment_rows)
    upsert_pending_event_rows(conn, batch.event_rows)
    batch.turn_rows.clear()
    batch.fragment_rows.clear()
    batch.event_rows.tool_call_rows.clear()
    batch.event_rows.command_run_rows.clear()
    batch.event_rows.file_event_rows.clear()
    batch.linked_records = 0


def _upsert_turn_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "turn_key",
        "record_id",
        "session_id",
        "turn_id",
        "turn_index",
        "role",
        "event_timestamp",
        "source_record_hash",
        "source_file_id",
        "line_start",
        "line_end",
        "content_hash",
        "content_size_bytes",
        "indexed_content_included",
        "parser_adapter",
        "parser_version",
        "parse_warnings_json",
    )
    conn.executemany(
        _upsert_sql("conversation_turns", columns, "turn_key"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_fragment_rows(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    columns = (
        "fragment_id",
        "record_id",
        "turn_key",
        "fragment_kind",
        "role",
        "safe_label",
        "content_hash",
        "content_size_bytes",
        "fragment_text",
        "includes_raw_fragment",
        "source_file_id",
        "line_start",
        "line_end",
        "token_link_record_id",
        "created_at",
    )
    conn.executemany(
        _upsert_sql("content_fragments", columns, "fragment_id"),
        ([row[column] for column in columns] for row in rows),
    )


def _upsert_sql(table_name: str, columns: tuple[str, ...], primary_key: str) -> str:
    placeholders = ", ".join("?" for _column in columns)
    update_clause = ", ".join(
        f"{column}=excluded.{column}" for column in columns if column != primary_key
    )
    return (
        f"INSERT INTO {table_name} ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT({primary_key}) DO UPDATE SET {update_clause}"
    )


def _rebuild_content_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
        conn.execute(
            """
            INSERT INTO content_fts(rowid, fragment_text, safe_label, fragment_kind)
            SELECT fragment_rowid, fragment_text, safe_label, fragment_kind
            FROM content_fragments
            WHERE fragment_text != ''
            """
        )
    except sqlite3.DatabaseError:
        return


def _sync_content_fts_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    min_line_start: int,
) -> None:
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO content_fts(rowid, fragment_text, safe_label, fragment_kind)
            SELECT cf.fragment_rowid, cf.fragment_text, cf.safe_label, cf.fragment_kind
            FROM content_fragments cf
            JOIN usage_events u ON u.record_id = cf.record_id
            WHERE u.source_file = ?
              AND cf.line_start >= ?
              AND cf.fragment_text != ''
            """,
            (source_file, min_line_start),
        )
    except sqlite3.DatabaseError:
        return


def _clear_content_fts(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("INSERT INTO content_fts(content_fts) VALUES ('delete-all')")
    except sqlite3.DatabaseError:
        return


def _content_counts_for_source_file(
    conn: sqlite3.Connection,
    *,
    source_file: str,
) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT
            (SELECT COUNT(*)
             FROM conversation_turns
             WHERE record_id IN (
                 SELECT record_id FROM usage_events WHERE source_file = ?
             )) AS conversation_turns,
            (SELECT COUNT(*)
             FROM content_fragments
             WHERE record_id IN (
                 SELECT record_id FROM usage_events WHERE source_file = ?
             )) AS content_fragments
        """,
        (source_file, source_file),
    ).fetchone()
    if rows is None:
        return {"conversation_turns": 0, "content_fragments": 0}
    return {
        "conversation_turns": int(rows["conversation_turns"] or 0),
        "content_fragments": int(rows["content_fragments"] or 0),
    }
