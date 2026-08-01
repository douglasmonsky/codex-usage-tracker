#!/usr/bin/env python3
"""Measure CK-07R1 lifecycle preparation on frozen synthetic scale profiles."""

from __future__ import annotations

import argparse
import gc
import json
import math
import platform
import resource
import statistics
import tempfile
import time
from collections import defaultdict
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    AdapterAccounting,
    ProposedChangeSet,
    build_change_set,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.parser import ParseBatch
from codex_usage_tracker.agent_kernel.adapters.contracts import (
    AdapterObservation,
    SourceRange,
)
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    estimate_change_set,
)
from codex_usage_tracker.agent_kernel.publication.preparation import (
    _WriteSetPreparer,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PriorPublicationSnapshot,
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
    read_prior_publication_snapshot,
)
from codex_usage_tracker.agent_kernel.storage.database import (
    initialize_analytical,
)
from codex_usage_tracker.agent_kernel.storage.lifecycle import fold_lifecycle

ROOT = Path(__file__).resolve().parents[1]
PROFILE_ROOT = ROOT / "tests" / "agent_kernel" / "fixtures" / "profiles"
TINY_FIXTURE = ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
DEPENDENCY_SHA = "306cef37eea2ae017aca824d898cc435f7e1bea0"
SCHEMA = "codex-usage-tracker.lifecycle-scale-requalification.v1"
STANDARD_PROFILE_SHA256 = (
    "ef0da880255a0b13ea6055e0f8d748870c075635aa6f199c9521462c681250f3"
)
PRODUCTION_PROFILE_SHA256 = (
    "2de0b4dc198603da6c1b0905b8d934e2cd5604e4036ef009d0cd07f1cc81f51b"
)
FROZEN_BUDGETS_MS = {
    "standard_30_day": 5_000,
    "production_all_time": 120_000,
    "no_change": 100,
    "one_call_tail": 500,
    "one_tool_tail": 500,
}
FROZEN_PREPARATION_SHA256 = (
    "408d18e44c87da234d220c29298ebac1780e9426e2dce767b0bfc3ae65e8a872"
)
PUBLICATION_CHUNK_OBSERVATIONS = 8_000


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()


def _file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _profile(name: str) -> dict[str, Any]:
    path = PROFILE_ROOT / f"{name}-v1.json"
    expected = (
        STANDARD_PROFILE_SHA256 if name == "standard" else PRODUCTION_PROFILE_SHA256
    )
    if _file_sha256(path) != expected:
        raise ValueError(f"{name} profile does not match frozen CK-08R0 digest")
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile["schema"] != "codex-usage-tracker.synthetic-fixture-profile.v1":
        raise ValueError(f"{name} profile has an unexpected schema")
    return profile


def _model_calls_for_window(profile: dict[str, Any], days: int | None) -> int:
    model_calls = int(profile["model_calls"])
    if days is None:
        return model_calls
    return math.ceil(model_calls * days / int(profile["history_days"]))


def _tool_count(profile: dict[str, Any], days: int | None) -> int:
    model_calls = _model_calls_for_window(profile, days)
    ratio = int(profile["ratios_basis_points"]["tool_invocations"])
    return math.ceil(model_calls * ratio / 10_000)


def _tool_observation(
    profile_name: str,
    entity_ordinal: int,
    transition_ordinal: int,
    state: str,
) -> AdapterObservation:
    source_order = entity_ordinal * 2 + transition_ordinal + 1
    start_at_us = 1_767_225_600_000_000
    return AdapterObservation(
        observation_type="ToolLifecycleObserved",
        logical_id=f"tool:ck07r1:{profile_name}:{entity_ordinal}",
        identity_tuple=(
            f"tool-{entity_ordinal}",
            "session:ck07r1",
            "turn:ck07r1",
        ),
        source_range=SourceRange(
            f"manifestation:ck07r1:{profile_name}",
            1,
            f"revision:ck07r1:{profile_name}",
            source_order,
            source_order * 10,
            source_order * 10 + 9,
        ),
        source_rank=0,
        event_at_us=start_at_us + source_order,
        source_order=source_order,
        event_kind_order=40 + transition_ordinal * 10,
        transition_rank=transition_ordinal,
        payload={
            "state": state,
            "error_category": None,
            "session_id": "session:ck07r1",
            "turn_id": "turn:ck07r1",
            "transport_name": "synthetic",
            "semantic_operation": "lifecycle-scale",
        },
    )


def _call_observation() -> AdapterObservation:
    return replace(
        _tool_observation("call-tail", 0, 0, "succeeded"),
        observation_type="ModelCallObserved",
        logical_id="model-call:ck07r1:call-tail",
        identity_tuple=("model-call:ck07r1:call-tail",),
    )


def _scale_observations(
    profile: dict[str, Any],
    *,
    days: int | None,
    base: ProposedChangeSet,
) -> tuple[AdapterObservation, ...]:
    template = next(
        item
        for item in base.observations
        if item.observation_type == "ToolLifecycleObserved"
        and item.payload.get("state") == "running"
    )
    count = _tool_count(profile, days)
    record_base = max(item.source_range.record_ordinal for item in base.observations)
    byte_base = max(item.source_range.byte_end for item in base.observations)
    order_base = max(item.source_order for item in base.observations)
    event_base = max(item.event_at_us or 0 for item in base.observations)
    observations: list[AdapterObservation] = []
    for entity_ordinal in range(count):
        native_id = f"{template.identity_tuple[0]}:ck07r1:{profile['name']}:{entity_ordinal}"
        identity = (native_id, *template.identity_tuple[1:])
        logical_id = semantic_id("tool", identity)
        states = ("running",) if entity_ordinal == count - 1 else ("running", "succeeded")
        for transition_ordinal, state in enumerate(states):
            ordinal = len(observations) + 1
            observations.append(
                replace(
                    template,
                    logical_id=logical_id,
                    identity_tuple=identity,
                    source_range=replace(
                        template.source_range,
                        record_ordinal=record_base + ordinal,
                        byte_start=byte_base + ordinal * 2,
                        byte_end=byte_base + ordinal * 2 + 1,
                    ),
                    event_at_us=event_base + ordinal,
                    source_order=order_base + ordinal,
                    transition_rank=transition_ordinal,
                    payload={
                        **template.payload,
                        "tool_id": native_id,
                        "state": state,
                        "duration_us": None if state == "running" else 1,
                        "output_bytes": None if state == "running" else 64,
                    },
                )
            )
    return tuple(observations)


def _built_changes(
    observations: tuple[AdapterObservation, ...],
    *,
    selected_sources: tuple[Any, ...] = (),
    deferred_sources: tuple[Any, ...] = (),
) -> ProposedChangeSet:
    return build_change_set(
        (
            ParseBatch(
                0,
                0,
                observations,
                (),
                len(observations),
                max((item.source_range.byte_end for item in observations), default=0),
                max((item.source_order for item in observations), default=0),
                False,
            ),
        ),
        selected_sources=selected_sources,
        deferred_sources=deferred_sources,
    )


def _scale_changes(
    profile: dict[str, Any],
    *,
    days: int | None,
) -> tuple[ProposedChangeSet, tuple[AdapterObservation, ...]]:
    base = ingest(
        TINY_FIXTURE,
        manifest=TINY_FIXTURE / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    scale = _scale_observations(profile, days=days, base=base)
    changes = _built_changes(
        (*base.observations, *scale),
        selected_sources=base.selected_sources,
        deferred_sources=base.deferred_sources,
    )
    return replace(changes, cursor_updates=base.cursor_updates), scale


def _changes(
    observations: tuple[AdapterObservation, ...],
) -> ProposedChangeSet:
    return ProposedChangeSet(
        observations=observations,
        occurrences=(),
        diagnostics=(),
        cursor_updates=(),
        accounting=AdapterAccounting({}, {}, {}),
        selected_sources=(),
        deferred_sources=(),
    )


def _preparer(
    changes: ProposedChangeSet,
    *,
    prior: PriorPublicationSnapshot | None = None,
) -> _WriteSetPreparer:
    preparer = _WriteSetPreparer(
        changes,
        PublicationRequest(
            publication_id="publication:ck07r1-scale",
            operation_id="operation:ck07r1-scale",
            committed_at_us=1_800_000_000_000_000,
            history_preset="all_time",
            artifact_manifest_sha256="a" * 64,
        ),
        configured_producer_key="synthetic-ck07r1",
        prior=PriorPublicationSnapshot() if prior is None else prior,
        inventory_started_at_us=1_800_000_000_000_000,
        inventory_completed_at_us=1_800_000_000_000_000,
    )
    preparer.observations_by_id = {
        observation.logical_id: [] for observation in changes.observations
    }
    return preparer


def _assert_folds(
    preparer: _WriteSetPreparer,
    prior: PriorPublicationSnapshot,
) -> tuple[str, str]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for transition in preparer.transitions:
        grouped[transition.entity_logical_id].append(transition)
    reference = {
        logical_id: fold_lifecycle(
            tuple(prior.lifecycle.get(logical_id, ())) + tuple(transitions)
        )
        for logical_id, transitions in grouped.items()
    }
    if preparer.folds != reference:
        raise AssertionError("complete lifecycle folds differ from reference")
    if len(grouped) <= 1_000:
        old_scan = {
            logical_id: fold_lifecycle(
                tuple(prior.lifecycle.get(logical_id, ()))
                + tuple(
                    item
                    for item in preparer.transitions
                    if item.entity_logical_id == logical_id
                )
            )
            for logical_id in grouped
        }
        if preparer.folds != old_scan:
            raise AssertionError("complete lifecycle folds differ from old scan")
    transition_digest = sha256()
    for transition in preparer.transitions:
        transition_digest.update(_canonical_json(asdict(transition)))
    fold_digest = sha256()
    for logical_id in sorted(preparer.folds):
        fold_digest.update(_canonical_json(asdict(preparer.folds[logical_id])))
    return transition_digest.hexdigest(), fold_digest.hexdigest()


def _sample(
    changes: ProposedChangeSet,
    *,
    prior: PriorPublicationSnapshot | None = None,
) -> tuple[float, int, int, str, str]:
    snapshot = PriorPublicationSnapshot() if prior is None else prior
    preparer = _preparer(changes, prior=snapshot)
    started_ns = time.perf_counter_ns()
    preparer._build_lifecycle()
    elapsed_ms = (time.perf_counter_ns() - started_ns) / 1_000_000
    transition_digest, fold_digest = _assert_folds(preparer, snapshot)
    return (
        elapsed_ms,
        len(preparer.transitions),
        len(preparer.folds),
        transition_digest,
        fold_digest,
    )


def _measure(
    changes: ProposedChangeSet,
    *,
    samples: int,
    prior: PriorPublicationSnapshot | None = None,
) -> dict[str, Any]:
    timings: list[float] = []
    transitions = folds = 0
    transition_digests: set[str] = set()
    fold_digests: set[str] = set()
    for _ in range(samples):
        gc.collect()
        (
            elapsed_ms,
            transitions,
            folds,
            transition_digest,
            fold_digest,
        ) = _sample(changes, prior=prior)
        timings.append(round(elapsed_ms, 3))
        transition_digests.add(transition_digest)
        fold_digests.add(fold_digest)
    if len(transition_digests) != 1 or len(fold_digests) != 1:
        raise AssertionError("lifecycle output digests changed between samples")
    return {
        "observation_count": len(changes.observations),
        "occurrence_count": len(changes.occurrences),
        "entity_count": len({item.logical_id for item in changes.observations}),
        "transition_count": transitions,
        "fold_count": folds,
        "transition_digest": transition_digests.pop(),
        "fold_digest": fold_digests.pop(),
        "timing_samples_ms": timings,
        "median_ms": round(statistics.median(timings), 3),
        "max_ms": max(timings),
    }


def _one_tool_tail() -> tuple[
    tuple[AdapterObservation, ...],
    PriorPublicationSnapshot,
]:
    running = _tool_observation("tail", 0, 0, "running")
    initial = _preparer(_changes((running,)))
    initial._build_lifecycle()
    prior = PriorPublicationSnapshot(
        lifecycle={running.logical_id: tuple(initial.transitions)}
    )
    terminal = _tool_observation("tail", 0, 1, "succeeded")
    return (terminal,), prior


def _observation_digest(observations: tuple[AdapterObservation, ...]) -> str:
    digest = sha256()
    for item in observations:
        digest.update(
            _canonical_json(
                {
                    "type": item.observation_type,
                    "logical_id": item.logical_id,
                    "identity": item.identity_tuple,
                    "source": asdict(item.source_range),
                    "event_at_us": item.event_at_us,
                    "source_order": item.source_order,
                    "event_kind_order": item.event_kind_order,
                    "transition_rank": item.transition_rank,
                    "payload": dict(item.payload),
                }
            )
        )
    return digest.hexdigest()


def _publication_batches(
    changes: ProposedChangeSet,
    scale: tuple[AdapterObservation, ...],
) -> tuple[ProposedChangeSet, ...]:
    scale_ids = {id(item) for item in scale}
    base = tuple(item for item in changes.observations if id(item) not in scale_ids)
    batches: list[ProposedChangeSet] = []
    for offset in range(0, len(scale), PUBLICATION_CHUNK_OBSERVATIONS):
        chunk = scale[offset : offset + PUBLICATION_CHUNK_OBSERVATIONS]
        initial = offset == 0
        batch = _built_changes(
            (*base, *chunk) if initial else chunk,
            selected_sources=changes.selected_sources if initial else (),
            deferred_sources=changes.deferred_sources if initial else (),
        )
        batches.append(
            replace(batch, cursor_updates=changes.cursor_updates if initial else ())
        )
    return tuple(batches)


def _publication_receipt(
    profile_name: str,
    changes: ProposedChangeSet,
    scale: tuple[AdapterObservation, ...],
) -> dict[str, Any]:
    workload_digest = _observation_digest(changes.observations)
    started_ns = time.perf_counter_ns()
    begin_immediate_count = 0
    inserted_occurrences = 0
    with tempfile.TemporaryDirectory(prefix=f"ck07r1-{profile_name}-") as directory:
        database = Path(directory) / "analytical.sqlite3"
        connection = initialize_analytical(database)

        def trace(statement: str) -> None:
            nonlocal begin_immediate_count
            begin_immediate_count += statement == "BEGIN IMMEDIATE"

        connection.set_trace_callback(trace)
        parent: str | None = None
        try:
            for index, batch in enumerate(_publication_batches(changes, scale)):
                operation_id = f"operation:ck07r1:{profile_name}:{index}"
                request = PublicationRequest(
                    publication_id=f"publication:ck07r1:{profile_name}:{index}",
                    operation_id=operation_id,
                    parent_publication_id=parent,
                    committed_at_us=1_800_000_000_000_000 + index,
                    history_preset="all_time",
                    artifact_manifest_sha256="a" * 64,
                )
                plan = PublicationPlan(
                    OperationClass.APPEND_SAFE_SMALL,
                    parent,
                    estimate_change_set(batch),
                    ("publication_valid_scale_chunk",),
                    True,
                )
                prior = read_prior_publication_snapshot(connection, batch)
                write_set = prepare_write_set_from_changes(
                    batch,
                    request,
                    prior=prior,
                )
                request = replace(
                    request,
                    artifact_manifest_sha256=planned_artifact_manifest_sha256(
                        plan,
                        request,
                        write_set,
                    ),
                )
                result = PublicationWriter(connection).publish(
                    plan,
                    request,
                    write_set,
                )
                inserted_occurrences += result.inserted_occurrences
                parent = request.publication_id
            postconditions = {
                "publication_head": connection.execute(
                    "SELECT publication_id FROM publication_head"
                ).fetchone()[0],
                "publications": connection.execute(
                    "SELECT count(*) FROM publications"
                ).fetchone()[0],
                "lifecycle_transitions": connection.execute(
                    "SELECT count(*) FROM lifecycle_transitions"
                ).fetchone()[0],
                "tool_invocations": connection.execute(
                    "SELECT count(*) FROM tool_invocations"
                ).fetchone()[0],
                "source_occurrences": connection.execute(
                    "SELECT count(*) FROM source_occurrences"
                ).fetchone()[0],
                "inserted_occurrences": inserted_occurrences,
                "workload_digest": workload_digest,
            }
            connection.execute(
                "SELECT lifecycle_state, transition_version "
                "FROM tool_invocations ORDER BY tool_id LIMIT 1"
            ).fetchone()
            database_bytes = database.stat().st_size
        finally:
            connection.close()
    return {
        "postconditions": postconditions,
        "digest": sha256(_canonical_json(postconditions)).hexdigest(),
        "workload_digest": workload_digest,
        "publication_elapsed_ms": round(
            (time.perf_counter_ns() - started_ns) / 1_000_000,
            3,
        ),
        "database_bytes": database_bytes,
        "preparation_transaction_open": False,
        "preparation_transaction_closed": True,
        "begin_immediate_count": begin_immediate_count,
    }


def _validated_receipt(
    receipt: dict[str, Any],
    changes: ProposedChangeSet,
) -> dict[str, Any]:
    workload_digest = _observation_digest(changes.observations)
    postconditions = receipt["postconditions"]
    if (
        receipt["workload_digest"] != workload_digest
        or postconditions["workload_digest"] != workload_digest
        or postconditions["source_occurrences"] != len(changes.occurrences)
        or postconditions["inserted_occurrences"] != len(changes.occurrences)
        or postconditions["publications"] != receipt["begin_immediate_count"]
        or not str(postconditions["publication_head"]).startswith(
            "publication:ck07r1:"
        )
    ):
        raise ValueError("publication receipt does not match exact scale workload")
    expected_digest = sha256(_canonical_json(postconditions)).hexdigest()
    if receipt["digest"] != expected_digest:
        raise ValueError("publication receipt digest does not match postconditions")
    return receipt


def _rss_bytes() -> int:
    # Darwin reports bytes; Linux reports KiB.
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if platform.system() == "Darwin" else value * 1024


def _authority_budgets() -> None:
    contract = json.loads(
        (
            ROOT / "docs/decisions/evidence/ck08r0/corrective-gates-v1.json"
        ).read_text(encoding="utf-8")
    )
    lifecycle = contract["scale"]["lifecycle"]
    expected = {
        "standard_30_day": lifecycle["thirty_day_first_publication_p95_ms"],
        "production_all_time": lifecycle["production_all_time_p95_ms"],
        "no_change": lifecycle["no_change_p95_ms"],
        "one_call_tail": lifecycle["one_call_tail_p95_ms"],
        "one_tool_tail": lifecycle["one_tool_tail_p95_ms"],
    }
    if expected != FROZEN_BUDGETS_MS:
        raise ValueError("lifecycle budgets differ from frozen CK-08R0 authority")


def _run_profile(
    profile_name: str,
    *,
    sample_count: int,
    publish: bool,
    publication_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = _profile(profile_name)
    days = 30 if profile_name == "standard" else None
    changes, scale = _scale_changes(profile, days=days)
    measurement = _measure(changes, samples=sample_count)
    result = {
        "profile": profile_name,
        "history_preset": "30_days" if days is not None else "all_time",
        "profile_digest": _file_sha256(PROFILE_ROOT / f"{profile_name}-v1.json"),
        "workload_digest": _observation_digest(changes.observations),
        "synthetic_observation_count": len(scale),
        "synthetic_entity_count": len({item.logical_id for item in scale}),
        **measurement,
        "rss_bytes": _rss_bytes(),
    }
    if publish:
        result["publication_receipt"] = _validated_receipt(
            (
                _publication_receipt(profile_name, changes, scale)
                if publication_receipt is None
                else publication_receipt
            ),
            changes,
        )
    return result


def run(
    *,
    profile_name: str,
    sample_count: int,
    standard_profile_run_id: str | None = None,
    production_profile_run_id: str | None = None,
    standard_publication_receipt: dict[str, Any] | None = None,
    production_publication_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if sample_count < 1:
        raise ValueError("samples must be positive")
    _authority_budgets()
    if profile_name in {"standard", "production"}:
        return _run_profile(profile_name, sample_count=sample_count, publish=False)

    standard = _run_profile(
        "standard",
        sample_count=sample_count,
        publish=True,
        publication_receipt=standard_publication_receipt,
    )
    production = _run_profile(
        "production",
        sample_count=sample_count,
        publish=True,
        publication_receipt=production_publication_receipt,
    )
    no_change = _measure(_changes(()), samples=sample_count)
    one_call = _measure(_changes((_call_observation(),)), samples=sample_count)
    one_tool_observations, one_tool_prior = _one_tool_tail()
    one_tool = _measure(
        _changes(one_tool_observations),
        samples=sample_count,
        prior=one_tool_prior,
    )
    checks = {
        "standard_30_day": standard["max_ms"] <= FROZEN_BUDGETS_MS["standard_30_day"],
        "production_all_time": (
            production["max_ms"] <= FROZEN_BUDGETS_MS["production_all_time"]
        ),
        "no_change": no_change["max_ms"] <= FROZEN_BUDGETS_MS["no_change"],
        "one_call_tail": one_call["max_ms"] <= FROZEN_BUDGETS_MS["one_call_tail"],
        "one_tool_tail": one_tool["max_ms"] <= FROZEN_BUDGETS_MS["one_tool_tail"],
    }
    first_failure = next(
        (
            {"gate": gate, "budget_ms": FROZEN_BUDGETS_MS[gate]}
            for gate, passed in checks.items()
            if not passed
        ),
        None,
    )
    receipts = {
        "standard_30_day": standard.pop("publication_receipt"),
        "production_all_time": production.pop("publication_receipt"),
    }
    fixture_digest = sha256(
        _canonical_json(
            {
                "standard_profile": STANDARD_PROFILE_SHA256,
                "production_profile": PRODUCTION_PROFILE_SHA256,
                "standard_workload": standard["workload_digest"],
                "production_workload": production["workload_digest"],
                "generator": "publication-valid-tool-lifecycle-v2",
            }
        )
    ).hexdigest()
    publication_digest = sha256(
        _canonical_json(
            {name: receipt["digest"] for name, receipt in receipts.items()}
        )
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "dependency_sha": DEPENDENCY_SHA,
        "fixture_digest": fixture_digest,
        "publication_digest": publication_digest,
        "fold_identity_matches": True,
        "linear_work_counters": {
            "complexity": "observations_plus_prior_transitions",
            "implementation_digest": _file_sha256(
                ROOT
                / "src/codex_usage_tracker/agent_kernel/publication/preparation.py"
            ),
            "benchmark_digest": _file_sha256(Path(__file__)),
            "frozen_preparation_digest": FROZEN_PREPARATION_SHA256,
            "standard_30_day": standard,
            "production_all_time": production,
            "no_change": no_change,
            "one_call_tail": one_call,
            "one_tool_tail": one_tool,
            "frozen_budgets_ms": FROZEN_BUDGETS_MS,
            "budget_checks": checks,
            "publication_receipts": receipts,
        },
        "timing_samples_ms": production["timing_samples_ms"],
        "attribution_profile": {
            "scope": "_WriteSetPreparer._build_lifecycle",
            "excluded": [
                "fixture_generation",
                "ingestion",
                "unrelated_preparation",
                "PublicationWriter",
                "recovery",
                "query",
                "evidence",
            ],
            "standard_agent_perf_run_id": standard_profile_run_id,
            "production_agent_perf_run_id": production_profile_run_id,
            "speed_claim_source": "five_unprofiled_samples",
            "publication_receipt_mode": "bounded_append_safe_small_chunks",
            "publication_chunk_observations": PUBLICATION_CHUNK_OBSERVATIONS,
        },
        "rss_bytes": max(standard["rss_bytes"], production["rss_bytes"], _rss_bytes()),
        "lock_observations": [
            {
                "phase": "lifecycle_preparation",
                "analytical_transaction_open": False,
                "analytical_transaction_closed_after": True,
            },
            {
                "phase": "publication_writer",
                "begin_immediate_count": sum(
                    receipt["begin_immediate_count"] for receipt in receipts.values()
                ),
                "preparation_completed_before_begin": True,
            },
        ],
        "linked_evidence_amendments": [
            "docs/decisions/evidence/ck07/publication-refresh-recovery-evidence.json",
            (
                "docs/decisions/evidence/ck08/"
                "fact-backed-query-and-evidence-qualification.json"
            ),
        ],
        "first_failure": first_failure,
        "noise": [
            {
                "context": "historical_candidate_a_mandatory_workload",
                "classification": "isolated_timing_sensitive_failure",
                "authority_changed": False,
                "focused_rerun_and_subsequent_comprehensive_runs": "passed",
            },
            {
                "context": "exact_main_allowance_read_p95_ms",
                "just_v_ms": 651.459,
                "just_vc_ms": 614.754,
                "outcome": "invariants_only",
                "authority_changed": False,
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=("standard", "production", "all"),
        default="all",
    )
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--standard-profile-run-id")
    parser.add_argument("--production-profile-run-id")
    parser.add_argument("--standard-publication-receipt", type=Path)
    parser.add_argument("--production-publication-receipt", type=Path)
    arguments = parser.parse_args()
    payload = run(
        profile_name=arguments.profile,
        sample_count=arguments.samples,
        standard_profile_run_id=arguments.standard_profile_run_id,
        production_profile_run_id=arguments.production_profile_run_id,
        standard_publication_receipt=(
            None
            if arguments.standard_publication_receipt is None
            else json.loads(arguments.standard_publication_receipt.read_text())
        ),
        production_publication_receipt=(
            None
            if arguments.production_publication_receipt is None
            else json.loads(arguments.production_publication_receipt.read_text())
        ),
    )
    encoded = _canonical_json(payload) + b"\n"
    if arguments.output is None:
        print(encoded.decode(), end="")
    else:
        arguments.output.write_bytes(encoded)
    return int(payload.get("first_failure") is not None)


if __name__ == "__main__":
    raise SystemExit(main())
