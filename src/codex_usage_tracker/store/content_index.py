"""Normalized local content indexing for Codex JSONL source logs."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.parser.state import PARSER_ADAPTER_VERSION, optional_str
from codex_usage_tracker.store.content_index_event_store import (
    PendingEventRows,
    pending_event_rows,
    upsert_pending_event_rows,
)
from codex_usage_tracker.store.content_index_events import (
    PendingCommandRun,
    PendingFileEvent,
    PendingToolCall,
    extract_pending_local_events,
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

MAX_FRAGMENT_CHARS = 4000
DEFAULT_SEARCH_SNIPPET_CHARS = 800
PARSER_ADAPTER_NAME = "codex-jsonl"
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


@dataclass(frozen=True)
class ContentIndexResult:
    """Content indexing counts for one refresh operation."""

    source_files: int
    conversation_turns: int
    content_fragments: int
    parse_warnings: int = 0


@dataclass(frozen=True)
class ContentIndexPlan:
    """Plan for full or append-only content indexing of a source log."""

    source_path: Path
    replace_existing: bool = True
    start_byte: int = 0
    start_line: int = 0


@dataclass(frozen=True)
class _PendingFragment:
    role: str
    fragment_kind: str
    safe_label: str
    text: str
    line_start: int
    line_end: int
    turn_id: str | None
    turn_index: int
    event_timestamp: str | None


@dataclass
class _PendingContentRows:
    turn_rows: list[dict[str, object]]
    fragment_rows: list[dict[str, object]]
    event_rows: PendingEventRows
    linked_records: int = 0


@dataclass(frozen=True)
class _ExtractedContentRows:
    source_path: str
    has_usage_rows: bool
    turn_rows: list[dict[str, object]]
    fragment_rows: list[dict[str, object]]
    event_rows: PendingEventRows
    parse_warnings: int = 0


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


ContentIndexProgressCallback = Callable[[dict[str, object]], None]
UsageContentRow = sqlite3.Row | Mapping[str, object]


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


def _content_usage_rows_for_plans(
    conn: sqlite3.Connection,
    *,
    source_plans: list[ContentIndexPlan],
) -> dict[str, dict[int, dict[str, object]]]:
    rows_by_path: dict[str, dict[int, dict[str, object]]] = {}
    for plan in source_plans:
        rows_by_path[str(plan.source_path)] = {
            line_number: dict(row)
            for line_number, row in _usage_rows_by_token_line(
                conn,
                source_file=str(plan.source_path),
                min_line_number=None if plan.replace_existing else plan.start_line + 1,
            ).items()
        }
    return rows_by_path


def _extract_content_rows_for_source_file(
    *,
    source_path: Path,
    usage_rows: Mapping[int, Mapping[str, object]],
    start_byte: int,
    start_line: int,
) -> _ExtractedContentRows:
    if not usage_rows:
        return _empty_extracted_content_rows(source_path=source_path, has_usage_rows=False)

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
        return _empty_extracted_content_rows(source_path=source_path, has_usage_rows=False)

    return _ExtractedContentRows(
        source_path=str(source_path),
        has_usage_rows=True,
        turn_rows=pending_rows.turn_rows,
        fragment_rows=pending_rows.fragment_rows,
        event_rows=pending_rows.event_rows,
        parse_warnings=parse_warnings,
    )


def _empty_extracted_content_rows(
    *,
    source_path: Path,
    has_usage_rows: bool,
) -> _ExtractedContentRows:
    empty_rows = _empty_pending_content_rows()
    return _ExtractedContentRows(
        source_path=str(source_path),
        has_usage_rows=has_usage_rows,
        turn_rows=[],
        fragment_rows=[],
        event_rows=empty_rows.event_rows,
    )


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


def _usage_rows_by_token_line(
    conn: sqlite3.Connection,
    *,
    source_file: str,
    min_line_number: int | None = None,
) -> dict[int, sqlite3.Row]:
    line_filter = "" if min_line_number is None else "AND u.line_number >= ?"
    params: list[object] = [source_file]
    if min_line_number is not None:
        params.append(min_line_number)
    rows = conn.execute(
        f"""
        SELECT
            u.record_id,
            u.session_id,
            u.turn_id,
            u.event_timestamp,
            u.source_file,
            u.line_number,
            sr.source_file_id,
            sr.source_record_hash,
            sr.parser_adapter,
            sr.parser_version
        FROM usage_events AS u
        JOIN source_records AS sr ON sr.record_id = u.record_id
        WHERE u.source_file = ?
          {line_filter}
        ORDER BY u.line_number
        """,
        params,
    ).fetchall()
    return {int(row["line_number"]): row for row in rows}


def _extract_pending_fragments(
    *,
    envelope: dict[str, Any],
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    entry_type = envelope.get("type")
    payload_type = optional_str(payload.get("type")) or ""
    if entry_type == "response_item":
        return _response_item_fragments(
            payload=payload,
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    if entry_type == "compacted":
        return _compaction_fragments(
            payload=payload,
            payload_type="compacted",
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    if entry_type == "event_msg" and payload_type == "context_compacted":
        return _compaction_fragments(
            payload=payload,
            payload_type="context_compacted",
            line_number=line_number,
            timestamp=timestamp,
            turn_id=turn_id,
            turn_index=turn_index,
        )
    return []


def _response_item_fragments(
    *,
    payload: dict[str, Any],
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    payload_type = optional_str(payload.get("type")) or "response_item"
    role = optional_str(payload.get("role")) or _role_from_payload_type(payload_type)
    fragments: list[_PendingFragment] = []
    for index, text in enumerate(_content_texts(payload.get("content"))):
        fragments.append(
            _pending_fragment(
                role=role,
                fragment_kind="message",
                safe_label=f"response_item.{payload_type}.{role}.{index}",
                text=text,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    for index, text in enumerate(_reasoning_summary_texts(payload.get("summary"))):
        fragments.append(
            _pending_fragment(
                role="reasoning",
                fragment_kind="reasoning_summary",
                safe_label=f"response_item.{payload_type}.reasoning_summary.{index}",
                text=text,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    return fragments


def _compaction_fragments(
    *,
    payload: dict[str, Any],
    payload_type: str,
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> list[_PendingFragment]:
    fragments: list[_PendingFragment] = []
    message = optional_str(payload.get("message"))
    if message:
        fragments.append(
            _pending_fragment(
                role="system",
                fragment_kind="compaction",
                safe_label=f"{payload_type}.message",
                text=message,
                line_number=line_number,
                timestamp=timestamp,
                turn_id=turn_id,
                turn_index=turn_index,
            )
        )
    for index, item in enumerate(_message_history(payload.get("replacement_history"))):
        role = optional_str(item.get("role")) or "unknown"
        for content_index, text in enumerate(_content_texts(item.get("content"))):
            fragments.append(
                _pending_fragment(
                    role=role,
                    fragment_kind="compaction_history",
                    safe_label=f"{payload_type}.replacement_history.{role}.{index}.{content_index}",
                    text=text,
                    line_number=line_number,
                    timestamp=timestamp,
                    turn_id=turn_id,
                    turn_index=turn_index,
                )
            )
    return fragments


def _pending_fragment(
    *,
    role: str,
    fragment_kind: str,
    safe_label: str,
    text: str,
    line_number: int,
    timestamp: str | None,
    turn_id: str | None,
    turn_index: int,
) -> _PendingFragment:
    return _PendingFragment(
        role=role,
        fragment_kind=fragment_kind,
        safe_label=safe_label,
        text=text[:MAX_FRAGMENT_CHARS],
        line_start=line_number,
        line_end=line_number,
        turn_id=turn_id,
        turn_index=turn_index,
        event_timestamp=timestamp,
    )


def _empty_pending_content_rows() -> _PendingContentRows:
    return _PendingContentRows(
        turn_rows=[],
        fragment_rows=[],
        event_rows=PendingEventRows(
            tool_call_rows=[],
            command_run_rows=[],
            file_event_rows=[],
        ),
    )


def _append_pending_content_rows(
    batch: _PendingContentRows,
    *,
    pending: list[_PendingFragment],
    tool_calls: list[PendingToolCall],
    command_runs: list[PendingCommandRun],
    file_events: list[PendingFileEvent],
    usage_row: UsageContentRow,
) -> None:
    turn_rows, fragment_rows = _pending_fragment_rows(
        pending=pending,
        usage_row=usage_row,
    )
    event_rows = pending_event_rows(
        tool_calls=tool_calls,
        command_runs=command_runs,
        file_events=file_events,
        usage_row=usage_row,
    )
    batch.turn_rows.extend(turn_rows)
    batch.fragment_rows.extend(fragment_rows)
    batch.event_rows.tool_call_rows.extend(event_rows.tool_call_rows)
    batch.event_rows.command_run_rows.extend(event_rows.command_run_rows)
    batch.event_rows.file_event_rows.extend(event_rows.file_event_rows)
    batch.linked_records += 1


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


def _pending_fragment_rows(
    *,
    pending: list[_PendingFragment],
    usage_row: UsageContentRow,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not pending:
        return [], []
    turn_rows: list[dict[str, object]] = []
    fragment_rows: list[dict[str, object]] = []
    for index, fragment in enumerate(pending):
        turn_key = _stable_hash(
            f"turn:{usage_row['record_id']}:{fragment.line_start}:{fragment.role}:{index}"
        )
        turn_rows.append(_turn_row(turn_key=turn_key, fragment=fragment, usage_row=usage_row))
        fragment_rows.append(
            _fragment_row(
                fragment_id=_stable_hash(
                    f"fragment:{turn_key}:{index}:{_stable_hash(fragment.text)}"
                ),
                turn_key=turn_key,
                fragment=fragment,
                usage_row=usage_row,
            )
        )
    return turn_rows, fragment_rows


def _turn_row(
    *,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: UsageContentRow,
) -> dict[str, object]:
    return {
        "turn_key": turn_key,
        "record_id": str(usage_row["record_id"]),
        "session_id": str(usage_row["session_id"]),
        "turn_id": fragment.turn_id or usage_row["turn_id"],
        "turn_index": fragment.turn_index,
        "role": fragment.role,
        "event_timestamp": fragment.event_timestamp or usage_row["event_timestamp"],
        "source_record_hash": usage_row["source_record_hash"],
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "content_hash": _stable_hash(fragment.text),
        "content_size_bytes": len(fragment.text.encode("utf-8")),
        "indexed_content_included": 1,
        "parser_adapter": usage_row["parser_adapter"] or PARSER_ADAPTER_NAME,
        "parser_version": usage_row["parser_version"] or PARSER_ADAPTER_VERSION,
        "parse_warnings_json": "[]",
    }


def _fragment_row(
    *,
    fragment_id: str,
    turn_key: str,
    fragment: _PendingFragment,
    usage_row: UsageContentRow,
) -> dict[str, object]:
    return {
        "fragment_id": fragment_id,
        "record_id": str(usage_row["record_id"]),
        "turn_key": turn_key,
        "fragment_kind": fragment.fragment_kind,
        "role": fragment.role,
        "safe_label": fragment.safe_label,
        "content_hash": _stable_hash(fragment.text),
        "content_size_bytes": len(fragment.text.encode("utf-8")),
        "fragment_text": fragment.text,
        "includes_raw_fragment": 1,
        "source_file_id": usage_row["source_file_id"],
        "line_start": fragment.line_start,
        "line_end": fragment.line_end,
        "token_link_record_id": str(usage_row["record_id"]),
        "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


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


def _content_texts(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, str):
            texts.append(item)
        elif isinstance(item, dict):
            text = optional_str(item.get("text"))
            if text:
                texts.append(text)
    return texts


def _reasoning_summary_texts(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    texts: list[str] = []
    for item in value:
        if isinstance(item, dict):
            text = optional_str(item.get("text")) or optional_str(item.get("summary_text"))
            if text:
                texts.append(text)
    return texts


def _message_history(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _role_from_payload_type(payload_type: str) -> str:
    if payload_type == "reasoning":
        return "reasoning"
    if payload_type in {"function_call", "function_call_output"}:
        return "tool"
    return "unknown"


def _is_token_count(entry_type: object, payload: dict[str, Any]) -> bool:
    return entry_type == "event_msg" and payload.get("type") == "token_count"


def _stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
