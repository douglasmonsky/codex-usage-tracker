from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_derivations_structural import DERIVATIONS
from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    FactCoordinates,
    PlanOperandContractError,
    PlanRequest,
    compile_plan_operands,
    evaluate_plan,
)

_SYMBOLS = {
    "derive_turn_completion_efficiency_v1",
    "derive_first_action_mutation_v1",
    "derive_retry_cycles_v1",
    "derive_model_effort_transitions_v1",
    "derive_automation_candidates_v1",
    "derive_parent_subagent_usage_v1",
    "derive_delegation_cohorts_v1",
    "derive_data_health_v1",
    "derive_dedup_source_audit_v1",
    "derive_weekly_review_v1",
    "derive_investigation_candidates_v1",
    "derive_compare_sessions_v1",
}


def test_structural_derivation_surface_is_complete() -> None:
    assert set(DERIVATIONS) == _SYMBOLS
    assert all(callable(value) for value in DERIVATIONS.values())


def test_data_health_rejects_missing_observed_through_field() -> None:
    plan = {
        "plan_id": "data_health",
        "formula_uses": [
            {
                "formula_id": "freshness_age_v1",
                "use_id": "use",
                "output_bindings": {"freshness_age_us": "$"},
                "internal_only": False,
            }
        ],
    }
    fact = CanonicalFact(
        "publication",
        "publication:1",
        {
            "capabilities": {},
            "guaranteed_complete_from_us": 1,
            "indexed_from_us": 1,
            "measurements": {},
            "valuation_coverage": {},
        },
        FactCoordinates(1, 0, 0, 0),
    )
    request = PlanRequest("data_health", {"as_of_us": 2})

    with pytest.raises(PlanOperandContractError, match="observed_through_us"):
        DERIVATIONS["derive_data_health_v1"](plan, request, {"publication": [fact]})


@pytest.mark.parametrize(
    "symbol",
    sorted(_SYMBOLS - {"derive_data_health_v1", "derive_retry_cycles_v1"}),
)
def test_symbols_reject_missing_required_relation_fields(symbol: str) -> None:
    # No derivation may silently manufacture a result from a malformed fact.
    plan = {"plan_id": symbol, "formula_uses": []}
    request = PlanRequest(symbol, {"window": {"start_us": 0, "end_us": 2}})
    malformed = CanonicalFact("canonical_call", "call:1", {}, FactCoordinates(1, 0, 0, 0))
    with pytest.raises((PlanOperandContractError, KeyError, IndexError)):
        DERIVATIONS[symbol](plan, request, {"canonical_call": [malformed]})


def test_retry_cycles_rejects_missing_required_tool_fields() -> None:
    plan = {"plan_id": "retry_cycles", "formula_uses": []}
    request = PlanRequest("retry_cycles", {"window": {"start_us": 0, "end_us": 2}})
    malformed = CanonicalFact("tool_invocation", "tool:1", {}, FactCoordinates(1, 0, 0, 0))
    with pytest.raises(PlanOperandContractError, match="resource_id"):
        DERIVATIONS["derive_retry_cycles_v1"](plan, request, {"tool_invocation": [malformed]})


_ROOT = Path(__file__).resolve().parents[3]
_PLAN_CONTRACT = json.loads(
    (_ROOT / "config/agent-kernel/plan-operand-contract-v1.json").read_text(encoding="utf-8")
)
_ANSWER_VECTORS = json.loads(
    (_ROOT / "tests/agent_kernel/fixtures/contracts/answer-semantics-v1-vectors.json").read_text(
        encoding="utf-8"
    )
)


def _request(plan_id: str, parameters: dict[str, Any]) -> PlanRequest:
    plan = next(item for item in _PLAN_CONTRACT["plans"] if item["plan_id"] == plan_id)
    return PlanRequest(plan_id, parameters, {gate: True for gate in plan["gates"]})


def _vector_coordinate(raw: list[Any]) -> FactCoordinates:
    return FactCoordinates(
        raw[1] if not raw[0] else None,
        raw[2],
        raw[3],
        raw[4],
        raw[6],
    )


def _boundary_facts(vector: dict[str, Any]) -> list[CanonicalFact]:
    calls: list[CanonicalFact] = []
    changes: list[CanonicalFact] = []
    tools: dict[str, dict[str, Any]] = {}
    for event in vector["events"]:
        coordinate = _vector_coordinate(event["coordinate"])
        kind = event["kind"]
        if kind == "call":
            call_id = event["coordinate"][5]
            calls.append(
                CanonicalFact(
                    "canonical_call",
                    f"call:{call_id}",
                    {
                        "call_id": call_id,
                        "session_id": "session:test",
                        "turn_id": "turn:test",
                        **dict(
                            zip(
                                (
                                    "uncached_input_tokens",
                                    "cached_input_tokens",
                                    "reasoning_tokens",
                                    "output_tokens",
                                ),
                                event["tokens"],
                                strict=True,
                            )
                        ),
                    },
                    coordinate,
                )
            )
        elif kind in {"tool_start", "tool_terminal"}:
            tool_id = event["coordinate"][5]
            values = tools.setdefault(
                tool_id,
                {
                    "tool_id": tool_id,
                    "session_id": "session:test",
                    "turn_id": "turn:test",
                    "lifecycle": "open",
                    "_coordinate": coordinate,
                },
            )
            if kind == "tool_start":
                values.update(
                    {
                        "start_at_us": coordinate.event_at_us,
                        "start_source_rank": coordinate.source_rank,
                        "start_source_order": coordinate.source_order,
                        "start_event_kind_order": coordinate.event_kind_order,
                        "start_transition_rank": coordinate.transition_rank,
                        "_coordinate": coordinate,
                    }
                )
            else:
                values.update(
                    {
                        "lifecycle": event["lifecycle"],
                        "terminal_at_us": coordinate.event_at_us,
                        "terminal_source_rank": coordinate.source_rank,
                        "terminal_source_order": coordinate.source_order,
                        "terminal_event_kind_order": coordinate.event_kind_order,
                        "terminal_transition_rank": coordinate.transition_rank,
                    }
                )
        elif kind == "state_change":
            state_id = event["coordinate"][5]
            changes.append(
                CanonicalFact(
                    "state_change",
                    f"change:{state_id}",
                    {
                        "state_change_id": state_id,
                        "session_id": "session:test",
                        "turn_id": "turn:test",
                        "mutation_kind": "modified",
                    },
                    coordinate,
                )
            )
    return (
        calls
        + [
            CanonicalFact(
                "tool_invocation",
                f"tool:{tool_id}",
                {key: value for key, value in values.items() if key != "_coordinate"},
                values["_coordinate"],
            )
            for tool_id, values in tools.items()
        ]
        + changes
    )


@pytest.mark.parametrize("vector", _ANSWER_VECTORS["q_wf_02"])
def test_production_qwf02_matches_all_frozen_boundary_vectors(
    vector: dict[str, Any],
) -> None:
    request = _request(
        "first_action_mutation",
        {"window": {"start_us": 0, "end_us": 100}},
    )
    facts = _boundary_facts(vector)
    row = dict(evaluate_plan(_PLAN_CONTRACT, request, facts).rows[0])
    assert {
        field: row[field]
        for field in (
            "first_action_tokens",
            "first_success_tokens",
            "first_mutation_tokens",
            "mutation_observed",
        )
    } == {
        field: vector["expected"].get(field)
        for field in (
            "first_action_tokens",
            "first_success_tokens",
            "first_mutation_tokens",
            "mutation_observed",
        )
    }
    if vector["id"] == "seven_part_tie":
        materialization = compile_plan_operands(_PLAN_CONTRACT, request, facts)
        assert (
            materialization.groups[0].formula_calls[0].operands["records"][0]["logical_id"]
            == "tool-a"
        )
        assert (
            materialization.groups[0].formula_calls[2].operands["records"][0]["logical_id"]
            == "tool-b"
        )


def test_qwf02_window_uses_explicit_tool_start_coordinate() -> None:
    request = _request(
        "first_action_mutation",
        {"window": {"start_us": 0, "end_us": 100}},
    )
    facts = [
        CanonicalFact(
            "canonical_call",
            "call:1",
            {
                "call_id": "call:1",
                "session_id": "session:test",
                "turn_id": "turn:test",
                "uncached_input_tokens": 1,
                "cached_input_tokens": 1,
                "reasoning_tokens": 1,
                "output_tokens": 1,
            },
            FactCoordinates(10, 0, 1, 10),
        ),
        CanonicalFact(
            "tool_invocation",
            "tool:explicit-start",
            {
                "tool_id": "tool:explicit-start",
                "session_id": "session:test",
                "turn_id": "turn:test",
                "lifecycle": "succeeded",
                "start_at_us": 20,
                "start_source_rank": 0,
                "start_source_order": 2,
                "start_event_kind_order": 10,
                "start_transition_rank": 0,
                "terminal_at_us": 21,
                "terminal_source_rank": 0,
                "terminal_source_order": 3,
                "terminal_event_kind_order": 10,
                "terminal_transition_rank": 1,
            },
            # The generic occurrence anchor is outside the request window;
            # the R1A explicit start coordinate is the semantic membership.
            FactCoordinates(200, 0, 4, 40),
        ),
    ]
    row = dict(evaluate_plan(_PLAN_CONTRACT, request, facts).rows[0])
    assert row["first_action_tokens"] == 4
    assert row["first_success_tokens"] == 4
    assert row["first_mutation_tokens"] is None
    assert row["mutation_observed"] is False


def test_qwf02_excludes_valid_tools_outside_the_selected_window() -> None:
    request = _request(
        "first_action_mutation",
        {"window": {"start_us": 0, "end_us": 100}},
    )
    facts = _boundary_facts(_ANSWER_VECTORS["q_wf_02"][0])
    facts.append(
        CanonicalFact(
            "tool_invocation",
            "tool:outside",
            {
                "tool_id": "tool:outside",
                "session_id": "session:test",
                "turn_id": "turn:test",
                "lifecycle": "succeeded",
                "start_at_us": 150,
                "start_source_rank": 0,
                "start_source_order": 150,
                "start_event_kind_order": 10,
                "start_transition_rank": 0,
                "terminal_at_us": 151,
                "terminal_source_rank": 0,
                "terminal_source_order": 151,
                "terminal_event_kind_order": 10,
                "terminal_transition_rank": 1,
            },
            FactCoordinates(151, 0, 151, 10),
        )
    )
    expected = dict(evaluate_plan(_PLAN_CONTRACT, request, facts[:-1]).rows[0])
    assert dict(evaluate_plan(_PLAN_CONTRACT, request, facts).rows[0]) == expected


@pytest.mark.parametrize(
    ("start_at_us", "terminal_at_us", "first_action", "first_success"),
    [
        (90, 150, None, 4),
        (150, 210, 4, None),
    ],
)
def test_qwf02_selects_start_and_terminal_boundaries_independently(
    start_at_us: int,
    terminal_at_us: int,
    first_action: int | None,
    first_success: int | None,
) -> None:
    request = _request(
        "first_action_mutation",
        {"window": {"start_us": 100, "end_us": 200}},
    )
    facts = [
        CanonicalFact(
            "canonical_call",
            "call:straddling",
            {
                "call_id": "call:straddling",
                "session_id": "session:test",
                "turn_id": "turn:test",
                "uncached_input_tokens": 1,
                "cached_input_tokens": 1,
                "reasoning_tokens": 1,
                "output_tokens": 1,
            },
            FactCoordinates(120, 0, 1, 30),
        ),
        CanonicalFact(
            "tool_invocation",
            "tool:straddling",
            {
                "tool_id": "tool:straddling",
                "session_id": "session:test",
                "turn_id": "turn:test",
                "lifecycle": "succeeded",
                "start_at_us": start_at_us,
                "start_source_rank": 0,
                "start_source_order": 2,
                "start_event_kind_order": 40,
                "start_transition_rank": 0,
                "terminal_at_us": terminal_at_us,
                "terminal_source_rank": 0,
                "terminal_source_order": 3,
                "terminal_event_kind_order": 50,
                "terminal_transition_rank": 1,
            },
            FactCoordinates(terminal_at_us, 0, 3, 50),
        ),
    ]
    row = dict(evaluate_plan(_PLAN_CONTRACT, request, facts).rows[0])
    assert row["first_action_tokens"] == first_action
    assert row["first_success_tokens"] == first_success


@pytest.mark.parametrize("prefix", ["start", "terminal"])
def test_qwf02_rejects_null_required_tool_boundary_timestamp(prefix: str) -> None:
    request = _request(
        "first_action_mutation",
        {"window": {"start_us": 0, "end_us": 100}},
    )
    facts = _boundary_facts(_ANSWER_VECTORS["q_wf_02"][0])
    tool = next(fact for fact in facts if fact.relation == "tool_invocation")
    facts[facts.index(tool)] = CanonicalFact(
        tool.relation,
        tool.logical_id,
        {**tool.values, f"{prefix}_at_us": None},
        tool.coordinates,
    )
    with pytest.raises(
        PlanOperandContractError,
        match=rf"tool {prefix} event_at_us must not be null",
    ):
        evaluate_plan(_PLAN_CONTRACT, request, facts)


def _qrev_fact(relation: str, logical_id: str, values: dict[str, Any], order: int) -> CanonicalFact:
    return CanonicalFact(
        relation,
        logical_id,
        values,
        FactCoordinates(order, 0, order, 10),
    )


def _qrev_session(
    session_id: str,
    *,
    root: str | None = None,
    parent: str | None = None,
    depth: int | None = 0,
    omit_parent: bool = False,
) -> CanonicalFact:
    values: dict[str, Any] = {
        "session_id": session_id,
        "root_session_id": root or session_id,
        "parent_session_id": parent,
        "delegation_depth": depth,
        "lifecycle_state": "open" if session_id == "left" else "completed",
        "completion_basis": "open" if session_id == "left" else "completed",
    }
    if omit_parent:
        values.pop("parent_session_id")
    return _qrev_fact("session", f"session:{session_id}", values, 1)


def _qrev_call(
    call_id: str,
    session_id: str,
    tokens: tuple[int | None, int | None, int | None, int | None],
    context: int | None,
    mask: int,
    order: int,
    *,
    omit_reasoning: bool = False,
) -> CanonicalFact:
    values: dict[str, Any] = {
        "call_id": call_id,
        "session_id": session_id,
        "turn_id": f"turn:{call_id}",
        "uncached_input_tokens": tokens[0],
        "cached_input_tokens": tokens[1],
        "reasoning_tokens": tokens[2],
        "output_tokens": tokens[3],
        "context_window_tokens": context,
        "measurement_mask": mask,
    }
    if omit_reasoning:
        values.pop("reasoning_tokens")
    return _qrev_fact("canonical_call", f"call:{call_id}", values, order)


def _qrev_facts(
    *,
    capability: bool = True,
    missing_hierarchy: bool = False,
    missing_reasoning: bool = False,
) -> list[CanonicalFact]:
    facts: list[CanonicalFact] = [
        _qrev_fact(
            "publication",
            "publication:test",
            {
                "publication_id": "publication:test",
                "capabilities": {"structural_context": capability},
            },
            0,
        ),
        _qrev_session("left", omit_parent=missing_hierarchy),
        _qrev_session("right"),
        _qrev_call(
            "left-call",
            "left",
            (1, 2, 3, 4),
            100,
            16,
            10,
            omit_reasoning=missing_reasoning,
        ),
        _qrev_call("right-call", "right", (5, 6, 7, 8), 300, 16, 11),
        _qrev_fact("resource", "resource:r1", {"resource_id": "r1", "resource_kind": "file"}, 20),
        _qrev_fact(
            "tool_invocation",
            "tool:left",
            {
                "tool_id": "left-tool",
                "session_id": "left",
                "lifecycle": "succeeded",
                "resource_id": "r1",
                "resource_links": ["r1"],
            },
            21,
        ),
        _qrev_fact(
            "turn",
            "turn:left",
            {"turn_id": "left-turn", "session_id": "left"},
            22,
        ),
    ]
    return facts


def _qrev_row(facts: list[CanonicalFact]) -> dict[str, Any]:
    request = _request(
        "compare_sessions",
        {"left_session": "left", "right_session": "right"},
    )
    return dict(evaluate_plan(_PLAN_CONTRACT, request, facts).rows[0])


def test_production_qrev03_derives_exact_side_fields_from_synthetic_facts() -> None:
    facts = _qrev_facts()
    row = _qrev_row(facts)
    assert row["completion_state"] == {
        "left": {"lifecycle_state": "open", "completion_basis": "open"},
        "right": {"lifecycle_state": "completed", "completion_basis": "completed"},
    }
    assert row["context_features"] == {
        "left": {"observed_call_count": 1, "distinct_context_window_tokens": [100]},
        "right": {"observed_call_count": 1, "distinct_context_window_tokens": [300]},
    }
    assert row["delegation_metrics"] == {
        "left": {"exclusive_tokens": 10, "descendant_tokens": 0, "inclusive_tokens": 10},
        "right": {"exclusive_tokens": 26, "descendant_tokens": 0, "inclusive_tokens": 26},
    }
    assert row["token_deltas"] == {
        "uncached_input_tokens": 4,
        "cached_input_tokens": 4,
        "reasoning_tokens": 4,
        "output_tokens": 4,
        "total_tokens": 16,
    }
    assert row["resource_metrics"] == {
        "left": {"count": 1, "by_kind": {"file": 1}},
        "right": {"count": 0, "by_kind": {}},
    }
    assert row["tool_metrics"]["left"] == {
        "invocation_count": 1,
        "succeeded_count": 1,
        "failed_count": 0,
        "open_count": 0,
    }
    assert row["turn_call_counts"] == {
        "left": {"turn_count": 1, "call_count": 1},
        "right": {"turn_count": 0, "call_count": 1},
    }
    materialization = compile_plan_operands(
        _PLAN_CONTRACT,
        _request(
            "compare_sessions",
            {"left_session": "left", "right_session": "right"},
        ),
        facts,
    )
    diagnostics = {
        call.formula_id: (dict(call.output_bindings), call.internal_only, call.consume_as)
        for call in materialization.groups[0].formula_calls
    }
    assert diagnostics["exclusive_inclusive_scope_v1"] == (
        {},
        True,
        "left_exclusive_inclusive_scope",
    )
    assert diagnostics["side_by_side_delta_v1"] == ({}, True, "total_token_delta")


def test_production_qrev03_null_and_empty_semantics_are_typed() -> None:
    unavailable = _qrev_row(_qrev_facts(capability=False))
    assert unavailable["context_features"] == {"left": None, "right": None}

    empty = _qrev_facts()
    empty = [fact for fact in empty if fact.relation in {"publication", "session"}]
    empty_row = _qrev_row(empty)
    assert empty_row["context_features"] == {
        "left": {"observed_call_count": 0, "distinct_context_window_tokens": []},
        "right": {"observed_call_count": 0, "distinct_context_window_tokens": []},
    }
    assert empty_row["delegation_metrics"] == {
        "left": {"exclusive_tokens": 0, "descendant_tokens": 0, "inclusive_tokens": 0},
        "right": {"exclusive_tokens": 0, "descendant_tokens": 0, "inclusive_tokens": 0},
    }
    assert empty_row["token_deltas"] == {
        "uncached_input_tokens": 0,
        "cached_input_tokens": 0,
        "reasoning_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


@pytest.mark.parametrize("mutation", ["missing", "null", "mismatch"])
def test_production_qrev03_validates_measurement_authority_when_capability_unavailable(
    mutation: str,
) -> None:
    facts = _qrev_facts(capability=False)
    facts = [
        CanonicalFact(
            fact.relation,
            fact.logical_id,
            (
                {key: value for key, value in fact.values.items() if key != "measurement_mask"}
                if mutation == "missing" and fact.logical_id == "call:left-call"
                else {
                    **fact.values,
                    "measurement_mask": None if mutation == "null" else 0,
                }
                if fact.logical_id == "call:left-call"
                else fact.values
            ),
            fact.coordinates,
        )
        for fact in facts
    ]
    with pytest.raises(PlanOperandContractError):
        _qrev_row(facts)


def test_production_qrev03_accepts_committed_context_components_capability() -> None:
    facts = _qrev_facts()
    publication = facts[0]
    facts[0] = CanonicalFact(
        publication.relation,
        publication.logical_id,
        {
            **publication.values,
            "capabilities": {"context_components": True},
        },
        publication.coordinates,
    )
    assert _qrev_row(facts)["context_features"]["left"] is not None


def test_production_qrev03_rejects_conflicting_context_capability_aliases() -> None:
    facts = _qrev_facts()
    publication = facts[0]
    facts[0] = CanonicalFact(
        publication.relation,
        publication.logical_id,
        {
            **publication.values,
            "capabilities": {
                "structural_context": True,
                "context_components": False,
            },
        },
        publication.coordinates,
    )
    with pytest.raises(PlanOperandContractError):
        _qrev_row(facts)


def test_production_qrev03_missingness_nulls_only_affected_values() -> None:
    hierarchy_row = _qrev_row(_qrev_facts(missing_hierarchy=True))
    assert hierarchy_row["delegation_metrics"]["left"] == {
        "exclusive_tokens": 10,
        "descendant_tokens": None,
        "inclusive_tokens": None,
    }
    token_row = _qrev_row(_qrev_facts(missing_reasoning=True))
    assert token_row["delegation_metrics"]["left"]["exclusive_tokens"] is None
    assert token_row["token_deltas"]["reasoning_tokens"] is None
    assert token_row["token_deltas"]["total_tokens"] is None


@pytest.mark.parametrize("failure", ["absent", "duplicate", "malformed", "unknown_lifecycle"])
def test_production_qrev03_rejects_unsupported_structures(failure: str) -> None:
    facts = _qrev_facts()
    if failure == "absent":
        facts = [fact for fact in facts if fact.logical_id != "session:left"]
    elif failure == "duplicate":
        facts.append(_qrev_session("left"))
    elif failure == "malformed":
        facts = [
            CanonicalFact(
                fact.relation,
                fact.logical_id,
                {**fact.values, "delegation_depth": -1}
                if fact.logical_id == "session:left"
                else fact.values,
                fact.coordinates,
            )
            for fact in facts
        ]
    else:
        facts.append(
            _qrev_fact(
                "tool_invocation",
                "tool:unknown",
                {
                    "tool_id": "unknown",
                    "session_id": "left",
                    "lifecycle": "cancelled",
                    "resource_id": "r1",
                    "resource_links": ["r1"],
                },
                30,
            )
        )
    with pytest.raises(PlanOperandContractError):
        compile_plan_operands(
            _PLAN_CONTRACT,
            _request(
                "compare_sessions",
                {"left_session": "left", "right_session": "right"},
            ),
            facts,
        )
