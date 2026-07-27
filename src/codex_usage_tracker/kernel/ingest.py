"""One explicit incremental refresh composition for every ingestion caller."""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .database import (
    analytical_generation_digest,
    analytical_schema_version,
    initialize_analytical_database,
    open_read_snapshot,
)
from .discovery import (
    SourceCursor,
    SourceObservation,
    SourcePlan,
    observe_source,
    plan_source,
)
from .hydration import (
    HydrationPreset,
    HydrationSelection,
    catalog_checkpoints,
    catalog_sources,
    select_hydration_sources,
)
from .lease import RefreshLeaseRepository
from .live.journal import GenerationJournal
from .models import CutoverState
from .normalize import NormalizedBatch, normalize_batch, parser_state_from_json
from .operational import (
    discard_staged_hydration,
    hydrated_source_ids,
    hydrated_source_locations,
    hydration_catalog_checkpoints,
    hydration_selection_revision,
    initialize_operational_database,
    load_cutover_control,
    load_staged_hydration,
    promote_cutover,
    record_hydration_catalog,
    record_legacy_cache_metadata,
    register_source,
    reset_cutover_for_schema_upgrade,
    restore_hydration_states,
    stage_hydration_catalog,
    transition_cutover,
)
from .parser import ParsedBatch, iter_jsonl_batches, parse_jsonl
from .schema import SCHEMA_VERSION
from .writer import (
    WriteResult,
    commit_empty_initial_refresh,
    commit_initial_batches,
    commit_refresh,
    finalize_initial_refresh,
    prepare_initial_refresh,
)

_INITIAL_STREAM_BATCH_LINES = 1_000
_INITIAL_WRITE_BATCHES = 25
_BULK_EXPANSION_MIN_SOURCES = 8
_BULK_EXPANSION_MIN_BYTES = 8 * 1024 * 1024


class RefreshTrigger(str, Enum):
    CLI_REFRESH = "cli_refresh"
    MCP_USAGE_REFRESH = "mcp_usage_refresh"
    CONSOLE_REFRESH = "console_refresh"
    WATCHER = "watcher"


@dataclass(frozen=True)
class RefreshResult:
    refresh_run_id: str
    planner_reason: str
    generation: int
    changed_sources: int
    inserted_calls: int
    inserted_tools: int
    deleted_rows: int
    writer_transaction_ms: tuple[float, ...]
    joined: bool = False
    live_event_id: int | None = None
    live_journal_status: str = "not_configured"


class KernelIngestor:
    """Coordinate discovery, parsing, normalization, writing, and cutover."""

    def __init__(
        self,
        analytical_path: Path,
        operational_path: Path,
        *,
        journal: GenerationJournal | None = None,
    ) -> None:
        self.analytical_path = analytical_path.resolve()
        self.operational_path = operational_path.resolve()
        self._journal = journal
        self._build_path_override: Path | None = None

    def refresh(
        self,
        sources: list[Path],
        *,
        trigger: RefreshTrigger,
        owner_id: str,
        hydration_preset: HydrationPreset = HydrationPreset.COMPLETE,
        captured_at: datetime | None = None,
    ) -> RefreshResult:
        if not isinstance(trigger, RefreshTrigger):
            raise ValueError("first build requires an explicit refresh trigger")
        if trigger is RefreshTrigger.WATCHER and not self._has_active_kernel():
            raise ValueError("watcher requires an existing active kernel")
        self._initialize_for_explicit_refresh()
        captured = captured_at or datetime.now(timezone.utc)
        catalog = catalog_sources(
            tuple(sources),
            checkpoints=hydration_catalog_checkpoints(
                self.operational_path,
            ),
        )
        selection = select_hydration_sources(
            catalog,
            preset=hydration_preset,
            captured_at=captured,
            hydrated_source_ids=hydrated_source_ids(self.operational_path),
            hydrated_paths=hydrated_source_locations(self.operational_path),
        )
        observations = tuple(
            item.observation for item in selection.hydrate
        )
        request_hash = _request_hash(
            tuple(item.observation for item in catalog),
            scope=hydration_preset.value,
        )
        leases = RefreshLeaseRepository(self.operational_path)
        lease = leases.acquire(request_hash, owner_id)
        if not lease.created:
            return RefreshResult(
                refresh_run_id=lease.refresh_run_id,
                planner_reason="busy" if lease.busy else "joined",
                generation=self._active_generation(),
                changed_sources=0,
                inserted_calls=0,
                inserted_tools=0,
                deleted_rows=0,
                writer_transaction_ms=(),
                joined=not lease.busy,
            )
        try:
            was_failed = (
                load_cutover_control(self.operational_path).state
                is CutoverState.FAILED
            )
            recovered_generation = self._recover_or_active_generation(
                selection,
            )
            if (
                was_failed
                and load_cutover_control(self.operational_path).state
                is CutoverState.ACTIVE
            ):
                for observation in observations:
                    register_source(
                        self.operational_path,
                        observation.source_id,
                        observation.path,
                    )
            active_path = self._active_path()
            plans = self._plans(observations, active_path)
            stage_hydration_catalog(
                self.operational_path,
                selection,
            )
            if not plans:
                if recovered_generation == 0:
                    generation = 1
                    with leases.maintain(
                        lease.refresh_run_id,
                        owner_id,
                    ) as guard:
                        self._begin_cutover(
                            lease.refresh_run_id,
                            active_path,
                        )
                        written = commit_empty_initial_refresh(
                            active_path,
                            generation=generation,
                            assert_fence=guard.check,
                        )
                        written, selection, catch_up_source_ids = self._catch_up(
                            sources,
                            active_path,
                            generation,
                            False,
                            written,
                            guard.check,
                            selection,
                        )
                        self._promote(
                            active_path,
                            generation,
                            hydration_selection=selection,
                        )
                    result = _write_result(
                        lease.refresh_run_id,
                        (),
                        generation,
                        written,
                        changed_sources=len(catch_up_source_ids),
                    )
                    leases.complete(
                        lease.refresh_run_id,
                        generation=generation,
                        result=_result_payload(result),
                    )
                    return result
                result = _empty_result(
                    lease.refresh_run_id,
                    recovered_generation,
                    "no_changes",
                )
                record_hydration_catalog(
                    self.operational_path,
                    selection,
                    hydrated_generation=recovered_generation,
                )
                leases.complete(
                    lease.refresh_run_id,
                    generation=recovered_generation,
                    result=_result_payload(result),
                )
                return result
            generation = self._next_generation()
            timings: dict[str, float] = {}
            with leases.maintain(lease.refresh_run_id, owner_id) as guard:
                stage_started = time.perf_counter()
                new_plans = tuple(
                    plan for plan in plans if plan.prior_source_id is None
                )
                all_new_sources = len(new_plans) == len(plans)
                large_new_source_set = (
                    len(new_plans) >= _BULK_EXPANSION_MIN_SOURCES
                    or sum(
                        plan.end_byte - plan.start_byte
                        for plan in new_plans
                    )
                    >= _BULK_EXPANSION_MIN_BYTES
                )
                streamed_bulk = (
                    self._active_generation() == 0 and all_new_sources
                ) or (
                    self._active_generation() > 0
                    and large_new_source_set
                    and all(
                        not plan.replace_existing
                        for plan in plans
                        if plan.prior_source_id is not None
                    )
                )
                if streamed_bulk:
                    parsed: tuple[ParsedBatch, ...] = ()
                    normalized: tuple[NormalizedBatch, ...] = ()
                else:
                    parsed, normalized = self._prepare(
                        plans,
                        generation,
                        active_path,
                    )
                timings["parsing"] = time.perf_counter() - stage_started
                guard.check()
                leases.progress(
                    lease.refresh_run_id,
                    owner_id,
                    stage="writing",
                    percent=45,
                    high_water={
                        plan.observation.source_id: plan.end_byte
                        for plan in plans
                    },
                    changed_sources=len(plans),
                    timings=timings,
                )
                stage_started = time.perf_counter()

                def report_initial_progress(
                    stage: str,
                    percent: float,
                    high_water: dict[str, int],
                ) -> None:
                    timings["writing"] = time.perf_counter() - stage_started
                    leases.progress(
                        lease.refresh_run_id,
                        owner_id,
                        stage=stage,
                        percent=percent,
                        high_water=high_water,
                        changed_sources=len(plans),
                        timings=timings,
                    )

                write_path, isolated = self._write_path(
                    active_path,
                    plans,
                    normalized,
                    generation,
                    lease.refresh_run_id,
                    force_isolation=(
                        streamed_bulk and self._active_generation() > 0
                    ),
                )
                self._begin_cutover(lease.refresh_run_id, write_path)
                if streamed_bulk:
                    written = self._commit_initial_stream(
                        write_path,
                        plans,
                        generation,
                        guard.check,
                        report_initial_progress,
                    )
                else:
                    written = commit_refresh(
                        write_path,
                        plans,
                        parsed,
                        normalized,
                        generation=generation,
                        reselect_canonical=isolated,
                        assert_fence=guard.check,
                    )
                timings["writing"] = time.perf_counter() - stage_started
                written, selection, catch_up_source_ids = self._catch_up(
                    sources,
                    write_path,
                    generation,
                    isolated,
                    written,
                    guard.check,
                    selection,
                )
                guard.check()
                leases.progress(
                    lease.refresh_run_id,
                    owner_id,
                    stage="promoting",
                    percent=90,
                    changed_sources=len(plans),
                    inserted=written.inserted_calls + written.inserted_tools,
                    deleted=written.deleted_rows,
                    timings=timings,
                )
                stage_started = time.perf_counter()
                self._promote(
                    write_path,
                    generation,
                    hydration_selection=selection,
                )
                timings["promoting"] = time.perf_counter() - stage_started
            for plan in plans:
                register_source(
                    self.operational_path,
                    plan.observation.source_id,
                    plan.observation.path,
                )
            result = _write_result(
                lease.refresh_run_id,
                plans,
                generation,
                written,
                changed_sources=len(
                    {
                        plan.observation.source_id for plan in plans
                    }
                    | catch_up_source_ids
                ),
            )
            result = self._publish_generation(result)
            leases.complete(
                lease.refresh_run_id,
                generation=generation,
                result=_result_payload(result),
            )
            return result
        except BaseException:
            leases.fail(lease.refresh_run_id, "refresh.failed")
            self._mark_cutover_failed()
            restore_hydration_states(self.operational_path)
            raise
    def _initialize_for_explicit_refresh(self) -> None:
        initialize_operational_database(self.operational_path)
        control = load_cutover_control(self.operational_path)
        active = control.active_kernel_path
        active_version = (
            analytical_schema_version(active) if active is not None else None
        )
        base_version = analytical_schema_version(self.analytical_path)
        if active is not None and active_version == SCHEMA_VERSION:
            self._build_path_override = None
            return
        if active_version is not None or (
            active is None
            and base_version is not None
            and base_version != SCHEMA_VERSION
        ):
            legacy_cache = active if active_version is not None else self.analytical_path
            if legacy_cache is None:
                raise ValueError("schema upgrade requires a preserved cache artifact")
            record_legacy_cache_metadata(self.operational_path, legacy_cache)
            upgrade_path = self.analytical_path.with_name(
                f".{self.analytical_path.stem}.schema-{SCHEMA_VERSION}.sqlite3"
            )
            initialize_analytical_database(upgrade_path, replace=True)
            self.analytical_path = upgrade_path
            self._build_path_override = upgrade_path
            if active is None:
                reset_cutover_for_schema_upgrade(self.operational_path)
            return
        initialize_analytical_database(
            self.analytical_path,
            replace=(
                active is None
                and base_version == SCHEMA_VERSION
                and control.state
                in {
                    CutoverState.BUILDING,
                    CutoverState.READY,
                    CutoverState.FAILED,
                }
            ),
        )

    def _publish_generation(self, result: RefreshResult) -> RefreshResult:
        if self._journal is None:
            return result
        try:
            event = self._journal.publish_generation(
                result.generation,
                publication_id=(
                    load_cutover_control(self.operational_path).integrity_digest
                    or result.refresh_run_id
                ),
                changed_sources=result.changed_sources,
                inserted_calls=result.inserted_calls,
                inserted_tools=result.inserted_tools,
                deleted_rows=result.deleted_rows,
            )
        except (OSError, sqlite3.Error, ValueError):
            return replace(result, live_journal_status="snapshot_required")
        return replace(
            result,
            live_event_id=event.event_id,
            live_journal_status="published",
        )

    def _plans(
        self,
        observations: tuple[SourceObservation, ...],
        analytical_path: Path,
    ) -> tuple[SourcePlan, ...]:
        plans = []
        for observation in observations:
            planned = plan_source(
                observation,
                self._cursor(observation, analytical_path),
            )
            if planned is not None:
                plans.append(planned)
        return tuple(plans)

    def _cursor(
        self,
        observation: SourceObservation,
        analytical_path: Path,
    ) -> SourceCursor | None:
        source = _registered_source_id(
            self.operational_path,
            observation.path,
            observation.source_id,
        )
        if source is None:
            return None
        with open_read_snapshot(analytical_path) as connection:
            row = connection.execute(
                "SELECT * FROM sources WHERE source_id = ?",
                (source,),
            ).fetchone()
        if row is None:
            return None
        return SourceCursor(
            source_id=str(row["source_id"]),
            parsed_byte_offset=int(row["parsed_byte_offset"]),
            parsed_line_number=int(row["parsed_line_number"]),
            size_bytes=int(row["size_bytes"]),
            prefix_fingerprint=str(row["replacement_fingerprint"]),
            is_archived=str(row["archive_state"]) == "archived",
        )

    def _prepare(
        self,
        plans: tuple[SourcePlan, ...],
        generation: int,
        analytical_path: Path,
    ) -> tuple[tuple[ParsedBatch, ...], tuple[NormalizedBatch, ...]]:
        parsed_batches = []
        normalized_batches = []
        for plan in plans:
            prior_state = self._parser_state(plan, analytical_path)
            parsed = parse_jsonl(plan, prior_state)
            parsed_batches.append(parsed)
            normalized_batches.append(
                normalize_batch(plan, parsed, generation=generation)
            )
        return tuple(parsed_batches), tuple(normalized_batches)

    def _parser_state(self, plan: SourcePlan, analytical_path: Path):
        if plan.replace_existing or plan.prior_source_id is None:
            return None
        with open_read_snapshot(analytical_path) as connection:
            row = connection.execute(
                "SELECT parser_state_json FROM sources WHERE source_id = ?",
                (plan.prior_source_id,),
            ).fetchone()
        return parser_state_from_json(row[0] if row else None)

    def _commit_initial_stream(
        self,
        path: Path,
        plans: tuple[SourcePlan, ...],
        generation: int,
        assert_fence,
        report_progress: Callable[[str, float, dict[str, int]], None],
    ) -> WriteResult:
        transaction_ms: list[float] = []
        parser_states = {
            plan.observation.source_id: self._parser_state(plan, path)
            for plan in plans
        }
        prepare_initial_refresh(
            path,
            transaction_ms,
            assert_fence=assert_fence,
        )
        initialize_generation = True
        pending: list[tuple[SourcePlan, ParsedBatch, NormalizedBatch]] = []
        total_bytes = sum(
            max(0, plan.end_byte - plan.start_byte)
            for plan in plans
        )
        committed_bytes = 0
        pending_bytes = 0
        high_water: dict[str, int] = {}

        def report_committed() -> None:
            ratio = committed_bytes / max(1, total_bytes)
            report_progress(
                "writing",
                min(80.0, 45.0 + 35.0 * ratio),
                dict(high_water),
            )

        for plan in plans:
            prior_state = parser_states[plan.observation.source_id]
            start_byte = plan.start_byte
            start_line = plan.start_line
            for parsed in iter_jsonl_batches(
                plan,
                prior_state,
                max_lines=_INITIAL_STREAM_BATCH_LINES,
            ):
                chunk_plan = replace(
                    plan,
                    start_byte=start_byte,
                    end_byte=parsed.end_byte,
                    start_line=start_line,
                    end_line=parsed.end_line,
                )
                normalized = normalize_batch(
                    chunk_plan,
                    parsed,
                    generation=generation,
                )
                for row in normalized.model_calls:
                    row["duplicate_state"] = "canonical"
                for row in normalized.allowances:
                    row["duplicate_state"] = "canonical"
                pending.append((chunk_plan, parsed, normalized))
                pending_bytes += parsed.end_byte - start_byte
                high_water[plan.observation.source_id] = parsed.end_byte
                if len(pending) == _INITIAL_WRITE_BATCHES:
                    commit_initial_batches(
                        path,
                        tuple(pending),
                        generation=generation,
                        generation_plans=plans,
                        initialize_generation=initialize_generation,
                        transaction_ms=transaction_ms,
                        assert_fence=assert_fence,
                    )
                    pending.clear()
                    committed_bytes += pending_bytes
                    pending_bytes = 0
                    report_committed()
                    initialize_generation = False
                prior_state = parsed.final_state
                start_byte = parsed.end_byte
                start_line = parsed.end_line
        if pending:
            commit_initial_batches(
                path,
                tuple(pending),
                generation=generation,
                generation_plans=plans,
                initialize_generation=initialize_generation,
                transaction_ms=transaction_ms,
                assert_fence=assert_fence,
            )
            initialize_generation = False
            committed_bytes += pending_bytes
            report_committed()
        if initialize_generation:
            raise RuntimeError("initial stream produced no source state")
        report_progress("canonicalizing", 82, dict(high_water))
        return finalize_initial_refresh(
            path,
            generation=generation,
            transaction_ms=transaction_ms,
            assert_fence=assert_fence,
            on_indexing=lambda: report_progress(
                "indexing",
                84,
                dict(high_water),
            ),
            on_indexes_built=lambda: report_progress(
                "validating",
                87,
                dict(high_water),
            ),
        )

    def _catch_up(
        self,
        sources: list[Path],
        write_path: Path,
        generation: int,
        isolated: bool,
        written: WriteResult,
        assert_fence,
        selection: HydrationSelection,
    ) -> tuple[WriteResult, HydrationSelection, frozenset[str]]:
        """Reach a stable complete-line high water before first promotion."""

        transaction_ms = list(written.transaction_ms)
        deleted_rows = written.deleted_rows
        latest = written
        catch_up_source_ids: set[str] = set()
        selected_source_ids = frozenset(
            item.observation.source_id for item in selection.hydrate
        )
        selected_paths = frozenset(item.path for item in selection.hydrate)
        checkpoints = catalog_checkpoints(
            selection.hydrate + selection.deferred
        )
        for _attempt in range(3):
            catalog = catalog_sources(
                tuple(sources),
                checkpoints=checkpoints,
            )
            checkpoints = catalog_checkpoints(catalog)
            selection = select_hydration_sources(
                catalog,
                preset=selection.preset,
                captured_at=selection.captured_at,
                hydrated_source_ids=selected_source_ids,
                hydrated_paths=selected_paths,
            )
            observations = tuple(
                item.observation for item in selection.hydrate
            )
            plans = self._plans_from_artifact(observations, write_path)
            if not plans:
                return (
                    WriteResult(
                    inserted_calls=latest.inserted_calls,
                    inserted_tools=latest.inserted_tools,
                    deleted_rows=deleted_rows,
                    canonical_calls=latest.canonical_calls,
                    excluded_calls=latest.excluded_calls,
                    transaction_ms=tuple(transaction_ms),
                    ),
                    selection,
                    frozenset(catch_up_source_ids),
                )
            parsed, normalized = self._prepare(plans, generation, write_path)
            latest = commit_refresh(
                write_path,
                plans,
                parsed,
                normalized,
                generation=generation,
                reselect_canonical=isolated,
                assert_fence=assert_fence,
            )
            deleted_rows += latest.deleted_rows
            transaction_ms.extend(latest.transaction_ms)
            catch_up_source_ids.update(
                plan.observation.source_id for plan in plans
            )
            selected_source_ids = frozenset(
                item.observation.source_id for item in selection.hydrate
            )
            selected_paths = frozenset(
                item.path for item in selection.hydrate
            )
        raise RuntimeError("source high water did not stabilize")

    def _plans_from_artifact(
        self,
        observations: tuple[SourceObservation, ...],
        analytical_path: Path,
    ) -> tuple[SourcePlan, ...]:
        plans: list[SourcePlan] = []
        with open_read_snapshot(analytical_path) as connection:
            for observation in observations:
                row = connection.execute(
                    "SELECT * FROM sources WHERE source_id = ?",
                    (observation.source_id,),
                ).fetchone()
                cursor = (
                    SourceCursor(
                        source_id=str(row["source_id"]),
                        parsed_byte_offset=int(row["parsed_byte_offset"]),
                        parsed_line_number=int(row["parsed_line_number"]),
                        size_bytes=int(row["size_bytes"]),
                        prefix_fingerprint=str(row["replacement_fingerprint"]),
                        is_archived=str(row["archive_state"]) == "archived",
                    )
                    if row is not None
                    else None
                )
                plan = plan_source(observation, cursor)
                if plan is not None:
                    plans.append(plan)
        return tuple(plans)

    def _begin_cutover(
        self,
        refresh_run_id: str,
        staging_path: Path,
    ) -> None:
        control = load_cutover_control(self.operational_path)
        if control.state in {
            CutoverState.ABSENT,
            CutoverState.ACTIVE,
            CutoverState.FAILED,
        }:
            transition_cutover(
                self.operational_path,
                CutoverState.BUILDING,
                staging_kernel_path=staging_path,
                refresh_run_id=refresh_run_id,
            )

    def _promote(
        self,
        staging_path: Path,
        generation: int,
        *,
        hydration_selection: HydrationSelection | None = None,
    ) -> None:
        digest = analytical_generation_digest(staging_path, generation)
        promote_cutover(
            self.operational_path,
            active_kernel_path=staging_path,
            generation=generation,
            integrity_digest=digest,
            hydration_selection=hydration_selection,
        )

    def _mark_cutover_failed(self) -> None:
        control = load_cutover_control(self.operational_path)
        if control.state in {CutoverState.BUILDING, CutoverState.READY}:
            transition_cutover(
                self.operational_path,
                CutoverState.FAILED,
                failure_code="refresh.failed",
            )

    def _has_active_kernel(self) -> bool:
        if not self.analytical_path.is_file() or not self.operational_path.is_file():
            return False
        return load_cutover_control(self.operational_path).active_kernel_path is not None

    def _active_path(self) -> Path:
        if self._build_path_override is not None:
            return self._build_path_override
        if self.operational_path.is_file():
            control = load_cutover_control(self.operational_path)
            active = control.active_kernel_path
            if active is not None:
                if control.active_schema == SCHEMA_VERSION:
                    return active
                return self.analytical_path
        return self.analytical_path

    def _active_generation(self) -> int:
        if not self.operational_path.is_file():
            return 0
        return load_cutover_control(self.operational_path).active_generation or 0

    def _next_generation(self) -> int:
        return self._active_generation() + 1

    def _recover_or_active_generation(
        self,
        hydration_selection: HydrationSelection,
    ) -> int:
        control = load_cutover_control(self.operational_path)
        active = control.active_generation or 0
        candidate = control.staging_kernel_path
        staged = load_staged_hydration(self.operational_path)
        latest = 0
        if candidate is not None:
            try:
                with open_read_snapshot(candidate) as connection:
                    latest = int(
                        connection.execute(
                            """
                            SELECT COALESCE(MAX(generation), 0)
                            FROM generations
                            WHERE integrity_status = 'valid'
                            """
                        ).fetchone()[0]
                    )
            except (ValueError, sqlite3.DatabaseError):
                latest = 0
        compatible = (
            staged is not None
            and staged["preset"] == hydration_selection.preset.value
            and staged["coverage_revision"]
            == hydration_selection_revision(hydration_selection)
        )
        if latest > active and compatible and candidate is not None:
            assert staged is not None
            recovered_selection = replace(
                hydration_selection,
                captured_at=_required_timestamp(staged["captured_at"]),
                cutoff_at=_optional_timestamp(staged["cutoff_at"]),
            )
            if control.state is CutoverState.FAILED:
                self._begin_cutover(
                    control.refresh_run_id or "recovery",
                    candidate,
                )
            self._promote(
                candidate,
                latest,
                hydration_selection=recovered_selection,
            )
            return latest
        if control.state in {CutoverState.BUILDING, CutoverState.READY}:
            transition_cutover(
                self.operational_path,
                CutoverState.FAILED,
                failure_code="refresh.interrupted",
            )
            restore_hydration_states(self.operational_path)
        if candidate is not None:
            discard_staged_hydration(self.operational_path)
        return active

    def _write_path(
        self,
        active_path: Path,
        plans: tuple[SourcePlan, ...],
        normalized: tuple[NormalizedBatch, ...],
        generation: int,
        refresh_run_id: str,
        *,
        force_isolation: bool = False,
    ) -> tuple[Path, bool]:
        requires_isolation = force_isolation or any(
            plan.replace_existing and plan.prior_source_id is not None
            for plan in plans
        ) or self._active_collision_requires_isolation(
            active_path,
            plans,
            normalized,
        )
        if not requires_isolation:
            return active_path, False
        suffix = uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{generation}:{refresh_run_id}",
        ).hex[:12]
        staging = active_path.with_name(
            f".{active_path.stem}.g{generation}-{suffix}.sqlite3"
        )
        _clone_database(active_path, staging)
        return staging, True

    def _active_collision_requires_isolation(
        self,
        active_path: Path,
        plans: tuple[SourcePlan, ...],
        normalized: tuple[NormalizedBatch, ...],
    ) -> bool:
        if self._active_generation() == 0:
            return False
        fingerprints = tuple(
            sorted(
                {
                    str(row["canonical_call_id"])
                    for plan, batch in zip(plans, normalized, strict=True)
                    if not plan.observation.is_archived
                    for row in batch.model_calls
                }
            )
        )
        if not fingerprints:
            return False
        with open_read_snapshot(active_path) as connection:
            for start in range(0, len(fingerprints), 500):
                chunk = fingerprints[start : start + 500]
                placeholders = ", ".join("?" for _ in chunk)
                row = connection.execute(
                    f"""
                    SELECT 1
                    FROM model_calls
                    JOIN sources USING (source_id)
                    WHERE model_calls.duplicate_state = 'canonical'
                      AND sources.archive_state = 'archived'
                      AND model_calls.canonical_call_id IN ({placeholders})
                    LIMIT 1
                    """,
                    chunk,
                ).fetchone()
                if row is not None:
                    return True
        return False


def refresh_request_hash(
    sources: list[Path],
    *,
    hydration_preset: HydrationPreset = HydrationPreset.COMPLETE,
) -> str:
    """Return the same bounded source-set identity used by refresh leases."""

    return _request_hash(
        tuple(observe_source(path) for path in sources),
        scope=hydration_preset.value,
    )


def _registered_source_id(
    path: Path,
    source: Path,
    observed_source_id: str,
) -> str | None:
    if not path.is_file():
        return None
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            """
            SELECT source_id
            FROM source_registry
            WHERE source_location = ? OR source_id = ?
            ORDER BY source_location = ? DESC
            LIMIT 1
            """,
            (
                str(source.resolve()),
                observed_source_id,
                str(source.resolve()),
            ),
        ).fetchone()
        return str(row[0]) if row else None


def _clone_database(source: Path, destination: Path) -> None:
    if destination.exists():
        raise ValueError("staging analytical database already exists")
    source_uri = source.as_uri() + "?mode=ro"
    try:
        with (
            sqlite3.connect(source_uri, uri=True) as reader,
            sqlite3.connect(destination) as writer,
        ):
            reader.backup(writer)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    destination.chmod(0o600)


def _request_hash(
    observations: tuple[SourceObservation, ...],
    *,
    scope: str = HydrationPreset.COMPLETE.value,
) -> str:
    payload = scope + "|" + "|".join(
        f"{item.source_id}:{item.complete_size}:{item.modified_ns}"
        for item in observations
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _required_timestamp(value: object) -> datetime:
    parsed = _optional_timestamp(value)
    if parsed is None:
        raise ValueError("staged coverage timestamp is invalid")
    return parsed


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _write_result(
    refresh_run_id: str,
    plans: tuple[SourcePlan, ...],
    generation: int,
    written: WriteResult,
    *,
    changed_sources: int | None = None,
) -> RefreshResult:
    reasons = sorted({plan.kind.value for plan in plans})
    return RefreshResult(
        refresh_run_id=refresh_run_id,
        planner_reason="+".join(reasons),
        generation=generation,
        changed_sources=len(plans) if changed_sources is None else changed_sources,
        inserted_calls=written.inserted_calls,
        inserted_tools=written.inserted_tools,
        deleted_rows=written.deleted_rows,
        writer_transaction_ms=written.transaction_ms,
    )


def _empty_result(
    refresh_run_id: str,
    generation: int,
    reason: str,
) -> RefreshResult:
    return RefreshResult(
        refresh_run_id=refresh_run_id,
        planner_reason=reason,
        generation=generation,
        changed_sources=0,
        inserted_calls=0,
        inserted_tools=0,
        deleted_rows=0,
        writer_transaction_ms=(),
    )


def _result_payload(result: RefreshResult) -> dict[str, object]:
    return {
        "planner_reason": result.planner_reason,
        "generation": result.generation,
        "changed_sources": result.changed_sources,
        "inserted_calls": result.inserted_calls,
        "inserted_tools": result.inserted_tools,
        "deleted_rows": result.deleted_rows,
        "writer_transaction_ms": list(result.writer_transaction_ms),
        "live_event_id": result.live_event_id,
        "live_journal_status": result.live_journal_status,
    }
