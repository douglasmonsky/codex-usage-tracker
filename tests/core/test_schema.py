from __future__ import annotations

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.core.schema import USAGE_EVENT_COLUMN_NAMES
from codex_usage_tracker.store.api import EVENT_COLUMNS


def test_usage_event_schema_matches_persisted_row_shape() -> None:
    event = UsageEvent(
        record_id="record",
        session_id="session",
        thread_name="Thread",
        session_updated_at="2026-05-17T18:58:27Z",
        event_timestamp="2026-05-17T18:59:00Z",
        source_file="/tmp/session.jsonl",
        line_number=12,
        turn_id="turn",
        turn_timestamp="2026-05-17T18:58:59Z",
        cwd="/tmp/project",
        model="gpt-5.5",
        effort="high",
        current_date="2026-05-17",
        timezone="America/New_York",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=0,
        thread_key="thread:Thread",
        thread_call_index=None,
        previous_record_id=None,
        next_record_id=None,
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=1000,
        input_tokens=100,
        cached_input_tokens=25,
        output_tokens=40,
        reasoning_output_tokens=10,
        total_tokens=140,
        cumulative_input_tokens=100,
        cumulative_cached_input_tokens=25,
        cumulative_output_tokens=40,
        cumulative_reasoning_output_tokens=10,
        cumulative_total_tokens=140,
    )

    assert tuple(EVENT_COLUMNS) == USAGE_EVENT_COLUMN_NAMES
    assert tuple(event.to_row().keys()) == USAGE_EVENT_COLUMN_NAMES
