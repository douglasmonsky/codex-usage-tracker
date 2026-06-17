from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.models import UsageEvent
from codex_usage_tracker.store import connect, init_db, upsert_usage_events
from codex_usage_tracker.store_context_epochs import (
    context_epochs_payload,
    materialize_thread_context_epochs,
    query_context_epochs,
    rebuild_thread_context_epochs,
)
from codex_usage_tracker.store_work_sessions import query_thread_work_sessions


def test_materialize_session_without_compaction_creates_one_epoch() -> None:
    rows = [
        _row(
            "a",
            "work-session-alpha",
            "thread:Alpha",
            1,
            "2026-06-01T10:00:00+00:00",
            input_tokens=30_000,
            cached=29_000,
        ),
        _row(
            "b",
            "work-session-alpha",
            "thread:Alpha",
            2,
            "2026-06-01T10:05:00+00:00",
            input_tokens=35_000,
            cached=33_000,
        ),
    ]

    epochs = materialize_thread_context_epochs(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert len(epochs) == 1
    assert epochs[0]["start_reason"] == "session_start"
    assert epochs[0]["call_count"] == 2
    assert epochs[0]["uncached_input_tokens"] == 3_000
    assert epochs[0]["compaction_effectiveness"] == "unknown"


def test_post_compaction_call_starts_new_epoch_inside_session() -> None:
    rows = [
        _row(
            "a",
            "work-session-alpha",
            "thread:Alpha",
            1,
            "2026-06-01T10:00:00+00:00",
            input_tokens=40_000,
            cached=38_000,
        ),
        _row(
            "b",
            "work-session-alpha",
            "thread:Alpha",
            2,
            "2026-06-01T10:05:00+00:00",
            input_tokens=50_000,
            cached=10_000,
            initiator_reason="post_compaction",
            previous_record_id="a",
        ),
        _row(
            "c",
            "work-session-alpha",
            "thread:Alpha",
            3,
            "2026-06-01T10:10:00+00:00",
            input_tokens=35_000,
            cached=28_000,
        ),
    ]

    epochs = materialize_thread_context_epochs(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert [epoch["start_reason"] for epoch in epochs] == ["session_start", "post_compaction"]
    assert epochs[1]["start_record_id"] == "b"
    assert epochs[1]["compaction_before_record_id"] == "a"
    assert epochs[1]["post_compaction_uncached_spike"] == 40_000
    assert epochs[1]["compaction_effectiveness"] == "mixed"
    assert sum(epoch["call_count"] for epoch in epochs) == 3


def test_compaction_effectiveness_labels_post_compaction_epochs() -> None:
    rows = [
        _row(
            "a",
            "work-session-alpha",
            "thread:Alpha",
            1,
            "2026-06-01T10:00:00+00:00",
            input_tokens=40_000,
            cached=38_000,
        ),
        _row(
            "b",
            "work-session-alpha",
            "thread:Alpha",
            2,
            "2026-06-01T10:05:00+00:00",
            input_tokens=60_000,
            cached=45_000,
            initiator_reason="post_compaction",
            previous_record_id="a",
        ),
        _row(
            "c",
            "work-session-alpha",
            "thread:Alpha",
            3,
            "2026-06-01T10:10:00+00:00",
            input_tokens=100_000,
            cached=50_000,
            initiator_reason="post_compaction",
            previous_record_id="b",
        ),
        _row(
            "d",
            "work-session-alpha",
            "thread:Alpha",
            4,
            "2026-06-01T10:15:00+00:00",
            input_tokens=100_000,
            cached=5_000,
            initiator_reason="post_compaction",
            previous_record_id="c",
        ),
    ]

    epochs = materialize_thread_context_epochs(rows, updated_at="2026-06-01T00:00:00+00:00")

    assert [epoch["compaction_effectiveness"] for epoch in epochs] == [
        "unknown",
        "effective",
        "mixed",
        "ineffective",
    ]


def test_context_epoch_totals_sum_to_work_session_totals(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _event("a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=40_000, cached=38_000),
            _event(
                "b",
                "thread:Alpha",
                "2026-06-01T10:05:00+00:00",
                input_tokens=50_000,
                cached=10_000,
                initiator_reason="post_compaction",
            ),
            _event("c", "thread:Alpha", "2026-06-01T10:10:00+00:00", input_tokens=35_000, cached=28_000),
        ],
        db_path=db_path,
    )

    sessions = query_thread_work_sessions(
        db_path=db_path,
        limit=0,
        include_archived=True,
        sort="started",
        direction="asc",
    )
    assert len(sessions) == 1
    epochs = query_context_epochs(
        db_path=db_path,
        work_session_id=sessions[0]["work_session_id"],
        limit=0,
    )

    assert [epoch["start_reason"] for epoch in epochs] == ["session_start", "post_compaction"]
    assert sum(epoch["total_tokens"] for epoch in epochs) == sessions[0]["total_tokens"]
    assert sum(epoch["uncached_input_tokens"] for epoch in epochs) == sessions[0]["uncached_input_tokens"]
    assert sum(epoch["call_count"] for epoch in epochs) == sessions[0]["call_count"]
    assert sessions[0]["compaction_count"] == 1


def test_partial_context_epoch_rebuild_touches_only_affected_thread(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _event("alpha-a", "thread:Alpha", "2026-06-01T10:00:00+00:00", input_tokens=40_000, cached=38_000),
            _event("beta-a", "thread:Beta", "2026-06-01T10:00:00+00:00", input_tokens=10_000, cached=9_000),
        ],
        db_path=db_path,
    )
    beta_before = query_context_epochs(db_path=db_path, thread_key="thread:Beta", limit=0)

    upsert_usage_events(
        [
            _event(
                "alpha-b",
                "thread:Alpha",
                "2026-06-01T10:05:00+00:00",
                input_tokens=50_000,
                cached=10_000,
                initiator_reason="post_compaction",
            ),
        ],
        db_path=db_path,
    )
    partial = query_context_epochs(db_path=db_path, limit=0)
    with connect(db_path) as conn:
        init_db(conn)
        rebuild_thread_context_epochs(conn)
    full = query_context_epochs(db_path=db_path, limit=0)

    assert [row["start_reason"] for row in partial if row["thread_key"] == "thread:Alpha"] == [
        "session_start",
        "post_compaction",
    ]
    assert sorted(row["context_epoch_id"] for row in partial) == sorted(
        row["context_epoch_id"] for row in full
    )
    assert query_context_epochs(db_path=db_path, thread_key="thread:Beta", limit=0) == beta_before


def test_context_epoch_payload_is_aggregate_only() -> None:
    rows = materialize_thread_context_epochs(
        [
            _row(
                "a",
                "work-session-alpha",
                "thread:Alpha",
                1,
                "2026-06-01T10:00:00+00:00",
            )
        ],
        updated_at="2026-06-01T00:00:00+00:00",
    )
    payload = context_epochs_payload(rows, work_session_id="work-session-alpha", limit=100)

    serialized = json.dumps(payload)
    assert payload["schema"] == "codex-usage-tracker-context-epochs-v1"
    assert payload["raw_context_included"] is False
    assert "prompt" not in serialized.lower()
    assert "assistant" not in serialized.lower()
    assert "tool output" not in serialized.lower()


def _row(
    record_id: str,
    work_session_id: str,
    thread_key: str,
    thread_call_index: int,
    timestamp: str,
    *,
    input_tokens: int = 10_000,
    cached: int = 8_000,
    output_tokens: int = 100,
    reasoning_tokens: int = 20,
    initiator_reason: str = "user_message",
    previous_record_id: str | None = None,
) -> dict[str, object]:
    return _event(
        record_id,
        thread_key,
        timestamp,
        input_tokens=input_tokens,
        cached=cached,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        initiator_reason=initiator_reason,
        previous_record_id=previous_record_id,
    ).to_row() | {
        "work_session_id": work_session_id,
        "resolved_thread_key": thread_key,
        "thread_call_index": thread_call_index,
    }


def _event(
    record_id: str,
    thread_key: str,
    timestamp: str,
    *,
    input_tokens: int,
    cached: int,
    output_tokens: int = 100,
    reasoning_tokens: int = 20,
    initiator_reason: str = "user_message",
    previous_record_id: str | None = None,
) -> UsageEvent:
    uncached = max(input_tokens - cached, 0)
    total = input_tokens + output_tokens
    initiator = "codex" if initiator_reason == "post_compaction" else "user"
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
        call_initiator=initiator,
        call_initiator_reason=initiator_reason,
        call_initiator_confidence="high",
        is_archived=0,
        thread_key=thread_key,
        thread_call_index=None,
        previous_record_id=previous_record_id,
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
