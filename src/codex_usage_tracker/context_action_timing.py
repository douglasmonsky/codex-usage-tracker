"""Action timing helpers for selected context evidence entries."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def annotate_action_timing(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Annotate context entries with timing gaps derived from entry timestamps."""
    first_ms: float | None = None
    previous_ms: float | None = None
    last_ms: float | None = None
    timed_entries = 0
    slowest_gap_ms = 0.0

    for entry in entries:
        timestamp_ms = _timestamp_epoch_ms(entry.get("timestamp"))
        if timestamp_ms is None:
            continue
        first_ms = timestamp_ms if first_ms is None else first_ms
        old_previous_ms = previous_ms
        _annotate_entry_timing(
            entry,
            first_ms=first_ms,
            previous_ms=old_previous_ms,
            timestamp_ms=timestamp_ms,
        )
        slowest_gap_ms = _slowest_gap_ms(
            slowest_gap_ms,
            previous_ms=old_previous_ms,
            timestamp_ms=timestamp_ms,
        )
        previous_ms = timestamp_ms
        last_ms = timestamp_ms
        timed_entries += 1

    return {
        "available": timed_entries > 1,
        "scope": "selected_turn_evidence_entries",
        "source": "entry_timestamps",
        "timed_entry_count": timed_entries,
        "total_elapsed_ms": _total_elapsed_ms(first_ms, last_ms),
        "slowest_gap_ms": normalize_millisecond_value(slowest_gap_ms),
    }


def normalize_millisecond_value(value: float) -> int | float:
    """Round millisecond values without keeping unnecessary decimals."""
    rounded = round(value, 3)
    return int(rounded) if rounded.is_integer() else rounded


def _annotate_entry_timing(
    entry: dict[str, Any],
    *,
    first_ms: float,
    previous_ms: float | None,
    timestamp_ms: float,
) -> float:
    existing_timing = entry.get("action_timing")
    action_timing = dict(existing_timing) if isinstance(existing_timing, dict) else {}
    action_timing["since_turn_start_ms"] = _duration_between_ms(first_ms, timestamp_ms)
    if previous_ms is not None:
        action_timing["since_previous_entry_ms"] = _duration_between_ms(previous_ms, timestamp_ms)
    action_timing["timestamp_source"] = "entry.timestamp"
    entry["action_timing"] = action_timing
    return timestamp_ms


def _slowest_gap_ms(
    current_slowest_ms: float,
    *,
    previous_ms: float | None,
    timestamp_ms: float,
) -> float:
    if previous_ms is None:
        return current_slowest_ms
    gap_ms = _duration_between_ms(previous_ms, timestamp_ms)
    return max(current_slowest_ms, float(gap_ms))


def _total_elapsed_ms(first_ms: float | None, last_ms: float | None) -> int | float:
    if first_ms is None or last_ms is None:
        return 0
    return _duration_between_ms(first_ms, last_ms)


def _timestamp_epoch_ms(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp() * 1000


def _duration_between_ms(start_ms: float, end_ms: float) -> int | float:
    return normalize_millisecond_value(max(0.0, end_ms - start_ms))
