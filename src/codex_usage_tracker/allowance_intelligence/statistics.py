"""Nonparametric evidence statistics for allowance-change detection."""

from __future__ import annotations

from itertools import combinations
from math import comb
from statistics import median
from typing import Any

_PUBLIC_CLAIM_MIN_SPLIT_SPANS = 6
_PUBLIC_CLAIM_P_VALUE_THRESHOLD = 0.05
_PERMUTATION_EXACT_MAX_COMBINATIONS = 50_000


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

    values = previous + recent
    extreme_count = 0
    for before_indices in combinations(range(total_size), before_size):
        before_index_set = set(before_indices)
        permuted_previous = [values[index] for index in before_indices]
        permuted_recent = [
            values[index] for index in range(total_size) if index not in before_index_set
        ]
        permuted_shift = _mean_shift(permuted_previous, permuted_recent)
        if permuted_shift is not None and permuted_shift <= observed + 1e-12:
            extreme_count += 1
    return extreme_count / combination_count, "exact_permutation_mean_shift", combination_count


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
    if (
        before_count >= _PUBLIC_CLAIM_MIN_SPLIT_SPANS
        and after_count >= _PUBLIC_CLAIM_MIN_SPLIT_SPANS
        and effect_size <= -0.8
        and p_value is not None
        and p_value <= _PUBLIC_CLAIM_P_VALUE_THRESHOLD
    ):
        return "strong_nonparametric_shift"
    if effect_size <= -0.8 and p_value is not None and p_value <= 0.2:
        return "directionally_consistent_small_sample"
    if effect_size <= -0.5:
        return "directional_effect_limited"
    return "weak_or_mixed"


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
