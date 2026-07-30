from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    ProposedChangeSet,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.contracts import SourceState
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    RefreshIntent,
    TailLimits,
    bounded_moving_tail_catchup,
    plan_refresh,
    reconciliation_required,
)
from codex_usage_tracker.agent_kernel.publication.projections import (
    DirtyKey,
    ProjectionFanoutError,
    ProjectionRegistry,
)
from codex_usage_tracker.agent_kernel.publication.validation import (
    artifact_manifest_sha256,
    canonical_json_bytes,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tiny-v1"


def _intent(**changes: object) -> RefreshIntent:
    values: dict[str, object] = {
        "parent_publication_id": "publication:parent",
        "parent_observed_at_us": 1_000_000,
        "planned_at_us": 1_000_001,
        "history_preset": "all_time",
        "current_history_preset": "all_time",
    }
    values.update(changes)
    return RefreshIntent(**values)  # type: ignore[arg-type]


def _empty(changes: ProposedChangeSet) -> ProposedChangeSet:
    return replace(
        changes,
        observations=(),
        occurrences=(),
        diagnostics=(),
        cursor_updates=(),
    )


@pytest.mark.parametrize(
    ("change_kind", "intent_changes", "expected_class", "expected_reason"),
    (
        (
            "empty",
            {},
            OperationClass.NO_CHANGE,
            "source_revisions_and_compatibility_unchanged",
        ),
        (
            "empty",
            {"rate_card_changed": True},
            OperationClass.VALUATION_ONLY,
            "rate_card_changed",
        ),
        (
            "replaced",
            {},
            OperationClass.SOURCE_REPLACE,
            "source_replaced_or_truncated",
        ),
        (
            "active",
            {"canonical_owner_changed": True},
            OperationClass.SOURCE_REPLACE,
            "canonical_owner_changed",
        ),
        (
            "active",
            {"adapter_changed": True},
            OperationClass.RECANONICALIZE,
            "adapter_identity_or_normalization_changed",
        ),
        (
            "active",
            {"schema_changed": True},
            OperationClass.SCHEMA_UPGRADE,
            "schema_contract_changed",
        ),
        (
            "active",
            {"projection_registry_changed": True},
            OperationClass.PROJECTION_UPGRADE,
            "projection_registry_changed",
        ),
        (
            "active",
            {"parent_publication_id": None, "current_history_preset": None},
            OperationClass.HISTORY_EXPAND,
            "initial_isolated_publication",
        ),
        (
            "active",
            {"history_preset": "one_year"},
            OperationClass.HISTORY_EXPAND,
            "history_preset_changed",
        ),
    ),
)
def test_planner_classifies_non_append_work(
    change_kind: str,
    intent_changes: dict[str, object],
    expected_class: OperationClass,
    expected_reason: str,
) -> None:
    changes = ingest(FIXTURE, manifest=FIXTURE / "manifest.json").changes
    changes = replace(
        changes,
        selected_sources=tuple(
            replace(
                item,
                state=(SourceState.REPLACED if change_kind == "replaced" else SourceState.ACTIVE),
            )
            for item in changes.selected_sources
        ),
    )
    if change_kind == "empty":
        changes = _empty(changes)

    plan = plan_refresh(changes, _intent(**intent_changes))

    assert plan.operation_class is expected_class
    assert plan.reasons == (expected_reason,)


def test_planner_keeps_no_change_out_of_the_analytical_writer() -> None:
    changes = ingest(FIXTURE, manifest=FIXTURE / "manifest.json").changes
    plan = plan_refresh(_empty(changes), _intent())
    assert plan.operation_class is OperationClass.NO_CHANGE
    assert plan.analytical_write_required is False


def test_planner_routes_unsafe_and_unbounded_work_before_the_write_lock() -> None:
    changes = ingest(FIXTURE, manifest=FIXTURE / "manifest.json").changes
    initial = plan_refresh(
        changes,
        _intent(parent_publication_id=None, current_history_preset=None),
    )
    assert initial.operation_class is OperationClass.HISTORY_EXPAND
    schema = plan_refresh(changes, _intent(schema_changed=True))
    assert schema.operation_class is OperationClass.SCHEMA_UPGRADE
    append_only = replace(
        changes,
        selected_sources=tuple(
            replace(item, state=SourceState.ACTIVE) for item in changes.selected_sources
        ),
    )
    bounded = plan_refresh(
        append_only,
        _intent(),
        limits=TailLimits(selected_bytes=1),
    )
    assert bounded.operation_class is OperationClass.APPEND_SAFE_LARGE
    assert "limit_exceeded:selected_bytes" in bounded.reasons


def test_planner_admits_a_one_call_tail_but_folds_before_32k() -> None:
    changes = ingest(FIXTURE, manifest=FIXTURE / "manifest.json").changes
    one_call_id = next(
        item.logical_id
        for item in changes.observations
        if item.observation_type == "ModelCallObserved"
    )
    one_call = replace(
        changes,
        observations=tuple(item for item in changes.observations if item.logical_id == one_call_id),
        occurrences=tuple(
            item for item in changes.occurrences if item.semantic_logical_id == one_call_id
        ),
        diagnostics=(),
        cursor_updates=(),
        selected_sources=(),
        deferred_sources=(),
    )
    small = plan_refresh(one_call, _intent())
    assert small.operation_class is OperationClass.APPEND_SAFE_SMALL
    folded = plan_refresh(one_call, _intent(current_tail_rows=32_000))
    assert folded.operation_class is OperationClass.APPEND_SAFE_LARGE
    assert "limit_exceeded:model_call_tail_rows" in folded.reasons


def test_measured_small_tail_ceiling_routes_record_33_to_artifact() -> None:
    changes = ingest(FIXTURE, manifest=FIXTURE / "manifest.json").changes
    original = next(
        item for item in changes.observations if item.observation_type == "ModelCallObserved"
    )

    def with_records(count: int):
        observations = tuple(
            replace(
                original,
                source_range=replace(
                    original.source_range,
                    record_ordinal=10_000 + index,
                    byte_start=20_000 + (index * 2),
                    byte_end=20_001 + (index * 2),
                ),
                source_order=10_000 + index,
            )
            for index in range(count)
        )
        return replace(
            changes,
            observations=observations,
            occurrences=(),
            diagnostics=(),
            cursor_updates=(),
            selected_sources=(),
            deferred_sources=(),
        )

    assert (
        plan_refresh(with_records(32), _intent()).operation_class
        is OperationClass.APPEND_SAFE_SMALL
    )
    large = plan_refresh(with_records(33), _intent())
    assert large.operation_class is OperationClass.APPEND_SAFE_LARGE
    assert large.reasons == ("limit_exceeded:selected_records",)


def test_empty_projection_registry_is_valid_and_fanout_fails_closed() -> None:
    registry = ProjectionRegistry()
    assert (
        registry.apply(
            {DirtyKey("session_id", "session:one")},
            maximum_dirty_keys=1,
            maximum_rows_written=0,
        )
        == ()
    )
    with pytest.raises(ProjectionFanoutError, match="dirty-key fanout"):
        registry.apply(
            {
                DirtyKey("session_id", "session:one"),
                DirtyKey("session_id", "session:two"),
            },
            maximum_dirty_keys=1,
            maximum_rows_written=0,
        )


def test_artifact_manifest_serialization_is_canonical_and_nonrecursive() -> None:
    first = {"b": [2, 1], "a": {"z": None, "x": "value"}}
    second = {"a": {"x": "value", "z": None}, "b": [2, 1]}
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert artifact_manifest_sha256(first) == artifact_manifest_sha256(second)
    assert len(artifact_manifest_sha256(first)) == 64


def test_moving_tail_is_bounded_and_discloses_pending_work() -> None:
    boundaries = iter((1, 2, 3))
    applied: list[tuple[int, int]] = []

    def apply(previous: int, current: int, bytes_left: int, records_left: int):
        assert bytes_left > 0 and records_left > 0
        applied.append((previous, current))
        return 10, 1

    result = bounded_moving_tail_catchup(
        0,
        capture=lambda: next(boundaries),
        apply=apply,
        maximum_bytes=20,
        maximum_records=2,
    )
    assert applied == [(0, 1), (1, 2)]
    assert result.passes == 2
    assert result.tail_pending is True
    assert result.boundary == 2


def test_watcher_hints_are_accelerators_not_correctness_authority() -> None:
    assert reconciliation_required(
        dirty_hint_count=1,
        last_reconciled_at_us=100,
        observed_at_us=101,
        maximum_interval_us=1_000,
    )
    assert reconciliation_required(
        dirty_hint_count=0,
        last_reconciled_at_us=100,
        observed_at_us=1_100,
        maximum_interval_us=1_000,
    )
    assert not reconciliation_required(
        dirty_hint_count=0,
        last_reconciled_at_us=100,
        observed_at_us=1_099,
        maximum_interval_us=1_000,
    )
