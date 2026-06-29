from __future__ import annotations

from codex_usage_tracker.formatting import format_recommendations


def test_format_recommendations_handles_empty_payload() -> None:
    assert format_recommendations({}) == "No aggregate recommendations are currently flagged."


def test_format_recommendations_includes_threads_and_call_fallbacks() -> None:
    payload = {
        "threads": [
            {
                "thread": "Thread A",
                "recommendation_score": 7.25,
                "call_count": 3,
                "total_tokens": 12345,
            }
        ],
        "rows": [
            {
                "thread_attachment_label": "Attached Thread",
                "model": "gpt-5.5",
                "effort": "high",
                "recommendation_score": 4,
                "primary_recommendation": {
                    "title": "Trim context",
                    "action": "Start a fresh handoff.",
                },
            },
            {
                "session_id": "session-1",
                "model": "",
                "effort": None,
                "recommendation_score": None,
                "primary_recommendation": "not-a-dict",
                "primary_signal": "pricing-gap",
            },
        ],
    }

    assert format_recommendations(payload) == "\n".join(
        [
            "Codex usage recommendations",
            "",
            "Top threads:",
            "- Thread A: score 7.2, 3 calls, 12,345 tokens",
            "",
            "Top calls:",
            "1. Attached Thread | gpt-5.5 (high) | score 4.0 | Trim context: Start a fresh handoff.",
            "2. session-1 | unknown (unknown) | score 0.0 | pricing-gap: Review aggregate usage.",
        ]
    )
