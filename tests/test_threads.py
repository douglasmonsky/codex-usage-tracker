from __future__ import annotations

from codex_usage_tracker.threads import annotate_thread_attachments


def test_thread_attachment_infers_auto_review_by_cwd_and_time() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "parent-1",
                "session_id": "parent-session",
                "thread_name": "Parent Thread",
                "event_timestamp": "2026-05-17T10:00:00Z",
                "cwd": "/tmp/project",
                "thread_source": "user",
            },
            {
                "record_id": "review-1",
                "session_id": "review-session",
                "thread_name": None,
                "event_timestamp": "2026-05-17T10:05:00Z",
                "cwd": "/tmp/project",
                "model": "codex-auto-review",
                "thread_source": "subagent",
                "subagent_type": "guardian",
            },
        ]
    )

    review = rows[1]
    assert review["thread_attachment_key"] == "thread:Parent Thread"
    assert review["thread_attachment_label"] == "Parent Thread"
    assert review["thread_attachment_relation"] == "inferred by cwd/time"


def test_thread_attachment_prefers_explicit_parent_thread() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "child-1",
                "session_id": "child-session",
                "thread_name": None,
                "parent_session_id": "parent-session",
                "resolved_parent_thread_name": "Parent Thread",
            }
        ]
    )

    child = rows[0]
    assert child["thread_attachment_key"] == "thread:Parent Thread"
    assert child["thread_attachment_label"] == "Parent Thread"
    assert child["thread_attachment_relation"] == "explicit parent thread"
    assert child["thread_attachment_parent_session_id"] == "parent-session"
