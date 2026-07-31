from __future__ import annotations

import ast
import sqlite3
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.domain.valuation import (
    RateCardFrontier,
    RateCardRevision,
    derive_frontier_dirty_intervals,
)
from tests.agent_kernel.fact_adapters.database import (
    DatabaseAdapterContractError,
    DatabaseV1FactAdapter,
)
from tests.agent_kernel.fact_adapters.reference import (
    StructuralReferenceAdapterError,
    StructuralReferenceFactAdapter,
)
from tests.agent_kernel.fact_adapters.support import (
    HEAD_DIGEST,
    OLD_DIGEST,
    adapter_request,
    build_query_only_database,
    build_structural_v2,
    emitted_structural_jsonl,
    normalize_materialization,
    plan_contract,
    required_references,
    selector_contract,
)

PACKAGE = Path(__file__).resolve().parent
PLAN_RELATIONS = {
    source["relation"] for plan in plan_contract()["plans"] for source in plan["permitted_sources"]
}
SELECTOR_KINDS = {
    "allowance_interval",
    "allowance_observation",
    "call",
    "model_profile",
    "project",
    "publication",
    "rate_card",
    "resource",
    "session",
    "source_manifestation",
    "state_change",
    "tool",
    "turn",
    "window",
}
PROVENANCE_KINDS = {
    "configured_artifact",
    "derived_boundary_pair",
    "publication_commit",
    "request_derivation",
    "source_inventory",
    "source_occurrence",
}


def _references(request, *, window: bool) -> tuple[dict[str, str], ...]:
    references = [
        dict(item) for item in required_references(request=request, include_window=window)
    ]
    if window:
        # The selector is a pure request derivation and is intentionally not
        # declared as a scenario/database entity.
        pass
    return tuple(references)


def _materialize_pair(
    declaration,
    *,
    plan_id: str = "current_usage",
    window: bool = True,
):
    contract = plan_contract()
    selectors = selector_contract()
    request = adapter_request(plan_id, with_window=window)
    evidence = _references(request, window=window)
    reference = StructuralReferenceFactAdapter(contract, selectors).materialize(
        declaration,
        request,
        evidence,
    )
    connection = build_query_only_database(declaration)
    database = DatabaseV1FactAdapter(contract, selectors, evidence).materialize(
        connection,
        request,
        evidence,
    )
    return reference, database


def test_current_usage_facts_request_and_evidence_are_equivalent() -> None:
    reference, database = _materialize_pair(build_structural_v2())

    assert normalize_materialization(reference) == normalize_materialization(database)
    assert len(reference.evidence_references) == len(SELECTOR_KINDS)
    assert {item.selector_kind for item in reference.evidence_references} == SELECTOR_KINDS
    assert {item.provenance_kind for item in reference.evidence_references} == PROVENANCE_KINDS


def test_every_plan_relation_is_selected_independently() -> None:
    declaration = build_structural_v2()
    reference_relations: set[str] = set()
    database_relations: set[str] = set()

    for plan in plan_contract()["plans"]:
        plan_id = plan["plan_id"]
        reference, database = _materialize_pair(
            declaration,
            plan_id=plan_id,
        )
        reference_facts = {(fact.relation, fact.logical_id): fact for fact in reference.facts}
        database_facts = {(fact.relation, fact.logical_id): fact for fact in database.facts}
        assert set(reference_facts) == set(database_facts), plan_id
        reference_relations.update(fact.relation for fact in reference.facts)
        database_relations.update(fact.relation for fact in database.facts)

    assert reference_relations == database_relations == PLAN_RELATIONS
    assert len(PLAN_RELATIONS) == 16


@pytest.mark.parametrize(
    "plan_id",
    ["allowance_interval_events", "latest_publication_delta"],
)
def test_owner_specific_no_window_plans_do_not_fabricate_windows(plan_id: str) -> None:
    reference, database = _materialize_pair(
        build_structural_v2(),
        plan_id=plan_id,
        window=False,
    )

    assert "window" not in reference.request.parameters
    assert "window" not in database.request.parameters
    assert all(item.selector_kind != "window" for item in reference.evidence_references)
    assert all(item.selector_kind != "window" for item in database.evidence_references)


@pytest.mark.parametrize(
    ("lifecycle", "include_late_call"),
    [
        ("initial", False),
        ("rebuild", False),
        ("replacement", False),
        ("late_event", True),
    ],
)
def test_rebuild_replacement_and_late_event_preserve_parity(
    lifecycle: str,
    include_late_call: bool,
) -> None:
    declaration = build_structural_v2(
        lifecycle=lifecycle,
        include_late_call=include_late_call,
    )
    reference, database = _materialize_pair(
        declaration,
        plan_id="dedup_source_audit",
    )

    assert normalize_materialization(reference) == normalize_materialization(database)
    assert [
        (item.role, item.selector_kind, item.selector) for item in reference.evidence_references
    ] == [(item.role, item.selector_kind, item.selector) for item in database.evidence_references]


def test_effective_dated_selection_and_typed_missingness_reconcile() -> None:
    reference, database = _materialize_pair(
        build_structural_v2(
            include_late_call=True,
            null_cached_tokens=True,
        ),
        plan_id="pricing_coverage",
        window=False,
    )
    normalized_reference = normalize_materialization(reference)
    normalized_database = normalize_materialization(database)
    assert normalized_reference == normalized_database

    matches = {
        fact.values["call_id"]: fact
        for fact in reference.facts
        if fact.relation == "valuation_match"
    }
    assert matches["call:before"].values["rate_card_digest"] == OLD_DIGEST
    assert matches["call:late"].values["rate_card_digest"] == OLD_DIGEST
    assert matches["call:boundary"].values["rate_card_digest"] == HEAD_DIGEST
    assert matches["call:boundary"].values["match_basis"] == "model_alias"
    assert matches["call:other"].values["rate_card_digest"] == OLD_DIGEST
    assert matches["call:before"].values["cost_unpriced_reason"] == "missing_measurement"


def test_same_time_exact_profile_precedes_alias_in_both_adapters() -> None:
    declaration = build_structural_v2()
    declaration["rate_card_frontier"]["revisions"][-1]["model_match_rules"].insert(
        0,
        {
            "model_profile_id": "profile:alpha",
            "match_basis": "exact_model_profile",
        },
    )
    reference, database = _materialize_pair(declaration)
    assert normalize_materialization(reference) == normalize_materialization(database)
    boundary = next(
        fact
        for fact in reference.facts
        if fact.relation == "valuation_match" and fact.values["call_id"] == "call:boundary"
    )
    assert boundary.values["match_basis"] == "exact_model_profile"


def test_backdated_revision_has_one_bounded_dirty_interval() -> None:
    declaration = build_structural_v2()

    def revision(value) -> RateCardRevision:
        return RateCardRevision(**value)

    old = revision(declaration["rate_card_frontier"]["revisions"][0])
    head = revision(declaration["rate_card_frontier"]["revisions"][1])
    previous = RateCardFrontier(head_digest=old.digest, revisions=(old,))
    current = RateCardFrontier(head_digest=head.digest, revisions=(old, head))

    intervals = derive_frontier_dirty_intervals(previous, current)
    assert [
        (
            item.revision_digest,
            item.effective_at_us,
            item.next_effective_at_us,
        )
        for item in intervals
    ] == [(HEAD_DIGEST, 250, None)]


def test_database_adapter_requires_a_query_only_caller_owned_snapshot() -> None:
    declaration = build_structural_v2()
    connection = build_query_only_database(declaration)
    connection.execute("PRAGMA query_only = OFF")
    adapter = DatabaseV1FactAdapter(
        plan_contract(),
        selector_contract(),
        _references(adapter_request(), window=True),
    )

    with pytest.raises(DatabaseAdapterContractError, match="query_only"):
        adapter.materialize(
            connection,
            adapter_request(),
            _references(adapter_request(), window=True),
        )


def test_structural_adapter_rejects_expected_grading_body_and_float_inputs() -> None:
    adapter = StructuralReferenceFactAdapter(plan_contract(), selector_contract())
    request = adapter_request()
    evidence = _references(request, window=True)
    forbidden_values = [
        {"oracle_case": "forbidden"},
        {"expected": {"calls": 1}},
        {"grading": {"status": "forbidden"}},
        {"prompt": "private body"},
        {"measurement": 0.5},
    ]

    for value in forbidden_values:
        declaration = build_structural_v2()
        declaration["facts"][0]["values"]["forbidden_probe"] = value
        with pytest.raises(StructuralReferenceAdapterError):
            adapter.materialize(declaration, request, evidence)


def test_emitted_structural_jsonl_contains_only_body_free_fact_records() -> None:
    payload = emitted_structural_jsonl(build_structural_v2())
    lowered = payload.lower()
    for token in (
        b"oracle_case",
        b"expected",
        b'"grade"',
        b"grading",
        b"comparison",
        b"answer_cache",
        b'"prompt"',
        b'"response"',
        b'"reasoning"',
        b'"command"',
        b'"patch"',
    ):
        assert token not in lowered
    assert payload.count(b"\n") > 0


def test_adapter_imports_and_sources_enforce_independence() -> None:
    allowed_domain_imports = {
        "codex_usage_tracker.agent_kernel.domain.identity",
        "codex_usage_tracker.agent_kernel.domain.plan_operands",
        "codex_usage_tracker.agent_kernel.domain.valuation",
    }
    forbidden_import_roots = (
        "codex_usage_tracker.agent_kernel.publication",
        "codex_usage_tracker.agent_kernel.query",
        "codex_usage_tracker.agent_kernel.storage",
        "tests.agent_kernel.fact_adapters",
        "tests.agent_kernel.fixtures",
        "tests.experiments.physical_architecture.candidate_a",
    )

    for name in ("reference.py", "database.py"):
        source = (PACKAGE / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
        agent_kernel_imports = {
            module
            for module in imported_modules
            if module.startswith("codex_usage_tracker.agent_kernel")
        }
        assert agent_kernel_imports <= allowed_domain_imports
        for module in imported_modules:
            assert not module.startswith(forbidden_import_roots)


def test_total_order_preserves_null_and_same_time_ties() -> None:
    reference, database = _materialize_pair(
        build_structural_v2(),
        plan_id="allowance_interval_events",
        window=False,
    )
    assert normalize_materialization(reference) == normalize_materialization(database)
    observations = [fact for fact in reference.facts if fact.relation == "allowance_observation"]
    same_time = [
        fact.logical_id
        for fact in observations
        if fact.coordinates and fact.coordinates.event_at_us == 190
    ]
    assert same_time == ["allowance-observation:2", "allowance-observation:3"]
    assert all(fact.coordinates is not None for fact in reference.facts)


def test_all_plans_use_exact_request_window_roles_and_559_references() -> None:
    declaration = build_structural_v2()
    total_references = 0
    roles_by_plan: dict[str, set[str]] = {}
    for plan in plan_contract()["plans"]:
        plan_id = plan["plan_id"]
        request = adapter_request(plan_id)
        has_window = any(
            role == "window" or role.endswith("_window") for role in request.parameters
        )
        references = _references(request, window=has_window)
        reference, database = _materialize_pair(
            declaration,
            plan_id=plan_id,
            window=has_window,
        )
        assert [
            (item.role, item.selector_kind, item.selector) for item in reference.evidence_references
        ] == [
            (item.role, item.selector_kind, item.selector) for item in database.evidence_references
        ]
        total_references += len(references)
        roles_by_plan[plan_id] = {
            item["role"] for item in references if item["selector_kind"] == "window"
        }

    assert total_references == 559
    assert roles_by_plan["period_drivers"] == {
        "current_window",
        "previous_window",
    }
    assert roles_by_plan["weekly_review"] == {
        "current_window",
        "previous_window",
    }


def test_wrong_window_and_rate_card_selectors_fail_closed() -> None:
    declaration = build_structural_v2()
    contract = plan_contract()
    selectors = selector_contract()
    request = adapter_request("period_drivers")
    references = [dict(item) for item in _references(request, window=True)]
    window_index = next(
        index for index, item in enumerate(references) if item["selector_kind"] == "window"
    )
    references[window_index]["selector"] = "window:not-the-derived-window"
    references[window_index]["logical_id"] = "window:not-the-derived-window"

    with pytest.raises(StructuralReferenceAdapterError, match="window"):
        StructuralReferenceFactAdapter(contract, selectors).materialize(
            declaration,
            request,
            references,
        )
    connection = build_query_only_database(declaration)
    with pytest.raises(DatabaseAdapterContractError, match="window"):
        DatabaseV1FactAdapter(contract, selectors, references).materialize(
            connection,
            request,
            references,
        )

    request = adapter_request()
    references = [dict(item) for item in _references(request, window=True)]
    rate_index = next(
        index for index, item in enumerate(references) if item["selector_kind"] == "rate_card"
    )
    references[rate_index]["selector"] = f"rate-card:{'0' * 64}"
    with pytest.raises(StructuralReferenceAdapterError, match="rate-card"):
        StructuralReferenceFactAdapter(contract, selectors).materialize(
            declaration,
            request,
            references,
        )
    connection = build_query_only_database(declaration)
    with pytest.raises(DatabaseAdapterContractError, match="rate-card"):
        DatabaseV1FactAdapter(contract, selectors, references).materialize(
            connection,
            request,
            references,
        )


def test_model_profile_uses_representative_call_occurrences() -> None:
    declaration = build_structural_v2()
    assert "profile:alpha" not in declaration["occurrences"]
    assert "profile:beta" not in declaration["occurrences"]
    reference, database = _materialize_pair(declaration)
    assert normalize_materialization(reference) == normalize_materialization(database)
    profile = next(
        item for item in reference.evidence_references if item.selector_kind == "model_profile"
    )
    assert profile.provenance_kind == "source_occurrence"
    assert (
        profile.provenance["representative_call_occurrences"][0]["semantic_logical_id"]
        == "call:before"
    )


def test_authoritative_publication_coverage_excludes_unpriced_calls() -> None:
    reference, database = _materialize_pair(
        build_structural_v2(null_cached_tokens=True),
        plan_id="data_health",
        window=False,
    )
    assert normalize_materialization(reference) == normalize_materialization(database)
    publication = next(fact for fact in reference.facts if fact.relation == "publication")
    assert publication.values["valuation_coverage"] == {
        "basis": "configured_estimate",
        "priced_calls": 2,
    }
    assert publication.values["capabilities"] == {
        "context_components": True,
        "valuation": True,
    }


def test_tool_resource_links_include_every_normalized_relationship() -> None:
    reference, database = _materialize_pair(
        build_structural_v2(),
        plan_id="repeated_resource_operations",
    )
    assert normalize_materialization(reference) == normalize_materialization(database)
    tool = next(
        fact
        for fact in reference.facts
        if fact.relation == "tool_invocation" and fact.logical_id == "tool:inspect"
    )
    assert tuple(tool.values["resource_links"]) == (
        "resource:file",
        "resource:test",
    )


def test_allowance_forms_normalize_to_remaining_percent_basis() -> None:
    reference, database = _materialize_pair(
        build_structural_v2(),
        plan_id="allowance_interval_events",
        window=False,
    )
    assert normalize_materialization(reference) == normalize_materialization(database)
    values = {
        fact.logical_id: fact.values["allowance_percent"]
        for fact in reference.facts
        if fact.relation == "allowance_observation"
    }
    assert values == {
        "allowance-observation:1": 90,
        "allowance-observation:2": 80,
        "allowance-observation:3": 80,
        "allowance-observation:4": 70,
    }


def test_each_allowance_interval_resolves_its_own_boundary_pair() -> None:
    declaration = build_structural_v2()
    request = adapter_request("allowance_interval_events", with_window=False)
    references = [dict(item) for item in _references(request, window=False)]
    interval = next(item for item in references if item["selector_kind"] == "allowance_interval")
    interval.update(
        {
            "selector": "allowance-interval:allowance-interval:two",
            "logical_id": "allowance-interval:two",
        }
    )
    contract = plan_contract()
    selectors = selector_contract()
    reference = StructuralReferenceFactAdapter(contract, selectors).materialize(
        declaration,
        request,
        references,
    )
    connection = build_query_only_database(declaration)
    database = DatabaseV1FactAdapter(contract, selectors, references).materialize(
        connection,
        request,
        references,
    )
    assert normalize_materialization(reference) == normalize_materialization(database)
    selected = next(
        item for item in reference.evidence_references if item.selector_kind == "allowance_interval"
    )
    assert (
        selected.provenance["start_observation_selector"]
        == "allowance-observation:allowance-observation:3"
    )
    assert (
        selected.provenance["end_observation_selector"]
        == "allowance-observation:allowance-observation:4"
    )


def test_database_frontier_publication_mismatch_fails_closed() -> None:
    declaration = build_structural_v2()
    connection = build_query_only_database(declaration)
    connection.execute("PRAGMA query_only = OFF")
    connection.execute("UPDATE active_rate_card SET publication_id = 'publication:stale'")
    connection.commit()
    connection.execute("PRAGMA query_only = ON")
    request = adapter_request("pricing_coverage", with_window=False)
    references = _references(request, window=False)
    with pytest.raises(DatabaseAdapterContractError, match="rate-card"):
        DatabaseV1FactAdapter(
            plan_contract(),
            selector_contract(),
            references,
        ).materialize(connection, request, references)


def test_database_publication_coverage_missing_state_fails_closed() -> None:
    declaration = build_structural_v2()
    connection = build_query_only_database(declaration)
    connection.execute("PRAGMA query_only = OFF")
    connection.execute(
        """
        DELETE FROM publication_capability_coverage
        WHERE capability_id = 'valuation'
        """
    )
    connection.commit()
    connection.execute("PRAGMA query_only = ON")
    request = adapter_request("data_health", with_window=False)
    references = _references(request, window=False)
    with pytest.raises(DatabaseAdapterContractError, match="coverage"):
        DatabaseV1FactAdapter(
            plan_contract(),
            selector_contract(),
            references,
        ).materialize(connection, request, references)


@pytest.mark.parametrize(
    ("used_percent", "remaining_percent"),
    [
        ("20", "70"),
        ("101", None),
    ],
)
def test_database_allowance_inconsistent_or_out_of_range_fails_closed(
    used_percent: str,
    remaining_percent: str | None,
) -> None:
    declaration = build_structural_v2()
    connection = build_query_only_database(declaration)
    connection.execute("PRAGMA query_only = OFF")
    connection.execute(
        """
        UPDATE allowance_observations
        SET used_percent = ?, remaining_percent = ?
        WHERE observation_id = 'allowance-observation:1'
        """,
        (used_percent, remaining_percent),
    )
    connection.commit()
    connection.execute("PRAGMA query_only = ON")
    request = adapter_request("allowance_interval_events", with_window=False)
    references = _references(request, window=False)
    with pytest.raises(DatabaseAdapterContractError, match="allowance|percent"):
        DatabaseV1FactAdapter(
            plan_contract(),
            selector_contract(),
            references,
        ).materialize(connection, request, references)


def test_occurrence_provenance_is_coordinate_ordered() -> None:
    declaration = build_structural_v2(
        lifecycle="late_event",
        include_late_call=True,
    )
    declaration["occurrences"]["call:before"].reverse()
    reference, database = _materialize_pair(declaration)
    assert normalize_materialization(reference) == normalize_materialization(database)
    profile = next(
        item for item in reference.evidence_references if item.selector_kind == "model_profile"
    )
    assert [
        item["record_ordinal"]
        for item in profile.provenance["representative_call_occurrences"]
        if item["semantic_logical_id"] == "call:before"
    ] == [8, 10_008]


def test_tool_resource_links_are_primary_first_and_stably_deduplicated() -> None:
    declaration = build_structural_v2()
    tool = next(
        fact
        for fact in declaration["facts"]
        if fact["relation"] == "tool_invocation" and fact["logical_id"] == "tool:inspect"
    )
    tool["values"]["resource_links"] = [
        "resource:test",
        "resource:file",
        "resource:test",
    ]
    reference, database = _materialize_pair(
        declaration,
        plan_id="repeated_resource_operations",
    )
    assert normalize_materialization(reference) == normalize_materialization(database)
    normalized = next(
        fact
        for fact in reference.facts
        if fact.relation == "tool_invocation" and fact.logical_id == "tool:inspect"
    )
    assert normalized.values["resource_links"] == [
        "resource:file",
        "resource:test",
    ]


def test_database_noncanonical_allowance_decimal_fails_closed() -> None:
    declaration = build_structural_v2()
    connection = build_query_only_database(declaration)
    connection.execute("PRAGMA query_only = OFF")
    connection.execute(
        """
        UPDATE allowance_observations
        SET used_percent = '2E1', remaining_percent = NULL
        WHERE observation_id = 'allowance-observation:1'
        """
    )
    connection.commit()
    connection.execute("PRAGMA query_only = ON")
    request = adapter_request("allowance_interval_events", with_window=False)
    references = _references(request, window=False)
    with pytest.raises(DatabaseAdapterContractError, match="canonical decimal"):
        DatabaseV1FactAdapter(
            plan_contract(),
            selector_contract(),
            references,
        ).materialize(connection, request, references)


def test_database_rolls_back_snapshot_for_unexpected_row_factory_error() -> None:
    declaration = build_structural_v2()
    connection = build_query_only_database(declaration)

    def exploding_row_factory(cursor, row):
        fields = {column[0] for column in cursor.description or ()}
        if "call_id" in fields:
            raise RuntimeError("synthetic row-factory failure")
        return sqlite3.Row(cursor, row)

    connection.row_factory = exploding_row_factory
    request = adapter_request()
    references = _references(request, window=True)
    with pytest.raises(RuntimeError, match="row-factory"):
        DatabaseV1FactAdapter(
            plan_contract(),
            selector_contract(),
            references,
        ).materialize(connection, request, references)
    assert not connection.in_transaction
