"""Causal history feature helpers for usage-drain modeling."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain_utils import (
    ceil_to_visible_tick,
    number,
    parse_timestamp,
    value_mode,
    value_stddev,
)


def add_causal_history_features(rows: list[dict[str, Any]]) -> None:
    """Attach walk-forward features that only use previous closed spans."""

    previous_rows: list[dict[str, Any]] = []
    bucket_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    date_rows: dict[str, list[dict[str, Any]]] = {}
    hour_rows: dict[str, list[dict[str, Any]]] = {}
    day_of_week_rows: dict[str, list[dict[str, Any]]] = {}
    ewma_delta: float | None = None
    ewma_drain: float | None = None
    ewma_capacity: float | None = None
    remainder_states = {
        "previous": 0.0,
        "rolling3": 0.0,
        "rolling10": 0.0,
        "rolling10_median": 0.0,
        "ewma": 0.0,
    }
    alpha = 0.2
    for row in rows:
        bucket_key = (
            str(row.get("rate_limit_plan_type") or "missing"),
            str(row.get("rate_limit_limit_id") or "missing"),
        )
        date_key = str(row.get("date") or "missing")
        hour_key = str(row.get("hour_bucket") or "missing")
        day_of_week_key = str(row.get("day_of_week") or "missing")
        recent_bucket_rows = bucket_rows.get(bucket_key, [])
        recent_date_rows = date_rows.get(date_key, [])
        recent_hour_rows = hour_rows.get(hour_key, [])
        recent_day_of_week_rows = day_of_week_rows.get(day_of_week_key, [])
        row["previous_delta_percent"] = previous_value(previous_rows, "target")
        row["previous_drain_per_credit"] = previous_drain_per_credit(previous_rows)
        row["rolling3_delta_percent"] = rolling_mean(previous_rows, "target", 3)
        row["rolling10_delta_percent"] = rolling_mean(previous_rows, "target", 10)
        row["rolling50_delta_percent"] = rolling_mean(previous_rows, "target", 50)
        row["rolling10_median_delta_percent"] = rolling_median(
            previous_rows, "target", 10
        )
        row["rolling10_mode_delta_percent"] = rolling_mode(previous_rows, "target", 10)
        row["rolling10_delta_stddev"] = rolling_stddev(previous_rows, "target", 10)
        row["rolling50_delta_stddev"] = rolling_stddev(previous_rows, "target", 50)
        one_percent_streak = row_tail_streak(
            previous_rows,
            predicate=lambda previous: is_one_percent_delta(
                number(previous.get("target"))
            ),
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
        row["hybrid_streak_delta_percent"] = (
            1.0
            if one_percent_streak >= 3
            else number(row["previous_delta_percent"])
            if same_delta_streak >= 2
            else number(row["rolling3_delta_percent"])
        )
        row["rolling3drain_per_credit"] = rolling_drain_per_credit(previous_rows, 3)
        row["rolling10drain_per_credit"] = rolling_drain_per_credit(previous_rows, 10)
        row["rolling50drain_per_credit"] = rolling_drain_per_credit(previous_rows, 50)
        row["rolling10_low_delta_share"] = rolling_low_delta_share(previous_rows, 10)
        capacity_estimates = {
            "previous": previous_capacity_per_visible_percent(previous_rows),
            "rolling3": rolling_capacity_per_visible_percent(previous_rows, 3),
            "rolling10": rolling_capacity_per_visible_percent(previous_rows, 10),
            "rolling10_median": rolling_capacity_median_per_visible_percent(
                previous_rows, 10
            ),
            "ewma": ewma_capacity or 0.0,
        }
        row["previous_capacity_credits_per_percent"] = capacity_estimates["previous"]
        row["rolling3_capacity_credits_per_percent"] = capacity_estimates["rolling3"]
        row["rolling10_capacity_credits_per_percent"] = capacity_estimates["rolling10"]
        row["rolling10_median_capacity_credits_per_percent"] = capacity_estimates[
            "rolling10_median"
        ]
        row["ewma_capacity_credits_per_percent"] = capacity_estimates["ewma"]
        current_credits = number(row.get("standard_usage_credits"))
        for capacity_name, capacity in capacity_estimates.items():
            prefix = (
                "rolling10_median"
                if capacity_name == "rolling10_median"
                else capacity_name
            )
            row[f"{prefix}_capacity_delta_prediction"] = (
                current_credits / capacity if capacity > 0 else 0.0
            )
        attach_remainder_features(
            row,
            prefix="rolling3",
            capacity=capacity_estimates["rolling3"],
            current_credits=current_credits,
            remainder=remainder_states["rolling3"],
        )
        attach_remainder_features(
            row,
            prefix="ewma",
            capacity=capacity_estimates["ewma"],
            current_credits=current_credits,
            remainder=remainder_states["ewma"],
        )
        rolling50 = number(row["rolling50_delta_percent"])
        row["rolling3_to_50_delta_ratio"] = (
            number(row["rolling3_delta_percent"]) / rolling50 if rolling50 > 0 else 0.0
        )
        row["same_bucket_rolling10_delta_percent"] = rolling_mean(
            recent_bucket_rows, "target", 10
        )
        row["same_bucket_rolling10_mode_delta_percent"] = rolling_mode(
            recent_bucket_rows, "target", 10
        )
        row["same_bucket_rolling10drain_per_credit"] = rolling_drain_per_credit(
            recent_bucket_rows, 10
        )
        row["same_bucket_seen_count"] = float(len(recent_bucket_rows))
        row["same_date_rolling10_delta_percent"] = rolling_mean(
            recent_date_rows, "target", 10
        )
        row["same_date_rolling10_mode_delta_percent"] = rolling_mode(
            recent_date_rows, "target", 10
        )
        row["same_date_seen_count"] = float(len(recent_date_rows))
        row["same_hour_rolling10_delta_percent"] = rolling_mean(
            recent_hour_rows, "target", 10
        )
        row["same_hour_rolling10_mode_delta_percent"] = rolling_mode(
            recent_hour_rows, "target", 10
        )
        row["same_hour_seen_count"] = float(len(recent_hour_rows))
        row["same_day_of_week_rolling10_delta_percent"] = rolling_mean(
            recent_day_of_week_rows, "target", 10
        )
        row["same_day_of_week_rolling10_mode_delta_percent"] = rolling_mode(
            recent_day_of_week_rows, "target", 10
        )
        row["same_day_of_week_seen_count"] = float(len(recent_day_of_week_rows))
        row["ewma_delta_percent"] = ewma_delta or 0.0
        row["ewmadrain_per_credit"] = ewma_drain or 0.0

        current_delta = number(row.get("target"))
        current_drain = drain_per_credit(row)
        current_capacity = capacity_per_visible_percent(row)
        ewma_delta = (
            current_delta
            if ewma_delta is None
            else (alpha * current_delta) + ((1 - alpha) * ewma_delta)
        )
        ewma_drain = (
            current_drain
            if ewma_drain is None
            else (alpha * current_drain) + ((1 - alpha) * ewma_drain)
        )
        ewma_capacity = (
            current_capacity
            if ewma_capacity is None
            else (alpha * current_capacity) + ((1 - alpha) * ewma_capacity)
        )
        for capacity_name, capacity in capacity_estimates.items():
            remainder_states[capacity_name] = updated_remainder_credits(
                remainder_states[capacity_name],
                current_credits=current_credits,
                actual_delta=current_delta,
                capacity=capacity,
            )
        previous_rows.append(row)
        bucket_rows.setdefault(bucket_key, []).append(row)
        date_rows.setdefault(date_key, []).append(row)
        hour_rows.setdefault(hour_key, []).append(row)
        day_of_week_rows.setdefault(day_of_week_key, []).append(row)


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
