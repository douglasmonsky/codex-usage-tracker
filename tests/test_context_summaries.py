from __future__ import annotations

from codex_usage_tracker.context_summaries import (
    dedupe_chat_message_echoes,
    summarize_payload,
    summarize_turn_context,
)


def test_summarize_turn_context_formats_available_fields() -> None:
    text = summarize_turn_context(
        {
            "turn_id": "turn-1",
            "cwd": "/tmp/project",
            "model": "gpt-test",
            "summary": "short summary",
        }
    )

    assert "turn_id: turn-1" in text
    assert "cwd: /tmp/project" in text
    assert "model: gpt-test" in text
    assert "summary: short summary" in text


def test_summarize_payload_hides_tool_output_by_default() -> None:
    summary = summarize_payload(
        "response_item",
        {"type": "function_call_output", "output": "SECRET TOOL OUTPUT"},
        include_tool_output=False,
        include_compaction_history=False,
    )

    assert summary is not None
    assert summary["tool_output_omitted"] is True
    assert "SECRET TOOL OUTPUT" not in summary["text"]


def test_summarize_payload_includes_token_count_summary() -> None:
    summary = summarize_payload(
        "event_msg",
        {
            "type": "token_count",
            "info": {
                "last_token_usage": {"input_tokens": 10, "cached_input_tokens": 4},
                "total_token_usage": {"input_tokens": 20, "cached_input_tokens": 7},
                "model_context_window": 100,
            },
        },
        include_tool_output=False,
        include_compaction_history=False,
    )

    assert summary is not None
    assert summary["label"] == "Token count"
    assert summary["token_usage"]["last_token_usage"]["uncached_input_tokens"] == 6
    assert summary["token_usage"]["total_token_usage"]["uncached_input_tokens"] == 13


def test_summarize_payload_carries_safe_structured_event_duration() -> None:
    summary = summarize_payload(
        "event_msg",
        {
            "type": "mcp_tool_call_end",
            "call_id": "call-1",
            "tool_name": "local-tool",
            "duration_ms": 1250,
        },
        include_tool_output=False,
        include_compaction_history=False,
    )

    assert summary is not None
    assert summary["carry_into_next_turn"] is True
    assert summary["action_duration_ms"] == 1250


def test_summarize_payload_optionally_includes_compaction_history() -> None:
    summary = summarize_payload(
        "compacted",
        {
            "replacement_history": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"text": "replacement text"}],
                }
            ]
        },
        include_tool_output=False,
        include_compaction_history=True,
    )

    assert summary is not None
    assert summary["compaction"]["replacement_history_included"] is True
    assert summary["compaction"]["replacement_history"][0]["text"] == "replacement text"


def test_dedupe_chat_message_echoes_prefers_structured_message() -> None:
    entries = [
        {"label": "user_message", "text": "same text"},
        {"label": "message / user", "text": "same text"},
        {"label": "agent_message", "text": "assistant text"},
        {"label": "message / assistant", "text": "assistant text"},
    ]

    deduped = dedupe_chat_message_echoes(entries)

    assert [entry["label"] for entry in deduped] == ["message / user", "message / assistant"]
