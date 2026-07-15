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
MULTI_DETECTOR_VERSION = "hierarchical-maxstat-cycle-v3"
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


def detect_cycle_changes(
    cycles: list[dict[str, Any]],
    *,
    semantic_key: str,
    min_cycles_per_regime: int = 4,
    permutation_count: int = 1_999,
    familywise_alpha: float = 0.05,
) -> dict[str, Any]:
    """Detect zero or more supported capacity regimes with alpha spending."""
    if min_cycles_per_regime < 2:
        raise ValueError("min_cycles_per_regime must be at least 2")
    if permutation_count < 99:
        raise ValueError("permutation_count must be at least 99")
    if not 0 < familywise_alpha < 1:
        raise ValueError("familywise_alpha must be between 0 and 1")
    ordered = sorted(
        cycles,
        key=lambda row: (
            str(row.get("last_observed_at") or ""),
            str(row.get("cycle_id") or ""),
        ),
    )
    eligible, caveats = _eligible_cycles(ordered)
    plan_segments = _plan_segments(eligible)
    analyzable_segments = [
        segment
        for segment in plan_segments
        if segment[1] - segment[0] >= 2 * min_cycles_per_regime
    ]
    segment_alpha = familywise_alpha / max(1, len(analyzable_segments))
    boundaries: list[dict[str, Any]] = []
    for start, end, plan_type in analyzable_segments:
        segment_key = (
            semantic_key
            if len(plan_segments) == 1
            else f"{semantic_key}:plan:{plan_type}:{start}:{end}"
        )
        boundaries.extend(
            _detect_segment(
                eligible,
                start=start,
                end=end,
                alpha=segment_alpha,
                semantic_key=segment_key,
                minimum=min_cycles_per_regime,
                permutation_count=permutation_count,
            )
        )
    boundaries.sort(key=lambda row: int(row["split_index"]))
    forced_plan_splits = [start for start, _, _ in plan_segments[1:]]
    regimes = _capacity_regimes(
        eligible,
        boundaries,
        forced_splits=forced_plan_splits,
    )
    singular = boundaries[0] if len(boundaries) == 1 else None
    enough_evidence = bool(analyzable_segments)
    return {
        "detector_version": MULTI_DETECTOR_VERSION,
        "selection_correction": "hierarchical_max_statistic_cycle_block_permutation",
        "permutation_unit": "cycle",
        "familywise_alpha": familywise_alpha,
        "minimum_cycles_per_regime": min_cycles_per_regime,
        "eligible_cycle_count": len(eligible),
        "excluded_cycle_count": len(ordered) - len(eligible),
        "candidate_count": sum(
            max(0, end - start - (2 * min_cycles_per_regime) + 1)
            for start, end, _ in plan_segments
        ),
        "status": "supported_changes" if boundaries else (
            "no_supported_change"
            if enough_evidence
            else "insufficient_evidence"
        ),
        "reason": None if boundaries else (
            "selection_adjusted_evidence_below_threshold"
            if enough_evidence
            else "insufficient_quality_approved_completed_cycles"
        ),
        "boundaries": boundaries,
        "regimes": regimes,
        "caveats": [
            *caveats,
            *(
                ["subscription_plan_segments_analyzed_independently"]
                if len(plan_segments) > 1
                else []
            ),
            "familywise_error_controlled_by_hierarchical_alpha_spending",
            "unsupported_candidate_boundaries_suppressed",
        ],
        "selected_boundary": _compatibility_boundary(singular),
        "adjusted_p_value": singular.get("adjusted_p_value") if singular else None,
        "effect_size": singular.get("effect_size") if singular else None,
        "confidence_interval": singular.get("confidence_interval") if singular else None,
        "compatibility_status": (
            "deprecated_single_boundary" if singular else "not_applicable"
        ),
    }


def _plan_segments(
    cycles: list[dict[str, Any]],
) -> list[tuple[int, int, str]]:
    if not cycles:
        return []
    segments: list[tuple[int, int, str]] = []
    start = 0
    current = str(cycles[0].get("plan_type") or "unknown")
    for index, cycle in enumerate(cycles[1:], 1):
        plan_type = str(cycle.get("plan_type") or "unknown")
        if plan_type == current:
            continue
        segments.append((start, index, current))
        start, current = index, plan_type
    segments.append((start, len(cycles), current))
    return segments


def _detect_segment(
    cycles: list[dict[str, Any]],
    *,
    start: int,
    end: int,
    alpha: float,
    semantic_key: str,
    minimum: int,
    permutation_count: int,
) -> list[dict[str, Any]]:
    if end - start < 2 * minimum:
        return []
    tested = _test_segment(
        cycles[start:end],
        start=start,
        end=end,
        alpha=alpha,
        semantic_key=semantic_key,
        minimum=minimum,
        permutation_count=permutation_count,
    )
    if not tested["supported"]:
        return []
    split = int(tested["split_index"])
    child_alpha = alpha / 2
    return [
        *_detect_segment(
            cycles,
            start=start,
            end=split,
            alpha=child_alpha,
            semantic_key=semantic_key,
            minimum=minimum,
            permutation_count=permutation_count,
        ),
        {key: value for key, value in tested.items() if key != "supported"},
        *_detect_segment(
            cycles,
            start=split,
            end=end,
            alpha=child_alpha,
            semantic_key=semantic_key,
            minimum=minimum,
            permutation_count=permutation_count,
        ),
    ]


def _test_segment(
    cycles: list[dict[str, Any]],
    *,
    start: int,
    end: int,
    alpha: float,
    semantic_key: str,
    minimum: int,
    permutation_count: int,
) -> dict[str, Any]:
    values = [float(row["credits_per_percent"]) for row in cycles]
    selected = _best_split(values, minimum)
    assert selected is not None
    local_split, observed_statistic = selected
    adjusted_p, method, evaluated, seed, uncertainty = _permutation_result(
        values,
        observed_statistic=observed_statistic,
        semantic_key=f"{semantic_key}:{start}:{end}:{alpha:.12g}",
        minimum=minimum,
        permutation_count=permutation_count,
    )
    before, after = values[:local_split], values[local_split:]
    cliffs_delta = _cliffs_delta(before, after)
    split = start + local_split
    effect_size = {
        "median_before_credits_per_percent": _rounded(median(before)),
        "median_after_credits_per_percent": _rounded(median(after)),
        "median_shift_credits_per_percent": _rounded(
            median(after) - median(before)
        ),
        "cliffs_delta": _rounded(cliffs_delta),
    }
    return {
        "supported": adjusted_p < alpha
        and _monte_carlo_decision_supported(
            method=method,
            uncertainty=uncertainty,
            alpha=alpha,
        )
        and abs(cliffs_delta or 0.0) >= _STRONG_EFFECT_THRESHOLD,
        "boundary_id": f"boundary-{split}",
        "split_index": split,
        "before_cycle_id": str(cycles[local_split - 1]["cycle_id"]),
        "after_cycle_id": str(cycles[local_split]["cycle_id"]),
        "effective_at": cycles[local_split].get("last_observed_at"),
        "segment_start_index": start,
        "segment_end_index": end,
        "alpha": _rounded(alpha),
        "observed_max_statistic": _rounded(observed_statistic),
        "adjusted_p_value": _rounded(adjusted_p),
        "effect_size": effect_size,
        "confidence_interval": _shift_confidence_interval(before, after),
        "permutation_method": method,
        "permutation_count": evaluated,
        "seed": seed,
        "monte_carlo_uncertainty": uncertainty,
    }


def _monte_carlo_decision_supported(
    *, method: str, uncertainty: dict[str, Any], alpha: float
) -> bool:
    if method != "deterministic_monte_carlo":
        return True
    interval = uncertainty.get("confidence_interval_95")
    return bool(
        isinstance(interval, dict)
        and isinstance(interval.get("high"), int | float)
        and float(interval["high"]) < alpha
    )


def _permutation_result(
    values: list[float],
    *,
    observed_statistic: float,
    semantic_key: str,
    minimum: int,
    permutation_count: int,
) -> tuple[float, str, int, int | None, dict[str, Any]]:
    exact_space = _bounded_factorial(len(values), limit=_EXACT_PERMUTATION_LIMIT)
    if exact_space <= _EXACT_PERMUTATION_LIMIT:
        extreme = 0
        evaluated = 0
        for ordering in itertools.permutations(values):
            permuted_best = _best_split(list(ordering), minimum)
            assert permuted_best is not None
            extreme += permuted_best[1] >= observed_statistic - 1e-12
            evaluated += 1
        return (
            extreme / evaluated,
            "exact_cycle_block_permutation",
            evaluated,
            None,
            _unavailable_uncertainty(),
        )
    seed = int.from_bytes(hashlib.sha256(semantic_key.encode()).digest()[:8], "big")
    generator = random.Random(seed)
    extreme = 0
    for _ in range(permutation_count):
        permuted = list(values)
        generator.shuffle(permuted)
        permuted_best = _best_split(permuted, minimum)
        assert permuted_best is not None
        extreme += permuted_best[1] >= observed_statistic - 1e-12
    return (
        (extreme + 1) / (permutation_count + 1),
        "deterministic_monte_carlo",
        permutation_count,
        seed,
        _monte_carlo_uncertainty(extreme, permutation_count),
    )


def _capacity_regimes(
    cycles: list[dict[str, Any]],
    boundaries: list[dict[str, Any]],
    *,
    forced_splits: list[int] | None = None,
) -> list[dict[str, Any]]:
    splits = sorted(
        {
            0,
            *(int(row["split_index"]) for row in boundaries),
            *(forced_splits or []),
            len(cycles),
        }
    )
    regimes = []
    for index, (start, end) in enumerate(
        zip(splits, splits[1:], strict=False), 1
    ):
        segment = cycles[start:end]
        if not segment:
            continue
        values = [float(row["credits_per_percent"]) for row in segment]
        regimes.append(
            {
                "regime_id": f"regime-{index}",
                "start_at": segment[0].get("last_observed_at"),
                "end_at": segment[-1].get("last_observed_at"),
                "start_index": start,
                "end_index": end,
                "plan_type": str(segment[0].get("plan_type") or "unknown"),
                "eligible_cycle_count": len(segment),
                "median_credits_per_percent": _rounded(median(values)),
                "iqr_credits_per_percent": _rounded(
                    _quantile(values, 0.75) - _quantile(values, 0.25)
                ),
                "price_coverage": _rounded(
                    sum(float(row["price_coverage"]) for row in segment)
                    / len(segment)
                ),
            }
        )
    return regimes


def _compatibility_boundary(
    boundary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if boundary is None:
        return None
    return {
        "split_index": boundary["split_index"],
        "before_cycle_id": boundary["before_cycle_id"],
        "after_cycle_id": boundary["after_cycle_id"],
    }


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + ((ordered[upper] - ordered[lower]) * (position - lower))


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
