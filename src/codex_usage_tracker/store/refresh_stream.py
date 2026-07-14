"""Single-writer persistence pipeline for parsed refresh batches."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

from codex_usage_tracker.store.api import (
    _deferred_usage_event_indexes,
    _finalize_streamed_usage_event_upserts,
    _upsert_usage_events_in_connection,
    init_db,
)
from codex_usage_tracker.store.compression_fact_ingest import IngestionFactWriter
from codex_usage_tracker.store.compression_fact_sync import (
    content_index_plans,
    sync_compression_detector_facts,
)
from codex_usage_tracker.store.compression_facts import backfill_compression_detector_facts
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.content_index import (
    index_content_for_source_plans,
    index_preextracted_content_rows,
)
from codex_usage_tracker.store.content_index_models import (
    ContentIndexPlan,
    _ExtractedContentRows,
)
from codex_usage_tracker.store.refresh_callbacks import DerivedFactSyncCallback
from codex_usage_tracker.store.refresh_parse import (
    ParsedRefreshFile,
    RefreshProgressCallback,
    default_parser_is_active,
    emit_refresh_progress,
    iter_parse_refresh_plans,
)
from codex_usage_tracker.store.source_records import upsert_source_records_from_events
from codex_usage_tracker.store.sources import (
    SourceParsePlan,
    upsert_source_file_metadata,
)

_STREAM_SOURCE_BATCH_SIZE = 16


@dataclass(frozen=True)
class RefreshStreamResult:
    stats: dict[str, int]
    parsed_events: int
    inserted_or_updated_events: int
    stage_timings_seconds: dict[str, float]


@dataclass
class _StageTimings:
    values: dict[str, float] = field(default_factory=dict)

    def add(self, name: str, started: float) -> None:
        self.values[name] = self.values.get(name, 0.0) + (perf_counter() - started)

    def segment_callback(self, prefix: str) -> Callable[[str], None]:
        segment_started = perf_counter()

        def record(stage: str) -> None:
            nonlocal segment_started
            now = perf_counter()
            self.values[f"{prefix}.{stage}"] = now - segment_started
            segment_started = now

        return record


class _RefreshStreamWriter:
    def __init__(
        self,
        *,
        db_path: Path,
        parse_plans: list[SourceParsePlan],
        session_index: dict[str, Any],
        aggregate_only: bool,
        progress_callback: RefreshProgressCallback | None,
        force_serial: bool,
        derived_fact_sync: DerivedFactSyncCallback | None,
    ) -> None:
        self.db_path = db_path
        self.parse_plans = parse_plans
        self.session_index = session_index
        self.aggregate_only = aggregate_only
        self.progress_callback = progress_callback
        self.force_serial = force_serial
        self.derived_fact_sync = derived_fact_sync
        self.stats: dict[str, int] = {}
        self.parsed_events = 0
        self.inserted = 0
        self.record_ids: list[str] = []
        self.affected_thread_keys: set[str] = set()
        self.timings = _StageTimings()
        self.content_plans = list(content_index_plans(parse_plans))
        self.content_plan_by_path = {str(plan.source_path): plan for plan in self.content_plans}
        self.collect_content = not aggregate_only and default_parser_is_active()

    def run(self) -> RefreshStreamResult:
        with connect(self.db_path) as conn:
            init_db(conn)
            full_rebuild = self._is_full_rebuild(conn)
            if full_rebuild:
                _tune_full_refresh_connection(conn)
            conn.execute("BEGIN IMMEDIATE")
            fact_writer = (
                IngestionFactWriter(conn) if full_rebuild and self.collect_content else None
            )
            self._emit_initial_progress()
            parsed_stream = iter_parse_refresh_plans(
                self.parse_plans,
                session_index=self.session_index,
                collect_content=self.collect_content,
                collect_facts=fact_writer is not None,
                progress_callback=self.progress_callback,
                force_serial=self.force_serial,
            )
            self._replace_sources(conn)
            self._stream_and_index(conn, parsed_stream, fact_writer, full_rebuild)
            finalized = self._finalize_derived_state(conn)
            self._index_fallback(conn)
            self._sync_facts(conn, fact_writer, finalized, full_rebuild)
        return RefreshStreamResult(
            stats=self.stats,
            parsed_events=self.parsed_events,
            inserted_or_updated_events=self.inserted,
            stage_timings_seconds={
                key: round(value, 6) for key, value in sorted(self.timings.values.items())
            },
        )

    def _is_full_rebuild(self, conn: Any) -> bool:
        return (
            bool(self.parse_plans)
            and all(plan.replace_existing for plan in self.parse_plans)
            and conn.execute("SELECT 1 FROM usage_events LIMIT 1").fetchone() is None
        )

    def _emit_initial_progress(self) -> None:
        status = "running" if self.parse_plans else "completed"
        for phase, message in (
            ("upserting", "Streaming source batches into the usage index"),
            ("metadata", "Updating source metadata"),
        ):
            emit_refresh_progress(
                self.progress_callback,
                phase=phase,
                status=status,
                completed=0,
                total=len(self.parse_plans),
                message=message,
                **({"parsed_events": 0} if phase == "upserting" else {}),
            )

    def _replace_sources(self, conn: Any) -> None:
        started = perf_counter()
        result = _upsert_usage_events_in_connection(
            conn,
            (),
            refresh_links=False,
            replace_source_files=(plan.path for plan in self.parse_plans if plan.replace_existing),
            maintain_source_records=False,
            maintain_compression_facts=False,
            maintain_allowance_observations=False,
            touch_revisions=False,
            sync_content_fts_on_replace=False,
        )
        self.timings.add("replacement_cleanup", started)
        self.affected_thread_keys.update(result.affected_thread_keys)

    def _stream_and_index(
        self,
        conn: Any,
        parsed_stream: Iterator[ParsedRefreshFile],
        fact_writer: IngestionFactWriter | None,
        full_rebuild: bool,
    ) -> None:
        started = perf_counter()
        with _deferred_usage_event_indexes(
            conn,
            enabled=full_rebuild,
            additional_tables=("call_diagnostic_facts", "source_records"),
        ):
            entries = self._content_entries(conn, parsed_stream, fact_writer)
            if self.collect_content:
                content_started = perf_counter()
                index_preextracted_content_rows(
                    conn,
                    entries=entries,
                    progress_callback=self.progress_callback,
                    total_sources=len(self.content_plans),
                    defer_full_fts_rebuild=any(
                        plan.replace_existing for plan in self.content_plans
                    ),
                    replacement_cleanup_done=True,
                    write_batch_sources=_STREAM_SOURCE_BATCH_SIZE,
                    defer_secondary_indexes=full_rebuild,
                )
                self.timings.add("content_pipeline", content_started)
            else:
                for _entry in entries:
                    pass
        self.timings.add("stream_and_index_maintenance", started)

    def _content_entries(
        self,
        conn: Any,
        parsed_stream: Iterator[ParsedRefreshFile],
        fact_writer: IngestionFactWriter | None,
    ) -> Iterator[tuple[ContentIndexPlan, _ExtractedContentRows]]:
        completed_sources = 0
        for parsed_batch in self._timed_batches(parsed_stream):
            self._write_batch(conn, parsed_batch, fact_writer)
            for parsed in parsed_batch:
                self._merge_stats(parsed.stats)
                if self.collect_content:
                    if parsed.content_rows is None:
                        raise RuntimeError("default parser omitted pre-extracted content rows")
                    content_started = perf_counter()
                    yield self.content_plan_by_path[str(parsed.plan.path)], parsed.content_rows
                    self.timings.add("content_writes", content_started)
            completed_sources += len(parsed_batch)
            self._emit_batch_progress(completed_sources)

    def _timed_batches(
        self,
        parsed_stream: Iterator[ParsedRefreshFile],
    ) -> Iterator[list[ParsedRefreshFile]]:
        batches = iter(_batched_refresh_files(parsed_stream))
        while True:
            started = perf_counter()
            try:
                batch = next(batches)
            except StopIteration:
                self.timings.add("parsing", started)
                return
            self.timings.add("parsing", started)
            yield batch

    def _write_batch(
        self,
        conn: Any,
        parsed_batch: list[ParsedRefreshFile],
        fact_writer: IngestionFactWriter | None,
    ) -> None:
        file_events = [event for parsed in parsed_batch for event in parsed.events]
        diagnostic_facts = [fact for parsed in parsed_batch for fact in parsed.diagnostic_facts]
        started = perf_counter()
        result = _upsert_usage_events_in_connection(
            conn,
            file_events,
            refresh_links=False,
            diagnostic_facts=diagnostic_facts,
            maintain_source_records=False,
            maintain_compression_facts=False,
            maintain_allowance_observations=False,
            touch_revisions=False,
        )
        self.timings.add("usage_upserts", started)
        self.inserted += result.inserted_or_updated_events
        self.parsed_events += len(file_events)
        self.record_ids.extend(result.record_ids)
        self.affected_thread_keys.update(result.affected_thread_keys)
        started = perf_counter()
        upsert_source_file_metadata(
            conn,
            parsed_files=[
                (
                    parsed.plan.path,
                    parsed.events,
                    parsed.stats,
                    parsed.state,
                    parsed.final_line_number,
                )
                for parsed in parsed_batch
            ],
        )
        upsert_source_records_from_events(conn, events=file_events)
        if fact_writer is not None:
            fact_started = perf_counter()
            for parsed in parsed_batch:
                if parsed.fact_rows is None:
                    raise RuntimeError("default parser omitted prebuilt compression facts")
                fact_writer.add_prebuilt(parsed.fact_rows)
            self.timings.add("direct_fact_writes", fact_started)
        self.timings.add("source_metadata", started)

    def _merge_stats(self, parsed_stats: dict[str, int]) -> None:
        for key, value in parsed_stats.items():
            self.stats[key] = self.stats.get(key, 0) + int(value)

    def _emit_batch_progress(self, completed_sources: int) -> None:
        status = "running" if completed_sources < len(self.parse_plans) else "completed"
        emit_refresh_progress(
            self.progress_callback,
            phase="upserting",
            status=status,
            completed=completed_sources,
            total=len(self.parse_plans),
            message="Streamed source batches into the usage index",
            parsed_events=self.parsed_events,
            inserted_or_updated_events=self.inserted,
        )
        emit_refresh_progress(
            self.progress_callback,
            phase="metadata",
            status=status,
            completed=completed_sources,
            total=len(self.parse_plans),
            message="Updated source metadata",
        )

    def _finalize_derived_state(self, conn: Any) -> Any:
        started = perf_counter()
        finalized = _finalize_streamed_usage_event_upserts(
            conn,
            record_ids=self.record_ids,
            affected_thread_keys=self.affected_thread_keys,
            maintain_source_records=False,
            stage_callback=self.timings.segment_callback("derived_state"),
        )
        self.timings.add("derived_state", started)
        return finalized

    def _index_fallback(self, conn: Any) -> None:
        if not self.aggregate_only and not self.collect_content:
            started = perf_counter()
            index_content_for_source_plans(
                conn,
                plans=self.content_plans,
                progress_callback=self.progress_callback,
                force_serial=self.force_serial,
            )
            self.timings.add("fallback_content_index", started)
            return
        if self.aggregate_only:
            emit_refresh_progress(
                self.progress_callback,
                phase="indexing_content",
                status="skipped",
                completed=0,
                total=0,
                message="Skipped content index for aggregate-only refresh",
            )

    def _sync_facts(
        self,
        conn: Any,
        fact_writer: IngestionFactWriter | None,
        finalized: Any,
        full_rebuild: bool,
    ) -> None:
        emit_refresh_progress(
            self.progress_callback,
            phase="syncing_facts",
            status="running",
            completed=0,
            total=1,
            message="Preparing compression evidence",
        )
        started = perf_counter()
        if fact_writer is not None:
            fact_writer.finish(stage_callback=self.timings.segment_callback("compression_facts"))
        elif full_rebuild:
            backfill_compression_detector_facts(
                conn,
                stage_callback=self.timings.segment_callback("compression_facts"),
            )
        else:
            sync_compression_detector_facts(
                conn,
                record_ids=finalized.record_ids,
                affected_thread_keys=finalized.affected_thread_keys,
            )
        self.timings.add("compression_facts", started)
        if self.derived_fact_sync is not None:
            recommendation_started = perf_counter()
            self.derived_fact_sync(conn, finalized.record_ids, full_rebuild)
            self.timings.add("recommendation_facts", recommendation_started)
        emit_refresh_progress(
            self.progress_callback,
            phase="syncing_facts",
            status="completed",
            completed=1,
            total=1,
            message="Prepared compression evidence",
        )


def write_refresh_stream(
    *,
    db_path: Path,
    parse_plans: list[SourceParsePlan],
    session_index: dict[str, Any],
    aggregate_only: bool,
    progress_callback: RefreshProgressCallback | None,
    force_serial: bool,
    derived_fact_sync: DerivedFactSyncCallback | None = None,
) -> RefreshStreamResult:
    return _RefreshStreamWriter(
        db_path=db_path,
        parse_plans=parse_plans,
        session_index=session_index,
        aggregate_only=aggregate_only,
        progress_callback=progress_callback,
        force_serial=force_serial,
        derived_fact_sync=derived_fact_sync,
    ).run()


def _batched_refresh_files(
    parsed_stream: Iterator[ParsedRefreshFile],
) -> Iterator[list[ParsedRefreshFile]]:
    batch: list[ParsedRefreshFile] = []
    for parsed in parsed_stream:
        batch.append(parsed)
        if len(batch) >= _STREAM_SOURCE_BATCH_SIZE:
            yield batch
            batch = []
    if batch:
        yield batch


def _tune_full_refresh_connection(conn: Any) -> None:
    """Use bounded connection-local memory for one rebuildable cache load."""

    conn.execute("PRAGMA cache_size = -30720")
    conn.execute("PRAGMA temp_store = FILE")
    conn.execute("PRAGMA synchronous = NORMAL")
