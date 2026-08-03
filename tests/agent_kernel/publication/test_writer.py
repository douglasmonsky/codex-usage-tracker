from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    build_change_set,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.parser import ParseBatch
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    estimate_change_set,
)
from codex_usage_tracker.agent_kernel.publication.validation import (
    PublicationValidationError,
    build_isolated_artifact,
    validate_artifact_path,
    validate_open_artifact,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriteError,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
    read_prior_publication_snapshot,
)
from codex_usage_tracker.agent_kernel.storage.database import initialize_analytical

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "tiny-v1"
FIXTURE_MANIFEST = FIXTURE_ROOT / "manifest.json"


def _request(
    operation_id: str = "operation:ck07",
    *,
    parent_publication_id: str | None = None,
    committed_at_us: int = 1_800_000_000_000_000,
) -> PublicationRequest:
    return PublicationRequest(
        publication_id=f"publication:{operation_id}",
        operation_id=operation_id,
        committed_at_us=committed_at_us,
        history_preset="all_time",
        artifact_manifest_sha256="a" * 64,
        parent_publication_id=parent_publication_id,
        indexed_from_us=1_700_000_000_000_000,
        indexed_through_us=1_800_000_000_000_000,
        guaranteed_complete_from_us=1_700_000_000_000_000,
    )


def _plan(changes, parent_publication_id: str | None = None):
    return PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        parent_publication_id,
        estimate_change_set(changes),
        ("test_small_tail_bounds_proven",),
        True,
    )


def _tiny_changes():
    return ingest(
        FIXTURE_ROOT,
        manifest=FIXTURE_MANIFEST,
        workers=2,
        batch_size=32,
    ).changes


def _provenance_write_set(operation_id: str = "operation:provenance"):
    changes = _tiny_changes()
    request = _request(operation_id)
    return changes, prepare_write_set_from_changes(changes, request)


def test_turn_provenance_persists_nonzero_rank_and_null_order_fallback() -> None:
    changes = _tiny_changes()
    target = next(
        item for item in changes.observations if item.observation_type == "TurnBoundaryObserved"
    )
    target_key = target.source_range.manifestation_key
    observations = []
    for item in changes.observations:
        if item is target:
            item = replace(item, source_rank=3)
            # AdapterObservation is normally non-null; this models a legacy
            # proposal reaching the defensive current-schema boundary.
            object.__setattr__(item, "source_order", None)
        observations.append(item)
    selected_sources = tuple(
        replace(item, source_rank=3) if item.manifestation_key == target_key else item
        for item in changes.selected_sources
    )
    candidate = replace(
        changes,
        observations=tuple(observations),
        selected_sources=selected_sources,
    )
    write_set = prepare_write_set_from_changes(candidate, _request("operation:provenance"))
    row = next(
        row
        for row in write_set.rows
        if row.table == "turns" and row.values["primary_occurrence_id"] == target.occurrence_id
    )
    assert row.values["start_source_rank"] == 3
    assert row.values["start_source_order"] == target.source_range.record_ordinal


@pytest.mark.parametrize("failure", ("rank", "unresolved", "ambiguous", "manifestation", "lifecycle"))
def test_turn_provenance_rejects_unresolved_or_mismatched_candidates(failure: str) -> None:
    changes, write_set = _provenance_write_set(f"operation:provenance-{failure}")
    turn_row = next(row for row in write_set.rows if row.table == "turns")
    occurrence_id = str(turn_row.values["primary_occurrence_id"])
    bad_rows = list(write_set.rows)
    row_index = bad_rows.index(turn_row)
    values = dict(turn_row.values)
    bad_changes = changes
    if failure == "rank":
        values["start_source_rank"] = int(values["start_source_rank"]) + 1
    elif failure == "unresolved":
        bad_changes = replace(
            changes,
            occurrences=tuple(
                item for item in changes.occurrences if item.occurrence_id != occurrence_id
            ),
        )
    elif failure == "ambiguous":
        observation = next(
            item
            for item in changes.observations
            if item.observation_type == "TurnBoundaryObserved"
            and item.logical_id == turn_row.values["turn_id"]
        )
        duplicate = replace(
            observation,
            source_range=replace(
                observation.source_range,
                record_ordinal=observation.source_range.record_ordinal + 1,
                byte_start=observation.source_range.byte_start + 1,
                byte_end=observation.source_range.byte_end + 1,
            ),
        )
        bad_changes = replace(changes, observations=(*changes.observations, duplicate))
    elif failure == "manifestation":
        bad_changes = replace(
            changes,
            selected_sources=tuple(
                replace(item, manifestation_id="source-manifestation:wrong")
                if item.manifestation_key
                == next(
                    occurrence.source_range.manifestation_key
                    for occurrence in changes.occurrences
                    if occurrence.occurrence_id == occurrence_id
                )
                else item
                for item in changes.selected_sources
            ),
        )
    else:
        start_at_us = int(values["start_at_us"] or 0)
        values["end_at_us"] = start_at_us - 1
    bad_rows[row_index] = replace(turn_row, values=values)
    bad_write_set = replace(write_set, changes=bad_changes, rows=tuple(bad_rows))
    connection = sqlite3.connect(":memory:")
    try:
        with pytest.raises(PublicationWriteError):
            PublicationWriter(connection)._validate_turn_provenance(bad_write_set)
    finally:
        connection.close()


def test_tiny_fixture_publication_is_atomic_exact_and_idempotent(tmp_path: Path) -> None:
    changes = _tiny_changes()
    request = _request()
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        result = PublicationWriter(connection).publish(plan, request, write_set)
        assert result.inserted_occurrences == len(changes.occurrences)
        assert result.transaction_elapsed_ns is not None
        assert result.transaction_elapsed_ns > 0
        assert (
            connection.execute("SELECT publication_id FROM publication_head").fetchone()[0]
            == request.publication_id
        )
        assert connection.execute("SELECT count(*) FROM model_call_tail").fetchone()[0] == 100
        assert connection.execute("SELECT count(*) FROM tool_invocations").fetchone()[0] == 25
        assert connection.execute("SELECT count(*) FROM source_occurrences").fetchone()[0] == len(
            changes.occurrences
        )
        assert (
            connection.execute("SELECT row_count FROM model_call_tail_state").fetchone()[0] == 100
        )
        entity_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                """
                SELECT entity_kind, entity_count
                FROM publication_entity_counts
                WHERE publication_id = ?
                """,
                (request.publication_id,),
            )
        }
        assert entity_counts == {
            "activities": 5,
            "allowance_limits": 1,
            "allowance_observations": 4,
            "compaction_boundaries": 2,
            "model_calls": 100,
            "projects": 2,
            "resources": 25,
            "sessions": 10,
            "source_manifestations": 12,
            "source_occurrences": 450,
            "state_changes": 5,
            "tool_invocations": 25,
            "turns": 50,
        }
        assert (
            connection.execute(
                """
            SELECT count(*)
            FROM source_occurrences
            WHERE semantic_logical_id IN (
              SELECT call_id FROM model_call_locations
            )
            """
            ).fetchone()[0]
            == 102
        )
        token_accounting = connection.execute(
            """
            SELECT
              sum(uncached_input_tokens),
              count(uncached_input_tokens),
              count(*) - count(uncached_input_tokens),
              CASE WHEN count(*) = count(cached_input_tokens)
                   THEN sum(cached_input_tokens) END,
              count(cached_input_tokens),
              count(*) - count(cached_input_tokens),
              sum(reasoning_tokens),
              count(reasoning_tokens),
              count(*) - count(reasoning_tokens),
              sum(output_tokens),
              count(output_tokens),
              count(*) - count(output_tokens)
            FROM model_call_tail
            """
        ).fetchone()
        assert tuple(token_accounting) == (
            53_650,
            100,
            0,
            None,
            95,
            5,
            31_850,
            100,
            0,
            47_450,
            100,
            0,
        )
        assert (
            validate_open_artifact(
                connection, expected_publication_id=request.publication_id
            ).identity.operation_id
            == request.operation_id
        )

        replay = PublicationWriter(connection).publish(plan, request, write_set)
        assert replay.idempotent_replay
        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM source_occurrences").fetchone()[0] == len(
            changes.occurrences
        )
    finally:
        connection.close()


def test_initial_history_build_isolated_artifact_is_durable(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    changes = _tiny_changes()
    request = _request("operation:isolated")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )

    def build(connection: sqlite3.Connection) -> None:
        PublicationWriter(connection).publish(plan, request, write_set)

    candidate = build_isolated_artifact(
        tmp_path,
        request.operation_id,
        build,
        expected_publication_id=request.publication_id,
        expected_manifest_sha256=request.artifact_manifest_sha256,
    )

    assert candidate.path.stat().st_mode & 0o777 == 0o600
    validation = validate_artifact_path(
        candidate.path,
        expected_publication_id=request.publication_id,
        expected_manifest_sha256=request.artifact_manifest_sha256,
        expected_file_sha256=candidate.file_sha256,
        integrity=True,
    )
    assert validation.identity.operation_id == request.operation_id


def test_isolated_validation_rejects_entity_count_tamper_before_promotion(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    changes = _tiny_changes()
    request = _request("operation:tampered-count")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )

    def build(connection: sqlite3.Connection) -> None:
        PublicationWriter(connection).publish(plan, request, write_set)
        connection.execute(
            """
            UPDATE publication_entity_counts SET entity_count = 999999
            WHERE publication_id = ? AND entity_kind = 'model_calls'
            """,
            (request.publication_id,),
        )
        connection.commit()

    with pytest.raises(PublicationValidationError, match="entity counts"):
        build_isolated_artifact(
            tmp_path,
            request.operation_id,
            build,
            expected_publication_id=request.publication_id,
            expected_manifest_sha256=request.artifact_manifest_sha256,
        )


def test_isolated_validation_recomputes_manifest_before_promotion(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    changes = _tiny_changes()
    request = _request("operation:tampered-manifest")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )

    def build(connection: sqlite3.Connection) -> None:
        PublicationWriter(connection).publish(plan, request, write_set)
        connection.execute(
            """
            UPDATE publications SET projection_registry_sha256 = ?
            WHERE publication_id = ?
            """,
            ("b" * 64, request.publication_id),
        )
        connection.commit()

    with pytest.raises(PublicationValidationError, match="canonical artifact manifest"):
        build_isolated_artifact(
            tmp_path,
            request.operation_id,
            build,
            expected_publication_id=request.publication_id,
            expected_manifest_sha256=request.artifact_manifest_sha256,
        )


def test_isolated_validation_rejects_lifecycle_fold_tamper_before_promotion(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    changes = _tiny_changes()
    request = _request("operation:tampered-lifecycle")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )

    def build(connection: sqlite3.Connection) -> None:
        PublicationWriter(connection).publish(plan, request, write_set)
        connection.execute(
            """
            UPDATE sessions
            SET lifecycle_state = CASE
              WHEN lifecycle_state = 'failed' THEN 'running'
              ELSE 'failed'
            END
            WHERE session_id = (SELECT session_id FROM sessions ORDER BY session_id LIMIT 1)
            """
        )
        connection.commit()

    with pytest.raises(PublicationValidationError, match="lifecycle fold"):
        build_isolated_artifact(
            tmp_path,
            request.operation_id,
            build,
            expected_publication_id=request.publication_id,
            expected_manifest_sha256=request.artifact_manifest_sha256,
        )


@pytest.mark.parametrize(
    ("tamper_sql", "expected_error"),
    (
        (
            """
            UPDATE publication_source_coverage
            SET selected_manifestation_count = selected_manifestation_count + 1
            WHERE source_id = (
              SELECT source_id FROM publication_source_coverage
              ORDER BY source_id LIMIT 1
            )
            """,
            "source coverage totals",
        ),
        (
            """
            UPDATE publication_deltas SET inserted_count = inserted_count + 1
            """,
            "delta aggregate",
        ),
        (
            """
            UPDATE identity_registry
            SET identity_sha256 =
              'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'
            WHERE logical_id = (
              SELECT logical_id FROM identity_registry
              WHERE entity_kind = 'session' ORDER BY logical_id LIMIT 1
            )
            """,
            "identity registry digest",
        ),
        (
            """
            UPDATE publication_source_coverage
            SET indexed_through_us = indexed_through_us + 1
            WHERE source_id = (
              SELECT source_id FROM publication_source_coverage
              ORDER BY source_id LIMIT 1
            )
            """,
            "source coverage clock bounds",
        ),
    ),
)
def test_isolated_validation_rejects_relationship_tamper_before_promotion(
    tmp_path: Path,
    tamper_sql: str,
    expected_error: str,
) -> None:
    tmp_path.chmod(0o700)
    changes = _tiny_changes()
    request = _request("operation:isolated")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )

    def build(connection: sqlite3.Connection) -> None:
        PublicationWriter(connection).publish(plan, request, write_set)
        connection.execute(tamper_sql)
        connection.commit()

    with pytest.raises(PublicationValidationError, match=expected_error):
        build_isolated_artifact(
            tmp_path,
            request.operation_id,
            build,
            expected_publication_id=request.publication_id,
            expected_manifest_sha256=request.artifact_manifest_sha256,
        )


@pytest.mark.parametrize(
    "fault_stage",
    (
        "after_begin",
        "after_recheck",
        "after_publication",
        "after_occurrences",
        "after_facts",
        "after_metadata",
        "after_head",
        "before_commit",
    ),
)
def test_fault_stages_roll_back_and_allow_retry(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    changes = _tiny_changes()
    request = _request("operation:rollback")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:

        def inject(stage: str) -> None:
            if stage == fault_stage:
                raise RuntimeError("synthetic crash")

        with pytest.raises(RuntimeError, match="synthetic crash"):
            PublicationWriter(connection).publish(plan, request, write_set, fault_injector=inject)
        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM publication_head").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM source_occurrences").fetchone()[0] == 0
        assert read_prior_publication_snapshot(connection, changes).entity_counts == {}

        result = PublicationWriter(connection).publish(plan, request, write_set)
        assert result.publication_id == request.publication_id
        assert (
            validate_open_artifact(
                connection, expected_publication_id=request.publication_id
            ).identity.operation_id
            == request.operation_id
        )
    finally:
        connection.close()


def test_prior_snapshot_extends_tail_across_publications(tmp_path: Path) -> None:
    first_changes = _tiny_changes()
    first_request = _request("operation:first-tail")
    first_plan = _plan(first_changes)
    first_write_set = prepare_write_set_from_changes(first_changes, first_request)
    first_request = replace(
        first_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            first_plan, first_request, first_write_set
        ),
    )
    original = next(
        item for item in first_changes.observations if item.observation_type == "ModelCallObserved"
    )
    assert original.event_at_us is not None
    next_identity = (
        f"{original.identity_tuple[0]}:next",
        *original.identity_tuple[1:],
    )
    next_logical_id = semantic_id("call", next_identity)
    next_revision = "b" * 64
    updated_inventory = replace(
        next(
            item
            for item in first_changes.selected_sources
            if item.manifestation_key == original.source_range.manifestation_key
        ),
        content_revision=next_revision,
    )
    next_range = replace(
        original.source_range,
        source_revision=next_revision,
        record_ordinal=original.source_range.record_ordinal + 10_000,
        byte_start=original.source_range.byte_end,
        byte_end=original.source_range.byte_end + 1,
    )
    next_observation = replace(
        original,
        logical_id=next_logical_id,
        identity_tuple=next_identity,
        source_range=next_range,
        event_at_us=original.event_at_us + 1,
        source_order=original.source_order + 10_000,
        payload={
            **original.payload,
            "call_id": next_logical_id,
        },
    )
    second_changes = build_change_set(
        (
            ParseBatch(
                source_rank=0,
                batch_index=0,
                observations=(next_observation,),
                diagnostics=(),
                records_seen=1,
                complete_end=next_range.byte_end,
                latest_source_order=next_observation.source_order,
                done=False,
            ),
        ),
        selected_sources=(updated_inventory,),
        deferred_sources=(),
    )
    second_changes = replace(
        second_changes,
        cursor_updates=(
            replace(
                next(
                    cursor
                    for cursor in first_changes.cursor_updates
                    if cursor.manifestation_key == updated_inventory.manifestation_key
                ),
                source_revision=next_revision,
            ),
        ),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        PublicationWriter(connection).publish(first_plan, first_request, first_write_set)
        prior = read_prior_publication_snapshot(connection, second_changes)
        assert prior.entity_counts["model_calls"] == 100
        assert prior.lifecycle == {}
        assert prior.tail_state is not None
        assert prior.tail_state.row_count == 100
        assert len(prior.source_coverage) == 11
        assert len(prior.source_cursors) == len(first_changes.cursor_updates)
        assert prior.source_revisions == {
            updated_inventory.manifestation_key: (
                next(
                    item
                    for item in first_changes.selected_sources
                    if item.manifestation_key == updated_inventory.manifestation_key
                ).content_revision
            )
        }

        second_request = _request(
            "operation:second-tail",
            parent_publication_id=first_request.publication_id,
            committed_at_us=first_request.committed_at_us + 1,
        )
        second_plan = _plan(second_changes, first_request.publication_id)
        second_write_set = prepare_write_set_from_changes(
            second_changes, second_request, prior=prior
        )
        second_request = replace(
            second_request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                second_plan, second_request, second_write_set
            ),
        )
        PublicationWriter(connection).publish(second_plan, second_request, second_write_set)
        validation = validate_open_artifact(
            connection,
            expected_publication_id=second_request.publication_id,
        )
        assert validation.identity.artifact_manifest_sha256 == (
            second_request.artifact_manifest_sha256
        )
        assert connection.execute("SELECT count(*) FROM model_call_tail").fetchone()[0] == 101
        assert (
            connection.execute("SELECT row_count FROM model_call_tail_state").fetchone()[0] == 101
        )
        assert (
            connection.execute(
                """
            SELECT content_revision
            FROM source_manifestations
            WHERE manifestation_key = ?
            """,
                (updated_inventory.manifestation_key,),
            ).fetchone()[0]
            == next_revision
        )
        current = read_prior_publication_snapshot(connection, second_changes)
        assert current.entity_counts["model_calls"] == 101
        assert len(current.lifecycle[next_logical_id]) == 1
        assert len(current.source_coverage) == len(prior.source_coverage)
        assert len(current.source_cursors) == len(prior.source_cursors)
        assert {cursor.manifestation_key for cursor in current.source_cursors} == {
            cursor.manifestation_key for cursor in prior.source_cursors
        }
    finally:
        connection.close()


def test_terminal_update_accounts_for_physical_state_without_reinsertion(
    tmp_path: Path,
) -> None:
    first_changes = _tiny_changes()
    first_request = _request("operation:running-tool")
    first_plan = _plan(first_changes)
    first_write_set = prepare_write_set_from_changes(first_changes, first_request)
    first_request = replace(
        first_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            first_plan, first_request, first_write_set
        ),
    )
    running_tool_id = next(
        str(row.values["tool_id"])
        for row in first_write_set.rows
        if row.table == "tool_invocations" and row.values["lifecycle_state"] == "running"
    )
    original = next(
        item
        for item in first_changes.observations
        if item.observation_type == "ToolLifecycleObserved" and item.logical_id == running_tool_id
    )
    assert original.event_at_us is not None
    terminal_range = replace(
        original.source_range,
        record_ordinal=original.source_range.record_ordinal + 10_000,
        byte_start=original.source_range.byte_end,
        byte_end=original.source_range.byte_end + 1,
    )
    terminal_observation = replace(
        original,
        source_range=terminal_range,
        event_at_us=original.event_at_us + 1,
        source_order=original.source_order + 10_000,
        payload={**original.payload, "state": "succeeded"},
    )
    terminal_changes = build_change_set(
        (
            ParseBatch(
                source_rank=terminal_observation.source_rank,
                batch_index=0,
                observations=(terminal_observation,),
                diagnostics=(),
                records_seen=1,
                complete_end=terminal_range.byte_end,
                latest_source_order=terminal_observation.source_order,
                done=False,
            ),
        ),
        selected_sources=(),
        deferred_sources=(),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        PublicationWriter(connection).publish(first_plan, first_request, first_write_set)
        prior = read_prior_publication_snapshot(connection, terminal_changes)
        assert prior.entity_counts["tool_invocations"] == 25
        assert prior.entity_counts["source_occurrences"] == 450
        assert len(prior.source_coverage) == 11
        assert len(prior.source_cursors) == len(first_changes.cursor_updates)

        terminal_request = _request(
            "operation:terminal-tool",
            parent_publication_id=first_request.publication_id,
            committed_at_us=first_request.committed_at_us + 1,
        )
        terminal_plan = _plan(
            terminal_changes,
            parent_publication_id=first_request.publication_id,
        )
        terminal_write_set = prepare_write_set_from_changes(
            terminal_changes,
            terminal_request,
            prior=prior,
        )
        terminal_request = replace(
            terminal_request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                terminal_plan, terminal_request, terminal_write_set
            ),
        )
        PublicationWriter(connection).publish(
            terminal_plan,
            terminal_request,
            terminal_write_set,
        )

        assert connection.execute("SELECT count(*) FROM tool_invocations").fetchone()[0] == 25
        assert (
            connection.execute(
                "SELECT lifecycle_state FROM tool_invocations WHERE tool_id = ?",
                (running_tool_id,),
            ).fetchone()[0]
            == "succeeded"
        )
        assert tuple(
            connection.execute(
                """
                SELECT inserted_count, corrected_count, terminalized_count,
                       uncached_input_token_delta, cached_input_token_delta,
                       reasoning_token_delta, output_token_delta
                FROM publication_deltas
                WHERE publication_id = ?
                """,
                (terminal_request.publication_id,),
            ).fetchone()
        ) == (0, 0, 1, 0, 0, 0, 0)
        assert tuple(
            connection.execute(
                """
                SELECT inserted_count, corrected_count, terminalized_count
                FROM publication_delta_entities
                WHERE publication_id = ? AND entity_kind = 'tool_invocations'
                """,
                (terminal_request.publication_id,),
            ).fetchone()
        ) == (0, 0, 1)
        declared_counts = {
            str(row[0]): int(row[1])
            for row in connection.execute(
                """
                SELECT entity_kind, entity_count
                FROM publication_entity_counts
                WHERE publication_id = ?
                """,
                (terminal_request.publication_id,),
            )
        }
        assert (
            declared_counts["tool_invocations"]
            == connection.execute("SELECT count(*) FROM tool_invocations").fetchone()[0]
        )
        assert (
            declared_counts["source_occurrences"]
            == connection.execute("SELECT count(*) FROM source_occurrences").fetchone()[0]
        )
        assert declared_counts["source_occurrences"] == 451
        validation = validate_open_artifact(
            connection,
            expected_publication_id=terminal_request.publication_id,
        )
        assert validation.identity.artifact_manifest_sha256 == (
            terminal_request.artifact_manifest_sha256
        )
    finally:
        connection.close()


def test_repeated_diagnostic_preserves_physical_source_coverage(
    tmp_path: Path,
) -> None:
    first_changes = _tiny_changes()
    first_request = _request("operation:diagnostic-base")
    first_plan = _plan(first_changes)
    first_write_set = prepare_write_set_from_changes(first_changes, first_request)
    first_request = replace(
        first_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            first_plan, first_request, first_write_set
        ),
    )
    diagnostic = first_changes.diagnostics[0]
    assert diagnostic.source_range is not None
    inventory = next(
        item
        for item in first_changes.selected_sources
        if item.manifestation_key == diagnostic.source_range.manifestation_key
    )
    repeated_changes = replace(
        first_changes,
        observations=(),
        occurrences=(),
        cursor_updates=(),
        diagnostics=(diagnostic,),
        selected_sources=(inventory,),
        deferred_sources=(),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        PublicationWriter(connection).publish(first_plan, first_request, first_write_set)
        prior = read_prior_publication_snapshot(connection, repeated_changes)
        assert len(prior.source_diagnostic_keys) == 1

        repeated_request = _request(
            "operation:diagnostic-repeat",
            parent_publication_id=first_request.publication_id,
            committed_at_us=first_request.committed_at_us + 1,
        )
        repeated_plan = _plan(
            repeated_changes,
            parent_publication_id=first_request.publication_id,
        )
        repeated_write_set = prepare_write_set_from_changes(
            repeated_changes,
            repeated_request,
            prior=prior,
        )
        repeated_request = replace(
            repeated_request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                repeated_plan,
                repeated_request,
                repeated_write_set,
            ),
        )
        PublicationWriter(connection).publish(
            repeated_plan,
            repeated_request,
            repeated_write_set,
        )

        assert connection.execute("SELECT count(*) FROM source_diagnostics").fetchone()[0] == 1
        assert (
            validate_open_artifact(
                connection,
                expected_publication_id=repeated_request.publication_id,
            ).identity.artifact_manifest_sha256
            == repeated_request.artifact_manifest_sha256
        )
    finally:
        connection.close()


def test_batched_writer_rejects_stable_identity_collision(
    tmp_path: Path,
) -> None:
    changes = _tiny_changes()
    first_request = _request("operation:identity-base")
    first_plan = _plan(changes)
    first_write_set = prepare_write_set_from_changes(changes, first_request)
    first_request = replace(
        first_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            first_plan, first_request, first_write_set
        ),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        PublicationWriter(connection).publish(first_plan, first_request, first_write_set)
        second_request = _request(
            "operation:identity-collision",
            parent_publication_id=first_request.publication_id,
            committed_at_us=first_request.committed_at_us + 1,
        )
        second_plan = _plan(changes, first_request.publication_id)
        prior = read_prior_publication_snapshot(connection, changes)
        second_write_set = replace(
            first_write_set,
            expected_source_revisions=prior.source_revisions,
        )
        collision_id = next(
            mutation for mutation in second_write_set.identities if mutation.entity_kind == "call"
        ).logical_id
        second_write_set = replace(
            second_write_set,
            identities=tuple(
                replace(
                    mutation,
                    identity_tuple=("synthetic-collision",),
                    enforce_semantic_id=False,
                )
                if mutation.logical_id == collision_id
                else mutation
                for mutation in second_write_set.identities
            ),
        )
        second_request = replace(
            second_request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                second_plan, second_request, second_write_set
            ),
        )

        with pytest.raises(PublicationWriteError, match="identity conflicts"):
            PublicationWriter(connection).publish(second_plan, second_request, second_write_set)

        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 1
        assert (
            connection.execute("SELECT publication_id FROM publication_head").fetchone()[0]
            == first_request.publication_id
        )
    finally:
        connection.close()


def test_no_change_does_not_begin_or_write_analytical_transaction(
    tmp_path: Path,
) -> None:
    changes = ingest(tmp_path, workers=1, batch_size=8).changes
    request = _request("operation:no-change")
    plan = PublicationPlan(
        OperationClass.NO_CHANGE,
        None,
        estimate_change_set(changes),
        ("no_source_changes",),
        False,
    )
    write_set = prepare_write_set_from_changes(changes, request)
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    statements: list[str] = []
    connection.set_trace_callback(statements.append)
    try:
        result = PublicationWriter(connection).publish(plan, request, write_set)
        assert result.no_change
        assert not any(statement == "BEGIN IMMEDIATE" for statement in statements)
        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 0
    finally:
        connection.close()


def test_foreign_key_failure_rolls_back_every_write(tmp_path: Path) -> None:
    changes = _tiny_changes()
    request = _request("operation:invalid")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )
    # Remove the session rows so calls/tools retain unresolved typed parents.
    broken = type(write_set)(
        changes=write_set.changes,
        identities=write_set.identities,
        rows=tuple(row for row in write_set.rows if row.table != "sessions"),
        lifecycle_transitions=write_set.lifecycle_transitions,
        tail_state=write_set.tail_state,
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        with pytest.raises((sqlite3.IntegrityError, RuntimeError)):
            PublicationWriter(connection).publish(plan, request, broken)
        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM publication_head").fetchone()[0] == 0
    finally:
        connection.close()


def test_short_writer_rejects_disabled_foreign_key_enforcement(
    tmp_path: Path,
) -> None:
    changes = _tiny_changes()
    request = _request("operation:foreign-keys-disabled")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(plan, request, write_set),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        with pytest.raises(RuntimeError, match="requires SQLite foreign-key enforcement"):
            PublicationWriter(connection).publish(plan, request, write_set)
        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 0
    finally:
        connection.close()


def test_manifest_mismatch_rolls_back_before_head_activation(tmp_path: Path) -> None:
    changes = _tiny_changes()
    request = _request("operation:bad-manifest")
    plan = _plan(changes)
    write_set = prepare_write_set_from_changes(changes, request)
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    try:
        with pytest.raises(RuntimeError, match="manifest differs"):
            PublicationWriter(connection).publish(plan, request, write_set)
        assert connection.execute("SELECT count(*) FROM publications").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM publication_head").fetchone()[0] == 0
    finally:
        connection.close()
