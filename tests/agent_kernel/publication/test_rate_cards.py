from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    AdapterAccounting,
    ProposedChangeSet,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.contracts import SourceState
from codex_usage_tracker.agent_kernel.domain.identity import semantic_id
from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    ValuationDirtyInterval,
)
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    RefreshIntent,
    estimate_change_set,
    plan_refresh,
)
from codex_usage_tracker.agent_kernel.publication.rate_cards import (
    PreparedRateCardFrontier,
    attach_rate_card_frontier,
    prepare_rate_card_frontier,
    read_current_valuation_inputs,
)
from codex_usage_tracker.agent_kernel.publication.validation import (
    PublicationValidationError,
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
from codex_usage_tracker.agent_kernel.storage.rate_cards import (
    load_publication_rate_card_frontier,
)

_FIXTURE = Path(__file__).parents[1] / "fixtures" / "tiny-v1"
_RULE = {"model_profile_id": "profile:synthetic"}
_RATES = {
    "uncached_input_tokens": "1",
    "cached_input_tokens": "0.5",
    "reasoning_tokens": "2",
    "output_tokens": "3",
}


def _empty_changes() -> ProposedChangeSet:
    return ProposedChangeSet(
        observations=(),
        occurrences=(),
        diagnostics=(),
        cursor_updates=(),
        accounting=AdapterAccounting({}, {}, {}),
        selected_sources=(),
        deferred_sources=(),
    )


def _revision(
    digit: str,
    *,
    predecessor_digest: str | None,
    effective_at_us: int,
    fetched_at_us: int,
) -> RateCardRevision:
    digest = digit * 64
    return RateCardRevision(
        rate_card_id=semantic_id("rate-card", [digest]),
        digest=digest,
        predecessor_digest=predecessor_digest,
        effective_at_us=effective_at_us,
        fetched_at_us=fetched_at_us,
        source_name="synthetic-rate-card",
        source_url=None,
        currency="USD",
        model_match_rules=(_RULE,),
        four_class_rates=_RATES,
        credit_rates={},
        reasoning_in_output=False,
        confidence="high",
        validation_status="valid",
    )


def _request(
    publication_id: str,
    *,
    parent_publication_id: str | None,
    digest: str,
    committed_at_us: int,
) -> PublicationRequest:
    return PublicationRequest(
        publication_id=publication_id,
        operation_id=f"operation:{publication_id}",
        committed_at_us=committed_at_us,
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        parent_publication_id=parent_publication_id,
        rate_card_digest=digest,
    )


def test_frontier_preparation_is_immutable_and_dirties_only_affected_interval() -> None:
    old = _revision(
        "1",
        predecessor_digest=None,
        effective_at_us=100,
        fetched_at_us=1_000,
    )
    later = _revision(
        "2",
        predecessor_digest=old.digest,
        effective_at_us=500,
        fetched_at_us=5_000,
    )
    previous = RateCardFrontier(later.digest, (later, old))
    correction = _revision(
        "3",
        predecessor_digest=later.digest,
        effective_at_us=300,
        fetched_at_us=9_000,
    )
    current = RateCardFrontier(correction.digest, (correction, later, old))

    prepared = prepare_rate_card_frontier(
        current,
        publication_id="publication:correction",
        previous=previous,
    )

    assert tuple(identity.logical_id for identity in prepared.identities) == (
        correction.rate_card_id,
    )
    assert tuple(row.values["digest"] for row in prepared.rows) == (correction.digest,)
    assert prepared.dirty_intervals == (
        ValuationDirtyInterval(
            revision_digest=correction.digest,
            effective_at_us=300,
            next_effective_at_us=500,
            model_match_rules=(_RULE,),
        ),
    )

    mutated_old = replace(old, fetched_at_us=9_999)
    with pytest.raises(ValueError, match="immutable"):
        prepare_rate_card_frontier(
            RateCardFrontier(correction.digest, (correction, later, mutated_old)),
            publication_id="publication:invalid",
            previous=previous,
        )

    ambiguous = _revision(
        "4",
        predecessor_digest=correction.digest,
        effective_at_us=later.effective_at_us,
        fetched_at_us=10_000,
    )
    with pytest.raises(ValueError, match="ambiguous_rate_card_match"):
        prepare_rate_card_frontier(
            RateCardFrontier(
                ambiguous.digest,
                (ambiguous, correction, later, old),
            ),
            publication_id="publication:ambiguous",
            previous=current,
        )


def test_writer_rejects_ambiguous_frontier_and_preserves_active_head(
    tmp_path: Path,
) -> None:
    changes = ingest(
        _FIXTURE,
        manifest=_FIXTURE / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    old = _revision(
        "1",
        predecessor_digest=None,
        effective_at_us=100,
        fetched_at_us=1_000,
    )
    first_frontier = RateCardFrontier(old.digest, (old,))
    first_request = _request(
        "publication:first",
        parent_publication_id=None,
        digest=old.digest,
        committed_at_us=2_000,
    )
    first_prepared = prepare_rate_card_frontier(
        first_frontier,
        publication_id=first_request.publication_id,
    )
    first_write_set = attach_rate_card_frontier(
        prepare_write_set_from_changes(changes, first_request),
        first_request,
        first_prepared,
    )
    first_plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        None,
        estimate_change_set(changes, dirty_keys=1),
        ("initial_isolated_publication",),
        True,
        first_prepared.dirty_intervals,
    )
    first_request = replace(
        first_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            first_plan,
            first_request,
            first_write_set,
        ),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    PublicationWriter(connection).publish(first_plan, first_request, first_write_set)

    first_same_time = _revision(
        "2",
        predecessor_digest=old.digest,
        effective_at_us=500,
        fetched_at_us=3_000,
    )
    second_valid = _revision(
        "3",
        predecessor_digest=first_same_time.digest,
        effective_at_us=501,
        fetched_at_us=4_000,
    )
    prepared_first = prepare_rate_card_frontier(
        RateCardFrontier(
            first_same_time.digest,
            (first_same_time, old),
        ),
        publication_id="publication:ambiguous",
        previous=first_frontier,
    )
    prepared_second = prepare_rate_card_frontier(
        RateCardFrontier(
            second_valid.digest,
            (second_valid, first_same_time, old),
        ),
        publication_id="publication:ambiguous",
        previous=RateCardFrontier(
            first_same_time.digest,
            (first_same_time, old),
        ),
    )
    second_ambiguous = replace(second_valid, effective_at_us=500)
    forged_second_row = replace(
        prepared_second.rows[0],
        values={
            **prepared_second.rows[0].values,
            "effective_at_us": second_ambiguous.effective_at_us,
        },
    )
    forged = PreparedRateCardFrontier(
        frontier=RateCardFrontier(
            second_ambiguous.digest,
            (second_ambiguous, first_same_time, old),
        ),
        identities=(*prepared_first.identities, *prepared_second.identities),
        rows=(*prepared_first.rows, forged_second_row),
        dirty_intervals=(),
    )
    request = _request(
        "publication:ambiguous",
        parent_publication_id=first_request.publication_id,
        digest=second_ambiguous.digest,
        committed_at_us=5_000,
    )
    prior = read_prior_publication_snapshot(connection, _empty_changes())
    write_set_without_frontier = prepare_write_set_from_changes(
        _empty_changes(),
        request,
        prior=prior,
    )
    write_set = attach_rate_card_frontier(
        write_set_without_frontier,
        request,
        forged,
        current_inputs=read_current_valuation_inputs(
            connection,
            write_set_without_frontier,
        ),
    )
    plan = PublicationPlan(
        OperationClass.VALUATION_ONLY,
        first_request.publication_id,
        estimate_change_set(_empty_changes()),
        ("rate_card_changed",),
        True,
    )
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            plan,
            request,
            write_set,
        ),
    )

    with pytest.raises(
        PublicationWriteError,
        match="ambiguous_rate_card_match",
    ):
        PublicationWriter(connection).publish(plan, request, write_set)
    assert connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM rate_card_revisions").fetchone()[0] == 1
    assert (
        connection.execute(
            """
        SELECT revision.digest
        FROM active_rate_card AS active
        JOIN rate_card_revisions AS revision
          ON revision.rate_card_id = active.rate_card_id
        """
        ).fetchone()[0]
        == old.digest
    )
    connection.close()


def test_rebuild_replacement_and_late_event_recovery_preserve_frontier(
    tmp_path: Path,
) -> None:
    changes = ingest(
        _FIXTURE,
        manifest=_FIXTURE / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    revision = _revision(
        "1",
        predecessor_digest=None,
        effective_at_us=100,
        fetched_at_us=1_000,
    )
    frontier = RateCardFrontier(revision.digest, (revision,))

    def publish_initial(path: Path, initial_changes: ProposedChangeSet):
        request = _request(
            "publication:initial",
            parent_publication_id=None,
            digest=revision.digest,
            committed_at_us=2_000,
        )
        prepared = prepare_rate_card_frontier(
            frontier,
            publication_id=request.publication_id,
        )
        write_set = attach_rate_card_frontier(
            prepare_write_set_from_changes(initial_changes, request),
            request,
            prepared,
        )
        plan = PublicationPlan(
            OperationClass.APPEND_SAFE_SMALL,
            None,
            estimate_change_set(
                initial_changes,
                dirty_keys=len(prepared.dirty_intervals),
            ),
            ("initial_isolated_publication",),
            True,
            prepared.dirty_intervals,
        )
        request = replace(
            request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                plan,
                request,
                write_set,
            ),
        )
        connection = initialize_analytical(path)
        PublicationWriter(connection).publish(plan, request, write_set)
        return connection, request

    replacement_changes = replace(
        changes,
        selected_sources=tuple(
            replace(source, state=SourceState.REPLACED) for source in changes.selected_sources
        ),
    )
    replacement_plan = plan_refresh(
        replacement_changes,
        RefreshIntent(
            parent_publication_id="publication:prior",
            parent_observed_at_us=1,
            planned_at_us=2,
            history_preset="all_time",
            current_history_preset="all_time",
        ),
    )
    assert replacement_plan.operation_class is OperationClass.SOURCE_REPLACE
    rebuilt, rebuilt_request = publish_initial(
        tmp_path / "replacement-rebuild.sqlite3",
        replacement_changes,
    )
    validate_open_artifact(
        rebuilt,
        expected_publication_id=rebuilt_request.publication_id,
    )
    assert (
        load_publication_rate_card_frontier(
            rebuilt,
            rebuilt_request.publication_id,
        )
        == frontier
    )
    rebuilt.close()

    connection, first_request = publish_initial(
        tmp_path / "late-event.sqlite3",
        _empty_changes(),
    )
    prior = read_prior_publication_snapshot(connection, changes)
    late_request = _request(
        "publication:late-event",
        parent_publication_id=first_request.publication_id,
        digest=revision.digest,
        committed_at_us=3_000,
    )
    unchanged = prepare_rate_card_frontier(
        frontier,
        publication_id=late_request.publication_id,
        previous=prior.rate_card_frontier,
    )
    late_write_set_without_frontier = prepare_write_set_from_changes(
        changes,
        late_request,
        prior=prior,
    )
    late_write_set = attach_rate_card_frontier(
        late_write_set_without_frontier,
        late_request,
        unchanged,
        current_inputs=read_current_valuation_inputs(
            connection,
            late_write_set_without_frontier,
        ),
    )
    late_plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        first_request.publication_id,
        estimate_change_set(changes),
        ("late_event_recovery",),
        True,
    )
    late_request = replace(
        late_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            late_plan,
            late_request,
            late_write_set,
        ),
    )

    def crash_after_metadata(stage: str) -> None:
        if stage == "after_metadata":
            raise RuntimeError("synthetic late-event crash")

    with pytest.raises(RuntimeError, match="synthetic late-event crash"):
        PublicationWriter(connection).publish(
            late_plan,
            late_request,
            late_write_set,
            fault_injector=crash_after_metadata,
        )
    assert connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1
    PublicationWriter(connection).publish(late_plan, late_request, late_write_set)
    validate_open_artifact(
        connection,
        expected_publication_id=late_request.publication_id,
    )
    assert (
        load_publication_rate_card_frontier(
            connection,
            late_request.publication_id,
        )
        == frontier
    )
    active = connection.execute(
        """
        SELECT revision.digest, active.selected_at_us
        FROM active_rate_card AS active
        JOIN rate_card_revisions AS revision
          ON revision.rate_card_id = active.rate_card_id
        """
    ).fetchone()
    assert tuple(active) == (revision.digest, first_request.committed_at_us)
    connection.close()


def test_publication_frontier_is_atomic_reproducible_and_recovery_safe(
    tmp_path: Path,
) -> None:
    changes = ingest(
        _FIXTURE,
        manifest=_FIXTURE / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    old = _revision(
        "1",
        predecessor_digest=None,
        effective_at_us=100,
        fetched_at_us=1_000,
    )
    later = _revision(
        "2",
        predecessor_digest=old.digest,
        effective_at_us=500,
        fetched_at_us=5_000,
    )
    initial_frontier = RateCardFrontier(later.digest, (later, old))
    first_request = _request(
        "publication:first",
        parent_publication_id=None,
        digest=later.digest,
        committed_at_us=6_000,
    )
    first_prepared = prepare_rate_card_frontier(
        initial_frontier,
        publication_id=first_request.publication_id,
    )
    first_write_set = attach_rate_card_frontier(
        prepare_write_set_from_changes(changes, first_request),
        first_request,
        first_prepared,
    )
    first_plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        None,
        estimate_change_set(changes, dirty_keys=len(first_prepared.dirty_intervals)),
        ("initial_isolated_publication",),
        True,
        first_prepared.dirty_intervals,
    )
    first_request = replace(
        first_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            first_plan,
            first_request,
            first_write_set,
        ),
    )

    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    PublicationWriter(connection).publish(first_plan, first_request, first_write_set)
    validate_open_artifact(
        connection,
        expected_publication_id=first_request.publication_id,
    )

    prior = read_prior_publication_snapshot(connection, _empty_changes())
    assert prior.rate_card_frontier == initial_frontier
    correction = _revision(
        "3",
        predecessor_digest=later.digest,
        effective_at_us=300,
        fetched_at_us=9_000,
    )
    corrected_frontier = RateCardFrontier(
        correction.digest,
        (correction, later, old),
    )
    second_request = _request(
        "publication:correction",
        parent_publication_id=first_request.publication_id,
        digest=correction.digest,
        committed_at_us=10_000,
    )
    second_prepared = prepare_rate_card_frontier(
        corrected_frontier,
        publication_id=second_request.publication_id,
        previous=prior.rate_card_frontier,
    )
    second_write_set_without_frontier = prepare_write_set_from_changes(
        _empty_changes(),
        second_request,
        prior=prior,
    )
    with pytest.raises(
        ValueError,
        match="require complete current valuation inputs",
    ):
        attach_rate_card_frontier(
            second_write_set_without_frontier,
            second_request,
            second_prepared,
        )
    second_inputs = read_current_valuation_inputs(
        connection,
        second_write_set_without_frontier,
    )
    second_write_set = attach_rate_card_frontier(
        second_write_set_without_frontier,
        second_request,
        second_prepared,
        current_inputs=second_inputs,
    )
    second_plan = PublicationPlan(
        OperationClass.VALUATION_ONLY,
        first_request.publication_id,
        estimate_change_set(
            _empty_changes(),
            dirty_keys=len(second_prepared.dirty_intervals),
        ),
        ("rate_card_changed",),
        True,
        second_prepared.dirty_intervals,
    )
    second_request = replace(
        second_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            second_plan,
            second_request,
            second_write_set,
        ),
    )

    def crash_after_metadata(stage: str) -> None:
        if stage == "after_metadata":
            raise RuntimeError("synthetic rate-card crash")

    with pytest.raises(RuntimeError, match="synthetic rate-card crash"):
        PublicationWriter(connection).publish(
            second_plan,
            second_request,
            second_write_set,
            fault_injector=crash_after_metadata,
        )
    assert connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM rate_card_revisions").fetchone()[0] == 2
    assert (
        connection.execute(
            """
        SELECT revision.digest
        FROM active_rate_card AS active
        JOIN rate_card_revisions AS revision
          ON revision.rate_card_id = active.rate_card_id
        """
        ).fetchone()[0]
        == later.digest
    )

    PublicationWriter(connection).publish(second_plan, second_request, second_write_set)
    valuation_coverage = connection.execute(
        """
        SELECT eligible_entity_count, observed_entity_count,
               unavailable_entity_count, basis
          FROM publication_capability_coverage
         WHERE publication_id = ? AND capability_id = 'valuation'
        """,
        (second_request.publication_id,),
    ).fetchone()
    assert valuation_coverage is not None
    assert valuation_coverage[0] == len(second_inputs.calls)
    assert valuation_coverage[1] + valuation_coverage[2] == len(second_inputs.calls)
    assert valuation_coverage[3] == "effective_dated_frontier_recompile_v1"
    validate_open_artifact(
        connection,
        expected_publication_id=second_request.publication_id,
    )
    assert (
        load_publication_rate_card_frontier(
            connection,
            first_request.publication_id,
        )
        == initial_frontier
    )
    assert (
        load_publication_rate_card_frontier(
            connection,
            second_request.publication_id,
        )
        == corrected_frontier
    )
    active = connection.execute(
        """
        SELECT revision.digest, active.selected_at_us, active.publication_id
        FROM active_rate_card AS active
        JOIN rate_card_revisions AS revision
          ON revision.rate_card_id = active.rate_card_id
        """
    ).fetchone()
    assert tuple(active) == (
        correction.digest,
        second_request.committed_at_us,
        second_request.publication_id,
    )

    current = read_prior_publication_snapshot(connection, _empty_changes())
    third_request = _request(
        "publication:tail",
        parent_publication_id=second_request.publication_id,
        digest=correction.digest,
        committed_at_us=11_000,
    )
    unchanged_prepared = prepare_rate_card_frontier(
        corrected_frontier,
        publication_id=third_request.publication_id,
        previous=current.rate_card_frontier,
    )
    assert unchanged_prepared.rows == ()
    assert unchanged_prepared.dirty_intervals == ()
    third_write_set_without_frontier = prepare_write_set_from_changes(
        _empty_changes(),
        third_request,
        prior=current,
    )
    third_write_set = attach_rate_card_frontier(
        third_write_set_without_frontier,
        third_request,
        unchanged_prepared,
        current_inputs=read_current_valuation_inputs(
            connection,
            third_write_set_without_frontier,
        ),
    )
    third_plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        second_request.publication_id,
        estimate_change_set(_empty_changes()),
        ("synthetic_tail_metadata",),
        True,
    )
    third_request = replace(
        third_request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            third_plan,
            third_request,
            third_write_set,
        ),
    )
    PublicationWriter(connection).publish(third_plan, third_request, third_write_set)
    validate_open_artifact(
        connection,
        expected_publication_id=third_request.publication_id,
    )
    unchanged_active = connection.execute(
        """
        SELECT revision.digest, active.selected_at_us, active.publication_id
        FROM active_rate_card AS active
        JOIN rate_card_revisions AS revision
          ON revision.rate_card_id = active.rate_card_id
        """
    ).fetchone()
    assert tuple(unchanged_active) == (
        correction.digest,
        second_request.committed_at_us,
        third_request.publication_id,
    )
    assert connection.execute("SELECT COUNT(*) FROM rate_card_revisions").fetchone()[0] == 3

    no_change_plan = PublicationPlan(
        OperationClass.NO_CHANGE,
        third_request.publication_id,
        estimate_change_set(_empty_changes()),
        ("source_revisions_and_compatibility_unchanged",),
        False,
    )
    no_change_request = _request(
        "publication:not-written",
        parent_publication_id=third_request.publication_id,
        digest=correction.digest,
        committed_at_us=12_000,
    )
    no_change_write_set = prepare_write_set_from_changes(
        _empty_changes(),
        no_change_request,
    )
    no_change_result = PublicationWriter(connection).publish(
        no_change_plan,
        no_change_request,
        no_change_write_set,
    )
    assert no_change_result.no_change
    assert no_change_result.publication_id == third_request.publication_id
    assert connection.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 3
    connection.close()


def test_publication_validation_rejects_active_head_mismatch(tmp_path: Path) -> None:
    changes = ingest(
        _FIXTURE,
        manifest=_FIXTURE / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    revision = _revision(
        "1",
        predecessor_digest=None,
        effective_at_us=100,
        fetched_at_us=1_000,
    )
    frontier = RateCardFrontier(revision.digest, (revision,))
    request = _request(
        "publication:head",
        parent_publication_id=None,
        digest=revision.digest,
        committed_at_us=2_000,
    )
    prepared = prepare_rate_card_frontier(
        frontier,
        publication_id=request.publication_id,
    )
    write_set = attach_rate_card_frontier(
        prepare_write_set_from_changes(changes, request),
        request,
        prepared,
    )
    plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        None,
        estimate_change_set(changes, dirty_keys=1),
        ("initial_isolated_publication",),
        True,
        prepared.dirty_intervals,
    )
    request = replace(
        request,
        artifact_manifest_sha256=planned_artifact_manifest_sha256(
            plan,
            request,
            write_set,
        ),
    )
    connection = initialize_analytical(tmp_path / "analytical.sqlite3")
    PublicationWriter(connection).publish(plan, request, write_set)
    connection.execute(
        "UPDATE publications SET rate_card_digest = ? WHERE publication_id = ?",
        ("2" * 64, request.publication_id),
    )
    connection.commit()
    with pytest.raises(
        PublicationValidationError,
        match="rate-card frontier invalid",
    ):
        validate_open_artifact(connection)
    connection.close()


def test_planner_carries_exact_valuation_dirty_interval() -> None:
    interval = ValuationDirtyInterval(
        revision_digest="3" * 64,
        effective_at_us=300,
        next_effective_at_us=500,
        model_match_rules=(_RULE,),
    )
    intent = RefreshIntent(
        parent_publication_id="publication:prior",
        parent_observed_at_us=1,
        planned_at_us=2,
        history_preset="all_time",
        current_history_preset="all_time",
        rate_card_changed=True,
        valuation_dirty_intervals=(interval,),
    )

    plan = plan_refresh(_empty_changes(), intent, dirty_keys=1)

    assert plan.operation_class is OperationClass.VALUATION_ONLY
    assert plan.is_small
    assert plan.valuation_dirty_intervals == (interval,)
    with pytest.raises(ValueError, match="dirty-key estimate"):
        plan_refresh(_empty_changes(), intent, dirty_keys=0)
