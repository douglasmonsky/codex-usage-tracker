from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.store import connect, init_db, upsert_usage_events
from codex_usage_tracker.store_work_sessions import (
    materialize_thread_work_sessions,
    query_thread_work_sessions,
    rebuild_thread_work_sessions,
    sessions_payload,
)


def test_materialize_thread_without_cold_resume_creates_one_session() -> None:
    rows = [
        _row("a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=30_000, cached=29_000),
        _row("b", "thread:Alpha", "2026-06-01T10:05:00+00:00", input_tokens=35_000, cached=33_000),
    ]

    sessions = materialize_thread_work_sessions(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert len(sessions) == 1
    assert sessions[0]["start_reason"] == "thread_start"
    assert sessions[0]["call_count"] == 2
    assert sessions[0]["uncached_input_tokens"] == 3_000
    assert sessions[0]["avg_cache_ratio"] > 0.90


def test_cold_resume_starts_new_work_session() -> None:
    rows = [
        _row("a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=40_000, cached=38_000),
        _row("b", "thread:Alpha", "2026-06-01T11:00:00+00:00", input_tokens=35_000, cached=2_000),
    ]

    sessions = materialize_thread_work_sessions(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert [session["start_reason"] for session in sessions] == ["thread_start", "cold_resume"]
    assert sessions[1]["cold_start_record_id"] == "b"
    assert sessions[1]["idle_minutes_before"] == 60
    assert sessions[1]["cold_resume_uncached_tokens"] == 33_000
    assert sessions[1]["suggested_next_action"] == "inspect_cold_resume"


def test_huge_uncached_boundary_does_not_need_idle_gap() -> None:
    rows = [
        _row("a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=40_000, cached=38_000),
        _row("b", "thread:Alpha", "2026-06-01T10:05:00+00:00", input_tokens=130_000, cached=5_000),
    ]

    sessions = materialize_thread_work_sessions(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert len(sessions) == 2
    assert sessions[1]["start_reason"] == "cold_resume"
    assert sessions[1]["suggested_next_action"] == "handoff_or_start_fresh"


def test_cold_resume_cluster_suppression_keeps_close_boundaries_together() -> None:
    rows = [
        _row("a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=40_000, cached=38_000),
        _row("b", "thread:Alpha", "2026-06-01T11:00:00+00:00", input_tokens=35_000, cached=2_000),
        _row("c", "thread:Alpha", "2026-06-01T11:05:00+00:00", input_tokens=130_000, cached=5_000),
    ]

    sessions = materialize_thread_work_sessions(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert len(sessions) == 2
    assert sessions[1]["start_record_id"] == "b"
    assert sessions[1]["end_record_id"] == "c"
    assert sessions[1]["call_count"] == 2


def test_partial_work_session_rebuild_touches_only_affected_thread(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _event("alpha-a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=40_000, cached=38_000),
            _event("beta-a", "thread:Beta", "2026-06-01T10:00:00+00:00", input_tokens=10_000, cached=9_000),
        ],
        db_path=db_path,
    )
    before = query_thread_work_sessions(
        db_path=db_path,
        limit=0,
        include_archived=True,
        sort="started",
        direction="asc",
    )
    beta_before = [row for row in before if row["thread_key"] == "thread:Beta"]

    upsert_usage_events(
        [
            _event("alpha-b", "thread:Alpha", "2026-06-01T11:00:00+00:00", input_tokens=35_000, cached=2_000),
        ],
        db_path=db_path,
    )
    partial = query_thread_work_sessions(
        db_path=db_path,
        limit=0,
        include_archived=True,
        sort="started",
        direction="asc",
    )
    with connect(db_path) as conn:
        init_db(conn)
        rebuild_thread_work_sessions(conn)
    full = query_thread_work_sessions(
        db_path=db_path,
        limit=0,
        include_archived=True,
        sort="started",
        direction="asc",
    )

    assert [row["session_index"] for row in partial if row["thread_key"] == "thread:Alpha"] == [1, 2]
    assert sorted(row["work_session_id"] for row in partial) == sorted(
        row["work_session_id"] for row in full
    )
    assert [row for row in partial if row["thread_key"] == "thread:Beta"] == beta_before


def test_work_session_payload_is_aggregate_only() -> None:
    rows = materialize_thread_work_sessions(
        [_row("a", "thread:Alpha", "2026-06-01T10:00:00+00:00")],
        updated_at="2026-06-01T00:00:00+00:00",
    )
    payload = sessions_payload(rows, limit=100, include_archived=True)

    serialized = json.dumps(payload)
    assert payload["schema"] == "codex-usage-tracker-sessions-v1"
    assert payload["raw_context_included"] is False
    assert "prompt" not in serialized.lower()
    assert "assistant" not in serialized.lower()
    assert "tool output" not in serialized.lower()


def _row(
    record_id: str,
    thread_key: str,
    timestamp: str,
    *,
    input_tokens: int = 10_000,
    cached: int = 8_000,
    output_tokens: int = 100,
    reasoning_tokens: int = 20,
) -> dict[str, object]:
    return _event(
        record_id,
        thread_key,
        timestamp,
        input_tokens=input_tokens,
        cached=cached,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
    ).to_row() | {"resolved_thread_key": thread_key}


def _event(
    record_id: str,
    thread_key: str,
    timestamp: str,
    *,
    input_tokens: int,
    cached: int,
    output_tokens: int = 100,
    reasoning_tokens: int = 20,
) -> UsageEvent:
    uncached = max(input_tokens - cached, 0)
    total = input_tokens + output_tokens
    return UsageEvent(
        record_id=record_id,
        session_id=f"session-{thread_key}",
        thread_name=thread_key.removeprefix("thread:"),
        session_updated_at=timestamp,
        event_timestamp=timestamp,
        source_file=f"/tmp/synthetic/{record_id}.jsonl",
        line_number=1,
        turn_id=f"turn-{record_id}",
        turn_timestamp=timestamp,
        cwd="/tmp/project",
        model="gpt-5.5",
        effort="high",
        current_date="2026-06-01",
        timezone="UTC",
        call_initiator="user",
        call_initiator_reason="user_message",
        call_initiator_confidence="high",
        is_archived=0,
        thread_key=thread_key,
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
        model_context_window=200_000,
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_tokens,
        total_tokens=total,
        cumulative_input_tokens=input_tokens,
        cumulative_cached_input_tokens=cached,
        cumulative_output_tokens=output_tokens,
        cumulative_reasoning_output_tokens=reasoning_tokens,
        cumulative_total_tokens=total + uncached,
    )
