from __future__ import annotations

from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.schema import USAGE_EVENT_COLUMN_NAMES
from codex_usage_tracker.store import EVENT_COLUMNS


def _usage_event() -> UsageEvent:
    return UsageEvent(
        record_id="record",
        session_id="session",
        thread_name="Thread",
        session_updated_at="2026-05-17T18:58:27Z",
        event_timestamp="2026-05-17T18:59:00Z",
        source_file="/tmp/session.jsonl",
        line_number=12,
        source_provider="openai",
        source_app="codex",
        source_format="codex-jsonl-v1",
        provider_request_id=None,
        turn_id="turn",
        turn_timestamp="2026-05-17T18:58:59Z",
        cwd="/tmp/project",
        model="gpt-5.5",
        effort="high",
        current_date="2026-05-17",
        timezone="America/New_York",
        thread_source="user",
        subagent_type=None,
        agent_role=None,
        agent_nickname=None,
        parent_session_id=None,
        parent_thread_name=None,
        parent_session_updated_at=None,
        model_context_window=1000,
        cache_creation_input_tokens=0,
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


def test_usage_event_schema_matches_persisted_row_shape() -> None:
    event = _usage_event()

    assert tuple(EVENT_COLUMNS) == USAGE_EVENT_COLUMN_NAMES
    assert tuple(event.to_row().keys()) == USAGE_EVENT_COLUMN_NAMES


def test_usage_event_includes_source_identity_fields() -> None:
    event = _usage_event()

    row = event.to_row()

    assert row["source_provider"] == "openai"
    assert row["source_app"] == "codex"
    assert row["source_format"] == "codex-jsonl-v1"
    assert row["provider_request_id"] is None
    assert row["cache_creation_input_tokens"] == 0


def test_schema_columns_include_provider_identity() -> None:
    assert "source_provider" in USAGE_EVENT_COLUMN_NAMES
    assert "source_app" in USAGE_EVENT_COLUMN_NAMES
    assert "source_format" in USAGE_EVENT_COLUMN_NAMES
    assert "provider_request_id" in USAGE_EVENT_COLUMN_NAMES
    assert "cache_creation_input_tokens" in USAGE_EVENT_COLUMN_NAMES
