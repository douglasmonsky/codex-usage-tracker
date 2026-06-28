from __future__ import annotations

from codex_usage_tracker import context_values


def test_redact_json_value_recurses_through_lists_and_dicts() -> None:
    redacted = context_values.redact_json_value(
        {
            "token": "sk-proj-" + "abcdefghijklmnopqrstuvwxyz1234567890",
            "items": ["Authorization: Bearer abc.def.ghi"],
        }
    )

    assert redacted == {
        "token": "[REDACTED_OPENAI_KEY]",
        "items": ["Authorization: Bearer [REDACTED_BEARER_TOKEN]"],
    }


def test_content_text_extracts_nested_text_pieces() -> None:
    assert context_values.content_text(
        [
            {"type": "input_text", "text": "first"},
            {"type": "output_text", "content": "second"},
            "third",
        ]
    ) == "first\nsecond\nthird"


def test_numeric_helpers_reject_invalid_values() -> None:
    assert context_values.positive_int("3") == 3
    assert context_values.positive_int("0") is None
    assert context_values.nonnegative_int("0") == 0
    assert context_values.nonnegative_int("-1") is None
    assert context_values.nonnegative_float("1.25") == 1.25
    assert context_values.nonnegative_float("-0.1") is None


def test_optional_str_and_jsonish_helpers() -> None:
    assert context_values.optional_str("value") == "value"
    assert context_values.optional_str("") is None
    assert context_values.compact_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert '"a": 1' in context_values.jsonish({"a": 1})
