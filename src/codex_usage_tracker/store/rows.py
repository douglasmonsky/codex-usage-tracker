"""SQLite row conversion helpers for store read models."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def usage_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return annotate_usage_row_timing(row_to_dict(row))


def annotate_usage_row_timing(row: dict[str, Any]) -> dict[str, Any]:
    previous_timestamp = optional_text(row.get("previous_call_event_timestamp"))
    previous_session_id = row.pop("previous_call_session_id", None)
    previous_turn_id = row.pop("previous_call_turn_id", None)
    event_timestamp = optional_text(row.get("event_timestamp"))
    turn_timestamp = optional_text(row.get("turn_timestamp"))
    same_turn_previous = (
        previous_timestamp is not None
        and previous_session_id == row.get("session_id")
        and previous_turn_id is not None
        and previous_turn_id == row.get("turn_id")
    )
    call_started_at = previous_timestamp if same_turn_previous else turn_timestamp

    row["previous_call_event_timestamp"] = previous_timestamp
    row["call_started_at"] = call_started_at
    row["call_duration_seconds"] = seconds_between(call_started_at, event_timestamp)
    row["previous_call_delta_seconds"] = seconds_between(previous_timestamp, event_timestamp)
    return row


def seconds_between(start: str | None, end: str | None) -> float | None:
    start_time = parse_timestamp(start)
    end_time = parse_timestamp(end)
    if start_time is None or end_time is None:
        return None
    seconds = (end_time - start_time).total_seconds()
    if seconds < 0:
        return None
    return round(seconds, 3)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
