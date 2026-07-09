"""Refresh orchestration for the aggregate usage index."""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker import store as store_facade
from codex_usage_tracker.core.models import DiagnosticFact, RefreshResult, UsageEvent
from codex_usage_tracker.core.paths import DEFAULT_CODEX_HOME, DEFAULT_DB_PATH
from codex_usage_tracker.parser.api import (
    find_session_logs,
    load_session_index,
)
from codex_usage_tracker.parser.api import (
    parse_usage_events_from_file_with_state as _parse_usage_events_from_file_with_state,
)
from codex_usage_tracker.parser.state import ParserState, compact_parser_diagnostics
from codex_usage_tracker.store.api import (
    clear_content_index_rows,
    init_db,
    record_refresh_metadata,
    record_source_file_metadata,
    upsert_usage_events,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.content_index import (
    ContentIndexPlan,
    index_content_for_source_plans,
)
from codex_usage_tracker.store.sources import (
    ParsedSourceFile,
    SourceParsePlan,
    source_logs_requiring_parse,
)

_PARALLEL_PARSE_WORKERS_ENV = "CODEX_USAGE_TRACKER_REFRESH_WORKERS"
_PARALLEL_PARSE_MIN_FILES = 4
_PARALLEL_PARSE_MAX_WORKERS = 8

vars(store_facade)["parse_usage_events_from_file_with_state"] = (
    _parse_usage_events_from_file_with_state
)


def _parse_usage_events_from_file(*args: Any, **kwargs: Any) -> Any:
    parser = getattr(
        store_facade,
        "parse_usage_events_from_file_with_state",
        _parse_usage_events_from_file_with_state,
    )
    return parser(*args, **kwargs)


@dataclass(frozen=True)
class _ParsedRefreshFile:
    plan: SourceParsePlan
    events: list[UsageEvent]
    diagnostic_facts: list[DiagnosticFact]
    stats: dict[str, int]
    state: ParserState
    final_line_number: int


RefreshProgressCallback = Callable[[dict[str, object]], None]


def refresh_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
    progress_callback: RefreshProgressCallback | None = None,
) -> RefreshResult:
    """Scan Codex logs and upsert aggregate usage events."""

    _emit_refresh_progress(
        progress_callback,
        phase="discovering",
        status="running",
        completed=0,
        total=None,
        message="Finding Codex session logs",
    )
    logs = find_session_logs(codex_home=codex_home, include_archived=include_archived)
    session_index = load_session_index(codex_home)
    with connect(db_path) as conn:
        init_db(conn)
        parse_plans = source_logs_requiring_parse(conn, logs)
    _emit_refresh_progress(
        progress_callback,
        phase="discovering",
        status="completed",
        completed=len(logs),
        total=len(logs),
        message="Planned source log refresh",
        scanned_files=len(logs),
        parsed_source_files=len(parse_plans),
        skipped_source_files=len(logs) - len(parse_plans),
    )
    parsed_refresh_files = _parse_refresh_plans(
        parse_plans,
        session_index,
        progress_callback=progress_callback,
    )
    stats: dict[str, int] = {}
    events: list[UsageEvent] = []
    diagnostic_facts: list[DiagnosticFact] = []
    parsed_files: list[ParsedSourceFile] = []
    for parsed_refresh_file in parsed_refresh_files:
        file_events = parsed_refresh_file.events
        events.extend(file_events)
        diagnostic_facts.extend(parsed_refresh_file.diagnostic_facts)
        parsed_files.append(
            (
                parsed_refresh_file.plan.path,
                file_events,
                parsed_refresh_file.stats,
                parsed_refresh_file.state,
                parsed_refresh_file.final_line_number,
            )
        )
        for key, value in parsed_refresh_file.stats.items():
            stats[key] = stats.get(key, 0) + int(value)
    _emit_refresh_progress(
        progress_callback,
        phase="upserting",
        status="running",
        completed=0,
        total=len(events),
        message="Writing aggregate usage rows",
        parsed_events=len(events),
    )
    inserted = upsert_usage_events(
        events,
        db_path=db_path,
        replace_source_files=(plan.path for plan in parse_plans if plan.replace_existing),
        diagnostic_facts=diagnostic_facts,
    )
    _emit_refresh_progress(
        progress_callback,
        phase="upserting",
        status="completed",
        completed=len(events),
        total=len(events),
        message="Wrote aggregate usage rows",
        inserted_or_updated_events=inserted,
    )
    _emit_refresh_progress(
        progress_callback,
        phase="metadata",
        status="running",
        completed=0,
        total=len(parsed_files),
        message="Updating source metadata",
    )
    record_source_file_metadata(db_path=db_path, parsed_files=parsed_files)
    _emit_refresh_progress(
        progress_callback,
        phase="metadata",
        status="completed",
        completed=len(parsed_files),
        total=len(parsed_files),
        message="Updated source metadata",
    )
    if not aggregate_only:
        with connect(db_path) as conn:
            init_db(conn)
            index_content_for_source_plans(
                conn,
                plans=(
                    ContentIndexPlan(
                        source_path=plan.path,
                        replace_existing=plan.replace_existing,
                        start_byte=plan.start_byte,
                        start_line=plan.start_line,
                    )
                    for plan in parse_plans
                ),
                progress_callback=progress_callback,
            )
    else:
        _emit_refresh_progress(
            progress_callback,
            phase="indexing_content",
            status="skipped",
            completed=0,
            total=0,
            message="Skipped content index for aggregate-only refresh",
        )
    skipped_events = stats.get("skipped_events", 0)
    diagnostics = compact_parser_diagnostics(stats)
    _emit_refresh_progress(
        progress_callback,
        phase="finalizing",
        status="running",
        completed=0,
        total=1,
        message="Recording refresh metadata",
    )
    record_refresh_metadata(
        db_path=db_path,
        scanned_files=len(logs),
        parsed_events=len(events),
        skipped_events=skipped_events,
        inserted_or_updated_events=inserted,
        parser_diagnostics=diagnostics,
        parsed_source_files=len(parse_plans),
        skipped_source_files=len(logs) - len(parse_plans),
    )
    result = RefreshResult(
        scanned_files=len(logs),
        parsed_events=len(events),
        inserted_or_updated_events=inserted,
        db_path=str(db_path),
        skipped_events=skipped_events,
        parser_diagnostics=diagnostics,
    )
    _emit_refresh_progress(
        progress_callback,
        phase="finalizing",
        status="completed",
        completed=1,
        total=1,
        message="Refresh complete",
        result={
            "scanned_files": result.scanned_files,
            "parsed_events": result.parsed_events,
            "skipped_events": result.skipped_events,
            "inserted_or_updated_events": result.inserted_or_updated_events,
            "db_path": result.db_path,
            "parser_diagnostics": result.parser_diagnostics,
        },
    )
    return result


def _emit_refresh_progress(
    progress_callback: RefreshProgressCallback | None,
    *,
    phase: str,
    status: str,
    completed: int | None,
    total: int | None,
    message: str,
    **extra: object,
) -> None:
    if progress_callback is None:
        return
    payload: dict[str, object] = {
        "schema": "codex-usage-tracker-refresh-progress-v1",
        "phase": phase,
        "status": status,
        "message": message,
    }
    if completed is not None:
        payload["completed"] = completed
    if total is not None:
        payload["total"] = total
        payload["percent"] = _refresh_progress_percent(completed or 0, total)
    payload.update(extra)
    progress_callback(payload)


def _refresh_progress_percent(completed: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round(min(100.0, max(0.0, (completed / total) * 100.0)), 1)


def _parse_refresh_plans(
    parse_plans: list[SourceParsePlan],
    session_index: dict[str, Any],
    *,
    progress_callback: RefreshProgressCallback | None = None,
) -> list[_ParsedRefreshFile]:
    worker_count = _parallel_parse_worker_count(len(parse_plans))
    if worker_count <= 1 or not _default_parser_is_active():
        return _parse_refresh_plans_serial(
            parse_plans,
            session_index=session_index,
            progress_callback=progress_callback,
        )
    try:
        return _parse_refresh_plans_parallel(
            parse_plans,
            session_index=session_index,
            worker_count=worker_count,
            progress_callback=progress_callback,
        )
    except BrokenProcessPool:
        return _parse_refresh_plans_serial(
            parse_plans,
            session_index=session_index,
            progress_callback=progress_callback,
        )


def _parse_refresh_plans_serial(
    parse_plans: list[SourceParsePlan],
    *,
    session_index: dict[str, Any],
    progress_callback: RefreshProgressCallback | None,
) -> list[_ParsedRefreshFile]:
    results: list[_ParsedRefreshFile] = []
    total = len(parse_plans)
    _emit_refresh_progress(
        progress_callback,
        phase="parsing",
        status="running",
        completed=0,
        total=total,
        message="Parsing source logs",
    )
    for index, plan in enumerate(parse_plans, start=1):
        parsed = _parse_source_plan_with_facade(plan, session_index=session_index)
        results.append(parsed)
        _emit_refresh_progress(
            progress_callback,
            phase="parsing",
            status="running" if index < total else "completed",
            completed=index,
            total=total,
            message="Parsed source logs",
            parsed_events=sum(len(result.events) for result in results),
        )
    return results


def _parse_refresh_plans_parallel(
    parse_plans: list[SourceParsePlan],
    *,
    session_index: dict[str, Any],
    worker_count: int,
    progress_callback: RefreshProgressCallback | None,
) -> list[_ParsedRefreshFile]:
    results: list[_ParsedRefreshFile | None] = [None] * len(parse_plans)
    total = len(parse_plans)
    completed = 0
    parsed_events = 0
    _emit_refresh_progress(
        progress_callback,
        phase="parsing",
        status="running",
        completed=0,
        total=total,
        message=f"Parsing source logs with {worker_count} workers",
        workers=worker_count,
    )
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _parse_source_plan_default,
                plan,
                session_index,
            ): index
            for index, plan in enumerate(parse_plans)
        }
        for future in as_completed(futures):
            result = future.result()
            results[futures[future]] = result
            completed += 1
            parsed_events += len(result.events)
            _emit_refresh_progress(
                progress_callback,
                phase="parsing",
                status="running" if completed < total else "completed",
                completed=completed,
                total=total,
                message="Parsed source logs",
                workers=worker_count,
                parsed_events=parsed_events,
            )
    return [result for result in results if result is not None]


def _parallel_parse_worker_count(plan_count: int) -> int:
    if plan_count <= 1:
        return 1
    configured_workers = _configured_parallel_parse_workers()
    if configured_workers is not None:
        return min(plan_count, configured_workers)
    if plan_count < _PARALLEL_PARSE_MIN_FILES:
        return 1
    cpu_count = os.cpu_count() or 1
    return min(plan_count, cpu_count, _PARALLEL_PARSE_MAX_WORKERS)


def _configured_parallel_parse_workers() -> int | None:
    raw_workers = os.environ.get(_PARALLEL_PARSE_WORKERS_ENV)
    if raw_workers is None:
        return None
    try:
        workers = int(raw_workers)
    except ValueError:
        return None
    return max(1, workers)


def _default_parser_is_active() -> bool:
    return (
        getattr(
            store_facade,
            "parse_usage_events_from_file_with_state",
            _parse_usage_events_from_file_with_state,
        )
        is _parse_usage_events_from_file_with_state
    )


def _parse_source_plan_with_facade(
    plan: SourceParsePlan,
    *,
    session_index: dict[str, Any],
) -> _ParsedRefreshFile:
    return _parse_source_plan(
        plan,
        session_index=session_index,
        parser=_parse_usage_events_from_file,
    )


def _parse_source_plan_default(
    plan: SourceParsePlan,
    session_index: dict[str, Any],
) -> _ParsedRefreshFile:
    return _parse_source_plan(
        plan,
        session_index=session_index,
        parser=_parse_usage_events_from_file_with_state,
    )


def _parse_source_plan(
    plan: SourceParsePlan,
    *,
    session_index: dict[str, Any],
    parser: Any,
) -> _ParsedRefreshFile:
    file_stats: dict[str, int] = {}
    parsed_file = parser(
        plan.path,
        session_index=session_index,
        stats=file_stats,
        start_byte=plan.start_byte,
        start_line=plan.start_line,
        initial_state=plan.initial_state,
    )
    return _ParsedRefreshFile(
        plan=plan,
        events=parsed_file.events,
        diagnostic_facts=parsed_file.diagnostic_facts,
        stats=file_stats,
        state=parsed_file.state,
        final_line_number=parsed_file.final_line_number,
    )


def rebuild_usage_index(
    codex_home: Path = DEFAULT_CODEX_HOME,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    aggregate_only: bool = False,
) -> RefreshResult:
    """Clear aggregate rows and rescan local Codex logs."""

    with connect(db_path) as conn:
        init_db(conn)
        clear_content_index_rows(conn)
        conn.execute("DELETE FROM call_diagnostic_facts")
        conn.execute("DELETE FROM diagnostic_snapshots")
        conn.execute("DELETE FROM source_records")
        conn.execute("DELETE FROM usage_events")
        conn.execute("DELETE FROM thread_summaries")
        conn.execute("DELETE FROM source_files")
        conn.execute("DELETE FROM refresh_meta")
    return refresh_usage_index(
        codex_home=codex_home,
        db_path=db_path,
        include_archived=include_archived,
        aggregate_only=aggregate_only,
    )
