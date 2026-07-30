"""Contract edges owned by the accounting/context derivation module."""

from __future__ import annotations

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_derivations_accounting import (
    DERIVATIONS,
    _need,
    derive_pricing_coverage_v1,
)
from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    FactCoordinates,
    PlanOperandContractError,
    PlanRequest,
)

_SYMBOLS = {
    "derive_top_sessions_v1",
    "derive_period_drivers_v1",
    "derive_project_family_usage_v1",
    "derive_top_valued_entities_v1",
    "derive_pricing_coverage_v1",
    "derive_cache_reuse_candidates_v1",
    "derive_context_pressure_trajectory_v1",
    "derive_token_acceleration_v1",
    "derive_uncached_input_jumps_v1",
    "derive_cached_replay_small_output_v1",
    "derive_context_composition_v1",
    "derive_compaction_comparison_v1",
    "derive_growth_without_mutation_v1",
    "derive_long_vs_split_cohorts_v1",
    "derive_allowance_movement_v1",
    "derive_allowance_local_efficiency_v1",
    "derive_allowance_cycle_comparison_v1",
}


def test_every_owned_symbol_is_exported_and_callable() -> None:
    assert _SYMBOLS <= set(DERIVATIONS)
    assert all(callable(DERIVATIONS[symbol]) for symbol in _SYMBOLS)


def test_missing_real_logical_field_fails_closed() -> None:
    fact = CanonicalFact("canonical_call", "call:1", {"call_id": "call:1"})
    with pytest.raises(PlanOperandContractError, match="missing output_tokens"):
        _need(fact, "output_tokens")


def test_typed_unpriced_valuation_row_is_not_counted_as_priced() -> None:
    plan = {
        "plan_id": "pricing_coverage",
        "formula_uses": [
            {
                "use_id": "Q-ACC-07:valuation_coverage_v1:0",
                "formula_id": "valuation_coverage_v1",
                "output_bindings": {"pricing_coverage": "$"},
                "internal_only": False,
                "consume_as": None,
            }
        ],
    }
    request = PlanRequest(
        "pricing_coverage",
        {"window": {"start_us": 0, "end_us": 100}, "rate_card": "digest"},
        {"measurement": True, "publication": True, "valuation": True, "window": True},
    )
    coordinates = FactCoordinates(10, 0, 0, 10)
    call = CanonicalFact(
        "canonical_call",
        "call:1",
        {
            "call_id": "call:1",
            "model_profile_id": "profile:1",
            "uncached_input_tokens": 2,
            "cached_input_tokens": 3,
            "output_tokens": 5,
        },
        coordinates,
    )
    unpriced = CanonicalFact(
        "valuation_match",
        "valuation:1",
        {
            "call_id": "call:1",
            "configured_cost_usd": None,
            "cost_grade": "unsupported",
            "cost_unpriced_reason": "model_unmatched",
        },
        coordinates,
    )

    materialization = derive_pricing_coverage_v1(
        plan,
        request,
        {"canonical_call": [call], "valuation_match": [unpriced]},
    )

    assert materialization.groups[0].direct_slots == {
        "priced_calls": 0,
        "unpriced_calls": 1,
        "unpriced_tokens": 10,
    }
    assert materialization.groups[0].formula_calls[0].operands == {
        "numerator": 0,
        "denominator": 1,
    }
