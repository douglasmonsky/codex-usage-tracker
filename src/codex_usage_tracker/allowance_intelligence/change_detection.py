"""Selection-corrected change detection over completed allowance cycles."""

from __future__ import annotations

import hashlib
import itertools
import math
import random
from statistics import median
from typing import Any

from codex_usage_tracker.allowance_intelligence.statistics import (
    _bounded_factorial,
    _cliffs_delta,
    _median_confidence_interval,
    _rounded,
    _wilson_interval,
)

DETECTOR_VERSION = "maxstat-cycle-v1"
_EXACT_PERMUTATION_LIMIT = 40_320
_STRONG_EFFECT_THRESHOLD = 0.474


def detect_cycle_change(
    cycles: list[dict[str, Any]],
    *,
    semantic_key: str,
    min_cycles_per_side: int = 3,
    permutation_count: int = 1_999,
) -> dict[str, Any]:
    """Test the best eligible boundary against best boundaries under the null."""
    if min_cycles_per_side < 2:
        raise ValueError("min_cycles_per_side must be at least 2")
    if permutation_count < 99:
        raise ValueError("permutation_count must be at least 99")
    ordered = sorted(cycles, key=lambda row: (str(row.get("last_observed_at") or ""), str(row.get("cycle_id") or "")))
    eligible, caveats = _eligible_cycles(ordered)
    candidate_count = max(0, len(eligible) - (2 * min_cycles_per_side) + 1)
    common = {
        "detector_version": DETECTOR_VERSION,
        "selection_correction": "max_statistic_cycle_block_permutation",
        "permutation_unit": "cycle",
        "eligible_cycle_count": len(eligible),
        "excluded_cycle_count": len(ordered) - len(eligible),
        "candidate_count": candidate_count,
        "caveats": caveats,
    }
    if candidate_count <= 0:
        return {
            **common,
            "status": "insufficient_evidence",
            "reason": "insufficient_quality_approved_completed_cycles",
            "selected_boundary": None,
            "adjusted_p_value": None,
            "effect_size": None,
            "confidence_interval": None,
            "permutation_method": None,
            "permutation_count": 0,
            "seed": None,
            "monte_carlo_uncertainty": _unavailable_uncertainty(),
            "validation_metrics": _validation_metrics(min_cycles_per_side),
        }

    values = [float(row["credits_per_percent"]) for row in eligible]
    selected = _best_split(values, min_cycles_per_side)
    assert selected is not None
    split, observed_statistic = selected
    exact_space = _bounded_factorial(len(values), limit=_EXACT_PERMUTATION_LIMIT)
    seed: int | None = None
    if exact_space <= _EXACT_PERMUTATION_LIMIT:
        extreme = 0
        evaluated = 0
        for ordering in itertools.permutations(values):
            permuted_best = _best_split(list(ordering), min_cycles_per_side)
            assert permuted_best is not None
            extreme += permuted_best[1] >= observed_statistic - 1e-12
            evaluated += 1
        adjusted_p = extreme / evaluated
        method = "exact_cycle_block_permutation"
        uncertainty = _unavailable_uncertainty()
    else:
        seed = int.from_bytes(hashlib.sha256(semantic_key.encode()).digest()[:8], "big")
        generator = random.Random(seed)
        extreme = 0
        for _ in range(permutation_count):
            permuted = list(values)
            generator.shuffle(permuted)
            permuted_best = _best_split(permuted, min_cycles_per_side)
            assert permuted_best is not None
            extreme += permuted_best[1] >= observed_statistic - 1e-12
        evaluated = permutation_count
        adjusted_p = (extreme + 1) / (evaluated + 1)
        method = "deterministic_monte_carlo"
        uncertainty = _monte_carlo_uncertainty(extreme, evaluated)

    before, after = values[:split], values[split:]
    shift = median(after) - median(before)
    cliffs_delta = _cliffs_delta(before, after)
    quality_blocked = any(
        caveat in {"conflicted_cycles_excluded", "low_coverage_cycles_excluded"}
        for caveat in caveats
    )
    statistical_support = (
        adjusted_p < 0.05 and abs(cliffs_delta or 0.0) >= _STRONG_EFFECT_THRESHOLD
    )
    supported = statistical_support and not quality_blocked
    return {
        **common,
        "status": "supported_change" if supported else "no_supported_change",
        "reason": (
            None
            if supported
            else (
                "quality_gates_blocked_strong_claim"
                if statistical_support and quality_blocked
                else "selection_adjusted_evidence_below_threshold"
            )
        ),
        "selected_boundary": {
            "split_index": split,
            "before_cycle_id": str(eligible[split - 1]["cycle_id"]),
            "after_cycle_id": str(eligible[split]["cycle_id"]),
        },
        "observed_max_statistic": _rounded(observed_statistic),
        "adjusted_p_value": _rounded(adjusted_p),
        "effect_size": {
            "median_before_credits_per_percent": _rounded(median(before)),
            "median_after_credits_per_percent": _rounded(median(after)),
            "median_shift_credits_per_percent": _rounded(shift),
            "cliffs_delta": _rounded(cliffs_delta),
        },
        "confidence_interval": _shift_confidence_interval(before, after),
        "permutation_method": method,
        "permutation_count": evaluated,
        "seed": seed,
        "monte_carlo_uncertainty": uncertainty,
        "validation_metrics": {
            **_validation_metrics(min_cycles_per_side),
            "adjusted_significance_threshold": 0.05,
            "strong_effect_threshold_abs_cliffs_delta": _STRONG_EFFECT_THRESHOLD,
        },
    }


def _eligible_cycles(
    cycles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    eligible = []
    conflicted = low_coverage = other = 0
    for row in cycles:
        if int(row.get("conflict_count") or 0) > 0 or row.get("status") == "ambiguous":
            conflicted += 1
            continue
        coverage = row.get("price_coverage")
        if not isinstance(coverage, int | float) or float(coverage) < 0.95:
            low_coverage += 1
            continue
        value = row.get("credits_per_percent")
        if (
            row.get("status") != "completed"
            or row.get("quality_grade") not in {"high", "medium"}
            or not isinstance(value, int | float)
            or float(value) <= 0
        ):
            other += 1
            continue
        eligible.append(row)
    caveats = [
        "selection_adjusted_across_all_eligible_boundaries",
        "effect_interval_is_descriptive_after_split_selection",
    ]
    if conflicted:
        caveats.append("conflicted_cycles_excluded")
    if low_coverage:
        caveats.append("low_coverage_cycles_excluded")
    if other:
        caveats.append("ineligible_cycles_excluded")
    return eligible, caveats


def _best_split(values: list[float], minimum: int) -> tuple[int, float] | None:
    candidates = []
    total = math.fsum(values)
    prefix = math.fsum(values[:minimum])
    for split in range(minimum, len(values) - minimum + 1):
        if split > minimum:
            prefix += values[split - 1]
        after_count = len(values) - split
        mean_before = prefix / split
        mean_after = (total - prefix) / after_count
        balance = math.sqrt((split * after_count) / len(values))
        candidates.append((split, abs(mean_after - mean_before) * balance))
    return max(candidates, key=lambda item: (item[1], -item[0]), default=None)


def _shift_confidence_interval(
    before: list[float], after: list[float]
) -> dict[str, Any]:
    before_interval = _median_confidence_interval(before)
    after_interval = _median_confidence_interval(after)
    available = bool(before_interval["available"] and after_interval["available"])
    low = (
        float(after_interval["low"]) - float(before_interval["high"])
        if available
        else None
    )
    high = (
        float(after_interval["high"]) - float(before_interval["low"])
        if available
        else None
    )
    return {
        "method": "conservative_difference_of_exact_median_intervals",
        "available": available,
        "low": _rounded(low),
        "high": _rounded(high),
        "before": before_interval,
        "after": after_interval,
    }


def _monte_carlo_uncertainty(successes: int, trials: int) -> dict[str, Any]:
    probability = (successes + 1) / (trials + 1)
    low, high = _wilson_interval(successes, trials)
    return {
        "available": True,
        "standard_error": _rounded(math.sqrt(probability * (1.0 - probability) / (trials + 1))),
        "confidence_interval_95": {"low": _rounded(low), "high": _rounded(high)},
    }


def _unavailable_uncertainty() -> dict[str, Any]:
    return {
        "available": False,
        "standard_error": None,
        "confidence_interval_95": None,
    }


def _validation_metrics(minimum: int) -> dict[str, Any]:
    return {
        "minimum_cycles_per_side": minimum,
        "selection_bias_controlled": True,
        "cycle_density_weight_capped": True,
    }
