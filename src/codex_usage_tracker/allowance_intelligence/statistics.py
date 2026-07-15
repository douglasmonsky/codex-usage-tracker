"""Nonparametric evidence statistics for allowance-change detection."""

from __future__ import annotations

import math
from heapq import heappop, heappush
from itertools import combinations
from math import comb
from statistics import median
from typing import Any

_PUBLIC_CLAIM_MIN_SPLIT_SPANS = 6
_PUBLIC_CLAIM_P_VALUE_THRESHOLD = 0.05
_PERMUTATION_EXACT_MAX_COMBINATIONS = 50_000

_ChangeSplit = tuple[int, float, float, float]


def _candidate_split_specs(
    spans: list[dict[str, Any]],
    *,
    min_baseline_spans: int,
    min_recent_spans: int,
    ratio_threshold: float,
) -> tuple[list[_ChangeSplit], _ChangeSplit | None]:
    prefix_medians, prefix_counts = _running_credit_medians(spans)
    suffix_medians, suffix_counts = _running_credit_medians(list(reversed(spans)))
    exact: list[_ChangeSplit] = []
    deferred: list[_ChangeSplit] = []
    for split in range(min_baseline_spans, len(spans) - min_recent_spans + 1):
        result = _candidate_split_spec(
            split,
            total_count=len(spans),
            prefix_medians=prefix_medians,
            prefix_counts=prefix_counts,
            suffix_medians=suffix_medians,
            suffix_counts=suffix_counts,
            ratio_threshold=ratio_threshold,
        )
        if result is None:
            continue
        spec, requires_exact = result
        (exact if requires_exact else deferred).append(spec)
    best_deferred = min(
        deferred,
        key=lambda item: _deferred_candidate_score(item, total_count=len(spans)),
        default=None,
    )
    return exact, best_deferred


def _candidate_split_spec(
    split: int,
    *,
    total_count: int,
    prefix_medians: list[float | None],
    prefix_counts: list[int],
    suffix_medians: list[float | None],
    suffix_counts: list[int],
    ratio_threshold: float,
) -> tuple[_ChangeSplit, bool] | None:
    recent_size = total_count - split
    previous_median = prefix_medians[split]
    recent_median = suffix_medians[recent_size]
    if previous_median is None or recent_median is None:
        return None
    ratio = recent_median / previous_median
    if ratio >= ratio_threshold:
        return None
    requires_exact = _split_requires_exact_statistics(
        prefix_counts[split], suffix_counts[recent_size]
    )
    return (split, previous_median, recent_median, ratio), requires_exact


def _split_requires_exact_statistics(previous_count: int, recent_count: int) -> bool:
    if previous_count == 0 or recent_count == 0:
        return False
    return (
        comb(previous_count + recent_count, previous_count) <= _PERMUTATION_EXACT_MAX_COMBINATIONS
    )


def _running_credit_medians(
    spans: list[dict[str, Any]],
) -> tuple[list[float | None], list[int]]:
    lower: list[float] = []
    upper: list[float] = []
    medians: list[float | None] = [None]
    counts = [0]
    for span in spans:
        value = _number(span.get("credits_per_percent"))
        if value is not None and value > 0:
            if not lower or value <= -lower[0]:
                heappush(lower, -value)
            else:
                heappush(upper, value)
            if len(lower) > len(upper) + 1:
                heappush(upper, -heappop(lower))
            elif len(upper) > len(lower):
                heappush(lower, -heappop(upper))
        counts.append(len(lower) + len(upper))
        if not lower:
            medians.append(None)
        elif len(lower) == len(upper):
            medians.append((-lower[0] + upper[0]) / 2.0)
        else:
            medians.append(-lower[0])
    return medians, counts


def _deferred_candidate_score(
    item: _ChangeSplit,
    *,
    total_count: int,
) -> tuple[float, int, int]:
    split, _previous_median, _recent_median, ratio = item
    recent_count = total_count - split
    return ratio, -min(split, recent_count), abs(split - recent_count)


def _statistical_evidence(
    previous: list[dict[str, Any]], recent: list[dict[str, Any]]
) -> dict[str, Any]:
    previous_values = _credits_per_percent_values(previous)
    recent_values = _credits_per_percent_values(recent)
    shift = _median_shift(previous_values, recent_values)
    p_value, method, combinations_evaluated = _exact_permutation_p_value(
        previous_values, recent_values
    )
    effect_size = _cliffs_delta(previous_values, recent_values)
    return {
        "detector_version": "nonparametric-v1",
        "method": method,
        "sample_size_before": len(previous_values),
        "sample_size_after": len(recent_values),
        "median_shift_credits_per_percent": _rounded(shift),
        "median_confidence_interval_before_95": _median_confidence_interval(previous_values),
        "median_confidence_interval_after_95": _median_confidence_interval(recent_values),
        "effect_size_cliffs_delta": _rounded(effect_size),
        "p_value_one_sided": _rounded(p_value),
        "combinations_evaluated": combinations_evaluated,
        "effect_direction": _effect_direction(shift),
        "signal": _statistical_signal(
            effect_size=effect_size,
            p_value=p_value,
            before_count=len(previous_values),
            after_count=len(recent_values),
        ),
        "public_claim_ready": _statistical_public_claim_ready(
            effect_size=effect_size,
            p_value=p_value,
            before_count=len(previous_values),
            after_count=len(recent_values),
        ),
    }


def _median_confidence_interval(values: list[float]) -> dict[str, Any]:
    """Return an exact distribution-free 95% interval for a population median."""

    ordered = sorted(values)
    sample_size = len(ordered)
    target_coverage = 0.95
    selected_rank: int | None = None
    achieved_coverage = _widest_median_interval_coverage(sample_size)
    log_target_tail = math.log(1.0 - target_coverage) - math.log(2.0)
    log_binomial_probability = -sample_size * math.log(2.0)
    log_lower_tail = -math.inf

    # Exact two-sided 95% coverage requires each binomial tail to be at most 1/40.
    for rank in range(1, (sample_size // 2) + 1):
        log_lower_tail = _log_add(log_lower_tail, log_binomial_probability)
        if log_lower_tail > log_target_tail:
            break
        selected_rank = rank
        achieved_coverage = 1.0 - (2.0 * math.exp(log_lower_tail))
        log_binomial_probability += math.log(sample_size - rank + 1) - math.log(rank)

    if selected_rank is None:
        return {
            "method": "exact_binomial_order_statistic",
            "confidence_level": target_coverage,
            "sample_size": sample_size,
            "available": False,
            "low": None,
            "high": None,
            "achieved_coverage": _rounded(achieved_coverage),
        }

    return {
        "method": "exact_binomial_order_statistic",
        "confidence_level": target_coverage,
        "sample_size": sample_size,
        "available": True,
        "low": _rounded(ordered[selected_rank - 1]),
        "high": _rounded(ordered[sample_size - selected_rank]),
        "achieved_coverage": _rounded(achieved_coverage),
    }


def _widest_median_interval_coverage(sample_size: int) -> float:
    if sample_size <= 0:
        return 0.0
    return max(0.0, 1.0 - (2.0 * math.exp(-sample_size * math.log(2.0))))


def _log_add(left: float, right: float) -> float:
    """Return log(exp(left) + exp(right)) without overflow."""

    if left == -math.inf:
        return right
    if right == -math.inf:
        return left
    larger, smaller = max(left, right), min(left, right)
    return larger + math.log1p(math.exp(smaller - larger))


def _bounded_factorial(value: int, *, limit: int) -> int:
    """Return ``value!`` by recurrence, stopping once the exact-work limit is exceeded."""
    result = 1
    for factor in range(2, value + 1):
        result *= factor
        if result > limit:
            return limit + 1
    return result


def _wilson_interval(successes: int, trials: int, *, z: float = 1.959963984540054) -> tuple[float, float]:
    """Stable binomial interval used to disclose Monte Carlo uncertainty."""
    if trials <= 0:
        return (0.0, 1.0)
    proportion = successes / trials
    z_squared = z * z
    denominator = 1.0 + z_squared / trials
    center = (proportion + z_squared / (2.0 * trials)) / denominator
    margin = (
        z
        * math.sqrt(
            (proportion * (1.0 - proportion) / trials)
            + (z_squared / (4.0 * trials * trials))
        )
        / denominator
    )
    return (max(0.0, center - margin), min(1.0, center + margin))


def _credits_per_percent_values(spans: list[dict[str, Any]]) -> list[float]:
    return [
        value
        for value in (_number(span.get("credits_per_percent")) for span in spans)
        if value is not None and value > 0
    ]


def _median_shift(previous: list[float], recent: list[float]) -> float | None:
    if not previous or not recent:
        return None
    return float(median(recent) - median(previous))


def _mean_shift(previous: list[float], recent: list[float]) -> float | None:
    if not previous or not recent:
        return None
    return (sum(recent) / len(recent)) - (sum(previous) / len(previous))


def _exact_permutation_p_value(
    previous: list[float], recent: list[float]
) -> tuple[float | None, str, int | None]:
    if not previous or not recent:
        return None, "insufficient_metric_values", None
    total_size = len(previous) + len(recent)
    before_size = len(previous)
    combination_count = comb(total_size, before_size)
    if combination_count > _PERMUTATION_EXACT_MAX_COMBINATIONS:
        return None, "exact_permutation_skipped_too_many_combinations", combination_count

    observed = _mean_shift(previous, recent)
    if observed is None:
        return None, "insufficient_metric_values", None

    extreme_count = _permutation_extreme_count(
        previous + recent,
        before_size=before_size,
        observed=observed,
    )
    return extreme_count / combination_count, "exact_permutation_mean_shift", combination_count


def _permutation_extreme_count(
    values: list[float],
    *,
    before_size: int,
    observed: float,
) -> int:
    extreme_count = 0
    for before_indices in combinations(range(len(values)), before_size):
        permuted_shift = _permuted_mean_shift(values, before_indices)
        if permuted_shift is not None and permuted_shift <= observed + 1e-12:
            extreme_count += 1
    return extreme_count


def _permuted_mean_shift(
    values: list[float],
    before_indices: tuple[int, ...],
) -> float | None:
    before_index_set = set(before_indices)
    permuted_previous = [values[index] for index in before_indices]
    permuted_recent = [
        values[index] for index in range(len(values)) if index not in before_index_set
    ]
    return _mean_shift(permuted_previous, permuted_recent)


def _cliffs_delta(previous: list[float], recent: list[float]) -> float | None:
    if not previous or not recent:
        return None
    higher = 0
    lower = 0
    for previous_value in previous:
        for recent_value in recent:
            if recent_value > previous_value:
                higher += 1
            elif recent_value < previous_value:
                lower += 1
    return (higher - lower) / (len(previous) * len(recent))


def _effect_direction(shift: float | None) -> str:
    if shift is None:
        return "unknown"
    if shift < 0:
        return "recent_lower_credits_per_percent"
    if shift > 0:
        return "recent_higher_credits_per_percent"
    return "no_median_shift"


def _statistical_signal(
    *,
    effect_size: float | None,
    p_value: float | None,
    before_count: int,
    after_count: int,
) -> str:
    if before_count < 2 or after_count < 2 or effect_size is None:
        return "insufficient_metric_values"
    if _is_strong_nonparametric_shift(
        effect_size=effect_size,
        p_value=p_value,
        before_count=before_count,
        after_count=after_count,
    ):
        return "strong_nonparametric_shift"
    if _is_directionally_consistent(effect_size=effect_size, p_value=p_value):
        return "directionally_consistent_small_sample"
    if effect_size <= -0.5:
        return "directional_effect_limited"
    return "weak_or_mixed"


def _is_strong_nonparametric_shift(
    *,
    effect_size: float,
    p_value: float | None,
    before_count: int,
    after_count: int,
) -> bool:
    if p_value is None:
        return False
    return all(
        (
            before_count >= _PUBLIC_CLAIM_MIN_SPLIT_SPANS,
            after_count >= _PUBLIC_CLAIM_MIN_SPLIT_SPANS,
            effect_size <= -0.8,
            p_value <= _PUBLIC_CLAIM_P_VALUE_THRESHOLD,
        )
    )


def _is_directionally_consistent(
    *,
    effect_size: float,
    p_value: float | None,
) -> bool:
    if p_value is None:
        return False
    return effect_size <= -0.8 and p_value <= 0.2


def _statistical_public_claim_ready(
    *,
    effect_size: float | None,
    p_value: float | None,
    before_count: int,
    after_count: int,
) -> bool:
    return (
        before_count >= _PUBLIC_CLAIM_MIN_SPLIT_SPANS
        and after_count >= _PUBLIC_CLAIM_MIN_SPLIT_SPANS
        and effect_size is not None
        and effect_size <= -0.8
        and p_value is not None
        and p_value <= _PUBLIC_CLAIM_P_VALUE_THRESHOLD
    )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None
