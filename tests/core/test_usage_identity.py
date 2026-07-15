from codex_usage_tracker.core.usage_identity import (
    FINGERPRINT_VERSION,
    extract_upstream_usage_id,
    usage_identity_from_values,
)


def _values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "event_timestamp": "2026-07-14T12:00:00Z",
        "turn_id": "turn-a",
        "turn_timestamp": "2026-07-14T11:59:00Z",
        "model": "gpt-5.5",
        "effort": "high",
        "model_context_window": 258400,
        "input_tokens": 90,
        "cached_input_tokens": 20,
        "output_tokens": 10,
        "reasoning_output_tokens": 5,
        "total_tokens": 100,
        "cumulative_input_tokens": 190,
        "cumulative_cached_input_tokens": 40,
        "cumulative_output_tokens": 20,
        "cumulative_reasoning_output_tokens": 10,
        "cumulative_total_tokens": 200,
        "rate_limit_plan_type": "pro",
        "rate_limit_limit_id": "codex",
        "rate_limit_primary_used_percent": 2.5,
        "rate_limit_primary_window_minutes": 300,
        "rate_limit_primary_resets_at": 1781562696,
        "rate_limit_secondary_used_percent": 29.0,
        "rate_limit_secondary_window_minutes": 10080,
        "rate_limit_secondary_resets_at": 1781887793,
    }
    values.update(overrides)
    return values


def test_strict_identity_ignores_physical_session_and_source_fields() -> None:
    original = usage_identity_from_values(
        {**_values(), "session_id": "original", "source_file": "/original.jsonl"}
    )
    clone = usage_identity_from_values(
        {**_values(), "session_id": "clone", "source_file": "/clone.jsonl"}
    )
    assert original == clone
    assert original.usage_fingerprint.startswith(f"{FINGERPRINT_VERSION}:")


def test_equal_tokens_with_different_timestamp_do_not_match() -> None:
    assert (
        usage_identity_from_values(_values()).usage_fingerprint
        != usage_identity_from_values(
            _values(event_timestamp="2026-07-14T12:01:00Z")
        ).usage_fingerprint
    )


def test_recognized_upstream_id_takes_precedence() -> None:
    upstream = extract_upstream_usage_id({"event_id": "evt-123"}, {"type": "token_count"}, {})
    assert (
        usage_identity_from_values(_values(), upstream_usage_id=upstream).usage_fingerprint
        == usage_identity_from_values(
            _values(event_timestamp="2026-07-14T13:00:00Z"), upstream_usage_id=upstream
        ).usage_fingerprint
    )


def test_generic_id_is_not_an_upstream_usage_id() -> None:
    assert extract_upstream_usage_id({"id": "session-id"}, {}, {}) is None


def test_upstream_ids_ignore_malformed_values_and_strip_valid_values() -> None:
    assert (
        extract_upstream_usage_id({"event_id": "  evt-123  "}, {}, {})
        == "envelope.event_id:evt-123"
    )
    for value in ("", "   ", 123, None):
        assert extract_upstream_usage_id({"event_id": value}, {}, {}) is None
