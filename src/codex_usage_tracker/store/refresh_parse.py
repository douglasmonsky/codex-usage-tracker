"""Bounded parser scheduling for usage-index refreshes."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from typing import Any, cast

from codex_usage_tracker import store as store_facade
from codex_usage_tracker.core.models import DiagnosticFact, UsageEvent
from codex_usage_tracker.parser.api import (
    parse_usage_events_from_file_with_state as _parse_usage_events_from_file_with_state,
)
from codex_usage_tracker.parser.state import ParserState
from codex_usage_tracker.store.compression_fact_rows import (
    IngestionFactRows,
    build_ingestion_fact_rows,
)
from codex_usage_tracker.store.content_extract import ContentRowAccumulator
from codex_usage_tracker.store.content_index_models import _ExtractedContentRows
from codex_usage_tracker.store.source_records import content_usage_row_from_event
from codex_usage_tracker.store.sources import SourceParsePlan

_PARALLEL_PARSE_WORKERS_ENV = "CODEX_USAGE_TRACKER_REFRESH_WORKERS"
_PARALLEL_CONTENT_WORKERS_ENV = "CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS"
_PARALLEL_PARSE_MIN_FILES = 8
_PARALLEL_PARSE_MIN_BYTES = 32 * 1024 * 1024
_PARALLEL_PARSE_MAX_WORKERS = 4
_PARALLEL_PARSE_QUEUE_FACTOR = 2

RefreshProgressCallback = Callable[[dict[str, object]], None]

cast(
    Any, store_facade
).parse_usage_events_from_file_with_state = _parse_usage_events_from_file_with_state


@dataclass(frozen=True)
class ParsedRefreshFile:
    plan: SourceParsePlan
    events: list[UsageEvent]
    diagnostic_facts: list[DiagnosticFact]
    stats: dict[str, int]
    state: ParserState
    final_line_number: int
    content_rows: _ExtractedContentRows | None = None
    fact_rows: IngestionFactRows | None = None


def emit_refresh_progress(
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


def iter_parse_refresh_plans(
    parse_plans: list[SourceParsePlan],
    *,
    session_index: dict[str, Any],
    collect_content: bool,
    progress_callback: RefreshProgressCallback | None,
    force_serial: bool,
    collect_facts: bool = False,
) -> Iterator[ParsedRefreshFile]:
    default_parser_active = default_parser_is_active()
    worker_count = parallel_parse_worker_count(
        parse_plans,
        collect_content=collect_content,
    )
    if force_serial or worker_count <= 1 or not default_parser_active:
        yield from _iter_parse_refresh_plans_serial(
            parse_plans,
            session_index=session_index,
            collect_content=collect_content and default_parser_active,
            collect_facts=collect_facts and default_parser_active,
            progress_callback=progress_callback,
        )
        return
    yield from _iter_parse_refresh_plans_parallel(
        parse_plans,
        session_index=session_index,
        worker_count=worker_count,
        collect_content=collect_content,
        collect_facts=collect_facts,
        progress_callback=progress_callback,
    )


def parse_refresh_plans_parallel(
    parse_plans: list[SourceParsePlan],
    *,
    session_index: dict[str, Any],
    worker_count: int,
    progress_callback: RefreshProgressCallback | None,
    collect_content: bool = False,
    collect_facts: bool = False,
) -> list[ParsedRefreshFile]:
    return list(
        _iter_parse_refresh_plans_parallel(
            parse_plans,
            session_index=session_index,
            worker_count=worker_count,
            collect_content=collect_content,
            collect_facts=collect_facts,
            progress_callback=progress_callback,
        )
    )


def _iter_parse_refresh_plans_serial(
    parse_plans: list[SourceParsePlan],
    *,
    session_index: dict[str, Any],
    collect_content: bool,
    progress_callback: RefreshProgressCallback | None,
    collect_facts: bool = False,
) -> Iterator[ParsedRefreshFile]:
    total = len(parse_plans)
    parsed_events = 0
    emit_refresh_progress(
        progress_callback,
        phase="parsing",
        status="running" if total else "completed",
        completed=0,
        total=total,
        message="Parsing source logs",
    )
    for index, plan in enumerate(parse_plans, start=1):
        if collect_content:
            parsed = _parse_source_plan_default(
                plan,
                session_index,
                True,
                collect_facts,
            )
        else:
            parsed = _parse_source_plan_with_facade(plan, session_index=session_index)
        parsed_events += len(parsed.events)
        emit_refresh_progress(
            progress_callback,
            phase="parsing",
            status="running" if index < total else "completed",
            completed=index,
            total=total,
            message="Parsed source logs",
            parsed_events=parsed_events,
        )
        yield parsed


def _iter_parse_refresh_plans_parallel(
    parse_plans: list[SourceParsePlan],
    *,
    session_index: dict[str, Any],
    worker_count: int,
    collect_content: bool,
    progress_callback: RefreshProgressCallback | None,
    collect_facts: bool = False,
) -> Iterator[ParsedRefreshFile]:
    total = len(parse_plans)
    completed = 0
    parsed_events = 0
    emit_refresh_progress(
        progress_callback,
        phase="parsing",
        status="running",
        completed=0,
        total=total,
        message=f"Parsing source logs with {worker_count} workers",
        workers=worker_count,
    )
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        plan_iterator = iter(enumerate(parse_plans))
        pending: dict[Future[ParsedRefreshFile], int] = {}
        ready: dict[int, ParsedRefreshFile] = {}
        next_result_index = 0
        queue_limit = worker_count * _PARALLEL_PARSE_QUEUE_FACTOR
        while pending or ready or next_result_index < total:
            if next_result_index in ready:
                result = ready.pop(next_result_index)
                next_result_index += 1
                completed += 1
                parsed_events += len(result.events)
                _submit_refresh_parse_plans(
                    executor,
                    plan_iterator=plan_iterator,
                    pending=pending,
                    session_index=session_index,
                    collect_content=collect_content,
                    collect_facts=collect_facts,
                    count=max(0, queue_limit - len(pending) - len(ready)),
                )
                emit_refresh_progress(
                    progress_callback,
                    phase="parsing",
                    status="running" if completed < total else "completed",
                    completed=completed,
                    total=total,
                    message="Parsed source logs",
                    workers=worker_count,
                    parsed_events=parsed_events,
                )
                yield result
                continue
            _submit_refresh_parse_plans(
                executor,
                plan_iterator=plan_iterator,
                pending=pending,
                session_index=session_index,
                collect_content=collect_content,
                collect_facts=collect_facts,
                count=max(0, queue_limit - len(pending) - len(ready)),
            )
            if not pending:
                break
            done, _not_done = wait(pending, return_when=FIRST_COMPLETED)
            for future in sorted(done, key=pending.__getitem__):
                result_index = pending.pop(future)
                ready[result_index] = future.result()


def _submit_refresh_parse_plans(
    executor: ProcessPoolExecutor,
    *,
    plan_iterator: Iterator[tuple[int, SourceParsePlan]],
    pending: dict[Future[ParsedRefreshFile], int],
    session_index: dict[str, Any],
    collect_content: bool,
    collect_facts: bool,
    count: int,
) -> None:
    for _index in range(count):
        try:
            result_index, plan = next(plan_iterator)
        except StopIteration:
            return
        future = executor.submit(
            _parse_source_plan_default,
            plan,
            session_index,
            collect_content,
            collect_facts,
        )
        pending[future] = result_index


def parallel_parse_worker_count(
    parse_plans: list[SourceParsePlan],
    *,
    collect_content: bool = False,
) -> int:
    plan_count = len(parse_plans)
    if plan_count <= 1:
        return 1
    configured_workers = _configured_worker_count(_PARALLEL_PARSE_WORKERS_ENV)
    if configured_workers is None and collect_content:
        configured_workers = _configured_worker_count(_PARALLEL_CONTENT_WORKERS_ENV)
    if configured_workers is not None:
        return min(plan_count, configured_workers)
    if plan_count < _PARALLEL_PARSE_MIN_FILES:
        return 1
    if _pending_parse_bytes(parse_plans) < _PARALLEL_PARSE_MIN_BYTES:
        return 1
    cpu_count = os.cpu_count() or 1
    return min(plan_count, cpu_count, _PARALLEL_PARSE_MAX_WORKERS)


def _pending_parse_bytes(parse_plans: list[SourceParsePlan]) -> int:
    total = 0
    for plan in parse_plans:
        try:
            total += max(0, plan.path.stat().st_size - plan.start_byte)
        except OSError:
            continue
    return total


def _configured_worker_count(environment_name: str) -> int | None:
    raw_workers = os.environ.get(environment_name)
    if raw_workers is None:
        return None
    try:
        workers = int(raw_workers)
    except ValueError:
        return None
    return max(1, workers)


def default_parser_is_active() -> bool:
    return (
        getattr(
            store_facade,
            "parse_usage_events_from_file_with_state",
            _parse_usage_events_from_file_with_state,
        )
        is _parse_usage_events_from_file_with_state
    )


def _parse_usage_events_from_file(*args: Any, **kwargs: Any) -> Any:
    parser = getattr(
        store_facade,
        "parse_usage_events_from_file_with_state",
        _parse_usage_events_from_file_with_state,
    )
    return parser(*args, **kwargs)


def _parse_source_plan_with_facade(
    plan: SourceParsePlan,
    *,
    session_index: dict[str, Any],
) -> ParsedRefreshFile:
    return _parse_source_plan(
        plan,
        session_index=session_index,
        parser=_parse_usage_events_from_file,
    )


def _parse_source_plan_default(
    plan: SourceParsePlan,
    session_index: dict[str, Any],
    collect_content: bool = False,
    collect_facts: bool = False,
) -> ParsedRefreshFile:
    return _parse_source_plan(
        plan,
        session_index=session_index,
        parser=_parse_usage_events_from_file_with_state,
        collect_content=collect_content,
        collect_facts=collect_facts,
    )


def _parse_source_plan(
    plan: SourceParsePlan,
    *,
    session_index: dict[str, Any],
    parser: Any,
    collect_content: bool = False,
    collect_facts: bool = False,
) -> ParsedRefreshFile:
    file_stats: dict[str, int] = {}
    accumulator = ContentRowAccumulator(source_path=plan.path) if collect_content else None

    def observe_entry(
        envelope: dict[str, Any],
        payload: dict[str, Any],
        line_number: int,
        event: UsageEvent | None,
    ) -> None:
        if accumulator is None:
            return
        accumulator.consume(
            envelope=envelope,
            payload=payload,
            line_number=line_number,
            usage_row=content_usage_row_from_event(event) if event is not None else None,
        )

    parser_kwargs: dict[str, Any] = {
        "session_index": session_index,
        "stats": file_stats,
        "start_byte": plan.start_byte,
        "start_line": plan.start_line,
        "initial_state": plan.initial_state,
    }
    if accumulator is not None:
        parser_kwargs["entry_observer"] = observe_entry
    parsed_file = parser(plan.path, **parser_kwargs)
    if accumulator is not None:
        accumulator.parse_warnings = int(file_stats.get("invalid_json", 0)) + int(
            file_stats.get("missing_payload", 0)
        )
    content_rows = accumulator.finish() if accumulator is not None else None
    fact_rows = None
    if collect_facts:
        if content_rows is None:
            raise RuntimeError("compression fact extraction requires content rows")
        fact_rows = build_ingestion_fact_rows(
            events=parsed_file.events,
            content_rows=(content_rows,),
        )
    return ParsedRefreshFile(
        plan=plan,
        events=parsed_file.events,
        diagnostic_facts=parsed_file.diagnostic_facts,
        stats=file_stats,
        state=parsed_file.state,
        final_line_number=parsed_file.final_line_number,
        content_rows=content_rows,
        fact_rows=fact_rows,
    )


def _refresh_progress_percent(completed: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round(min(100.0, max(0.0, (completed / total) * 100.0)), 1)
