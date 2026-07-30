from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    AdapterAccounting,
    ProposedChangeSet,
    ProposedOccurrence,
    build_change_set,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.normalize import (
    normalize_record,
    related_observations,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.parser import ParseBatch
from codex_usage_tracker.agent_kernel.adapters.contracts import SourceRange
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    estimate_change_set,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
    read_prior_publication_snapshot,
)
from codex_usage_tracker.agent_kernel.storage.database import initialize_analytical

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tiny-v1"


def _observation(record: dict[str, object], ordinal: int):
    return normalize_record(
        record,
        SourceRange(
            "manifestation:test",
            1,
            "revision-1",
            ordinal,
            ordinal * 100,
            ordinal * 100 + 99,
        ),
    )


def _write_set(*observations):
    expanded = tuple(
        related
        for observation in observations
        for related in (observation, *related_observations(observation))
    )
    changes = ProposedChangeSet(
        observations=expanded,
        occurrences=tuple(
            ProposedOccurrence(observation.logical_id, observation.source_range)
            for observation in expanded
        ),
        diagnostics=(),
        cursor_updates=(),
        accounting=AdapterAccounting({}, {}, {}),
        selected_sources=(),
        deferred_sources=(),
    )
    request = PublicationRequest(
        publication_id="publication:test",
        operation_id="operation:test",
        committed_at_us=1_800_000_000_000_000,
        history_preset="all_time",
        artifact_manifest_sha256="a" * 64,
    )
    return prepare_write_set_from_changes(changes, request)


def _request(operation: str, parent: str | None = None) -> PublicationRequest:
    return PublicationRequest(
        publication_id=f"publication:{operation}",
        operation_id=operation,
        committed_at_us=1_800_000_000_000_000,
        history_preset="all_time",
        artifact_manifest_sha256="a" * 64,
        parent_publication_id=parent,
    )


def _publish(connection, changes, request):
    plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        request.parent_publication_id,
        estimate_change_set(changes),
        ("synthetic_fact_contract",),
        True,
    )
    write_set = prepare_write_set_from_changes(
        changes,
        request,
        prior=read_prior_publication_snapshot(connection, changes),
    )
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )
    PublicationWriter(connection).publish(plan, request, write_set)
    return request.publication_id


def test_context_component_preparation_preserves_only_typed_structural_facts() -> None:
    component = _observation(
        {
            "type": "context_component",
            "event_at_us": 100,
            "source_order": 3,
            "payload": {
                "component_id": "component-1",
                "session_id": "session-1",
                "category": "system_instruction",
                "observed_utf8_bytes": 42,
                "observed_event_count": 1,
                "total_context_utf8_bytes": 64,
                "estimator": None,
                "estimated_tokens": None,
                "inclusion_basis": "known_included_in_call",
                "capability_basis": "codex_jsonl_structural_event",
                "measurement_basis": "exact_utf8_bytes",
            },
        },
        1,
    )

    row = next(row for row in _write_set(component).rows if row.table == "context_components")
    assert row.values["observed_utf8_bytes"] == 42
    assert row.values["estimated_tokens"] is None
    assert not set(row.values) & {"body", "content", "prompt", "response", "tool_output"}


def test_allowance_preparation_preserves_cycle_and_builds_equal_time_interval() -> None:
    common = {
        "limit_id": "weekly",
        "cycle_id": "cycle-1",
        "plan_identity": "plan-a",
        "window_kind": "rolling_week",
        "reset_identity": "reset-a",
        "provider": "openai",
        "account_local_identity": "account-a",
        "cycle_start_us": 50,
        "cycle_end_us": 500,
        "completion_status": "closed",
    }
    first = _observation(
        {
            "type": "allowance_observation",
            "event_at_us": 100,
            "source_order": 1,
            "payload": {
                **common,
                "observation_ordinal": 0,
                "used_percent": "10",
            },
        },
        2,
    )
    second = _observation(
        {
            "type": "allowance_observation",
            "event_at_us": 100,
            "source_order": 2,
            "payload": {
                **common,
                "observation_ordinal": 1,
                "used_percent": "12.5",
            },
        },
        3,
    )

    rows = _write_set(first, second).rows
    cycle = next(row for row in rows if row.table == "allowance_cycles")
    interval = next(row for row in rows if row.table == "allowance_intervals")
    assert (cycle.values["start_at_us"], cycle.values["end_at_us"]) == (50, 500)
    assert cycle.values["completion_status"] == "closed"
    assert interval.values["start_us"] == interval.values["end_us"] == 100
    assert interval.values["start_observation_id"] != interval.values["end_observation_id"]
    assert interval.values["percent_delta"] == "2.5"


def test_late_parent_preparation_writes_edge_and_current_hierarchy_without_labels() -> None:
    parent = _observation(
        {
            "type": "session_start",
            "event_at_us": 10,
            "source_order": 1,
            "payload": {"session_id": "parent", "state": "running", "project_id": "p"},
        },
        4,
    )
    child = _observation(
        {
            "type": "session_start",
            "event_at_us": 20,
            "source_order": 2,
            "payload": {"session_id": "child", "state": "running", "project_id": "p"},
        },
        5,
    )
    relationship = _observation(
        {
            "type": "late_parent",
            "event_at_us": 30,
            "source_order": 3,
            "payload": {
                "session_id": "child",
                "parent_session_id": "parent",
                "relationship_basis": "late_discovery",
            },
        },
        6,
    )

    rows = _write_set(parent, child, relationship).rows
    edge = next(row for row in rows if row.table == "late_parent_edges")
    updated_child = next(
        row
        for row in rows
        if row.table == "sessions" and row.values["session_id"] == edge.values["child_session_id"]
    )
    assert updated_child.values["parent_session_id"] == edge.values["parent_session_id"]
    assert updated_child.values["delegation_depth"] == 1
    assert updated_child.values["label_candidates_json"] == "[]"


def test_allowance_preparation_does_not_bridge_plan_or_reset_changes() -> None:
    def allowance(ordinal: int, plan: str, reset: str):
        return _observation(
            {
                "type": "allowance_observation",
                "event_at_us": 100 + ordinal,
                "source_order": ordinal,
                "payload": {
                    "limit_id": "weekly",
                    "cycle_id": f"cycle-{reset}",
                    "plan_identity": plan,
                    "window_kind": "rolling_week",
                    "reset_identity": reset,
                    "provider": "openai",
                    "account_local_identity": "account-a",
                    "observation_ordinal": 0,
                    "used_percent": "10",
                },
            },
            10 + ordinal,
        )

    rows = _write_set(
        allowance(1, "plan-a", "reset-a"),
        allowance(2, "plan-b", "reset-a"),
        allowance(3, "plan-a", "reset-b"),
    ).rows
    assert all(row.table != "allowance_intervals" for row in rows)


def test_context_component_and_late_parent_are_persisted(tmp_path: Path) -> None:
    changes = ingest(_FIXTURE, manifest=_FIXTURE / "manifest.json").changes
    sessions = [item for item in changes.observations if item.observation_type == "SessionObserved"]
    call = next(
        item for item in changes.observations if item.observation_type == "ModelCallObserved"
    )
    context_identity = (
        call.payload["session_id"],
        call.payload["turn_id"],
        call.logical_id,
        "system_instruction",
    )
    context = replace(
        call,
        observation_type="ContextComponentObserved",
        logical_id=semantic_id("context-component", context_identity),
        identity_tuple=context_identity,
        payload={
            "component_id": semantic_id("context-component", context_identity),
            "session_id": call.payload["session_id"],
            "turn_id": call.payload["turn_id"],
            "call_id": call.logical_id,
            "category": "system_instruction",
            "observed_utf8_bytes": 64,
            "observed_event_count": 1,
            "total_context_utf8_bytes": 96,
            "estimator": None,
            "estimated_tokens": None,
            "inclusion_basis": "known_included_in_call",
            "capability_basis": "synthetic_structural_event",
            "measurement_basis": "exact_utf8_bytes",
        },
    )
    child, parent = sessions[0], sessions[2]
    relationship_identity = (
        child.identity_tuple[0],
        parent.identity_tuple[0],
        "late_discovery",
    )
    relationship = replace(
        child,
        observation_type="SessionRelationshipObserved",
        logical_id=semantic_id("session-relationship", relationship_identity),
        identity_tuple=relationship_identity,
        payload={
            "session_id": child.logical_id,
            "parent_session_id": parent.logical_id,
            "relationship_basis": "late_discovery",
        },
    )
    augmented = replace(
        changes,
        observations=tuple(
            sorted((*changes.observations, context, relationship), key=lambda item: item.sort_key)
        ),
        occurrences=(
            *changes.occurrences,
            ProposedOccurrence(context.logical_id, context.source_range),
            ProposedOccurrence(relationship.logical_id, relationship.source_range),
        ),
    )
    connection = initialize_analytical(tmp_path / "facts.sqlite3")
    try:
        first = _publish(connection, augmented, _request("persisted-facts"))
        assert tuple(connection.execute("SELECT count(*) FROM context_components").fetchone()) == (
            1,
        )
        assert tuple(connection.execute("SELECT count(*) FROM late_parent_edges").fetchone()) == (
            1,
        )
        assert tuple(
            connection.execute(
                "SELECT parent_session_id, label_candidates_json FROM sessions WHERE session_id = ?",
                (child.logical_id,),
            ).fetchone()
        ) == (parent.logical_id, "[]")

        corrected_context = replace(
            context,
            source_range=replace(
                context.source_range,
                record_ordinal=10_001,
                byte_start=10_001_000,
                byte_end=10_001_099,
            ),
            payload={**context.payload, "observed_utf8_bytes": 80},
        )
        replayed_relationship = replace(
            relationship,
            source_range=replace(
                relationship.source_range,
                record_ordinal=10_002,
                byte_start=10_002_000,
                byte_end=10_002_099,
            ),
        )
        new_parent = normalize_record(
            {
                "type": "session_start",
                "event_at_us": 31,
                "source_order": 4,
                "payload": {
                    "session_id": "additional-parent",
                    "state": "running",
                    "project_id": "p",
                },
            },
            replace(
                relationship.source_range,
                record_ordinal=10_003,
                byte_start=10_003_000,
                byte_end=10_003_099,
            ),
        )
        other_parent = new_parent
        new_relationship_identity = (
            child.identity_tuple[0],
            other_parent.identity_tuple[0],
            "late_discovery",
        )
        new_relationship = replace(
            replayed_relationship,
            logical_id=semantic_id("session-relationship", new_relationship_identity),
            identity_tuple=new_relationship_identity,
            source_range=replace(
                relationship.source_range,
                record_ordinal=10_004,
                byte_start=10_004_000,
                byte_end=10_004_099,
            ),
            payload={
                "session_id": child.logical_id,
                "parent_session_id": other_parent.logical_id,
                "relationship_basis": "late_discovery",
            },
        )
        new_parent_observations = (new_parent, *related_observations(new_parent))
        replacement = ProposedChangeSet(
            observations=(
                corrected_context,
                replayed_relationship,
                *new_parent_observations,
                new_relationship,
            ),
            occurrences=tuple(
                ProposedOccurrence(item.logical_id, item.source_range)
                for item in (
                    corrected_context,
                    replayed_relationship,
                    *new_parent_observations,
                    new_relationship,
                )
            ),
            diagnostics=(),
            cursor_updates=(),
            accounting=AdapterAccounting({}, {}, {}),
            selected_sources=(),
            deferred_sources=(),
        )
        second = _publish(
            connection,
            replacement,
            _request("corrected-facts", parent=first),
        )

        assert tuple(
            connection.execute(
                """
                SELECT component_id, observed_utf8_bytes,
                       first_seen_publication_id, last_seen_publication_id
                FROM context_components
                """
            ).fetchone()
        ) == (context.logical_id, 80, first, second)
        assert [
            tuple(row)
            for row in connection.execute(
                """
                SELECT relationship_version, parent_session_id,
                       relationship_basis, first_seen_publication_id
                FROM late_parent_edges
                WHERE child_session_id = ?
                ORDER BY relationship_version
                """,
                (child.logical_id,),
            )
        ] == [
            (1, parent.logical_id, "late_discovery", first),
            (2, other_parent.logical_id, "late_discovery", second),
        ]

        unchanged_context = replace(
            corrected_context,
            source_range=replace(
                context.source_range,
                record_ordinal=10_005,
                byte_start=10_005_000,
                byte_end=10_005_099,
            ),
        )
        unchanged = ProposedChangeSet(
            observations=(unchanged_context,),
            occurrences=(
                ProposedOccurrence(
                    unchanged_context.logical_id,
                    unchanged_context.source_range,
                ),
            ),
            diagnostics=(),
            cursor_updates=(),
            accounting=AdapterAccounting({}, {}, {}),
            selected_sources=(),
            deferred_sources=(),
        )
        third = _publish(
            connection,
            unchanged,
            _request("unchanged-facts", parent=second),
        )
        stable_component = tuple(connection.execute("SELECT * FROM context_components").fetchone())
        assert stable_component[0] == context.logical_id
        assert stable_component[-2:] == (first, third)

        rebuilt = initialize_analytical(tmp_path / "facts-rebuilt.sqlite3")
        try:
            rebuilt_first = _publish(
                rebuilt,
                augmented,
                _request("persisted-facts"),
            )
            rebuilt_second = _publish(
                rebuilt,
                replacement,
                _request("corrected-facts", parent=rebuilt_first),
            )
            _publish(
                rebuilt,
                unchanged,
                _request("unchanged-facts", parent=rebuilt_second),
            )
            assert (
                tuple(rebuilt.execute("SELECT * FROM context_components").fetchone())
                == stable_component
            )
        finally:
            rebuilt.close()
    finally:
        connection.close()


def test_allowance_interval_bridges_prior_publication_and_preserves_closed_cycle(
    tmp_path: Path,
) -> None:
    inventory = ingest(_FIXTURE, manifest=_FIXTURE / "manifest.json").changes.selected_sources[0]

    def changes_for(ordinal: int, used: str):
        observation = normalize_record(
            {
                "type": "allowance_observation",
                "event_at_us": 100 + ordinal,
                "source_order": ordinal,
                "payload": {
                    "limit_id": "weekly",
                    "cycle_id": "cycle-a",
                    "plan_identity": "plan-a",
                    "window_kind": "rolling_week",
                    "reset_identity": "reset-a",
                    "provider": "openai",
                    "account_local_identity": "account-a",
                    "cycle_start_us": 50,
                    "cycle_end_us": 500,
                    "completion_status": "closed",
                    "observation_ordinal": ordinal - 1,
                    "used_percent": used,
                },
            },
            SourceRange(
                inventory.manifestation_id,
                inventory.manifestation_key,
                inventory.content_revision,
                ordinal,
                ordinal * 10,
                ordinal * 10 + 9,
            ),
        )
        return build_change_set(
            (
                ParseBatch(
                    inventory.source_rank,
                    0,
                    (observation, *related_observations(observation)),
                    (),
                    1,
                    ordinal * 10 + 9,
                    ordinal,
                    True,
                ),
            ),
            selected_sources=(inventory,),
            deferred_sources=(),
        )

    connection = initialize_analytical(tmp_path / "allowance.sqlite3")
    try:
        first = _publish(connection, changes_for(1, "10"), _request("allowance-1"))
        _publish(
            connection,
            changes_for(2, "12.5"),
            _request("allowance-2", parent=first),
        )
        assert tuple(
            connection.execute(
                "SELECT start_at_us, end_at_us, completion_status FROM allowance_cycles"
            ).fetchone()
        ) == (50, 500, "closed")
        assert tuple(
            connection.execute(
                """
                SELECT percent_delta, start_us, end_us, first_seen_publication_id
                FROM allowance_intervals
                """
            ).fetchone()
        ) == ("2.5", 101, 102, "publication:allowance-2")

        replay_first = changes_for(1, "10")
        replay_second = changes_for(2, "12.5")
        replay = replace(
            replay_first,
            observations=(*replay_first.observations, *replay_second.observations),
            occurrences=(*replay_first.occurrences, *replay_second.occurrences),
        )
        _publish(
            connection,
            replay,
            _request("allowance-replay", parent="publication:allowance-2"),
        )
        stable_rows = list(connection.execute("SELECT * FROM allowance_intervals"))
        assert len(stable_rows) == 1
        assert stable_rows[0][-1] == "publication:allowance-2"

        rebuilt = initialize_analytical(tmp_path / "allowance-rebuilt.sqlite3")
        try:
            rebuilt_first = _publish(
                rebuilt,
                changes_for(1, "10"),
                _request("allowance-1"),
            )
            rebuilt_second = _publish(
                rebuilt,
                changes_for(2, "12.5"),
                _request("allowance-2", parent=rebuilt_first),
            )
            _publish(
                rebuilt,
                replay,
                _request("allowance-replay", parent=rebuilt_second),
            )
            assert list(rebuilt.execute("SELECT * FROM allowance_intervals")) == stable_rows
        finally:
            rebuilt.close()
    finally:
        connection.close()


def test_allowance_equal_time_order_uses_logical_id_before_transition_rank(
    tmp_path: Path,
) -> None:
    inventory = ingest(_FIXTURE, manifest=_FIXTURE / "manifest.json").changes.selected_sources[0]
    common = {
        "limit_id": "weekly",
        "cycle_id": "cycle-tied",
        "plan_identity": "plan-a",
        "window_kind": "rolling_week",
        "reset_identity": "reset-tied",
        "provider": "openai",
        "account_local_identity": "account-a",
        "cycle_start_us": 50,
        "cycle_end_us": 500,
        "completion_status": "closed",
    }

    def observation(ordinal: int, used: str):
        return normalize_record(
            {
                "type": "allowance_observation",
                "event_at_us": 100,
                "source_order": 7,
                "payload": {
                    **common,
                    "observation_ordinal": ordinal,
                    "used_percent": used,
                },
            },
            SourceRange(
                inventory.manifestation_id,
                inventory.manifestation_key,
                inventory.content_revision,
                200 + ordinal,
                2_000 + ordinal * 10,
                2_009 + ordinal * 10,
            ),
        )

    left, right = observation(0, "10"), observation(1, "12")
    smaller, larger = sorted((left, right), key=lambda item: item.logical_id)
    smaller = replace(smaller, transition_rank=9)
    larger = replace(larger, transition_rank=0)
    expanded = tuple(
        related for item in (smaller, larger) for related in (item, *related_observations(item))
    )
    changes = build_change_set(
        (
            ParseBatch(
                inventory.source_rank,
                0,
                expanded,
                (),
                1,
                2_100,
                201,
                True,
            ),
        ),
        selected_sources=(inventory,),
        deferred_sources=(),
    )
    connection = initialize_analytical(tmp_path / "allowance-order.sqlite3")
    try:
        _publish(connection, changes, _request("allowance-order"))
        assert tuple(
            connection.execute(
                """
                SELECT start_observation_id, end_observation_id
                FROM allowance_intervals
                """
            ).fetchone()
        ) == (smaller.logical_id, larger.logical_id)

        prior = read_prior_publication_snapshot(connection, changes)
        predecessor = next(iter(prior.allowance_predecessors.values()))
        assert predecessor.values["observation_id"] == larger.logical_id
    finally:
        connection.close()
