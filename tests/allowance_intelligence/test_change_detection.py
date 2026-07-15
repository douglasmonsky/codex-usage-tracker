from __future__ import annotations

from codex_usage_tracker.allowance_intelligence.change_detection import (
    _monte_carlo_decision_supported,
    detect_cycle_change,
    detect_cycle_changes,
)
from codex_usage_tracker.allowance_intelligence.statistics import (
    _bounded_factorial,
    _wilson_interval,
)


def _cycles(values: list[float]) -> list[dict[str, object]]:
    return [
        {
            "cycle_id": f"cycle-{index:02d}",
            "last_observed_at": f"2026-06-{index + 1:02d}T00:00:00+00:00",
            "credits_per_percent": value,
            "status": "completed",
            "quality_grade": "high",
            "price_coverage": 1.0,
            "conflict_count": 0,
        }
        for index, value in enumerate(values)
    ]


def test_best_split_is_selection_corrected_and_not_reported_from_naive_search() -> None:
    result = detect_cycle_change(
        _cycles([10, 11, 9, 10, 13, 8, 11, 9, 12, 8, 10, 11]),
        semantic_key="noise-only",
        min_cycles_per_side=3,
        permutation_count=999,
    )
    assert result["status"] == "no_supported_change"
    assert result["candidate_count"] == 7
    assert result["adjusted_p_value"] >= 0.05
    assert result["selection_correction"] == "max_statistic_cycle_block_permutation"
    assert "public_claim_ready" not in result


def test_planted_regime_change_is_detected_deterministically() -> None:
    cycles = _cycles([10, 9, 11, 10, 9, 10, 30, 31, 29, 30, 31, 30])
    first = detect_cycle_change(
        cycles,
        semantic_key="planted-regime",
        min_cycles_per_side=3,
        permutation_count=1999,
    )
    second = detect_cycle_change(
        cycles,
        semantic_key="planted-regime",
        min_cycles_per_side=3,
        permutation_count=1999,
    )
    assert first == second
    assert first["status"] == "supported_change"
    assert first["selected_boundary"]["after_cycle_id"] == "cycle-06"
    assert first["adjusted_p_value"] < 0.05
    assert first["effect_size"]["median_shift_credits_per_percent"] >= 19
    assert first["permutation_unit"] == "cycle"


def test_conflicts_and_low_coverage_block_strong_change_claims() -> None:
    cycles = _cycles([10, 10, 10, 10, 10, 10, 30, 30, 30, 30, 30, 30])
    cycles[2]["conflict_count"] = 1
    cycles[6]["price_coverage"] = 0.8
    result = detect_cycle_change(
        cycles,
        semantic_key="quality-blocked",
        min_cycles_per_side=3,
        permutation_count=499,
    )
    assert result["status"] != "supported_change"
    assert result["eligible_cycle_count"] == 10
    assert result["reason"] == "quality_gates_blocked_strong_claim"
    assert "conflicted_cycles_excluded" in result["caveats"]
    assert "low_coverage_cycles_excluded" in result["caveats"]


def test_large_analysis_uses_bounded_monte_carlo_with_uncertainty() -> None:
    result = detect_cycle_change(
        _cycles([float(index % 5) for index in range(24)]),
        semantic_key="bounded-monte-carlo",
        min_cycles_per_side=4,
        permutation_count=399,
    )
    assert result["permutation_method"] == "deterministic_monte_carlo"
    assert result["permutation_count"] == 399
    assert result["seed"] is not None
    assert result["monte_carlo_uncertainty"]["standard_error"] is not None


def test_combinatorics_and_uncertainty_stay_bounded_for_large_inputs() -> None:
    assert _bounded_factorial(100_000, limit=40_320) == 40_321
    low, high = _wilson_interval(50_000, 100_000)
    assert 0.49 < low < 0.5 < high < 0.51


def test_detector_returns_multiple_supported_capacity_regimes() -> None:
    result = detect_cycle_changes(
        _cycles(([300.0] * 8) + ([100.0] * 8) + ([220.0] * 8)),
        semantic_key="three-regimes",
        permutation_count=499,
    )

    assert result["status"] == "supported_changes"
    assert len(result["boundaries"]) == 2
    assert [
        round(regime["median_credits_per_percent"])
        for regime in result["regimes"]
    ] == [300, 100, 220]
    assert result["selected_boundary"] is None
    assert result["effect_size"] is None
    assert {boundary["alpha"] for boundary in result["boundaries"]} == {
        0.05,
        0.025,
    }


def test_detector_suppresses_rejected_best_split_effect() -> None:
    result = detect_cycle_changes(
        _cycles([95.0, 110.0, 90.0, 105.0] * 4),
        semantic_key="null-history",
        permutation_count=499,
    )

    assert result["status"] == "no_supported_change"
    assert result["boundaries"] == []
    assert len(result["regimes"]) == 1
    assert result["selected_boundary"] is None
    assert result["adjusted_p_value"] is None
    assert result["effect_size"] is None


def test_detector_never_calls_a_subscription_tier_transition_a_capacity_change() -> None:
    cycles = _cycles(([40.0] * 8) + ([400.0] * 8))
    for cycle in cycles[:8]:
        cycle["plan_type"] = "prolite"
    for cycle in cycles[8:]:
        cycle["plan_type"] = "pro"

    result = detect_cycle_changes(
        cycles,
        semantic_key="plan-transition",
        permutation_count=499,
    )

    assert result["status"] == "no_supported_change"
    assert result["boundaries"] == []
    assert [regime["plan_type"] for regime in result["regimes"]] == [
        "prolite",
        "pro",
    ]
    assert "subscription_plan_segments_analyzed_independently" in result["caveats"]


def test_monte_carlo_decision_requires_uncertainty_below_allocated_alpha() -> None:
    assert _monte_carlo_decision_supported(
        method="deterministic_monte_carlo",
        uncertainty={"confidence_interval_95": {"low": 0.02, "high": 0.049}},
        alpha=0.05,
    )
    assert not _monte_carlo_decision_supported(
        method="deterministic_monte_carlo",
        uncertainty={"confidence_interval_95": {"low": 0.02, "high": 0.051}},
        alpha=0.05,
    )
    assert _monte_carlo_decision_supported(
        method="exact_cycle_block_permutation",
        uncertainty={"confidence_interval_95": None},
        alpha=0.05,
    )
