from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    AdapterAccounting,
    ProposedChangeSet,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.contracts import SourceState
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    RefreshIntent,
    estimate_change_set,
    plan_refresh,
)
from codex_usage_tracker.agent_kernel.publication.rate_cards import (
    attach_rate_card_frontier,
    prepare_rate_card_frontier,
    read_current_valuation_inputs,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
    read_prior_publication_snapshot,
)
from codex_usage_tracker.agent_kernel.storage.database import initialize_analytical
from tests.agent_kernel.fixtures.oracles.cases_v2 import build_question_scenarios
from tests.agent_kernel.fixtures.oracles.database_replay import (
    evaluate_published_question_case,
)
from tests.agent_kernel.fixtures.oracles.reference import evaluate_question_case
from tests.agent_kernel.fixtures.published_v2 import (
    PUBLICATION_ID,
    publish_structural_snapshot,
    published_question_case,
    rate_card_frontier,
    structural_records,
)

ROOT = Path(__file__).resolve().parents[2]
CATALOG = json.loads(
    (ROOT / "config/agent-kernel/question-catalog-v1.json").read_text(encoding="utf-8")
)


def test_real_publication_records_authoritative_capability_coverage(tmp_path) -> None:
    database_path = tmp_path / "database-v1.sqlite3"
    publish_structural_snapshot(tmp_path / "fixture", database_path)
    connection = sqlite3.connect(database_path)
    rows = connection.execute(
        """
        SELECT capability_id, eligible_entity_count, observed_entity_count,
               unavailable_entity_count, grade
        FROM publication_capability_coverage
        WHERE publication_id = ?
        ORDER BY capability_id
        """,
        (PUBLICATION_ID,),
    ).fetchall()
    assert rows == [
        ("context_components", 2, 2, 0, "exact"),
        ("valuation", 3, 3, 0, "configured_estimate"),
    ]


def test_all_80_cases_replay_through_real_ingestion_and_publication(
    tmp_path,
) -> None:
    questions = {question["question_id"]: question for question in CATALOG["questions"]}
    comparisons = []
    for index, original in enumerate(build_question_scenarios()["cases"]):
        profile = original["source_profile"]
        mutation = original["semantic_mutation"]
        case_root = tmp_path / f"case-{index:02d}"
        database_path = case_root / "database-v1.sqlite3"
        publish_structural_snapshot(
            case_root / "fixture",
            database_path,
            include_late_call=profile["late_event"],
            null_cached_tokens=profile["missing_cached_input"],
            variant_native_turn_id=mutation["native_turn_id"],
        )
        connection = sqlite3.connect(database_path)
        case = published_question_case(connection, original)
        question = questions[case["question_id"]]
        expected = evaluate_question_case(case, question)
        connection.execute("PRAGMA query_only = ON")
        actual = evaluate_published_question_case(
            connection,
            case["request"],
            case["required_evidence"],
            question,
            oracle_id=case["oracle_id"],
            variant=case["variant"],
        )
        connection.close()
        assert expected == actual, case["oracle_id"]
        comparisons.append(actual["comparison_digest"])

    assert len(comparisons) == 80
    assert len(set(comparisons)) == 80


def test_rebuild_replacement_and_late_event_keep_existing_identity_provenance(
    tmp_path,
) -> None:
    fixture = tmp_path / "fixture"
    fixture.mkdir()

    def write_records(*, late: bool) -> None:
        payload = b"".join(
            json.dumps(
                record,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
            for record in structural_records(include_late_call=late)
        )
        (fixture / "source.jsonl").write_bytes(payload)

    write_records(late=False)
    changes = ingest(fixture, workers=1, batch_size=32).changes
    empty_changes = ProposedChangeSet(
        observations=(),
        occurrences=(),
        diagnostics=(),
        cursor_updates=(),
        accounting=AdapterAccounting({}, {}, {}),
        selected_sources=(),
        deferred_sources=(),
    )
    replacement_full = replace(
        changes,
        selected_sources=tuple(
            replace(source, state=SourceState.REPLACED) for source in changes.selected_sources
        ),
    )
    replacement = replace(
        empty_changes,
        selected_sources=tuple(
            replace(source, state=SourceState.REPLACED) for source in changes.selected_sources
        ),
    )
    plan = plan_refresh(
        replacement_full,
        RefreshIntent(
            parent_publication_id=PUBLICATION_ID,
            parent_observed_at_us=600,
            planned_at_us=601,
            history_preset="all_time",
            current_history_preset="all_time",
        ),
    )
    assert plan.operation_class is OperationClass.SOURCE_REPLACE

    connection = initialize_analytical(tmp_path / "stateful.sqlite3")
    frontier = rate_card_frontier()

    def prepare_step(
        publication_id: str,
        *,
        parent_publication_id: str | None,
        committed_at_us: int,
        step_changes,
        operation_class: OperationClass,
    ):
        request = PublicationRequest(
            publication_id=publication_id,
            parent_publication_id=parent_publication_id,
            operation_id=f"operation:{publication_id}",
            committed_at_us=committed_at_us,
            history_preset="all_time",
            artifact_manifest_sha256="0" * 64,
            observed_through_us=500,
            indexed_from_us=50,
            indexed_through_us=500,
            guaranteed_complete_from_us=50,
            rate_card_digest=frontier.head_digest,
        )
        prior = (
            None
            if parent_publication_id is None
            else read_prior_publication_snapshot(connection, step_changes)
        )
        prepared = prepare_rate_card_frontier(
            frontier,
            publication_id=publication_id,
            previous=None if prior is None else prior.rate_card_frontier,
        )
        base_write_set = prepare_write_set_from_changes(
            step_changes,
            request,
            prior=prior,
        )
        write_set = attach_rate_card_frontier(
            base_write_set,
            request,
            prepared,
            current_inputs=(
                None if prior is None else read_current_valuation_inputs(connection, base_write_set)
            ),
        )
        publication_plan = PublicationPlan(
            operation_class,
            parent_publication_id,
            estimate_change_set(
                step_changes,
                dirty_keys=len(prepared.dirty_intervals),
            ),
            (f"stateful_{publication_id}",),
            True,
            prepared.dirty_intervals,
        )
        request = replace(
            request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                publication_plan,
                request,
                write_set,
            ),
        )
        return publication_plan, request, write_set

    initial_plan, initial_request, initial_write_set = prepare_step(
        "publication:stateful-initial",
        parent_publication_id=None,
        committed_at_us=600,
        step_changes=changes,
        operation_class=OperationClass.APPEND_SAFE_SMALL,
    )
    PublicationWriter(connection).publish(
        initial_plan,
        initial_request,
        initial_write_set,
    )
    initial_ids = {
        row[0]
        for row in connection.execute("SELECT call_id FROM model_calls_visible ORDER BY call_id")
    }

    rebuild_plan, rebuild_request, rebuild_write_set = prepare_step(
        "publication:stateful-rebuild",
        parent_publication_id=initial_request.publication_id,
        committed_at_us=700,
        step_changes=empty_changes,
        operation_class=OperationClass.APPEND_SAFE_SMALL,
    )
    PublicationWriter(connection).publish(
        rebuild_plan,
        rebuild_request,
        rebuild_write_set,
    )
    assert {
        row[0] for row in connection.execute("SELECT call_id FROM model_calls_visible")
    } == initial_ids

    replacement_plan, replacement_request, replacement_write_set = prepare_step(
        "publication:stateful-replacement",
        parent_publication_id=rebuild_request.publication_id,
        committed_at_us=800,
        step_changes=replacement,
        operation_class=OperationClass.APPEND_SAFE_SMALL,
    )
    PublicationWriter(connection).publish(
        replacement_plan,
        replacement_request,
        replacement_write_set,
    )
    assert (
        connection.execute(
            "SELECT publication_id FROM publication_head WHERE singleton = 1"
        ).fetchone()[0]
        == replacement_request.publication_id
    )
    assert (
        connection.execute(
            "SELECT state FROM source_manifestations ORDER BY manifestation_id LIMIT 1"
        ).fetchone()[0]
        == SourceState.REPLACED.value
    )

    write_records(late=True)
    full_late_changes = ingest(fixture, workers=1, batch_size=32).changes
    existing_logical_ids = {observation.logical_id for observation in changes.observations}
    late_observations = tuple(
        observation
        for observation in full_late_changes.observations
        if observation.logical_id not in existing_logical_ids
    )
    late_ids = {observation.logical_id for observation in late_observations}
    late_changes = replace(
        full_late_changes,
        observations=late_observations,
        occurrences=tuple(
            occurrence
            for occurrence in full_late_changes.occurrences
            if occurrence.semantic_logical_id in late_ids
        ),
    )
    late_plan, late_request, late_write_set = prepare_step(
        "publication:stateful-late",
        parent_publication_id=replacement_request.publication_id,
        committed_at_us=900,
        step_changes=late_changes,
        operation_class=OperationClass.APPEND_SAFE_SMALL,
    )

    def interrupt_after_metadata(stage: str) -> None:
        if stage == "after_metadata":
            raise RuntimeError("synthetic stateful interruption")

    with pytest.raises(RuntimeError, match="stateful interruption"):
        PublicationWriter(connection).publish(
            late_plan,
            late_request,
            late_write_set,
            fault_injector=interrupt_after_metadata,
        )
    assert (
        connection.execute(
            "SELECT publication_id FROM publication_head WHERE singleton = 1"
        ).fetchone()[0]
        == replacement_request.publication_id
    )
    PublicationWriter(connection).publish(late_plan, late_request, late_write_set)
    assert (
        connection.execute(
            "SELECT publication_id FROM publication_head WHERE singleton = 1"
        ).fetchone()[0]
        == late_request.publication_id
    )
    assert {
        row[0] for row in connection.execute("SELECT call_id FROM model_calls_visible")
    }.issuperset(initial_ids)
    assert (
        connection.execute("SELECT COUNT(*) FROM model_calls_visible").fetchone()[0]
        == len(initial_ids) + 1
    )
    connection.close()
