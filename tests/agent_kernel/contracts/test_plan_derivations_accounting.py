"""Contract edges owned by the accounting/context derivation module."""

from __future__ import annotations

import pytest

from codex_usage_tracker.agent_kernel.domain.plan_derivations_accounting import (
    DERIVATIONS,
    _need,
)
from codex_usage_tracker.agent_kernel.domain.plan_operands import (
    CanonicalFact,
    PlanOperandContractError,
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
