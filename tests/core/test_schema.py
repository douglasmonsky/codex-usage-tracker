from __future__ import annotations

import pickle

from codex_usage_tracker.core.models import DiagnosticFact, UsageEvent
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
    assert event.to_row()["service_tier"] is None
    assert event.to_row()["fast"] is None
    assert event.to_row()["service_tier_source"] is None
    assert event.to_row()["service_tier_confidence"] is None


def test_hot_refresh_models_are_pickle_compatible() -> None:
    event = UsageEvent(
        record_id="record",
        session_id="session",
        thread_name="Synthetic thread",
        session_updated_at="2026-07-25T12:00:00Z",
        event_timestamp="2026-07-25T12:00:01Z",
        source_file="/synthetic/session.jsonl",
        line_number=1,
        turn_id="turn",
        turn_timestamp="2026-07-25T12:00:01Z",
        cwd="/synthetic/project",
        model="gpt-5.5",
        effort="high",
        current_date="2026-07-25",
        timezone="America/New_York",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=0,
        thread_key="thread:Synthetic thread",
        thread_call_index=1,
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
    fact = DiagnosticFact(
        record_id="record",
        fact_type="tool",
        fact_name="usage_status",
        fact_category="mcp",
    )

    assert pickle.loads(pickle.dumps(event)) == event
    assert pickle.loads(pickle.dumps(fact)) == fact
