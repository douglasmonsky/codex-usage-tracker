"""Bounded deterministic scheduling for standalone content indexing."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait

from codex_usage_tracker.store.content_extract import _extract_content_rows_for_source_file
from codex_usage_tracker.store.content_index_bulk import (
    add_content_index_result,
    emit_content_index_progress,
    write_extracted_content_rows,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexPlan,
    ContentIndexProgressCallback,
    ContentIndexResult,
    _ExtractedContentRows,
)
from codex_usage_tracker.store.content_persistence import _rebuild_content_fts
from codex_usage_tracker.store.content_provenance import _usage_rows_by_token_line

_WORKERS_ENV = "CODEX_USAGE_TRACKER_CONTENT_INDEX_WORKERS"
_MIN_FILES = 8
_MIN_BYTES = 32 * 1024 * 1024
_MAX_WORKERS = 4
_QUEUE_FACTOR = 2


class _ContentIndexScheduler:
    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        source_plans: list[ContentIndexPlan],
        sync_fts: bool,
        progress_callback: ContentIndexProgressCallback | None,
        worker_count: int,
    ) -> None:
        self.conn = conn
        self.source_plans = source_plans
        self.sync_fts = sync_fts
        self.progress_callback = progress_callback
        self.worker_count = worker_count
        self.totals = ContentIndexResult(0, 0, 0)
        self.needs_full_fts_rebuild = False
        self.completed = 0
        self.next_write_index = 0
        self.ready: dict[int, _ExtractedContentRows] = {}

    def run(self) -> ContentIndexResult:
        with ProcessPoolExecutor(max_workers=self.worker_count) as executor:
            plan_iterator = iter(enumerate(self.source_plans))
            pending: dict[Future[_ExtractedContentRows], int] = {}
            self._submit(executor, plan_iterator, pending, self._queue_limit)
            while pending:
                self._collect_ready(pending)
                self._write_ready()
                open_slots = self._queue_limit - len(pending) - len(self.ready)
                self._submit(executor, plan_iterator, pending, open_slots)
        if self.needs_full_fts_rebuild:
            _rebuild_content_fts(self.conn)
        return self.totals

    @property
    def _queue_limit(self) -> int:
        return self.worker_count * _QUEUE_FACTOR

    def _collect_ready(self, pending: dict[Future[_ExtractedContentRows], int]) -> None:
        done, _not_done = wait(pending, return_when=FIRST_COMPLETED)
        for future in done:
            self.ready[pending.pop(future)] = future.result()

    def _write_ready(self) -> None:
        while self.next_write_index in self.ready:
            plan = self.source_plans[self.next_write_index]
            result = write_extracted_content_rows(
                self.conn,
                extracted=self.ready.pop(self.next_write_index),
                replace_existing=plan.replace_existing,
                sync_fts=self.sync_fts,
                start_line=0 if plan.replace_existing else plan.start_line,
            )
            self.needs_full_fts_rebuild |= plan.replace_existing and result.source_files > 0
            self.totals = add_content_index_result(self.totals, result)
            self.completed += 1
            self.next_write_index += 1
            emit_content_index_progress(
                self.progress_callback,
                status=("running" if self.completed < len(self.source_plans) else "completed"),
                completed=self.completed,
                total=len(self.source_plans),
                message="Indexed local content",
                content_fragments=self.totals.content_fragments,
                conversation_turns=self.totals.conversation_turns,
                workers=self.worker_count,
            )

    def _submit(
        self,
        executor: ProcessPoolExecutor,
        plan_iterator: Iterator[tuple[int, ContentIndexPlan]],
        pending: dict[Future[_ExtractedContentRows], int],
        count: int,
    ) -> None:
        for _index in range(count):
            next_plan = _next_plan(plan_iterator)
            if next_plan is None:
                return
            result_index, plan = next_plan
            pending[self._submit_plan(executor, plan)] = result_index

    def _submit_plan(
        self,
        executor: ProcessPoolExecutor,
        plan: ContentIndexPlan,
    ) -> Future[_ExtractedContentRows]:
        usage_rows: dict[int, Mapping[str, object]] = {
            line_number: dict(row)
            for line_number, row in _usage_rows_by_token_line(
                self.conn,
                source_file=str(plan.source_path),
                min_line_number=None if plan.replace_existing else plan.start_line + 1,
            ).items()
        }
        return executor.submit(
            _extract_content_rows_for_source_file,
            source_path=plan.source_path,
            usage_rows=usage_rows,
            start_byte=0 if plan.replace_existing else plan.start_byte,
            start_line=0 if plan.replace_existing else plan.start_line,
        )


def index_content_for_source_plans_parallel(
    conn: sqlite3.Connection,
    *,
    source_plans: list[ContentIndexPlan],
    sync_fts: bool,
    progress_callback: ContentIndexProgressCallback | None,
    worker_count: int,
) -> ContentIndexResult:
    return _ContentIndexScheduler(
        conn,
        source_plans=source_plans,
        sync_fts=sync_fts,
        progress_callback=progress_callback,
        worker_count=worker_count,
    ).run()


def parallel_content_index_worker_count(source_plans: list[ContentIndexPlan]) -> int:
    configured = _configured_workers()
    if configured is not None:
        return min(len(source_plans), configured)
    if len(source_plans) < _MIN_FILES or _pending_bytes(source_plans) < _MIN_BYTES:
        return 1
    return min(len(source_plans), max(1, os.cpu_count() or 1), _MAX_WORKERS)


def _pending_bytes(source_plans: list[ContentIndexPlan]) -> int:
    total = 0
    for plan in source_plans:
        try:
            total += max(0, plan.source_path.stat().st_size - plan.start_byte)
        except OSError:
            continue
    return total


def _configured_workers() -> int | None:
    raw_value = os.environ.get(_WORKERS_ENV)
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        return max(1, int(raw_value))
    except ValueError:
        return None


def _next_plan(
    plan_iterator: Iterator[tuple[int, ContentIndexPlan]],
) -> tuple[int, ContentIndexPlan] | None:
    try:
        return next(plan_iterator)
    except StopIteration:
        return None
