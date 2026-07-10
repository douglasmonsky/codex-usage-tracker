from codex_usage_tracker.reports.agentic_evidence import (
    _agentic_evidence_summary,
    _compact_agentic_evidence_row,
)


def test_compact_agentic_evidence_row_preserves_bounded_safe_fields() -> None:
    row = {
        "record_id": "record-1",
        "total_tokens": 1200,
        "ignored": "private detail",
        "primary_recommendation": {
            "key": "fresh-thread",
            "severity": "medium",
            "title": "Start a fresh thread",
            "action": "Create a handoff.",
            "ignored": "detail",
        },
        "nearby_activity": {
            "tool_call_count": 3,
            "command_run_count": 2,
            "failed_command_count": 1,
            "file_event_count": 4,
            "ignored": 99,
        },
        "trace_handles": [
            {
                "thread_key": f"thread-{index}",
                "call_count": index,
                "next_tool": "usage_thread_trace",
                "ignored": "detail",
            }
            for index in range(4)
        ],
    }

    compact = _compact_agentic_evidence_row(row)

    assert compact["record_id"] == "record-1"
    assert compact["total_tokens"] == 1200
    assert compact["primary_recommendation"] == {
        "key": "fresh-thread",
        "severity": "medium",
        "title": "Start a fresh thread",
        "action": "Create a handoff.",
    }
    assert compact["nearby_activity"] == {
        "tool_call_count": 3,
        "command_run_count": 2,
        "failed_command_count": 1,
        "file_event_count": 4,
    }
    assert [row["thread_key"] for row in compact["trace_handles"]] == [
        "thread-0",
        "thread-1",
        "thread-2",
    ]
    assert "ignored" not in compact


def test_agentic_evidence_summary_preserves_order_and_optional_totals() -> None:
    summary = _agentic_evidence_summary(
        [
            {
                "total_tokens": 100,
                "event_timestamp": "2026-01-02T00:00:00Z",
                "thread_name": "alpha",
                "model": "gpt-a",
                "effort": "high",
                "candidate_explanation": "large context",
                "recommendation": "start fresh",
                "occurrences": 2,
                "call_count": 3,
                "failure_count": 1,
            },
            {
                "total_tokens": 250.9,
                "event_timestamp": "2026-01-01T00:00:00Z",
                "thread_name": "alpha",
                "model": "gpt-b",
                "effort": "low",
                "candidate_explanation": "large context",
                "recommended_action": "narrow reads",
                "occurrences": 4,
                "call_count": 5,
            },
        ]
    )

    assert summary == {
        "row_count": 2,
        "total_tokens": 350,
        "max_total_tokens": 250,
        "threads": ["alpha"],
        "models": ["gpt-a", "gpt-b"],
        "efforts": ["high", "low"],
        "candidate_explanations": ["large context"],
        "recommendations": ["start fresh", "narrow reads"],
        "first_event_timestamp": "2026-01-01T00:00:00Z",
        "last_event_timestamp": "2026-01-02T00:00:00Z",
        "total_occurrences": 6,
        "total_call_count": 8,
        "total_failure_count": 1,
    }
