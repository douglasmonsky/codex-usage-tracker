"""Streaming JSONL parser with isolated malformed ranges."""

from __future__ import annotations

import hashlib
import json
import queue
import threading
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace

from ...domain.identity import semantic_id
from ..contracts import (
    ADAPTER_VERSION,
    AdapterObservation,
    CursorOutcome,
    ParseDiagnostic,
    SourceCursor,
    SourceRange,
    SourceState,
)
from .cursor import (
    CursorClassification,
    FramedRecord,
    build_cursor,
    classify_cursor,
    iter_complete_records,
)
from .discovery import SourcePlan
from .normalize import NormalizationError, assert_body_free, normalize_record, related_observations

PARSER_VERSION = "codex-jsonl-parser.v1"


@dataclass(frozen=True, slots=True)
class ParseBatch:
    source_rank: int
    batch_index: int
    observations: tuple[AdapterObservation, ...]
    diagnostics: tuple[ParseDiagnostic, ...]
    records_seen: int
    complete_end: int
    latest_source_order: int
    done: bool
    cursor: SourceCursor | None = None
    classification: CursorClassification | None = None


@dataclass(frozen=True, slots=True)
class SourceParseResult:
    source_rank: int
    observations: tuple[AdapterObservation, ...]
    diagnostics: tuple[ParseDiagnostic, ...]
    records_seen: int
    cursor: SourceCursor | None
    classification: CursorClassification
    tail_pending: bool


def _range(plan: SourcePlan, framed: FramedRecord) -> SourceRange:
    return SourceRange(
        manifestation_id=plan.inventory.manifestation_id,
        manifestation_key=plan.inventory.manifestation_key,
        source_revision=plan.inventory.content_revision,
        record_ordinal=framed.record_ordinal,
        byte_start=framed.byte_start,
        byte_end=framed.byte_end,
    )


def _replacement_plan(plan: SourcePlan, classification: CursorClassification) -> SourcePlan:
    if classification.outcome not in {CursorOutcome.REPLACED, CursorOutcome.TRUNCATED}:
        return plan
    digest = hashlib.sha256(
        f"{plan.inventory.manifestation_id}\0{plan.inventory.content_revision}\0{classification.outcome.value}".encode()
    ).digest()
    manifestation_key = max(1, int.from_bytes(digest[:8], "big") & ((1 << 63) - 1))
    manifestation_id = semantic_id(
        "source-manifestation",
        [plan.inventory.manifestation_id, plan.inventory.content_revision, classification.outcome.value],
    )
    return replace(
        plan,
        inventory=replace(
            plan.inventory,
            manifestation_id=manifestation_id,
            manifestation_key=manifestation_key,
            state=SourceState.REPLACED if classification.outcome is CursorOutcome.REPLACED else SourceState.TRUNCATED,
        ),
    )


def iter_source_batches(
    plan: SourcePlan,
    *,
    batch_size: int,
    cursor: SourceCursor | None = None,
    late_cutoff_us: int | None = None,
) -> Iterator[ParseBatch]:
    """Parse one source incrementally; each yielded batch is bounded."""

    if plan.path is None or not plan.inventory.selected:
        yield ParseBatch(
            source_rank=plan.inventory.source_rank,
            batch_index=0,
            observations=(),
            diagnostics=(),
            records_seen=0,
            complete_end=0 if cursor is None else cursor.byte_offset,
            latest_source_order=0 if cursor is None else cursor.latest_source_order,
            done=True,
            cursor=cursor,
            classification=CursorClassification(
                outcome=CursorOutcome.MISSING if plan.path is None else CursorOutcome.MALFORMED_RANGE,
                reason="source is not selected or not materialized",
            ),
        )
        return
    classification = classify_cursor(
        plan.path,
        inventory=plan.inventory,
        cursor=cursor,
        parser_version=PARSER_VERSION,
        adapter_version=ADAPTER_VERSION,
    )
    active_plan = _replacement_plan(plan, classification)
    if classification.outcome.value == "no_change":
        yield ParseBatch(
            source_rank=plan.inventory.source_rank,
            batch_index=0,
            observations=(),
            diagnostics=(),
            records_seen=0,
            complete_end=cursor.byte_offset if cursor else 0,
            latest_source_order=cursor.latest_source_order if cursor else 0,
            done=True,
            cursor=cursor,
            classification=classification,
        )
        return
    start_offset = cursor.byte_offset if cursor is not None and classification.outcome.value == "append_safe" else 0
    start_ordinal = cursor.record_ordinal if cursor is not None and start_offset else 0
    observations: list[AdapterObservation] = []
    diagnostics: list[ParseDiagnostic] = []
    batch_index = 0
    batch_records = 0
    records_seen = 0
    complete_end = start_offset
    latest_source_order = cursor.latest_source_order if cursor is not None and start_offset else 0
    last_complete_end = complete_end
    for framed in iter_complete_records(plan.path, start_offset=start_offset, start_ordinal=start_ordinal):
        records_seen += 1
        batch_records += 1
        complete_end = framed.byte_end
        last_complete_end = complete_end
        source_range = _range(active_plan, framed)
        try:
            decoded = framed.body[:-1].decode("utf-8")
            record = json.loads(decoded)
            if not isinstance(record, dict):
                raise NormalizationError("JSONL record must be an object")
            observation = normalize_record(record, source_range, source_rank=plan.inventory.source_rank, late_cutoff_us=late_cutoff_us)
            assert_body_free(observation)
            observations.append(observation)
            for related in related_observations(observation):
                assert_body_free(related)
                observations.append(related)
            latest_source_order = observation.source_order
        except (UnicodeDecodeError, json.JSONDecodeError, NormalizationError, TypeError, ValueError) as error:
            diagnostics.append(
                ParseDiagnostic(
                    code="malformed_range" if not isinstance(error, NormalizationError) or "unknown record kind" not in str(error) else "unknown_record_kind",
                    source_range=source_range,
                    detail=type(error).__name__,
                )
            )
        if batch_records >= batch_size:
            yield ParseBatch(
                source_rank=plan.inventory.source_rank,
                batch_index=batch_index,
                observations=tuple(observations),
                diagnostics=tuple(diagnostics),
                records_seen=records_seen,
                complete_end=complete_end,
                latest_source_order=latest_source_order,
                done=False,
            )
            batch_index += 1
            batch_records = 0
            observations.clear()
            diagnostics.clear()
    if observations or diagnostics or records_seen == 0:
        yield ParseBatch(
            source_rank=plan.inventory.source_rank,
            batch_index=batch_index,
            observations=tuple(observations),
            diagnostics=tuple(diagnostics),
            records_seen=records_seen,
            complete_end=last_complete_end,
            latest_source_order=latest_source_order,
            done=False,
        )
        batch_index += 1
        diagnostics.clear()
        observations.clear()
    terminal_diagnostics = tuple(diagnostics)
    if classification.outcome in {CursorOutcome.REPLACED, CursorOutcome.TRUNCATED}:
        terminal_diagnostics += (
            ParseDiagnostic(
                code=f"source_{classification.outcome.value}",
                source_range=None,
                detail=classification.reason,
            ),
        )
    next_cursor = build_cursor(
        plan.path,
        inventory=active_plan.inventory,
        byte_offset=last_complete_end,
        record_ordinal=(cursor.record_ordinal if cursor is not None and start_offset else 0) + records_seen,
        latest_source_order=latest_source_order,
        parser_version=PARSER_VERSION,
        adapter_version=ADAPTER_VERSION,
    )
    yield ParseBatch(
        source_rank=plan.inventory.source_rank,
        batch_index=batch_index,
        observations=(),
        diagnostics=terminal_diagnostics,
        records_seen=records_seen,
        complete_end=last_complete_end,
        latest_source_order=latest_source_order,
        done=True,
        cursor=next_cursor,
        classification=classification,
    )


def parse_source(
    plan: SourcePlan,
    *,
    batch_size: int = 256,
    cursor: SourceCursor | None = None,
    late_cutoff_us: int | None = None,
) -> SourceParseResult:
    """Convenience materialization for one source; worker ingestion is streaming."""

    observations: list[AdapterObservation] = []
    diagnostics: list[ParseDiagnostic] = []
    records_seen = 0
    next_cursor = cursor
    classification: CursorClassification | None = None
    complete_end = 0
    for batch in iter_source_batches(plan, batch_size=batch_size, cursor=cursor, late_cutoff_us=late_cutoff_us):
        observations.extend(batch.observations)
        diagnostics.extend(batch.diagnostics)
        records_seen = max(records_seen, batch.records_seen)
        complete_end = max(complete_end, batch.complete_end)
        if batch.done:
            next_cursor = batch.cursor
            classification = batch.classification
    assert classification is not None
    size = 0 if plan.path is None else plan.path.stat().st_size
    tail_pending = plan.path is not None and complete_end < size
    return SourceParseResult(
        source_rank=plan.inventory.source_rank,
        observations=tuple(observations),
        diagnostics=tuple(diagnostics),
        records_seen=records_seen,
        cursor=next_cursor,
        classification=classification,
        tail_pending=tail_pending,
    )


def parse_sources(
    plans: Iterable[SourcePlan],
    *,
    workers: int = 1,
    batch_size: int = 256,
    queue_capacity: int | None = None,
    cursors: Mapping[int, SourceCursor] | None = None,
    late_cutoff_us: int | None = None,
    metrics_sink: list[dict[str, int]] | None = None,
) -> Iterator[ParseBatch]:
    """Parse selected sources with bounded worker/output queues.

    Workers never return a whole source.  They emit bounded batches into a
    bounded queue, while the coordinator releases batches in source-rank order
    so worker scheduling cannot affect downstream canonicalization.
    """

    if not 1 <= workers <= 8:
        raise ValueError("workers must be one of the bounded 1/2/4/8-compatible range")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    selected = tuple(sorted((plan for plan in plans if plan.inventory.selected), key=lambda item: item.inventory.source_rank))
    if queue_capacity is None:
        queue_capacity = max(1, workers * 2)
    if queue_capacity <= 0:
        raise ValueError("queue_capacity must be positive")
    work_queue: queue.Queue[SourcePlan | None] = queue.Queue(maxsize=max(1, workers))
    output_queue: queue.Queue[tuple[int, ParseBatch | None]] = queue.Queue(maxsize=queue_capacity)
    reorder_slots = threading.BoundedSemaphore(queue_capacity)
    source_slots = {
        plan.inventory.source_rank: threading.BoundedSemaphore(1)
        for plan in selected
    }
    thread_count = min(workers, max(1, len(selected)))

    def feed() -> None:
        for plan in selected:
            work_queue.put(plan)
        for _ in range(thread_count):
            work_queue.put(None)

    def worker() -> None:
        while True:
            plan = work_queue.get()
            try:
                if plan is None:
                    return
                cursor = None if cursors is None else cursors.get(plan.inventory.manifestation_key)
                next_batch_index = 0
                try:
                    for batch in iter_source_batches(
                        plan,
                        batch_size=batch_size,
                        cursor=cursor,
                        late_cutoff_us=late_cutoff_us,
                    ):
                        source_slots[plan.inventory.source_rank].acquire()
                        reorder_slots.acquire()
                        output_queue.put((plan.inventory.source_rank, batch))
                        next_batch_index = max(next_batch_index, batch.batch_index + 1)
                except Exception as error:
                    source_slots[plan.inventory.source_rank].acquire()
                    reorder_slots.acquire()
                    output_queue.put(
                        (
                            plan.inventory.source_rank,
                            ParseBatch(
                                source_rank=plan.inventory.source_rank,
                                batch_index=next_batch_index,
                                observations=(),
                                diagnostics=(
                                    ParseDiagnostic(
                                        code="worker_failure",
                                        source_range=None,
                                        detail=type(error).__name__,
                                    ),
                                ),
                                records_seen=0,
                                complete_end=0 if cursor is None else cursor.byte_offset,
                                latest_source_order=0 if cursor is None else cursor.latest_source_order,
                                done=True,
                                cursor=cursor,
                                classification=CursorClassification(CursorOutcome.MALFORMED_RANGE, "worker failed"),
                            ),
                        )
                    )
            finally:
                work_queue.task_done()

    feeder = threading.Thread(target=feed, name="codex-adapter-feeder", daemon=True)
    threads = [threading.Thread(target=worker, name=f"codex-adapter-worker-{index}", daemon=True) for index in range(thread_count)]
    feeder.start()
    for thread in threads:
        thread.start()

    expected_rank_index = 0
    expected_batch_index = 0
    buffered: dict[tuple[int, int], ParseBatch] = {}
    max_depth = 0
    try:
        while expected_rank_index < len(selected):
            source_rank, batch = output_queue.get()
            max_depth = max(max_depth, output_queue.qsize() + len(buffered))
            if batch is None:
                continue
            buffered[(source_rank, batch.batch_index)] = batch
            while expected_rank_index < len(selected) and (
                selected[expected_rank_index].inventory.source_rank,
                expected_batch_index,
            ) in buffered:
                key = (selected[expected_rank_index].inventory.source_rank, expected_batch_index)
                ready = buffered.pop(key)
                reorder_slots.release()
                source_slots[ready.source_rank].release()
                yield ready
                if ready.done:
                    expected_rank_index += 1
                    expected_batch_index = 0
                else:
                    expected_batch_index += 1
        work_queue.join()
        feeder.join()
        for thread in threads:
            thread.join()
    finally:
        if metrics_sink is not None:
            metrics_sink.append({"max_queue_depth": max_depth, "selected_sources": len(selected)})
