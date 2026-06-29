"""One-percent grace calibration helpers for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.feature_history import (
    is_one_percent_delta,
    tail_streak,
)
from codex_usage_tracker.usage_drain.regression import regression_metrics
from codex_usage_tracker.usage_drain.types import UsageDeltaSpan
from codex_usage_tracker.usage_drain.utils import number, rounded

REGIME_GRACE_STREAK_THRESHOLD = 10

REGIME_GRACE_SPANS = 1

REGIME_GRACE_MAX_BREAK_DELTA = 2.0

REGIME_GRACE_THRESHOLD_GRID = (3, 5, 10, 25, 50, 100, 200)

REGIME_GRACE_SPAN_GRID = (1, 2, 3)

def one_percent_grace_calibration(
    spans: list[UsageDeltaSpan], scopes: dict[str, int]
) -> dict[str, Any]:
    values = [span.delta_usage_percent for span in spans]
    if len(values) < 2:
        return {
            "default_config": one_percent_grace_config(
                REGIME_GRACE_STREAK_THRESHOLD, REGIME_GRACE_SPANS
            ),
            "scopes": {},
        }
    scope_results: dict[str, Any] = {}
    for scope_name, start_index in scopes.items():
        rows = []
        for threshold in REGIME_GRACE_THRESHOLD_GRID:
            for grace_spans in REGIME_GRACE_SPAN_GRID:
                rows.append(
                    one_percent_grace_calibration_row(
                        values,
                        start_index=max(1, start_index),
                        streak_threshold=threshold,
                        grace_spans=grace_spans,
                    )
                )
        rows.sort(
            key=lambda row: (
                number(row["mae"]),
                number(row["rmse"]),
                int(row["streak_threshold"]),
                int(row["grace_spans"]),
            )
        )
        default_row = one_percent_grace_calibration_row(
            values,
            start_index=max(1, start_index),
            streak_threshold=REGIME_GRACE_STREAK_THRESHOLD,
            grace_spans=REGIME_GRACE_SPANS,
        )
        by_rmse = sorted(
            rows,
            key=lambda row: (
                number(row["rmse"]),
                number(row["mae"]),
                int(row["streak_threshold"]),
                int(row["grace_spans"]),
            ),
        )
        scope_results[scope_name] = {
            "default": default_row,
            "best_by_mae": rows[0] if rows else None,
            "best_by_rmse": by_rmse[0] if by_rmse else None,
            "top_by_mae": rows[:5],
        }
    return {
        "default_config": one_percent_grace_config(
            REGIME_GRACE_STREAK_THRESHOLD, REGIME_GRACE_SPANS
        ),
        "scopes": scope_results,
    }

def one_percent_grace_calibration_row(
    values: list[float],
    *,
    start_index: int,
    streak_threshold: int,
    grace_spans: int,
) -> dict[str, Any]:
    actual: list[float] = []
    predictions: list[float] = []
    for index in range(max(1, start_index), len(values)):
        previous = values[:index]
        actual.append(values[index])
        predictions.append(
            one_percent_regime_grace_prediction(
                previous,
                streak_threshold=streak_threshold,
                grace_spans=grace_spans,
                max_break_delta=REGIME_GRACE_MAX_BREAK_DELTA,
            )
        )
    metrics = regression_metrics(actual, predictions)
    return {
        **one_percent_grace_config(streak_threshold, grace_spans),
        "n": len(actual),
        "mae": metrics["mae"],
        "rmse": metrics["rmse"],
        "r2": metrics["r2"],
        "exact_match_share": rounded(
            sum(
                1
                for actual_value, predicted_value in zip(
                    actual, predictions, strict=True
                )
                if round(actual_value, 6) == round(predicted_value, 6)
            )
            / len(actual)
            if actual
            else None
        ),
    }

def one_percent_grace_config(
    streak_threshold: int, grace_spans: int
) -> dict[str, Any]:
    return {
        "streak_threshold": streak_threshold,
        "grace_spans": grace_spans,
        "max_break_delta_percent": REGIME_GRACE_MAX_BREAK_DELTA,
    }

def one_percent_regime_grace_prediction(
    previous_deltas: list[float],
    *,
    streak_threshold: int,
    grace_spans: int,
    max_break_delta: float,
) -> float:
    if not previous_deltas:
        return 0.0
    one_percent_streak = tail_streak(
        previous_deltas, predicate=is_one_percent_delta
    )
    if one_percent_streak >= streak_threshold:
        return 1.0
    break_age = small_break_age_after_one_percent_run(
        previous_deltas,
        streak_threshold=streak_threshold,
        max_break_delta=max_break_delta,
    )
    if break_age is not None and break_age <= grace_spans:
        return 1.0
    return previous_deltas[-1]

def small_break_age_after_one_percent_run(
    values: list[float], *, streak_threshold: int, max_break_delta: float
) -> int | None:
    if not values or is_one_percent_delta(values[-1]):
        return None
    index = len(values) - 1
    break_age = 0
    while (
        index >= 0
        and not is_one_percent_delta(values[index])
        and values[index] <= max_break_delta
    ):
        break_age += 1
        index -= 1
    if break_age == 0:
        return None
    preceding_streak = 0
    while index >= 0 and is_one_percent_delta(values[index]):
        preceding_streak += 1
        index -= 1
    if preceding_streak >= streak_threshold:
        return break_age
    return None
