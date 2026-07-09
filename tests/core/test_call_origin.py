from __future__ import annotations

from codex_usage_tracker.core.call_origin import (
    CallOriginFlags,
    classify_call_origin,
    event_flags_from_envelope,
    fallback_call_origin,
)


def test_call_origin_classifies_metadata_segments_without_raw_text() -> None:
    user_fields = classify_call_origin(
        [
            CallOriginFlags(user_message=True),
            CallOriginFlags(tool_result=True),
        ]
    )
    compaction_fields = classify_call_origin([CallOriginFlags(compaction=True)])
    tool_fields = classify_call_origin([CallOriginFlags(tool_result=True)])
    continuation_fields = classify_call_origin([CallOriginFlags(codex_activity=True)])
    unknown_fields = classify_call_origin([])

    assert user_fields == _origin("user", "user_message", "high")
    assert compaction_fields == _origin("codex", "post_compaction", "high")
    assert tool_fields == _origin("codex", "tool_result", "high")
    assert continuation_fields == _origin("codex", "agent_continuation", "medium")
    assert unknown_fields == _origin("unknown", "no_signal", "low")


def test_call_origin_reads_only_event_shape_metadata() -> None:
    assert (
        event_flags_from_envelope(
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "SECRET RAW PROMPT"}],
                },
            )
        ).user_message
        is True
    )
    assert (
        event_flags_from_envelope(
            _entry("response_item", {"type": "function_call_output", "output": "SECRET"})
        ).tool_result
        is True
    )
    assert (
        event_flags_from_envelope(
            _entry("event_msg", {"type": "context_compacted", "replacement_history": ["SECRET"]})
        ).compaction
        is True
    )
    assert (
        event_flags_from_envelope(
            _entry(
                "response_item",
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "SECRET RAW ANSWER"}],
                },
            )
        ).codex_activity
        is True
    )


def test_call_origin_falls_back_to_subagent_metadata_for_migrated_rows() -> None:
    subagent_fields = fallback_call_origin(
        {
            "record_id": "subagent",
            "thread_source": "subagent",
        }
    )
    normal_fields = fallback_call_origin(
        {
            "record_id": "normal",
            "thread_source": "user",
        }
    )

    assert subagent_fields == _origin("codex", "thread_source", "medium")
    assert normal_fields == _origin("unknown", "missing_origin", "low")


def test_event_flags_from_envelope_detects_event_message_user_shape() -> None:
    flags = event_flags_from_envelope({"type": "event_msg", "payload": {"type": "user_message"}})

    assert flags.user_message


def test_event_flags_from_envelope_detects_mcp_tool_result_shape() -> None:
    flags = event_flags_from_envelope(
        {"type": "event_msg", "payload": {"type": "mcp_tool_call_end"}}
    )

    assert flags.tool_result


def test_event_flags_from_envelope_detects_agent_event_activity_shape() -> None:
    flags = event_flags_from_envelope({"type": "event_msg", "payload": {"type": "agent_message"}})

    assert flags.codex_activity


def _origin(initiator: str, reason: str, confidence: str) -> dict[str, str]:
    return {
        "call_initiator": initiator,
        "call_initiator_reason": reason,
        "call_initiator_confidence": confidence,
    }


def _entry(entry_type: str, payload: dict[str, object]) -> dict[str, object]:
    return {"type": entry_type, "payload": payload}
