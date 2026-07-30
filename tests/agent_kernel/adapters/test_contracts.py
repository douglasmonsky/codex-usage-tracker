from __future__ import annotations

from datetime import datetime, timezone

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.normalize import (
    NormalizationError,
    normalize_record,
    normalize_timestamp,
)
from codex_usage_tracker.agent_kernel.adapters.contracts import (
    SourceRange,
    TimeRangeHint,
)


def test_source_range_occurrence_coordinates_include_physical_manifestation() -> None:
    first = SourceRange("manifestation:one", 1, "revision-1", 0, 0, 4)
    second = SourceRange("manifestation:two", 2, "revision-1", 0, 0, 4)
    assert first.coordinate_tuple != second.coordinate_tuple


def test_time_hint_uses_half_open_source_and_closed_window_overlap() -> None:
    hint = TimeRangeHint(100, 200)
    assert hint.overlaps_closed_window(200, 300) is False
    assert hint.overlaps_closed_window(199, 200) is True


def test_iso_timestamp_normalization_does_not_use_float_rounding() -> None:
    text = "1969-12-31T23:59:59.999999-00:00"
    expected = int((datetime.fromisoformat(text).astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1_000_000)
    actual, basis = normalize_timestamp(text)
    assert (actual, basis) == (expected, "upstream_iso8601")


def test_timestamp_precision_and_body_fields_fail_closed() -> None:
    with pytest.raises(NormalizationError, match="lossy"):
        normalize_timestamp("2026-01-01T00:00:00.1234567Z")


def test_codex_envelope_is_translated_without_crossing_body_boundary() -> None:
    observation = normalize_record(
        {
            "type": "response.completed",
            "id": "native-call-001",
            "timestamp": "2026-01-01T00:00:00Z",
            "session_id": "native-session-001",
            "turn_id": "native-turn-001",
            "model": "gpt-synthetic",
            "usage": {
                "uncached_input_tokens": 10,
                "cached_input_tokens": 20,
                "reasoning_tokens": 3,
                "output_tokens": 4,
            },
            "response": "must not be copied",
        },
        SourceRange("source-manifestation:v1:test", 1, "revision-1", 0, 0, 20),
    )
    assert observation.observation_type == "ModelCallObserved"
    assert observation.logical_id.startswith("call:v1:")
    assert observation.payload["uncached_input_tokens"] == 10
    assert "response" not in observation.payload
