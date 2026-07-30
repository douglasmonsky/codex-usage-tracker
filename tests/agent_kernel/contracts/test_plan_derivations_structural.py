from __future__ import annotations

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_derivations_structural import DERIVATIONS
from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    FactCoordinates,
    PlanOperandContractError,
    PlanRequest,
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
    malformed = CanonicalFact(
        "tool_invocation", "tool:1", {}, FactCoordinates(1, 0, 0, 0)
    )
    with pytest.raises(PlanOperandContractError, match="resource_id"):
        DERIVATIONS["derive_retry_cycles_v1"](
            plan, request, {"tool_invocation": [malformed]}
        )
