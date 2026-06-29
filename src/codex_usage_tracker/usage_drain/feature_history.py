"""Causal history feature helpers for usage-drain modeling."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain.utils import (
    ceil_to_visible_tick,
    number,
    parse_timestamp,
    value_mode,
    value_stddev,
)

_HISTORY_ALPHA = 0.2


@dataclass
class _CausalHistoryState:
    previous_rows: list[dict[str, Any]] = field(default_factory=list)
    bucket_rows: dict[tuple[str, str], list[dict[str, Any]]] = field(default_factory=dict)
    date_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    hour_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    day_of_week_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    ewma_delta: float | None = None
    ewma_drain: float | None = None
    ewma_capacity: float | None = None
    remainder_states: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.remainder_states:
            self.remainder_states = {
                "previous": 0.0,
                "rolling3": 0.0,
                "rolling10": 0.0,
                "rolling10_median": 0.0,
                "ewma": 0.0,
            }


@dataclass(frozen=True)
class _HistoryKeys:
    bucket: tuple[str, str]
    date: str
    hour: str
    day_of_week: str


def add_causal_history_features(rows: list[dict[str, Any]]) -> None:
    """Attach walk-forward features that only use previous closed spans."""

    state = _CausalHistoryState()
    for row in rows:
        keys = _history_keys(row)
        _attach_global_history_features(row, state)
        _attach_streak_features(row, state.previous_rows)
        capacity_estimates = _capacity_estimates(state)
        current_credits = number(row.get("standard_usage_credits"))
        _attach_capacity_features(row, capacity_estimates, current_credits)
        attach_remainder_features(
            row,
            prefix="rolling3",
            capacity=capacity_estimates["rolling3"],
            current_credits=current_credits,
            remainder=state.remainder_states["rolling3"],
        )
        attach_remainder_features(
            row,
            prefix="ewma",
            capacity=capacity_estimates["ewma"],
            current_credits=current_credits,
            remainder=state.remainder_states["ewma"],
        )
        _attach_same_period_features(row, state, keys)
        _attach_ewma_features(row, state)
        _update_history_state(state, keys, row, capacity_estimates, current_credits)


def _history_keys(row: dict[str, Any]) -> _HistoryKeys:
    return _HistoryKeys(
        bucket=(
            str(row.get("rate_limit_plan_type") or "missing"),
            str(row.get("rate_limit_limit_id") or "missing"),
        ),
        date=str(row.get("date") or "missing"),
        hour=str(row.get("hour_bucket") or "missing"),
        day_of_week=str(row.get("day_of_week") or "missing"),
    )


def _attach_global_history_features(
    row: dict[str, Any],
    state: _CausalHistoryState,
) -> None:
    previous_rows = state.previous_rows
    row["previous_delta_percent"] = previous_value(previous_rows, "target")
    row["previous_drain_per_credit"] = previous_drain_per_credit(previous_rows)
    row["rolling3_delta_percent"] = rolling_mean(previous_rows, "target", 3)
    row["rolling10_delta_percent"] = rolling_mean(previous_rows, "target", 10)
    row["rolling50_delta_percent"] = rolling_mean(previous_rows, "target", 50)
    row["rolling10_median_delta_percent"] = rolling_median(previous_rows, "target", 10)
    row["rolling10_mode_delta_percent"] = rolling_mode(previous_rows, "target", 10)
    row["rolling10_delta_stddev"] = rolling_stddev(previous_rows, "target", 10)
    row["rolling50_delta_stddev"] = rolling_stddev(previous_rows, "target", 50)
    row["rolling3drain_per_credit"] = rolling_drain_per_credit(previous_rows, 3)
    row["rolling10drain_per_credit"] = rolling_drain_per_credit(previous_rows, 10)
    row["rolling50drain_per_credit"] = rolling_drain_per_credit(previous_rows, 50)
    row["rolling10_low_delta_share"] = rolling_low_delta_share(previous_rows, 10)
    rolling50 = number(row["rolling50_delta_percent"])
    row["rolling3_to_50_delta_ratio"] = (
        number(row["rolling3_delta_percent"]) / rolling50 if rolling50 > 0 else 0.0
    )


def _attach_streak_features(row: dict[str, Any], previous_rows: list[dict[str, Any]]) -> None:
    one_percent_streak = row_tail_streak(
        previous_rows,
        predicate=lambda previous: is_one_percent_delta(number(previous.get("target"))),
    )
    low_delta_streak = row_tail_streak(
        previous_rows,
        predicate=lambda previous: number(previous.get("target")) <= 1.0,
    )
    same_delta_streak = same_target_tail_streak(previous_rows)
    high_delta_streak = row_tail_streak(
        previous_rows,
        predicate=lambda previous: number(previous.get("target")) > 1.0,
    )
    row["one_percent_streak"] = float(one_percent_streak)
    row["low_delta_streak"] = float(low_delta_streak)
    row["same_delta_streak"] = float(same_delta_streak)
    row["high_delta_streak"] = float(high_delta_streak)
    row["hybrid_streak_delta_percent"] = _hybrid_streak_delta(
        row,
        one_percent_streak,
        same_delta_streak,
    )


def _hybrid_streak_delta(
    row: dict[str, Any],
    one_percent_streak: int,
    same_delta_streak: int,
) -> float:
    if one_percent_streak >= 3:
        return 1.0
    if same_delta_streak >= 2:
        return number(row["previous_delta_percent"])
    return number(row["rolling3_delta_percent"])


def _capacity_estimates(state: _CausalHistoryState) -> dict[str, float]:
    previous_rows = state.previous_rows
    return {
        "previous": previous_capacity_per_visible_percent(previous_rows),
        "rolling3": rolling_capacity_per_visible_percent(previous_rows, 3),
        "rolling10": rolling_capacity_per_visible_percent(previous_rows, 10),
        "rolling10_median": rolling_capacity_median_per_visible_percent(
            previous_rows, 10
        ),
        "ewma": state.ewma_capacity or 0.0,
    }


def _attach_capacity_features(
    row: dict[str, Any],
    capacity_estimates: dict[str, float],
    current_credits: float,
) -> None:
    row["previous_capacity_credits_per_percent"] = capacity_estimates["previous"]
    row["rolling3_capacity_credits_per_percent"] = capacity_estimates["rolling3"]
    row["rolling10_capacity_credits_per_percent"] = capacity_estimates["rolling10"]
    row["rolling10_median_capacity_credits_per_percent"] = capacity_estimates[
        "rolling10_median"
    ]
    row["ewma_capacity_credits_per_percent"] = capacity_estimates["ewma"]
    for capacity_name, capacity in capacity_estimates.items():
        row[f"{capacity_name}_capacity_delta_prediction"] = (
            current_credits / capacity if capacity > 0 else 0.0
        )


def _attach_same_period_features(
    row: dict[str, Any],
    state: _CausalHistoryState,
    keys: _HistoryKeys,
) -> None:
    _attach_same_rows_features(
        row,
        prefix="same_bucket",
        rows=state.bucket_rows.get(keys.bucket, []),
        include_drain=True,
    )
    _attach_same_rows_features(
        row,
        prefix="same_date",
        rows=state.date_rows.get(keys.date, []),
    )
    _attach_same_rows_features(
        row,
        prefix="same_hour",
        rows=state.hour_rows.get(keys.hour, []),
    )
    _attach_same_rows_features(
        row,
        prefix="same_day_of_week",
        rows=state.day_of_week_rows.get(keys.day_of_week, []),
    )


def _attach_same_rows_features(
    row: dict[str, Any],
    *,
    prefix: str,
    rows: list[dict[str, Any]],
    include_drain: bool = False,
) -> None:
    row[f"{prefix}_rolling10_delta_percent"] = rolling_mean(rows, "target", 10)
    row[f"{prefix}_rolling10_mode_delta_percent"] = rolling_mode(rows, "target", 10)
    if include_drain:
        row[f"{prefix}_rolling10drain_per_credit"] = rolling_drain_per_credit(rows, 10)
    row[f"{prefix}_seen_count"] = float(len(rows))


def _attach_ewma_features(row: dict[str, Any], state: _CausalHistoryState) -> None:
    row["ewma_delta_percent"] = state.ewma_delta or 0.0
    row["ewmadrain_per_credit"] = state.ewma_drain or 0.0


def _update_history_state(
    state: _CausalHistoryState,
    keys: _HistoryKeys,
    row: dict[str, Any],
    capacity_estimates: dict[str, float],
    current_credits: float,
) -> None:
    current_delta = number(row.get("target"))
    state.ewma_delta = _updated_ewma(state.ewma_delta, current_delta)
    state.ewma_drain = _updated_ewma(state.ewma_drain, drain_per_credit(row))
    state.ewma_capacity = _updated_ewma(
        state.ewma_capacity,
        capacity_per_visible_percent(row),
    )
    for capacity_name, capacity in capacity_estimates.items():
        state.remainder_states[capacity_name] = updated_remainder_credits(
            state.remainder_states[capacity_name],
            current_credits=current_credits,
            actual_delta=current_delta,
            capacity=capacity,
        )
    state.previous_rows.append(row)
    state.bucket_rows.setdefault(keys.bucket, []).append(row)
    state.date_rows.setdefault(keys.date, []).append(row)
    state.hour_rows.setdefault(keys.hour, []).append(row)
    state.day_of_week_rows.setdefault(keys.day_of_week, []).append(row)


def _updated_ewma(previous: float | None, value: float) -> float:
    if previous is None:
        return value
    return (_HISTORY_ALPHA * value) + ((1 - _HISTORY_ALPHA) * previous)


def attach_remainder_features(
    row: dict[str, Any],
    *,
    prefix: str,
    capacity: float,
    current_credits: float,
    remainder: float,
) -> None:
    row[f"{prefix}_remainder_credits"] = remainder
    row[f"{prefix}_remainder_fraction"] = (
        min(max(remainder / capacity, 0.0), 1.0) if capacity > 0 else 0.0
    )
    accumulated = (remainder + current_credits) / capacity if capacity > 0 else 0.0
    row[f"{prefix}_remainder_floor_delta_prediction"] = (
        float(math.floor(accumulated + 1e-9)) if accumulated > 0 else 0.0
    )
    row[f"{prefix}_remainder_ceiling_delta_prediction"] = ceil_to_visible_tick(
        accumulated
    )


def updated_remainder_credits(
    previous_remainder: float,
    *,
    current_credits: float,
    actual_delta: float,
    capacity: float,
) -> float:
    if capacity <= 0:
        return 0.0
    return (previous_remainder + current_credits - (actual_delta * capacity)) % capacity


def capacity_per_visible_percent(row: dict[str, Any]) -> float:
    delta = number(row.get("target"))
    if delta <= 0:
        return 0.0
    return number(row.get("standard_usage_credits")) / delta


def previous_capacity_per_visible_percent(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return capacity_per_visible_percent(rows[-1])


def rolling_capacity_per_visible_percent(
    rows: list[dict[str, Any]], window: int
) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return sum(capacity_per_visible_percent(row) for row in selected) / len(selected)


def rolling_capacity_median_per_visible_percent(
    rows: list[dict[str, Any]], window: int
) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return float(median(capacity_per_visible_percent(row) for row in selected))


def previous_value(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return number(rows[-1].get(field))


def previous_drain_per_credit(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return drain_per_credit(rows[-1])


def rolling_mean(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return sum(number(row.get(field)) for row in selected) / len(selected)


def rolling_median(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return float(median(number(row.get(field)) for row in selected))


def rolling_mode(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return value_mode([number(row.get(field)) for row in selected])


def rolling_stddev(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return value_stddev([number(row.get(field)) for row in selected])


def rolling_drain_per_credit(rows: list[dict[str, Any]], window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return sum(drain_per_credit(row) for row in selected) / len(selected)


def rolling_low_delta_share(rows: list[dict[str, Any]], window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    low_count = sum(1 for row in selected if number(row.get("target")) <= 1.0)
    return low_count / len(selected)


def row_tail_streak(
    rows: list[dict[str, Any]], *, predicate: Any
) -> int:
    count = 0
    for row in reversed(rows):
        if not predicate(row):
            break
        count += 1
    return count


def tail_streak(values: list[float], *, predicate: Any) -> int:
    count = 0
    for value in reversed(values):
        if not predicate(value):
            break
        count += 1
    return count


def same_target_tail_streak(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    return tail_streak(
        [number(row.get("target")) for row in rows],
        predicate=lambda value: round(value, 6) == round(number(rows[-1].get("target")), 6),
    )


def same_value_tail_streak(values: list[float]) -> int:
    if not values:
        return 0
    target = round(values[-1], 6)
    return tail_streak(values, predicate=lambda value: round(value, 6) == target)


def is_one_percent_delta(value: float) -> bool:
    return round(value, 6) == 1.0


def streak_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value <= 2:
        return str(value)
    if value <= 9:
        return "3_9"
    if value <= 49:
        return "10_49"
    if value <= 199:
        return "50_199"
    return "200_plus"


def date_label(timestamp: str) -> str:
    parsed = parse_timestamp(timestamp)
    return parsed.date().isoformat() if parsed else "missing"


def drain_per_credit(row: dict[str, Any]) -> float:
    credits = number(row.get("standard_usage_credits"))
    if credits <= 0:
        return 0.0
    return number(row.get("target")) / credits
