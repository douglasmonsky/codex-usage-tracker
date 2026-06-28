from __future__ import annotations

from codex_usage_tracker.context_serialized import (
    collect_serialized_envelope,
    quick_serialized_context_estimate,
    serialized_context_estimate,
)


def test_collect_serialized_envelope_groups_safe_bucket_metadata() -> None:
    raw_entries: list[dict[str, object]] = []
    field_buckets: dict[str, dict[str, object]] = {}

    collect_serialized_envelope(
        raw_entries=raw_entries,
        field_buckets=field_buckets,
        envelope={"payload": {"type": "function_call_output"}},
        entry_type="response_item",
        payload={
            "type": "function_call_output",
            "output": "SECRET OUTPUT " + "sk-proj-" + "abc123abc123abc123abc123",
            "encrypted_content": "opaque",
        },
        encoding=None,
    )

    assert raw_entries == [{"payload": {"type": "function_call_output"}}]
    assert field_buckets["visible_payload_fields"]["count"] == 1
    assert field_buckets["encrypted_reasoning_state"]["count"] == 1
    serialized_bucket_text = repr(field_buckets)
    assert "SECRET OUTPUT" not in serialized_bucket_text
    assert "sk-proj" not in serialized_bucket_text


def test_serialized_context_estimate_returns_top_buckets() -> None:
    field_buckets = {
        "small": {"key": "small", "token_estimate": 1},
        "large": {"key": "large", "token_estimate": 20},
    }

    estimate = serialized_context_estimate(
        raw_entries=[{"payload": {"message": "hello"}}],
        field_buckets=field_buckets,
        parse_errors=2,
        encoding=None,
        estimator="chars_per_4_fallback",
    )

    assert estimate["available"] is True
    assert estimate["scope"] == "selected_turn_raw_jsonl"
    assert estimate["parse_errors"] == 2
    assert estimate["upper_bound"] is True
    assert estimate["raw_text_returned"] is False
    assert [bucket["key"] for bucket in estimate["buckets"]] == ["large", "small"]
    assert estimate["deferred_buckets"] is False


def test_quick_serialized_context_estimate_defers_bucket_work() -> None:
    estimate = quick_serialized_context_estimate(
        raw_line_count=3,
        raw_json_char_count=9,
        parse_errors=1,
    )

    assert estimate["available"] is True
    assert estimate["scope"] == "selected_turn_raw_jsonl_fast_estimate"
    assert estimate["raw_json_token_estimate"] == 3
    assert estimate["token_estimator"] == "chars_per_4_fallback"
    assert estimate["buckets"] == []
    assert estimate["deferred"] is True
    assert estimate["deferred_buckets"] is True
