"""Streaming structural JSONL parser with no raw-content retention."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from typing import Any

from .discovery import SourcePlan
from .identity import safe_label

PARSER_ADAPTER = "codex-jsonl-structural"
PARSER_VERSION = "1"
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/@+-]{0,127}\Z")
_ACTIVITY_KINDS = {
    "context_compacted": "compaction",
    "patch_apply_end": "patch",
    "skill_started": "skill",
    "task_complete": "task",
    "thread_rolled_back": "rollback",
    "turn_aborted": "turn_aborted",
}


@dataclass(frozen=True)
class ParserState:
    session_id: str | None = None
    parent_session_id: str | None = None
    agent_role: str | None = None
    agent_nickname: str | None = None
    turn_id: str | None = None
    turn_ordinal: int = 0
    model: str = "unknown"
    effort: str | None = None
    service_tier: str | None = None


@dataclass(frozen=True)
class StructuralEvent:
    kind: str
    timestamp: str
    source_offset: int
    line_number: int
    session_id: str | None
    parent_session_id: str | None
    agent_role: str | None
    agent_nickname: str | None
    turn_id: str | None
    turn_ordinal: int
    model: str
    effort: str | None
    service_tier: str | None
    upstream_id: str | None = None
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    upstream_total_tokens: int | None = None
    context_window: int | None = None
    tool_name: str | None = None
    server_name: str | None = None
    activity_kind: str | None = None
    activity_label: str | None = None
    allowance_window: str | None = None
    allowance_used_percent: float | None = None
    allowance_duration_minutes: int | None = None
    allowance_resets_at: str | None = None
    allowance_plan_type: str | None = None
    allowance_limit_id: str | None = None


@dataclass(frozen=True)
class ParsedBatch:
    events: tuple[StructuralEvent, ...]
    final_state: ParserState
    parse_warning_count: int
    unsupported_shape_count: int
    parsed_line_count: int
    end_byte: int
    end_line: int


def parse_jsonl(
    plan: SourcePlan,
    prior_state: ParserState | None = None,
) -> ParsedBatch:
    """Parse one complete source range and retain only normalized structure."""

    events: list[StructuralEvent] = []
    warnings = 0
    unsupported = 0
    parsed = 0
    state = prior_state or ParserState()
    end_byte = plan.start_byte
    end_line = plan.start_line
    for batch in iter_jsonl_batches(plan, prior_state, max_lines=1000):
        events.extend(batch.events)
        warnings = batch.parse_warning_count
        unsupported = batch.unsupported_shape_count
        parsed += batch.parsed_line_count
        state = batch.final_state
        end_byte = batch.end_byte
        end_line = batch.end_line
    return ParsedBatch(
        events=tuple(events),
        final_state=state,
        parse_warning_count=warnings,
        unsupported_shape_count=unsupported,
        parsed_line_count=parsed,
        end_byte=end_byte,
        end_line=end_line,
    )


def iter_jsonl_batches(
    plan: SourcePlan,
    prior_state: ParserState | None = None,
    *,
    max_lines: int = 1000,
) -> Iterator[ParsedBatch]:
    """Yield bounded structural batches while preserving parser state."""

    if max_lines < 1:
        raise ValueError("max_lines must be positive")
    state = prior_state or ParserState()
    events: list[StructuralEvent] = []
    total_warnings = 0
    total_unsupported = 0
    parsed = 0
    batch_lines = 0
    offset = plan.start_byte
    with plan.observation.path.open("rb") as handle:
        handle.seek(plan.start_byte)
        while offset < plan.end_byte:
            line = handle.readline(plan.end_byte - offset)
            if not line:
                break
            line_number = plan.start_line + parsed
            parsed += 1
            batch_lines += 1
            try:
                envelope = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                total_warnings += 1
            else:
                parsed_events, state, recognized = _parse_envelope(
                    envelope,
                    state,
                    source_offset=offset,
                    line_number=line_number,
                )
                events.extend(parsed_events)
                if not recognized:
                    total_unsupported += 1
            offset += len(line)
            if batch_lines >= max_lines:
                yield ParsedBatch(
                    events=tuple(events),
                    final_state=state,
                    parse_warning_count=total_warnings,
                    unsupported_shape_count=total_unsupported,
                    parsed_line_count=batch_lines,
                    end_byte=offset,
                    end_line=plan.start_line + parsed,
                )
                events = []
                batch_lines = 0
    if batch_lines or plan.start_byte == plan.end_byte:
        yield ParsedBatch(
            events=tuple(events),
            final_state=state,
            parse_warning_count=total_warnings,
            unsupported_shape_count=total_unsupported,
            parsed_line_count=batch_lines,
            end_byte=offset,
            end_line=plan.start_line + parsed,
        )


def _parse_envelope(
    envelope: Any,
    state: ParserState,
    *,
    source_offset: int,
    line_number: int,
) -> tuple[list[StructuralEvent], ParserState, bool]:
    if not isinstance(envelope, dict):
        return [], state, False
    envelope_type = envelope.get("type")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return [], state, False
    timestamp = _safe_timestamp(envelope.get("timestamp"))
    if envelope_type == "session_meta":
        return [], _session_state(state, payload), True
    if envelope_type == "turn_context":
        return [], _turn_state(state, payload), True
    if envelope_type == "response_item":
        if payload.get("type") == "function_call":
            event = _base_event(
                "tool",
                timestamp,
                source_offset,
                line_number,
                state,
                tool_name=_safe_name(payload.get("name")) or "function_call",
            )
            return [event], state, True
        return [], state, True
    if envelope_type != "event_msg":
        return [], state, False
    event_type = payload.get("type")
    if event_type == "token_count":
        return _token_events(
            envelope,
            payload,
            state,
            timestamp,
            source_offset,
            line_number,
        ), state, True
    if event_type == "mcp_tool_call_end":
        event = _base_event(
            "tool",
            timestamp,
            source_offset,
            line_number,
            state,
            tool_name=_safe_name(payload.get("tool_name")) or "mcp_tool",
            server_name=_safe_name(payload.get("server_name")),
        )
        return [event], state, True
    activity = _ACTIVITY_KINDS.get(str(event_type))
    if activity is not None:
        label = _activity_label(activity, payload)
        event = _base_event(
            "activity",
            timestamp,
            source_offset,
            line_number,
            state,
            activity_kind=activity,
            activity_label=label,
        )
        return [event], state, True
    return [], state, True


def _session_state(state: ParserState, payload: dict[str, Any]) -> ParserState:
    source = payload.get("source")
    subagent = source.get("subagent") if isinstance(source, dict) else None
    spawn = subagent.get("thread_spawn") if isinstance(subagent, dict) else None
    spawn = spawn if isinstance(spawn, dict) else {}
    return replace(
        state,
        session_id=_safe_identifier(payload.get("id")),
        parent_session_id=_safe_identifier(spawn.get("parent_thread_id")),
        agent_role=_safe_name(spawn.get("agent_role")),
        agent_nickname=_safe_display(spawn.get("agent_nickname")),
    )


def _turn_state(state: ParserState, payload: dict[str, Any]) -> ParserState:
    return replace(
        state,
        turn_id=_safe_identifier(payload.get("turn_id")),
        turn_ordinal=state.turn_ordinal + 1,
        model=_safe_name(payload.get("model")) or "unknown",
        effort=_safe_name(payload.get("effort")),
        service_tier=_safe_name(payload.get("service_tier")),
    )


def _token_events(
    envelope: dict[str, Any],
    payload: dict[str, Any],
    state: ParserState,
    timestamp: str,
    source_offset: int,
    line_number: int,
) -> list[StructuralEvent]:
    info = payload.get("info")
    info = info if isinstance(info, dict) else {}
    usage = info.get("last_token_usage")
    usage = usage if isinstance(usage, dict) else {}
    event = _base_event(
        "model_call",
        timestamp,
        source_offset,
        line_number,
        state,
        upstream_id=_safe_identifier(envelope.get("event_id")),
        input_tokens=_nonnegative_int(usage.get("input_tokens")),
        cached_input_tokens=_nonnegative_int(usage.get("cached_input_tokens")),
        output_tokens=_nonnegative_int(usage.get("output_tokens")),
        reasoning_tokens=_nonnegative_int(usage.get("reasoning_output_tokens")),
        upstream_total_tokens=_optional_nonnegative_int(usage.get("total_tokens")),
        context_window=_optional_positive_int(info.get("model_context_window")),
    )
    return [event, *_allowance_events(event, payload)]


def _allowance_events(
    call: StructuralEvent,
    payload: dict[str, Any],
) -> list[StructuralEvent]:
    limits = payload.get("rate_limits")
    if not isinstance(limits, dict):
        return []
    events: list[StructuralEvent] = []
    for window in ("primary", "secondary"):
        observation = limits.get(window)
        if not isinstance(observation, dict):
            continue
        used = observation.get("used_percent")
        if not isinstance(used, (int, float)) or not 0 <= float(used) <= 100:
            continue
        events.append(
            replace(
                call,
                kind="allowance",
                allowance_window=window,
                allowance_used_percent=float(used),
                allowance_duration_minutes=_optional_positive_int(
                    observation.get("window_minutes")
                ),
                allowance_resets_at=_safe_reset(observation.get("resets_at")),
                allowance_plan_type=_safe_name(limits.get("plan_type")),
                allowance_limit_id=_safe_name(limits.get("limit_id")),
            )
        )
    return events


def _base_event(
    kind: str,
    timestamp: str,
    source_offset: int,
    line_number: int,
    state: ParserState,
    **values: Any,
) -> StructuralEvent:
    return StructuralEvent(
        kind=kind,
        timestamp=timestamp,
        source_offset=source_offset,
        line_number=line_number,
        session_id=state.session_id,
        parent_session_id=state.parent_session_id,
        agent_role=state.agent_role,
        agent_nickname=state.agent_nickname,
        turn_id=state.turn_id,
        turn_ordinal=state.turn_ordinal,
        model=state.model,
        effort=state.effort,
        service_tier=state.service_tier,
        **values,
    )


def _activity_label(activity: str, payload: dict[str, Any]) -> str | None:
    if activity == "skill":
        return _safe_display(payload.get("skill_name"))
    return None


def _safe_name(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_NAME.fullmatch(value) else None


def _safe_display(value: Any) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    try:
        return safe_label(value)
    except ValueError:
        return None


def _safe_identifier(value: Any) -> str | None:
    return _safe_name(value)


def _safe_timestamp(value: Any) -> str:
    return value if isinstance(value, str) and 10 <= len(value) <= 40 else ""


def _safe_reset(value: Any) -> str | None:
    return str(value) if isinstance(value, (int, float, str)) else None


def _nonnegative_int(value: Any) -> int:
    return max(0, int(value)) if isinstance(value, (int, float)) else 0


def _optional_nonnegative_int(value: Any) -> int | None:
    return _nonnegative_int(value) if isinstance(value, (int, float)) else None


def _optional_positive_int(value: Any) -> int | None:
    parsed = _optional_nonnegative_int(value)
    return parsed if parsed and parsed > 0 else None
