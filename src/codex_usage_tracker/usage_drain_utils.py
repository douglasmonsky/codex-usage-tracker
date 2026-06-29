"""Shared helpers for usage-drain analysis modules."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from codex_usage_tracker.usage_drain_types import UsageDeltaSpan


def ceil_to_visible_tick(value: float, *, tick_size: float = 1.0) -> float:
    if value <= 0 or tick_size <= 0:
        return 0.0
    return math.ceil((value / tick_size) - 1e-9) * tick_size


def span_wall_time_seconds(span: UsageDeltaSpan) -> float:
    return bounded_wall_time_seconds(
        span.start_event_timestamp,
        span.end_event_timestamp,
    )


def bounded_wall_time_seconds(start_timestamp: str, end_timestamp: str) -> float:
    start_dt = parse_timestamp(start_timestamp)
    end_dt = parse_timestamp(end_timestamp)
    if start_dt is None or end_dt is None:
        return 0.0
    return max((end_dt - start_dt).total_seconds(), 0.0)


def reset_phase_bucket(elapsed_fraction: float) -> str:
    if elapsed_fraction <= 0:
        return "missing"
    if elapsed_fraction < 0.25:
        return "first_quarter"
    if elapsed_fraction < 0.5:
        return "second_quarter"
    if elapsed_fraction < 0.75:
        return "third_quarter"
    return "fourth_quarter"


def numeric_bucket(
    value: float, *, width: float, max_value: float, suffix: str
) -> str:
    if value <= 0 or width <= 0:
        return f"0_{suffix}"
    if value >= max_value:
        return f"{format_bucket_number(max_value)}_plus_{suffix}"
    lower = math.floor(value / width) * width
    upper = lower + width
    return (
        f"{format_bucket_number(lower)}_"
        f"{format_bucket_number(upper)}_{suffix}"
    )


def minute_bucket(minutes: float) -> str:
    if minutes <= 0:
        return "0_min"
    if minutes <= 15:
        return "0_15_min"
    if minutes <= 30:
        return "15_30_min"
    if minutes <= 60:
        return "30_60_min"
    if minutes <= 120:
        return "60_120_min"
    if minutes <= 240:
        return "120_240_min"
    if minutes <= 360:
        return "240_360_min"
    return "360_plus_min"


def second_bucket(seconds: float) -> str:
    if seconds <= 0:
        return "0_sec"
    if seconds <= 30:
        return "0_30_sec"
    if seconds <= 60:
        return "30_60_sec"
    if seconds <= 120:
        return "60_120_sec"
    if seconds <= 300:
        return "120_300_sec"
    if seconds <= 900:
        return "300_900_sec"
    if seconds <= 1800:
        return "900_1800_sec"
    return "1800_plus_sec"


def format_bucket_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "_")


def value_mode(values: list[float]) -> float:
    if not values:
        return 0.0
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    max_count = max(counts.values())
    candidates = {value for value, count in counts.items() if count == max_count}
    for value in reversed(values):
        if value in candidates:
            return value
    return values[-1]


def value_stddev(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00+00:00"
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def reset_remaining_minutes(
    event_timestamp: datetime | None, reset_at: float | None
) -> float | None:
    if event_timestamp is None or reset_at is None:
        return None
    return max((reset_at - event_timestamp.timestamp()) / 60.0, 0.0)


def span_reset_timestamp(span: UsageDeltaSpan) -> float | None:
    if span.usage_window_resets_at is not None:
        return span.usage_window_resets_at
    return span.rate_limit_primary_resets_at


def span_window_minutes(span: UsageDeltaSpan) -> float:
    if span.usage_window_minutes is not None:
        return span.usage_window_minutes
    return span.rate_limit_primary_window_minutes or 0.0


def window_elapsed_minutes(window_minutes: float, reset_minutes: float) -> float:
    return max(window_minutes - reset_minutes, 0.0) if window_minutes > 0 else 0.0


def window_elapsed_fraction(elapsed_minutes: float, window_minutes: float) -> float:
    if window_minutes <= 0:
        return 0.0
    return min(max(elapsed_minutes / window_minutes, 0.0), 1.0)


def dominant_label(counts: dict[str, int], *, default: str) -> str:
    if not counts:
        return default
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0


def rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)
