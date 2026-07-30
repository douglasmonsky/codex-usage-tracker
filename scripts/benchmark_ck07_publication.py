#!/usr/bin/env python3
"""Synthetic CK-07 publication qualification workload.

This harness measures only the database-v1 writer using the committed tiny
fixture.  It intentionally does not discover a user's Codex files, open a
local production database, or inspect JSONL bodies.  The JSON result is
bounded so CK-07 evidence can retain distributions rather than profiler data.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import resource
import sqlite3
import statistics
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    ProposedChangeSet,
    build_change_set,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.parser import ParseBatch
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    RefreshIntent,
    estimate_change_set,
    plan_refresh,
)
from codex_usage_tracker.agent_kernel.publication.recovery import (
    AnalyticalHead,
    PointerArtifact,
    PromotionRequest,
    promote_isolated_artifact,
)
from codex_usage_tracker.agent_kernel.publication.validation import (
    build_isolated_artifact,
    reopen_validated_artifact,
    validate_open_artifact,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
    read_prior_publication_snapshot,
)
from codex_usage_tracker.agent_kernel.storage.database import (
    initialize_analytical,
    initialize_operational,
    measure_database_size,
)
from codex_usage_tracker.agent_kernel.storage.operational import (
    JobRequest,
    JobState,
    OperationalStore,
    WorkerIdentity,
)
from codex_usage_tracker.agent_kernel.storage.operational import (
    OperationClass as OperationalOperationClass,
)
from codex_usage_tracker.agent_kernel.storage.schema import SCHEMA_CONTRACT_SHA256

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/agent_kernel/fixtures/tiny-v1"
FIXTURE_MANIFEST = FIXTURE_ROOT / "manifest.json"
_BASE_TIME_US = 1_800_000_000_000_000


def _request(operation_id: str, parent: str | None = None) -> PublicationRequest:
    return PublicationRequest(
        publication_id=f"publication:{operation_id}",
        operation_id=operation_id,
        committed_at_us=_BASE_TIME_US + len(operation_id),
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        parent_publication_id=parent,
        indexed_from_us=1_700_000_000_000_000,
        indexed_through_us=_BASE_TIME_US,
        guaranteed_complete_from_us=1_700_000_000_000_000,
    )


def _small_plan(changes: ProposedChangeSet, parent: str | None) -> PublicationPlan:
    return PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        parent,
        estimate_change_set(changes),
        ("synthetic_ck07_benchmark",),
        True,
    )


def tiny_changes() -> ProposedChangeSet:
    return ingest(FIXTURE_ROOT, manifest=FIXTURE_MANIFEST, workers=2, batch_size=32).changes


def _publication_inputs(
    connection: sqlite3.Connection,
    changes: ProposedChangeSet,
    operation_id: str,
    parent: str | None,
) -> tuple[PublicationPlan, PublicationRequest, Any]:
    plan = _small_plan(changes, parent)
    request = _request(operation_id, parent)
    prior = read_prior_publication_snapshot(connection, changes)
    write_set = prepare_write_set_from_changes(changes, request, prior=prior)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )
    return plan, request, write_set


def publish_initial(connection: sqlite3.Connection, changes: ProposedChangeSet) -> str:
    plan, request, write_set = _publication_inputs(connection, changes, "benchmark-initial", None)
    PublicationWriter(connection).publish(plan, request, write_set)
    return request.publication_id


def model_call_tail(changes: ProposedChangeSet, count: int) -> ProposedChangeSet:
    """Create count body-free, distinct model-call observations from the oracle."""

    if count <= 0:
        raise ValueError("model-call count must be positive")
    original = next(
        item for item in changes.observations if item.observation_type == "ModelCallObserved"
    )
    observations = []
    for offset in range(count):
        identity = (f"{original.identity_tuple[0]}:perf-{offset}", *original.identity_tuple[1:])
        logical_id = semantic_id("call", identity)
        source_range = replace(
            original.source_range,
            record_ordinal=original.source_range.record_ordinal + 10_000 + offset,
            byte_start=original.source_range.byte_end + (offset * 2),
            byte_end=original.source_range.byte_end + (offset * 2) + 1,
        )
        observations.append(
            replace(
                original,
                logical_id=logical_id,
                identity_tuple=identity,
                source_range=source_range,
                event_at_us=(original.event_at_us or 0) + offset + 1,
                source_order=original.source_order + 10_000 + offset,
                payload={**original.payload, "call_id": logical_id},
            )
        )
    result = build_change_set(
        (
            ParseBatch(
                0,
                0,
                tuple(observations),
                (),
                count,
                observations[-1].source_range.byte_end,
                observations[-1].source_order,
                False,
            ),
        ),
        selected_sources=(),
        deferred_sources=(),
    )
    return replace(result, cursor_updates=changes.cursor_updates)


def planner_class(changes: ProposedChangeSet, *, parent: str | None) -> OperationClass:
    """Classify a synthetic tail through the public, lock-free planner."""

    return plan_refresh(
        changes,
        RefreshIntent(
            parent_publication_id=parent,
            parent_observed_at_us=_BASE_TIME_US,
            planned_at_us=_BASE_TIME_US,
            history_preset="all_time",
        ),
    ).operation_class


def _combined_large_candidate(
    base: ProposedChangeSet,
    tail: ProposedChangeSet,
) -> ProposedChangeSet:
    """Build the isolated candidate from the public fixture plus synthetic tail."""

    observations = (*base.observations, *tail.observations)
    result = build_change_set(
        (
            ParseBatch(
                0,
                0,
                observations,
                (),
                len(observations),
                max(item.source_range.byte_end for item in observations),
                max(item.source_order for item in observations),
                False,
            ),
        ),
        selected_sources=base.selected_sources,
        deferred_sources=base.deferred_sources,
    )
    return replace(result, cursor_updates=base.cursor_updates)


def tool_lifecycle_completion(
    changes: ProposedChangeSet,
) -> tuple[ProposedChangeSet, ProposedChangeSet]:
    """Return a synthetic tool start and its terminal event for two publications."""

    start = next(
        item
        for item in changes.observations
        if item.observation_type == "ToolLifecycleObserved"
        and item.payload.get("state") == "running"
    )
    terminal = next(
        item
        for item in changes.observations
        if item.observation_type == "ToolLifecycleObserved"
        and item.payload.get("state") == "succeeded"
    )
    tool_id = f"{start.identity_tuple[0]}:perf-completion"
    identity = (tool_id, *start.identity_tuple[1:])
    logical_id = semantic_id("tool", identity)

    def changed(item, ordinal: int):
        source_range = replace(
            item.source_range,
            record_ordinal=item.source_range.record_ordinal + ordinal,
            byte_start=item.source_range.byte_end + ordinal,
            byte_end=item.source_range.byte_end + ordinal + 1,
        )
        return replace(
            item,
            logical_id=logical_id,
            identity_tuple=identity,
            source_range=source_range,
            source_order=item.source_order + ordinal,
            payload={**item.payload, "tool_id": tool_id},
        )

    def one(item):
        return replace(
            build_change_set(
                (
                    ParseBatch(
                        0, 0, (item,), (), 1, item.source_range.byte_end, item.source_order, False
                    ),
                ),
                selected_sources=(),
                deferred_sources=(),
            ),
            cursor_updates=changes.cursor_updates,
        )

    return one(changed(start, 20_000)), one(changed(terminal, 20_001))


def _stats(samples_ns: list[int]) -> dict[str, float]:
    ordered = sorted(samples_ns)
    average = statistics.fmean(ordered)
    p95_index = min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "median_ms": round(statistics.median(ordered) / 1_000_000, 3),
        "p95_ms": round(ordered[p95_index] / 1_000_000, 3),
        "max_ms": round(ordered[-1] / 1_000_000, 3),
        "cv": round(0.0 if average == 0 else statistics.pstdev(ordered) / average, 5),
    }


def _measure_append(changes: ProposedChangeSet, label: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="ck07-publication-") as directory:
        path = Path(directory) / "analytical.sqlite3"
        connection = initialize_analytical(path)
        try:
            parent = publish_initial(connection, tiny_changes())
            plan, request, write_set = _publication_inputs(connection, changes, label, parent)
            started = time.perf_counter_ns()
            stages: dict[str, int] = {}

            def observe_stage(stage: str) -> None:
                if stage in {"after_begin", "before_commit"}:
                    stages[stage] = time.perf_counter_ns()

            result = PublicationWriter(connection).publish(
                plan,
                request,
                write_set,
                fault_injector=observe_stage,
            )
            elapsed_ns = time.perf_counter_ns() - started
            validate_open_artifact(
                connection,
                expected_publication_id=request.publication_id,
                expected_manifest_sha256=request.artifact_manifest_sha256,
            )
            sizes = measure_database_size(path, connection)
            if result.transaction_elapsed_ns is None:
                raise RuntimeError("append publication did not report transaction timing")
            body_ns = stages["before_commit"] - stages["after_begin"]
            return {
                "wall_ns": elapsed_ns,
                "total_ns": result.elapsed_ns,
                "writer_ns": result.transaction_elapsed_ns,
                "transaction_body_ns": body_ns,
                "begin_and_commit_ns": result.transaction_elapsed_ns - body_ns,
                "wal_bytes": sizes.wal_bytes,
                "rss_raw": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                "inserted_occurrences": result.inserted_occurrences,
            }
        finally:
            connection.close()


def _measure_large_promotion(base: ProposedChangeSet, index: int) -> dict[str, Any]:
    """Build a 2,000-call candidate off authority, then time only activation."""

    tail = model_call_tail(base, 2_000)
    candidate_changes = _combined_large_candidate(base, tail)
    with tempfile.TemporaryDirectory(prefix="ck07-large-promotion-") as directory:
        owner_directory = Path(directory)
        owner_directory.chmod(0o700)
        operation_id = f"large-promotion-{index}"
        # Building/validating this candidate is host-waited long work.  It is
        # intentionally excluded from the bounded fenced activation timing.
        candidate_plan = _small_plan(candidate_changes, None)
        candidate_request = _request(f"candidate-{index}")
        candidate_set = prepare_write_set_from_changes(candidate_changes, candidate_request)
        candidate_request = replace(
            candidate_request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                candidate_plan, candidate_request, candidate_set
            ),
        )

        def build(connection: sqlite3.Connection) -> None:
            PublicationWriter(connection).publish(candidate_plan, candidate_request, candidate_set)

        build_started = time.perf_counter_ns()
        candidate = build_isolated_artifact(
            owner_directory,
            operation_id,
            build,
            expected_publication_id=candidate_request.publication_id,
            expected_manifest_sha256=candidate_request.artifact_manifest_sha256,
        )
        candidate_build_ns = time.perf_counter_ns() - build_started
        artifact = PointerArtifact(
            candidate.artifact_name,
            candidate.artifact_manifest_sha256,
            candidate.file_sha256,
            candidate.publication_id,
            SCHEMA_CONTRACT_SHA256,
        )
        operational_connection = initialize_operational(owner_directory / "operations.sqlite3")
        try:
            store = OperationalStore(operational_connection)
            store.start_or_join(
                JobRequest(
                    operation_id,
                    "a" * 64,
                    f"promotion:{index}",
                    None,
                    OperationalOperationClass.APPEND_SAFE_LARGE,
                ),
                now_us=1,
            )
            worker = WorkerIdentity(10_000 + index, f"benchmark-{index}")
            for expected, state, stamp in (
                (JobState.PLANNED, JobState.BUILDING, 2),
                (JobState.BUILDING, JobState.VALIDATING, 3),
                (JobState.VALIDATING, JobState.PROMOTING, 4),
            ):
                store.transition(
                    operation_id,
                    expected=expected,
                    state=state,
                    stage=state.value,
                    now_us=stamp,
                    worker=worker,
                )

            def validate(path: Path, selected: PointerArtifact) -> AnalyticalHead:
                checked = reopen_validated_artifact(
                    path,
                    expected_publication_id=selected.publication_id,
                    expected_manifest_sha256=selected.artifact_manifest_sha256,
                )
                return AnalyticalHead(
                    checked.publication_id,
                    checked.parent_publication_id,
                    checked.operation_id,
                    checked.artifact_manifest_sha256,
                    SCHEMA_CONTRACT_SHA256,
                )

            activation_started_ns: int | None = None
            activation_completed_ns: int | None = None

            def observe_promotion(stage: str) -> None:
                nonlocal activation_completed_ns, activation_started_ns
                if stage == "after_candidate_preflight":
                    activation_started_ns = time.perf_counter_ns()
                elif stage == "after_reopen_validate":
                    activation_completed_ns = time.perf_counter_ns()

            started = time.perf_counter_ns()
            result = promote_isolated_artifact(
                owner_directory / "active-artifact-pointer-v1.json",
                store=store,
                request=PromotionRequest(
                    f"recovery-{index}",
                    operation_id,
                    0,
                    None,
                    artifact,
                    f"nonce-{index}",
                    worker,
                    10,
                    100,
                ),
                worker_is_alive=lambda _pid, _start: True,
                validate_open=validate,
                finalize_rollback=lambda _path, _prior: (_ for _ in ()).throw(
                    AssertionError("initial promotion cannot finalize rollback")
                ),
                fault=observe_promotion,
            )
            promotion_completed_ns = time.perf_counter_ns()
            if activation_started_ns is None or activation_completed_ns is None:
                raise RuntimeError("promotion did not report activation boundaries")
            assert result.pointer.active.publication_id == candidate_request.publication_id
            return {
                "activation_ns": activation_completed_ns - activation_started_ns,
                "candidate_preflight_ns": activation_started_ns - started,
                "promotion_total_ns": promotion_completed_ns - started,
                "candidate_build_ns": candidate_build_ns,
                "pointer_generation": result.pointer.generation,
                "candidate_file_bytes": candidate.path.stat().st_size,
                "rss_raw": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            }
        finally:
            operational_connection.close()


def concurrent_reader_available() -> bool:
    """Hold the actual writer transaction open and read its previous head in WAL mode."""

    changes = tiny_changes()
    with tempfile.TemporaryDirectory(prefix="ck07-reader-") as directory:
        path = Path(directory) / "analytical.sqlite3"
        setup_connection = initialize_analytical(path)
        try:
            parent = publish_initial(setup_connection, changes)
            plan, request, write_set = _publication_inputs(
                setup_connection, model_call_tail(changes, 1), "reader", parent
            )
            setup_connection.close()
            entered = threading.Event()
            release = threading.Event()
            failure: list[BaseException] = []

            def pause_after_begin(stage: str) -> None:
                if stage == "after_begin":
                    entered.set()
                    release.wait(2.0)

            def write() -> None:
                try:
                    writer_connection = initialize_analytical(path)
                    try:
                        PublicationWriter(writer_connection).publish(
                            plan,
                            request,
                            write_set,
                            fault_injector=pause_after_begin,
                        )
                    finally:
                        writer_connection.close()
                except BaseException as error:  # propagated after the read assertion
                    failure.append(error)

            thread = threading.Thread(target=write)
            thread.start()
            if not entered.wait(2.0):
                raise RuntimeError("writer did not enter its bounded transaction")
            reader = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
            try:
                reader.execute("PRAGMA busy_timeout = 1000")
                visible = reader.execute(
                    "SELECT publication_id FROM publication_head WHERE singleton = 1"
                ).fetchone()
                available = visible is not None and visible[0] == parent
            finally:
                reader.close()
                release.set()
                thread.join(3.0)
            if thread.is_alive() or failure:
                raise RuntimeError("writer did not complete after concurrent reader") from (
                    failure[0] if failure else None
                )
            return available
        finally:
            # The setup connection is normally closed before the reader test;
            # this is harmless if setup failed before that point.
            with contextlib.suppress(sqlite3.ProgrammingError):
                setup_connection.close()


def run_benchmark(repetitions: int = 5) -> dict[str, Any]:
    if repetitions < 1 or repetitions > 20:
        raise ValueError("repetitions must be in [1, 20]")
    fixture_ingest = ingest(
        FIXTURE_ROOT,
        manifest=FIXTURE_MANIFEST,
        workers=2,
        batch_size=32,
    )
    changes = fixture_ingest.changes
    small_class = planner_class(model_call_tail(changes, 32), parent="publication:parent")
    large_class = planner_class(model_call_tail(changes, 2_000), parent="publication:parent")
    if small_class is not OperationClass.APPEND_SAFE_SMALL:
        raise RuntimeError(f"32-record tail was not planner-safe: {small_class.value}")
    if large_class is not OperationClass.APPEND_SAFE_LARGE:
        raise RuntimeError(f"2000-record tail was not routed large: {large_class.value}")
    scenarios: dict[str, Any] = {}
    no_change_ns: list[int] = []
    for index in range(repetitions):
        with tempfile.TemporaryDirectory(prefix="ck07-no-change-") as directory:
            connection = initialize_analytical(Path(directory) / "analytical.sqlite3")
            try:
                parent = publish_initial(connection, changes)
                empty = ingest(Path(directory), workers=1, batch_size=8).changes
                plan = PublicationPlan(
                    OperationClass.NO_CHANGE,
                    parent,
                    estimate_change_set(empty),
                    ("synthetic_no_change",),
                    False,
                )
                request = _request(f"no-change-{index}", parent)
                write_set = prepare_write_set_from_changes(empty, request)
                result = PublicationWriter(connection).publish(plan, request, write_set)
                no_change_ns.append(result.elapsed_ns)
            finally:
                connection.close()
    scenarios["no_change"] = {"writer": _stats(no_change_ns), "samples": repetitions}
    for name, tail in (("one_call", 1), ("thirty_two_calls", 32)):
        rows = [
            _measure_append(model_call_tail(changes, tail), f"{name}-{index}")
            for index in range(repetitions)
        ]
        scenarios[name] = {
            "writer": _stats([row["writer_ns"] for row in rows]),
            "transaction_body": _stats([row["transaction_body_ns"] for row in rows]),
            "begin_and_commit": _stats([row["begin_and_commit_ns"] for row in rows]),
            "total": _stats([row["total_ns"] for row in rows]),
            "wall": _stats([row["wall_ns"] for row in rows]),
            "max_wal_bytes": max(row["wal_bytes"] for row in rows),
            "max_rss_raw": max(row["rss_raw"] for row in rows),
            "inserted_occurrences": rows[0]["inserted_occurrences"],
            "samples": repetitions,
        }
    # This deliberately forces an unsafe plan through the writer solely to
    # expose its cost.  It is diagnostic evidence, never the selected path or
    # a hard-budget candidate.
    forced_rows = [
        _measure_append(model_call_tail(changes, 2_000), f"forced-unsafe-{index}")
        for index in range(repetitions)
    ]
    scenarios["forced_unsafe_two_thousand_writer"] = {
        "planner_class": large_class.value,
        "planner_rejected_for_short_writer": True,
        "writer": _stats([row["writer_ns"] for row in forced_rows]),
        "transaction_body": _stats([row["transaction_body_ns"] for row in forced_rows]),
        "begin_and_commit": _stats([row["begin_and_commit_ns"] for row in forced_rows]),
        "total": _stats([row["total_ns"] for row in forced_rows]),
        "wall": _stats([row["wall_ns"] for row in forced_rows]),
        "max_wal_bytes": max(row["wal_bytes"] for row in forced_rows),
        "max_rss_raw": max(row["rss_raw"] for row in forced_rows),
        "inserted_occurrences": forced_rows[0]["inserted_occurrences"],
        "samples": repetitions,
    }
    promotion_rows = [_measure_large_promotion(changes, index) for index in range(repetitions)]
    scenarios["two_thousand_large_path_promotion"] = {
        "planner_class": large_class.value,
        "candidate_build": _stats([row["candidate_build_ns"] for row in promotion_rows]),
        "candidate_preflight": _stats([row["candidate_preflight_ns"] for row in promotion_rows]),
        "activation_excludes_candidate_build_and_preflight": True,
        "activation": _stats([row["activation_ns"] for row in promotion_rows]),
        "promotion_total": _stats([row["promotion_total_ns"] for row in promotion_rows]),
        "max_candidate_file_bytes": max(row["candidate_file_bytes"] for row in promotion_rows),
        "max_rss_raw": max(row["rss_raw"] for row in promotion_rows),
        "pointer_generation": promotion_rows[0]["pointer_generation"],
        "samples": repetitions,
    }
    lifecycle_rows = []
    for index in range(repetitions):
        with tempfile.TemporaryDirectory(prefix="ck07-lifecycle-") as directory:
            path = Path(directory) / "analytical.sqlite3"
            connection = initialize_analytical(path)
            try:
                parent = publish_initial(connection, changes)
                started, terminal = tool_lifecycle_completion(changes)
                first_plan, first_request, first_set = _publication_inputs(
                    connection, started, f"tool-start-{index}", parent
                )
                PublicationWriter(connection).publish(first_plan, first_request, first_set)
                validate_open_artifact(
                    connection,
                    expected_publication_id=first_request.publication_id,
                    expected_manifest_sha256=first_request.artifact_manifest_sha256,
                )
                second_plan, second_request, second_set = _publication_inputs(
                    connection, terminal, f"tool-terminal-{index}", first_request.publication_id
                )
                tick = time.perf_counter_ns()
                result = PublicationWriter(connection).publish(
                    second_plan, second_request, second_set
                )
                validate_open_artifact(
                    connection,
                    expected_publication_id=second_request.publication_id,
                    expected_manifest_sha256=second_request.artifact_manifest_sha256,
                )
                if result.transaction_elapsed_ns is None:
                    raise RuntimeError("lifecycle publication did not report transaction timing")
                lifecycle_rows.append(
                    {
                        "writer_ns": result.transaction_elapsed_ns,
                        "total_ns": result.elapsed_ns,
                        "wall_ns": time.perf_counter_ns() - tick,
                    }
                )
            finally:
                connection.close()
    scenarios["one_tool_lifecycle_completion"] = {
        "writer": _stats([row["writer_ns"] for row in lifecycle_rows]),
        "total": _stats([row["total_ns"] for row in lifecycle_rows]),
        "wall": _stats([row["wall_ns"] for row in lifecycle_rows]),
        "samples": repetitions,
    }
    budgets = {
        "no_change_p95_le_100ms": scenarios["no_change"]["writer"]["p95_ms"] <= 100,
        "one_call_p95_le_500ms": scenarios["one_call"]["writer"]["p95_ms"] <= 500,
        "one_tool_p95_le_500ms": scenarios["one_tool_lifecycle_completion"]["writer"]["p95_ms"]
        <= 500,
        "two_thousand_large_path_activation_p95_le_50ms": (
            scenarios["two_thousand_large_path_promotion"]["activation"]["p95_ms"] <= 50
        ),
    }
    return {
        "fixture": "tests/agent_kernel/fixtures/tiny-v1",
        "synthetic_only": True,
        "repetitions": repetitions,
        "adapter_queue": {
            "workers": fixture_ingest.metrics.workers,
            "record_batch_size": fixture_ingest.metrics.batch_size,
            "max_queue_depth": fixture_ingest.metrics.max_queue_depth,
            "peak_rss_bytes": fixture_ingest.metrics.peak_rss_bytes,
        },
        "planner_classes": {
            "thirty_two_calls": small_class.value,
            "two_thousand_calls": large_class.value,
        },
        "concurrent_reader_available": concurrent_reader_available(),
        "scenarios": scenarios,
        "hard_budget_comparisons": budgets,
        "rss_unit": "platform ru_maxrss raw unit",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=5)
    arguments = parser.parse_args()
    print(json.dumps(run_benchmark(arguments.repetitions), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
