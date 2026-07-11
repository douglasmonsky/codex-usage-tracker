from __future__ import annotations

from codex_usage_tracker.context.action_timing import (
    annotate_action_timing,
    normalize_millisecond_value,
)


def test_annotate_action_timing_adds_elapsed_and_gap_metadata() -> None:
    entries: list[dict[str, object]] = [
        {"timestamp": "2026-06-01T10:00:00Z", "text": "start"},
        {"timestamp": "2026-06-01T10:00:01Z", "text": "middle"},
        {"timestamp": "2026-06-01T10:00:01.500Z", "text": "end"},
    ]

    summary = annotate_action_timing(entries)

    assert summary == {
        "available": True,
        "scope": "selected_turn_evidence_entries",
        "source": "entry_timestamps",
        "timed_entry_count": 3,
        "total_elapsed_ms": 1500,
        "slowest_gap_ms": 1000,
    }
    assert entries[0]["action_timing"] == {
        "since_turn_start_ms": 0,
        "timestamp_source": "entry.timestamp",
    }
    middle_timing = entries[1]["action_timing"]
    end_timing = entries[2]["action_timing"]
    assert isinstance(middle_timing, dict)
    assert isinstance(end_timing, dict)
    assert middle_timing["since_turn_start_ms"] == 1000
    assert middle_timing["since_previous_entry_ms"] == 1000
    assert end_timing["since_previous_entry_ms"] == 500


def test_annotate_action_timing_ignores_invalid_timestamps() -> None:
    entries = [{"timestamp": "not-a-date"}, {"text": "missing"}]

    summary = annotate_action_timing(entries)

    assert summary["available"] is False
    assert summary["timed_entry_count"] == 0
    assert summary["total_elapsed_ms"] == 0
    assert "action_timing" not in entries[0]


def test_normalize_millisecond_value_trims_unneeded_decimal_places() -> None:
    assert normalize_millisecond_value(12.0) == 12
    assert normalize_millisecond_value(12.34567) == 12.346
