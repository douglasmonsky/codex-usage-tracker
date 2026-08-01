from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    AdapterAccounting,
    ProposedChangeSet,
)
from codex_usage_tracker.agent_kernel.adapters.contracts import (
    AdapterObservation,
    SourceRange,
)
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.models import LifecycleTransition
from codex_usage_tracker.agent_kernel.publication import preparation
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    prepare_write_set_from_changes,
)

_ROOT = Path(__file__).parents[3]


def _tool_observation(entity_ordinal: int, transition_ordinal: int) -> AdapterObservation:
    state = "running" if transition_ordinal == 0 else "succeeded"
    logical_id = f"tool:scale:{entity_ordinal}"
    source_order = entity_ordinal * 2 + transition_ordinal
    return AdapterObservation(
        observation_type="ToolLifecycleObserved",
        logical_id=logical_id,
        identity_tuple=(f"tool-{entity_ordinal}", "session:scale", "turn:scale"),
        source_range=SourceRange(
            "manifestation:scale",
            1,
            "revision:scale",
            source_order,
            source_order * 10,
            source_order * 10 + 9,
        ),
        source_rank=0,
        event_at_us=1_800_000_000_000_000 + source_order,
        source_order=source_order,
        event_kind_order=40 + transition_ordinal,
        transition_rank=transition_ordinal,
        payload={
            "tool_id": logical_id,
            "session_id": "session:scale",
            "turn_id": "turn:scale",
            "transport_name": "synthetic_execute",
            "semantic_operation": "execute",
            "state": state,
            "write_intent": 1,
            "duration_us": None if transition_ordinal == 0 else 1,
            "output_bytes": None if transition_ordinal == 0 else 64,
        },
    )


def _changes(entity_count: int) -> ProposedChangeSet:
    observations = tuple(
        _tool_observation(entity_ordinal, transition_ordinal)
        for entity_ordinal in range(entity_count)
        for transition_ordinal in range(2)
    )
    return ProposedChangeSet(
        observations=observations,
        occurrences=(),
        diagnostics=(),
        cursor_updates=(),
        accounting=AdapterAccounting({}, {}, {}),
        selected_sources=(),
        deferred_sources=(),
    )


def test_lifecycle_preparation_groups_transitions_once_and_preserves_folds(
    monkeypatch,
) -> None:
    entity_count = 40
    entity_id_accesses = 0

    class CountingTransition:
        def __init__(self, **values: Any) -> None:
            self._transition = LifecycleTransition(**values)

        @property
        def entity_logical_id(self) -> str:
            nonlocal entity_id_accesses
            entity_id_accesses += 1
            return self._transition.entity_logical_id

        def __getattr__(self, name: str) -> Any:
            return getattr(self._transition, name)

    monkeypatch.setattr(preparation, "LifecycleTransition", CountingTransition)
    changes = _changes(entity_count)
    publication_id = "publication:lifecycle-scale"
    write_set = prepare_write_set_from_changes(
        changes,
        PublicationRequest(
            publication_id=publication_id,
            operation_id="operation:lifecycle-scale",
            committed_at_us=1_800_000_000_000_000,
            history_preset="all_time",
            artifact_manifest_sha256="a" * 64,
        ),
    )

    transition_count = entity_count * 2
    assert len(write_set.lifecycle_transitions) == transition_count
    assert entity_id_accesses <= transition_count * 12
    sequence: Counter[str] = Counter()
    expected_transitions: list[LifecycleTransition] = []
    for observation in changes.observations:
        sequence[observation.logical_id] += 1
        version = sequence[observation.logical_id]
        identity = [
            observation.logical_id,
            version,
            observation.payload["state"],
            observation.occurrence_id,
        ]
        expected_transitions.append(
            LifecycleTransition(
                transition_id=semantic_id("lifecycle-transition", identity),
                entity_logical_id=observation.logical_id,
                entity_kind="tool_invocation",
                lifecycle_state=str(observation.payload["state"]),
                state_basis=observation.basis,
                transition_version=version,
                transition_at_us=observation.event_at_us,
                source_rank=observation.source_rank,
                source_order=observation.source_order,
                event_kind_order=observation.event_kind_order,
                transition_rank=observation.transition_rank,
                occurrence_id=observation.occurrence_id,
                terminal_error_category=None,
                measurement_mask=observation.measurement_mask,
                first_seen_publication_id=publication_id,
            )
        )
    assert tuple(
        getattr(transition, "_transition", transition)
        for transition in write_set.lifecycle_transitions
    ) == tuple(expected_transitions)
    assert [
        transition.entity_logical_id for transition in write_set.lifecycle_transitions
    ] == [
        f"tool:scale:{entity_ordinal}"
        for entity_ordinal in range(entity_count)
        for _transition_ordinal in range(2)
    ]

    tool_rows = {
        str(row.values["tool_id"]): row
        for row in write_set.rows
        if row.table == "tool_invocations"
    }
    assert len(tool_rows) == entity_count
    assert {
        (
            row.values["lifecycle_state"],
            row.values["transition_version"],
            row.values["observed_duration_us"],
        )
        for row in tool_rows.values()
    } == {("succeeded", 2, 1)}


def test_lifecycle_requalification_is_schema_valid_and_source_bound() -> None:
    evidence = json.loads(
        (
            _ROOT
            / "docs/decisions/evidence/ck07r1/lifecycle-scale-requalification.json"
        ).read_text()
    )
    schema = json.loads(
        (
            _ROOT
            / "docs/decisions/evidence/ck08r0/"
            "corrective-lane-evidence-v1.schema.json"
        ).read_text()
    )
    Draft202012Validator(schema).validate(evidence)
    implementation = (
        _ROOT
        / "src/codex_usage_tracker/agent_kernel/publication/preparation.py"
    )
    assert evidence["dependency_sha"] == "306cef37eea2ae017aca824d898cc435f7e1bea0"
    assert evidence["fold_identity_matches"] is True
    assert evidence["first_failure"] is None
    assert evidence["linear_work_counters"]["implementation_digest"] == (
        hashlib.sha256(implementation.read_bytes()).hexdigest()
    )


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()


def _assert_requalification_bindings(evidence: dict[str, Any]) -> None:
    contract = json.loads(
        (
            _ROOT
            / "docs/decisions/evidence/ck08r0/corrective-gates-v1.json"
        ).read_text()
    )
    lifecycle = contract["scale"]["lifecycle"]
    expected_budgets = {
        "standard_30_day": lifecycle["thirty_day_first_publication_p95_ms"],
        "production_all_time": lifecycle["production_all_time_p95_ms"],
        "no_change": lifecycle["no_change_p95_ms"],
        "one_call_tail": lifecycle["one_call_tail_p95_ms"],
        "one_tool_tail": lifecycle["one_tool_tail_p95_ms"],
    }
    counters = evidence["linear_work_counters"]
    assert counters["frozen_budgets_ms"] == expected_budgets
    assert counters["budget_checks"] == dict.fromkeys(expected_budgets, True)
    assert counters["frozen_preparation_digest"] == (
        "408d18e44c87da234d220c29298ebac1780e9426e2dce767b0bfc3ae65e8a872"
    )
    benchmark = _ROOT / "scripts/benchmark_ck07r1_lifecycle_scale.py"
    assert counters["benchmark_digest"] == hashlib.sha256(
        benchmark.read_bytes()
    ).hexdigest()

    fixture_profiles = contract["scale"]["fixtures"]
    assert counters["standard_30_day"]["profile_digest"] == (
        fixture_profiles["standard"]["sha256"]
    )
    assert counters["production_all_time"]["profile_digest"] == (
        fixture_profiles["production"]["sha256"]
    )

    for name in expected_budgets:
        measurement = counters[name]
        samples = measurement["timing_samples_ms"]
        assert len(samples) == contract["scale"]["sample_count"]
        assert all(sample >= 0 for sample in samples)
        assert measurement["max_ms"] == max(samples)
        assert measurement["max_ms"] <= expected_budgets[name]

    receipt_digests: dict[str, str] = {}
    for name in ("standard_30_day", "production_all_time"):
        measurement = counters[name]
        receipt = counters["publication_receipts"][name]
        postconditions = receipt["postconditions"]
        assert measurement["observation_count"] == measurement["occurrence_count"]
        assert receipt["workload_digest"] == measurement["workload_digest"]
        assert postconditions["workload_digest"] == measurement["workload_digest"]
        assert postconditions["inserted_occurrences"] == measurement["occurrence_count"]
        assert postconditions["source_occurrences"] == measurement["occurrence_count"]
        assert postconditions["lifecycle_transitions"] == measurement["transition_count"]
        assert postconditions["publications"] == receipt["begin_immediate_count"]
        assert receipt["preparation_transaction_closed"] is True
        assert receipt["preparation_transaction_open"] is False
        assert str(postconditions["publication_head"]).startswith(
            "publication:ck07r1:"
        )
        assert receipt["digest"] == _canonical_digest(postconditions)
        receipt_digests[name] = receipt["digest"]

    assert evidence["publication_digest"] == _canonical_digest(receipt_digests)
    assert evidence["publication_digest"] != "0" * 64
    assert evidence["timing_samples_ms"] == counters["production_all_time"][
        "timing_samples_ms"
    ]
    assert evidence["rss_bytes"] == counters["production_all_time"]["rss_bytes"]


def test_lifecycle_requalification_is_fully_bound() -> None:
    evidence = json.loads(
        (
            _ROOT
            / "docs/decisions/evidence/ck07r1/lifecycle-scale-requalification.json"
        ).read_text()
    )
    _assert_requalification_bindings(evidence)


def test_lifecycle_requalification_rejects_unbound_mutations() -> None:
    evidence = json.loads(
        (
            _ROOT
            / "docs/decisions/evidence/ck07r1/lifecycle-scale-requalification.json"
        ).read_text()
    )
    mutated = deepcopy(evidence)
    mutated_counters = mutated["linear_work_counters"]
    mutated_counters["frozen_budgets_ms"]["production_all_time"] = 999_999_999
    mutated_counters["production_all_time"]["timing_samples_ms"] = [0.0] * 5
    mutated_counters["production_all_time"]["max_ms"] = 0.0
    mutated["publication_digest"] = "0" * 64

    with pytest.raises(AssertionError):
        _assert_requalification_bindings(mutated)
