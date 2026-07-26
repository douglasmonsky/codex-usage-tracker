"""One explicit incremental refresh composition for every ingestion caller."""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from .database import (
    analytical_generation_digest,
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
from .lease import RefreshLeaseRepository
from .models import CutoverState
from .normalize import NormalizedBatch, normalize_batch, parser_state_from_json
from .operational import (
    initialize_operational_database,
    load_cutover_control,
    promote_cutover,
    register_source,
    transition_cutover,
)
from .parser import ParsedBatch, iter_jsonl_batches, parse_jsonl
from .writer import WriteResult, commit_refresh


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


class KernelIngestor:
    """Coordinate discovery, parsing, normalization, writing, and cutover."""

    def __init__(self, analytical_path: Path, operational_path: Path) -> None:
        self.analytical_path = analytical_path.resolve()
        self.operational_path = operational_path.resolve()

    def refresh(
        self,
        sources: list[Path],
        *,
        trigger: RefreshTrigger,
        owner_id: str,
    ) -> RefreshResult:
        if not isinstance(trigger, RefreshTrigger):
            raise ValueError("first build requires an explicit refresh trigger")
        if trigger is RefreshTrigger.WATCHER and not self._has_active_kernel():
            raise ValueError("watcher requires an existing active kernel")
        self._initialize_for_explicit_refresh()
        observations = tuple(observe_source(path) for path in sources)
        request_hash = _request_hash(observations)
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
            recovered_generation = self._recover_or_active_generation()
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
            if not plans:
                result = _empty_result(
                    lease.refresh_run_id,
                    recovered_generation,
                    "no_changes",
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
                initial_stream = self._active_generation() == 0 and all(
                    plan.prior_source_id is None for plan in plans
                )
                if initial_stream:
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
                if initial_stream:
                    write_path, isolated = active_path, False
                else:
                    write_path, isolated = self._write_path(
                        active_path,
                        plans,
                        normalized,
                        generation,
                        lease.refresh_run_id,
                    )
                self._begin_cutover(lease.refresh_run_id, write_path)
                if initial_stream:
                    written = self._commit_initial_stream(
                        write_path,
                        plans,
                        generation,
                        guard.check,
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
                written = self._catch_up(
                    sources,
                    write_path,
                    generation,
                    isolated,
                    written,
                    guard.check,
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
                self._promote(write_path, generation)
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
            )
            leases.complete(
                lease.refresh_run_id,
                generation=generation,
                result=_result_payload(result),
            )
            return result
        except BaseException:
            leases.fail(lease.refresh_run_id, "refresh.failed")
            self._mark_cutover_failed()
            raise

    def _initialize_for_explicit_refresh(self) -> None:
        initialize_analytical_database(self.analytical_path)
        initialize_operational_database(self.operational_path)

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
    ) -> WriteResult:
        transaction_ms: list[float] = []
        latest: WriteResult | None = None
        for plan in plans:
            prior_state = None
            start_byte = plan.start_byte
            start_line = plan.start_line
            for parsed in iter_jsonl_batches(plan, prior_state, max_lines=1000):
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
                latest = commit_refresh(
                    path,
                    (chunk_plan,),
                    (parsed,),
                    (normalized,),
                    generation=generation,
                    reselect_canonical=True,
                    assert_fence=assert_fence,
                    generation_plans=plans,
                )
                transaction_ms.extend(latest.transaction_ms)
                prior_state = parsed.final_state
                start_byte = parsed.end_byte
                start_line = parsed.end_line
        if latest is None:
            raise RuntimeError("initial stream produced no source state")
        return WriteResult(
            inserted_calls=latest.inserted_calls,
            inserted_tools=latest.inserted_tools,
            deleted_rows=0,
            canonical_calls=latest.canonical_calls,
            excluded_calls=latest.excluded_calls,
            transaction_ms=tuple(transaction_ms),
        )

    def _catch_up(
        self,
        sources: list[Path],
        write_path: Path,
        generation: int,
        isolated: bool,
        written: WriteResult,
        assert_fence,
    ) -> WriteResult:
        """Reach a stable complete-line high water before first promotion."""

        transaction_ms = list(written.transaction_ms)
        deleted_rows = written.deleted_rows
        latest = written
        for _attempt in range(3):
            observations = tuple(observe_source(path) for path in sources)
            plans = self._plans_from_artifact(observations, write_path)
            if not plans:
                return WriteResult(
                    inserted_calls=latest.inserted_calls,
                    inserted_tools=latest.inserted_tools,
                    deleted_rows=deleted_rows,
                    canonical_calls=latest.canonical_calls,
                    excluded_calls=latest.excluded_calls,
                    transaction_ms=tuple(transaction_ms),
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

    def _promote(self, staging_path: Path, generation: int) -> None:
        digest = analytical_generation_digest(staging_path, generation)
        promote_cutover(
            self.operational_path,
            active_kernel_path=staging_path,
            generation=generation,
            integrity_digest=digest,
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
        if self.operational_path.is_file():
            active = load_cutover_control(self.operational_path).active_kernel_path
            if active is not None:
                return active
        return self.analytical_path

    def _active_generation(self) -> int:
        if not self.operational_path.is_file():
            return 0
        return load_cutover_control(self.operational_path).active_generation or 0

    def _next_generation(self) -> int:
        return self._active_generation() + 1

    def _recover_or_active_generation(self) -> int:
        control = load_cutover_control(self.operational_path)
        candidate = control.staging_kernel_path or self._active_path()
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
        active = control.active_generation or 0
        if latest > active and control.state in {
            CutoverState.FAILED,
            CutoverState.BUILDING,
            CutoverState.READY,
        }:
            if control.state is CutoverState.FAILED:
                self._begin_cutover(
                    control.refresh_run_id or "recovery",
                    candidate,
                )
            self._promote(candidate, latest)
            return latest
        if control.state in {CutoverState.BUILDING, CutoverState.READY}:
            transition_cutover(
                self.operational_path,
                CutoverState.FAILED,
                failure_code="refresh.interrupted",
            )
        return active

    def _write_path(
        self,
        active_path: Path,
        plans: tuple[SourcePlan, ...],
        normalized: tuple[NormalizedBatch, ...],
        generation: int,
        refresh_run_id: str,
    ) -> tuple[Path, bool]:
        requires_isolation = any(
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


def _request_hash(observations: tuple[SourceObservation, ...]) -> str:
    payload = "|".join(
        f"{item.source_id}:{item.complete_size}:{item.modified_ns}"
        for item in observations
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _write_result(
    refresh_run_id: str,
    plans: tuple[SourcePlan, ...],
    generation: int,
    written: WriteResult,
) -> RefreshResult:
    reasons = sorted({plan.kind.value for plan in plans})
    return RefreshResult(
        refresh_run_id=refresh_run_id,
        planner_reason="+".join(reasons),
        generation=generation,
        changed_sources=len(plans),
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
    }
