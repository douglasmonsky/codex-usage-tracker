from __future__ import annotations

from codex_usage_tracker.core.call_origin import CallOriginFlags
from codex_usage_tracker.core.models import DiagnosticFact
from codex_usage_tracker.parser.state import (
    ParserState,
    parser_state_from_json,
    parser_state_to_json,
)


def test_parser_state_from_json_rejects_invalid_payloads() -> None:
    assert parser_state_from_json(None) is None
    assert parser_state_from_json("") is None
    assert parser_state_from_json("{not json") is None
    assert parser_state_from_json('{"version": 2}') is None
    assert parser_state_from_json("[]") is None


def test_parser_state_json_round_trip_preserves_segments() -> None:
    state = ParserState(
        session_id="session",
        session_meta={"model": "gpt-5.5", "other": None},
        current_turn={"turn_id": "turn-a"},
        last_cumulative_total=123,
        call_origin_segment=(
            CallOriginFlags(user_message=True),
            CallOriginFlags(tool_result=True, codex_activity=True),
        ),
        diagnostic_facts_segment=(
            DiagnosticFact(
                record_id="record",
                fact_type="tool",
                fact_name="exec_command",
                fact_category="function",
            ),
        ),
        latest_record_id="record",
        latest_event_timestamp="2026-06-01T10:00:00Z",
    )

    decoded = parser_state_from_json(parser_state_to_json(state))

    assert decoded is not None
    assert decoded.session_id == state.session_id
    assert decoded.session_meta == state.session_meta
    assert decoded.current_turn == state.current_turn
    assert decoded.last_cumulative_total == state.last_cumulative_total
    assert decoded.call_origin_segment == state.call_origin_segment
    assert decoded.latest_record_id == state.latest_record_id
    assert decoded.latest_event_timestamp == state.latest_event_timestamp
    assert decoded.diagnostic_facts_segment[0].record_id is None
    assert decoded.diagnostic_facts_segment[0].fact_type == "tool"
    assert decoded.diagnostic_facts_segment[0].fact_name == "exec_command"
