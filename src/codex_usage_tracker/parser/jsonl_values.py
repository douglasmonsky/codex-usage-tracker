"""Value helpers for Codex JSONL usage event parsing."""

from __future__ import annotations

import hashlib
import re
from collections.abc import MutableMapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.models import SessionInfo, UsageEvent
from codex_usage_tracker.core.usage_identity import usage_identity_from_values
from codex_usage_tracker.parser.state import optional_str

SESSION_ID_RE = re.compile(
    r"rollout-[^-]+-[0-9T:-]+-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)


def build_usage_event(
    path: Path,
    line_number: int,
    event_timestamp: str,
    session_id: str,
    session_info: SessionInfo | None,
    session_meta: dict[str, str | None],
    current_turn: dict[str, Any],
    call_origin: dict[str, str],
    model_context_window: int | None,
    last_usage: dict[str, Any],
    total_usage: dict[str, Any],
    rate_limits: object = None,
    upstream_usage_id: str | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> UsageEvent:
    input_tokens = required_usage_int(last_usage, "input_tokens", stats=stats)
    cached_input_tokens = required_usage_int(last_usage, "cached_input_tokens", stats=stats)
    output_tokens = required_usage_int(last_usage, "output_tokens", stats=stats)
    reasoning_output_tokens = required_usage_int(last_usage, "reasoning_output_tokens", stats=stats)
    total_tokens = required_usage_int(last_usage, "total_tokens", stats=stats)
    cumulative_total_tokens = required_usage_int(
        total_usage,
        "total_tokens",
        stats=stats,
        missing_key="missing_cumulative_total",
    )
    observed_usage = _observed_usage_from_rate_limits(rate_limits, stats=stats)
    record_id = _record_id(
        session_id=session_id,
        turn_id=optional_str(current_turn.get("turn_id")),
        event_timestamp=event_timestamp,
        cumulative_total_tokens=cumulative_total_tokens,
        total_tokens=total_tokens,
    )
    event = UsageEvent(
        record_id=record_id,
        session_id=session_id,
        thread_name=session_info.thread_name if session_info else None,
        session_updated_at=session_info.updated_at if session_info else None,
        event_timestamp=event_timestamp,
        source_file=str(path),
        line_number=line_number,
        turn_id=optional_str(current_turn.get("turn_id")),
        turn_timestamp=optional_str(current_turn.get("turn_timestamp")),
        cwd=optional_str(current_turn.get("cwd")),
        model=optional_str(current_turn.get("model")),
        effort=optional_str(current_turn.get("effort")),
        current_date=optional_str(current_turn.get("current_date")),
        timezone=optional_str(current_turn.get("timezone")),
        call_initiator=call_origin.get("call_initiator"),
        call_initiator_reason=call_origin.get("call_initiator_reason"),
        call_initiator_confidence=call_origin.get("call_initiator_confidence"),
        is_archived=_is_archived_source(path),
        thread_key=_thread_key(
            session_id=session_id,
            session_info=session_info,
            session_meta=session_meta,
        ),
        thread_call_index=None,
        previous_record_id=None,
        next_record_id=None,
        thread_source=session_meta.get("thread_source"),
        subagent_type=session_meta.get("subagent_type"),
        agent_role=session_meta.get("agent_role"),
        agent_nickname=session_meta.get("agent_nickname"),
        parent_session_id=session_meta.get("parent_session_id"),
        parent_thread_name=session_meta.get("parent_thread_name"),
        parent_session_updated_at=session_meta.get("parent_session_updated_at"),
        model_context_window=model_context_window,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        total_tokens=total_tokens,
        cumulative_input_tokens=required_usage_int(total_usage, "input_tokens", stats=stats),
        cumulative_cached_input_tokens=required_usage_int(
            total_usage, "cached_input_tokens", stats=stats
        ),
        cumulative_output_tokens=required_usage_int(total_usage, "output_tokens", stats=stats),
        cumulative_reasoning_output_tokens=required_usage_int(
            total_usage, "reasoning_output_tokens", stats=stats
        ),
        cumulative_total_tokens=cumulative_total_tokens,
        **observed_usage,
    )
    identity = usage_identity_from_values(event.to_row(), upstream_usage_id=upstream_usage_id)
    return replace(
        event,
        upstream_usage_id=identity.upstream_usage_id,
        usage_fingerprint=identity.usage_fingerprint,
        canonical_record_id=identity.canonical_record_id,
    )


def _observed_usage_from_rate_limits(
    value: object,
    *,
    stats: MutableMapping[str, int] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    primary = _rate_limit_window(value.get("primary"), "primary", stats=stats)
    secondary = _rate_limit_window(value.get("secondary"), "secondary", stats=stats)
    return {
        "rate_limit_plan_type": optional_str(value.get("plan_type")),
        "rate_limit_limit_id": optional_str(value.get("limit_id")),
        **primary,
        **secondary,
    }


def _rate_limit_window(
    value: object,
    prefix: str,
    *,
    stats: MutableMapping[str, int] | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        f"rate_limit_{prefix}_used_percent": _nullable_float(
            value.get("used_percent"),
            stats=stats,
        ),
        f"rate_limit_{prefix}_window_minutes": nullable_int(
            value.get("window_minutes"),
            stats=stats,
        ),
        f"rate_limit_{prefix}_resets_at": nullable_int(
            value.get("resets_at"),
            stats=stats,
        ),
    }


def session_metadata(
    payload: dict[str, Any],
    session_index: dict[str, SessionInfo],
) -> dict[str, str | None]:
    source = payload.get("source")
    metadata = empty_session_metadata()
    metadata["thread_source"] = optional_str(payload.get("thread_source"))
    if not isinstance(source, dict):
        return metadata

    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return metadata

    other = optional_str(subagent.get("other"))
    if other:
        metadata["subagent_type"] = other
        return metadata

    thread_spawn = subagent.get("thread_spawn")
    if isinstance(thread_spawn, dict):
        metadata["subagent_type"] = "thread_spawn"
        metadata["agent_role"] = optional_str(thread_spawn.get("agent_role"))
        metadata["agent_nickname"] = optional_str(thread_spawn.get("agent_nickname"))
        parent_session_id = optional_str(thread_spawn.get("parent_thread_id"))
        metadata["parent_session_id"] = parent_session_id
        if parent_session_id:
            parent_info = session_index.get(parent_session_id)
            if parent_info:
                metadata["parent_thread_name"] = parent_info.thread_name
                metadata["parent_session_updated_at"] = parent_info.updated_at
    return metadata


def empty_session_metadata() -> dict[str, str | None]:
    return {
        "thread_source": None,
        "subagent_type": None,
        "agent_role": None,
        "agent_nickname": None,
        "parent_session_id": None,
        "parent_thread_name": None,
        "parent_session_updated_at": None,
    }


def _record_id(
    session_id: str,
    turn_id: str | None,
    event_timestamp: str,
    cumulative_total_tokens: int,
    total_tokens: int,
) -> str:
    raw = "|".join(
        [
            session_id,
            turn_id or "",
            event_timestamp,
            str(cumulative_total_tokens),
            str(total_tokens),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _is_archived_source(path: Path) -> int:
    return 1 if "archived_sessions" in path.parts else 0


def _thread_key(
    *,
    session_id: str,
    session_info: SessionInfo | None,
    session_meta: dict[str, str | None],
) -> str:
    thread_name = session_info.thread_name if session_info else None
    if thread_name:
        return f"thread:{thread_name}"
    parent_thread_name = session_meta.get("parent_thread_name")
    if parent_thread_name:
        return f"thread:{parent_thread_name}"
    parent_session_id = session_meta.get("parent_session_id")
    if parent_session_id:
        return f"session:{parent_session_id}"
    return f"session:{session_id}"


def session_id_from_path(path: Path) -> str | None:
    match = SESSION_ID_RE.search(path.name)
    if not match:
        return None
    return match.group(1)


def nullable_int(
    value: object,
    *,
    stats: MutableMapping[str, int] | None = None,
    invalid_key: str = "partial_field_count",
) -> int | None:
    if value is None:
        return None
    try:
        return _strict_int(value)
    except ValueError:
        increment_stat(stats, invalid_key)
        if invalid_key != "partial_field_count":
            increment_stat(stats, "partial_field_count")
        return None


def _nullable_float(
    value: object,
    *,
    stats: MutableMapping[str, int] | None = None,
    invalid_key: str = "partial_field_count",
) -> float | None:
    if value is None:
        return None
    try:
        return _strict_float(value)
    except ValueError:
        increment_stat(stats, invalid_key)
        if invalid_key != "partial_field_count":
            increment_stat(stats, "partial_field_count")
        return None


def _strict_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError(f"invalid integer value: {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ValueError(f"invalid integer value: {value!r}")
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"invalid integer value: {value!r}") from exc
    raise ValueError(f"invalid integer value: {value!r}")


def _strict_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"invalid float value: {value!r}")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"invalid float value: {value!r}") from exc
    raise ValueError(f"invalid float value: {value!r}")


def required_usage_int(
    values: dict[str, Any],
    key: str,
    *,
    stats: MutableMapping[str, int] | None = None,
    missing_key: str = "partial_field_count",
) -> int:
    if key not in values or values.get(key) is None:
        increment_stat(stats, missing_key)
        if missing_key != "partial_field_count":
            increment_stat(stats, "partial_field_count")
        raise ValueError(f"missing required integer field: {key}")
    try:
        return _strict_int(values.get(key))
    except ValueError:
        increment_stat(stats, "invalid_integer")
        increment_stat(stats, "partial_field_count")
        raise


def increment_stat(stats: MutableMapping[str, int] | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1
