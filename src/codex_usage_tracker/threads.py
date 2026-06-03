"""Thread attachment inference for aggregate dashboard rows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class ParentCandidate:
    key: str
    label: str
    session_id: str
    cwd: str | None
    first: str
    latest: str


def annotate_thread_attachments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copied rows with shared thread attachment metadata."""

    candidates = _build_parent_candidates(rows)
    return [_with_thread_attachment(row, candidates) for row in rows]


def _with_thread_attachment(
    row: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    copy = dict(row)
    attachment = _resolve_thread_attachment(row, candidates)
    copy["thread_attachment_key"] = attachment["key"]
    copy["thread_attachment_label"] = attachment["label"]
    copy["thread_attachment_relation"] = attachment["relation"]
    copy["thread_attachment_parent_session_id"] = attachment.get("parent_session_id")
    return copy


def _build_parent_candidates(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_session: dict[str, ParentCandidate] = {}
    by_cwd: dict[str, list[ParentCandidate]] = {}
    for row in rows:
        thread_name = _optional_str(row.get("thread_name"))
        session_id = _optional_str(row.get("session_id"))
        if not thread_name or not session_id or row.get("thread_source") == "subagent":
            continue
        key = f"thread:{thread_name}"
        event_timestamp = _optional_str(row.get("event_timestamp")) or ""
        candidate = by_session.setdefault(
            session_id,
            ParentCandidate(
                key=key,
                label=thread_name,
                session_id=session_id,
                cwd=_optional_str(row.get("cwd")),
                first=event_timestamp,
                latest=event_timestamp,
            ),
        )
        if event_timestamp < candidate.first:
            candidate.first = event_timestamp
        if event_timestamp > candidate.latest:
            candidate.latest = event_timestamp

    for candidate in by_session.values():
        if not candidate.cwd:
            continue
        by_cwd.setdefault(candidate.cwd, []).append(candidate)
    return {"by_session": by_session, "by_cwd": by_cwd}


def _resolve_thread_attachment(
    row: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
) -> dict[str, str | None]:
    thread_name = _optional_str(row.get("thread_name"))
    if thread_name:
        return {"key": f"thread:{thread_name}", "label": thread_name, "relation": "direct"}

    parent_session_id = _optional_str(row.get("parent_session_id"))
    parent_thread_name = _resolved_parent_thread_name(row)
    if parent_session_id and parent_thread_name:
        return {
            "key": f"thread:{parent_thread_name}",
            "label": parent_thread_name,
            "relation": "explicit parent thread",
            "parent_session_id": parent_session_id,
        }

    by_session: dict[str, ParentCandidate] = candidates["by_session"]
    if parent_session_id and parent_session_id in by_session:
        parent = by_session[parent_session_id]
        return {
            "key": parent.key,
            "label": parent.label,
            "relation": "explicit parent",
            "parent_session_id": parent_session_id,
        }

    if parent_session_id:
        return {
            "key": f"session:{parent_session_id}",
            "label": f"Parent {parent_session_id}",
            "relation": "explicit parent",
            "parent_session_id": parent_session_id,
        }

    if _is_auto_review(row):
        cwd = _optional_str(row.get("cwd"))
        by_cwd: dict[str, list[ParentCandidate]] = candidates["by_cwd"]
        cwd_candidates = by_cwd.get(cwd or "", [])
        if cwd_candidates:
            nearest = min(cwd_candidates, key=lambda candidate: _candidate_distance(row, candidate))
            return {
                "key": nearest.key,
                "label": nearest.label,
                "relation": "inferred by cwd/time",
            }
        return {
            "key": f"auto:{cwd or _optional_str(row.get('session_id')) or 'unknown'}",
            "label": f"Auto-review: {_basename_path(cwd)}",
            "relation": "unmatched auto-review",
        }

    session_id = _optional_str(row.get("session_id")) or "unknown"
    return {
        "key": f"session:{session_id}",
        "label": session_id if session_id != "unknown" else "Unknown thread",
        "relation": "unmatched subagent" if _is_subagent(row) else "session",
    }


def _resolved_parent_thread_name(row: dict[str, Any]) -> str:
    return (
        _optional_str(row.get("resolved_parent_thread_name"))
        or _optional_str(row.get("parent_thread_name"))
        or ""
    )


def _is_auto_review(row: dict[str, Any]) -> bool:
    return row.get("model") == "codex-auto-review" or row.get("subagent_type") == "guardian"


def _is_subagent(row: dict[str, Any]) -> bool:
    return (
        row.get("thread_source") == "subagent"
        or bool(row.get("subagent_type"))
        or bool(row.get("parent_session_id"))
    )


def _candidate_distance(row: dict[str, Any], candidate: ParentCandidate) -> float:
    event_time = _timestamp(row.get("event_timestamp"))
    first = _timestamp(candidate.first)
    latest = _timestamp(candidate.latest)
    if event_time is None or first is None or latest is None:
        return 0
    if first <= event_time <= latest:
        return 0
    return min(abs(event_time - first), abs(event_time - latest))


def _timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def _basename_path(path: str | None) -> str:
    if not path:
        return "Unknown project"
    return Path(path).name or path


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
