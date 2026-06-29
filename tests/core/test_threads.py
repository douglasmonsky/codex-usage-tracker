from __future__ import annotations

from codex_usage_tracker.core.threads import annotate_thread_attachments


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


def test_thread_attachment_uses_direct_thread_name() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "thread-1",
                "session_id": "session-1",
                "thread_name": "Direct Thread",
                "event_timestamp": "2026-05-17T10:00:00Z",
                "cwd": "/tmp/project",
                "thread_source": "user",
            }
        ]
    )

    direct = rows[0]
    assert direct["thread_attachment_key"] == "thread:Direct Thread"
    assert direct["thread_attachment_label"] == "Direct Thread"
    assert direct["thread_attachment_relation"] == "direct"
    assert direct["thread_attachment_parent_session_id"] is None


def test_thread_attachment_uses_matching_parent_session() -> None:
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
                "record_id": "child-1",
                "session_id": "child-session",
                "thread_name": None,
                "parent_session_id": "parent-session",
                "event_timestamp": "2026-05-17T10:05:00Z",
                "cwd": "/tmp/project",
                "thread_source": "subagent",
            },
        ]
    )

    child = rows[1]
    assert child["thread_attachment_key"] == "thread:Parent Thread"
    assert child["thread_attachment_label"] == "Parent Thread"
    assert child["thread_attachment_relation"] == "explicit parent"
    assert child["thread_attachment_parent_session_id"] == "parent-session"


def test_thread_attachment_keeps_unmatched_parent_session() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "child-1",
                "session_id": "child-session",
                "thread_name": None,
                "parent_session_id": "missing-session",
                "event_timestamp": "2026-05-17T10:05:00Z",
                "cwd": "/tmp/project",
                "thread_source": "subagent",
            }
        ]
    )

    child = rows[0]
    assert child["thread_attachment_key"] == "session:missing-session"
    assert child["thread_attachment_label"] == "Parent missing-session"
    assert child["thread_attachment_relation"] == "explicit parent"
    assert child["thread_attachment_parent_session_id"] == "missing-session"


def test_thread_attachment_keeps_unmatched_auto_review_project() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "review-1",
                "session_id": "review-session",
                "thread_name": None,
                "event_timestamp": "2026-05-17T10:05:00Z",
                "cwd": "/tmp/project",
                "model": "codex-auto-review",
                "thread_source": "subagent",
                "subagent_type": "guardian",
            }
        ]
    )

    review = rows[0]
    assert review["thread_attachment_key"] == "auto:/tmp/project"
    assert review["thread_attachment_label"] == "Auto-review: project"
    assert review["thread_attachment_relation"] == "unmatched auto-review"
    assert review["thread_attachment_parent_session_id"] is None


def test_thread_attachment_keeps_unmatched_auto_review_session_without_cwd() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "review-1",
                "session_id": "review-session",
                "thread_name": None,
                "event_timestamp": "2026-05-17T10:05:00Z",
                "model": "codex-auto-review",
                "thread_source": "subagent",
                "subagent_type": "guardian",
            }
        ]
    )

    review = rows[0]
    assert review["thread_attachment_key"] == "auto:review-session"
    assert review["thread_attachment_label"] == "Auto-review: Unknown project"
    assert review["thread_attachment_relation"] == "unmatched auto-review"
    assert review["thread_attachment_parent_session_id"] is None


def test_thread_attachment_labels_unmatched_subagent_and_plain_session() -> None:
    rows = annotate_thread_attachments(
        [
            {
                "record_id": "subagent-1",
                "session_id": "subagent-session",
                "thread_name": None,
                "event_timestamp": "2026-05-17T10:05:00Z",
                "thread_source": "subagent",
                "subagent_type": "worker",
            },
            {
                "record_id": "plain-1",
                "session_id": "plain-session",
                "thread_name": None,
                "event_timestamp": "2026-05-17T10:06:00Z",
                "thread_source": "user",
            },
        ]
    )

    subagent = rows[0]
    assert subagent["thread_attachment_key"] == "session:subagent-session"
    assert subagent["thread_attachment_label"] == "subagent-session"
    assert subagent["thread_attachment_relation"] == "unmatched subagent"

    plain = rows[1]
    assert plain["thread_attachment_key"] == "session:plain-session"
    assert plain["thread_attachment_label"] == "plain-session"
    assert plain["thread_attachment_relation"] == "session"
