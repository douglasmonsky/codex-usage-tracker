"""Walk-forward history state helpers for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain_feature_history import (
    is_one_percent_delta,
    same_value_tail_streak,
    streak_bucket,
    tail_streak,
)
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import (
    second_bucket,
    span_wall_time_seconds,
)


def history_state_for_span(
    spans: list[UsageDeltaSpan],
    index: int,
    metadata: dict[str, Any],
    previous_deltas: list[float],
) -> dict[str, Any]:
    if previous_deltas:
        one_percent_streak = tail_streak(
            previous_deltas, predicate=is_one_percent_delta
        )
        low_delta_streak = tail_streak(
            previous_deltas, predicate=lambda value: value <= 1.0
        )
        same_delta_streak = same_value_tail_streak(previous_deltas)
        previous_delta_value = previous_deltas[-1]
        previous_delta_bucket = delta_bucket(previous_deltas[-1])
    else:
        one_percent_streak = 0
        low_delta_streak = 0
        same_delta_streak = 0
        previous_delta_value = 0.0
        previous_delta_bucket = "missing"
    return {
        **metadata,
        "previous_delta_value": previous_delta_value,
        "previous_delta_bucket": previous_delta_bucket,
        "one_percent_streak_count": one_percent_streak,
        "one_percent_streak_bucket": streak_bucket(one_percent_streak),
        "low_delta_streak_count": low_delta_streak,
        "low_delta_streak_bucket": streak_bucket(low_delta_streak),
        "same_delta_streak_count": same_delta_streak,
        "same_delta_streak_bucket": streak_bucket(same_delta_streak),
        "previous_span_wall_time_bucket": previous_span_wall_time_bucket(
            spans, index
        ),
        "previous_call_duration_bucket": previous_call_duration_bucket(spans, index),
    }


def previous_span_wall_time_bucket(spans: list[UsageDeltaSpan], index: int) -> str:
    if index <= 0:
        return "missing"
    return second_bucket(span_wall_time_seconds(spans[index - 1]))


def previous_call_duration_bucket(spans: list[UsageDeltaSpan], index: int) -> str:
    if index <= 0:
        return "missing"
    return second_bucket(
        spans[index - 1].timing_totals.get("call_duration_seconds", 0.0)
    )


def delta_bucket(value: float) -> str:
    rounded = round(value, 6)
    if rounded == 1.0:
        return "1_pct"
    if rounded == 2.0:
        return "2_pct"
    if rounded == 3.0:
        return "3_pct"
    if rounded <= 0:
        return "0_pct"
    if rounded < 1.0:
        return "0_1_pct"
    if rounded < 5.0:
        return "3_5_pct"
    if rounded < 10.0:
        return "5_10_pct"
    if rounded < 25.0:
        return "10_25_pct"
    return "25_plus_pct"
