"""Codex JSONL v1 aggregate parser implementation."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.call_origin import (
    CallOriginFlags,
    classify_call_origin,
    event_flags_from_envelope,
)
from codex_usage_tracker.core.models import DiagnosticFact, SessionInfo, UsageEvent
from codex_usage_tracker.diagnostics.facts import (
    add_diagnostic_fact,
    assign_record_id_to_diagnostic_facts,
    diagnostic_facts_from_envelope,
)
from codex_usage_tracker.parser.jsonl_values import (
    build_usage_event,
    empty_session_metadata,
    increment_stat,
    nullable_int,
    required_usage_int,
    session_id_from_path,
    session_metadata,
)
from codex_usage_tracker.parser.state import ParserState, optional_str

KNOWN_NON_TOKEN_EVENT_MSG_TYPES = frozenset(
    {
        "agent_message",
        "context_compacted",
        "image_generation_end",
        "item_completed",
        "mcp_tool_call_begin",
        "mcp_tool_call_end",
        "patch_apply_end",
        "skill_completed",
        "skill_invoked",
        "skill_selected",
        "skill_started",
        "skill_used",
        "task_complete",
        "task_started",
        "thread_goal_updated",
        "thread_rolled_back",
        "turn_aborted",
        "user_message",
        "web_search_end",
        "web_search_begin",
    }
)

@dataclass(frozen=True)
class ParsedUsageFile:
    """Parsed aggregate usage events plus the final parser cursor."""
    events: list[UsageEvent]
    diagnostic_facts: list[DiagnosticFact]
    state: ParserState
    final_line_number: int = 0


@dataclass
class _JsonlParseState:
    session_id: str | None
    session_info: SessionInfo | None
    current_turn: dict[str, Any]
    session_meta: dict[str, str | None]
    last_cumulative_total: int
    events: list[UsageEvent]
    diagnostic_facts: list[DiagnosticFact]
    call_origin_segment: list[CallOriginFlags]
    diagnostic_facts_segment: tuple[DiagnosticFact, ...]
    latest_record_id: str | None
    latest_event_timestamp: str | None


def parse_codex_jsonl_v1(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
    *,
    start_byte: int = 0,
    start_line: int = 0,
    initial_state: ParserState | None = None,
) -> ParsedUsageFile:
    """Parse one Codex JSONL v1 log without storing raw message content."""

    index = session_index or {}
    file_session_id = session_id_from_path(path)
    if not file_session_id and start_byte <= 0:
        increment_stat(stats, "unknown_filename_format")

    previous_state = initial_state or ParserState()
    state = _initial_jsonl_parse_state(previous_state, file_session_id, index)
    final_line_number = start_line

    with path.open("rb") as handle:
        if start_byte > 0:
            handle.seek(start_byte)
        for line_number, raw_line in enumerate(handle, start_line + 1):
            final_line_number = line_number
            _handle_jsonl_line(
                path=path,
                index=index,
                state=state,
                line_number=line_number,
                raw_line=raw_line,
                stats=stats,
            )

    return ParsedUsageFile(
        events=state.events,
        diagnostic_facts=state.diagnostic_facts,
        state=ParserState(
            session_id=state.session_id,
            session_meta=state.session_meta,
            current_turn=state.current_turn,
            last_cumulative_total=state.last_cumulative_total,
            call_origin_segment=tuple(state.call_origin_segment),
            diagnostic_facts_segment=state.diagnostic_facts_segment,
            latest_record_id=state.latest_record_id,
            latest_event_timestamp=state.latest_event_timestamp,
        ),
        final_line_number=final_line_number,
    )


def _initial_jsonl_parse_state(
    previous_state: ParserState,
    file_session_id: str | None,
    index: dict[str, SessionInfo],
) -> _JsonlParseState:
    session_id = previous_state.session_id or file_session_id
    session_meta = (
        dict(previous_state.session_meta)
        if previous_state.session_meta
        else empty_session_metadata()
    )
    return _JsonlParseState(
        session_id=session_id,
        session_info=index.get(session_id) if session_id else None,
        current_turn=dict(previous_state.current_turn),
        session_meta=session_meta,
        last_cumulative_total=previous_state.last_cumulative_total,
        events=[],
        diagnostic_facts=[],
        call_origin_segment=list(previous_state.call_origin_segment),
        diagnostic_facts_segment=previous_state.diagnostic_facts_segment,
        latest_record_id=previous_state.latest_record_id,
        latest_event_timestamp=previous_state.latest_event_timestamp,
    )


def _handle_jsonl_line(
    *,
    path: Path,
    index: dict[str, SessionInfo],
    state: _JsonlParseState,
    line_number: int,
    raw_line: bytes,
    stats: MutableMapping[str, int] | None,
) -> None:
    envelope = _jsonl_envelope(raw_line, stats)
    if envelope is None:
        return
    payload = _jsonl_payload(envelope, stats)
    if payload is None:
        return

    entry_type = envelope.get("type")
    timestamp = optional_str(envelope.get("timestamp")) or ""
    if _handle_session_meta(entry_type, payload, index, state):
        return

    turn_context = _turn_context_payload(entry_type, payload, timestamp)
    if turn_context is not None:
        state.current_turn = turn_context
        return

    payload_type = payload.get("type")
    skipped, state.call_origin_segment, state.diagnostic_facts_segment = (
        _handle_non_token_event(
            envelope=envelope,
            entry_type=entry_type,
            payload_type=payload_type,
            line_number=line_number,
            call_origin_segment=state.call_origin_segment,
            diagnostic_facts_segment=state.diagnostic_facts_segment,
            stats=stats,
        )
    )
    if skipped:
        return
    _handle_token_count_event(
        path=path,
        index=index,
        state=state,
        line_number=line_number,
        timestamp=timestamp,
        payload=payload,
        stats=stats,
    )


def _handle_session_meta(
    entry_type: object,
    payload: dict[str, Any],
    index: dict[str, SessionInfo],
    state: _JsonlParseState,
) -> bool:
    if entry_type != "session_meta":
        return False
    if not state.session_id:
        state.session_id = optional_str(payload.get("id"))
        state.session_info = index.get(state.session_id) if state.session_id else None
    state.session_meta = session_metadata(payload, index)
    return True


def _handle_token_count_event(
    *,
    path: Path,
    index: dict[str, SessionInfo],
    state: _JsonlParseState,
    line_number: int,
    timestamp: str,
    payload: dict[str, Any],
    stats: MutableMapping[str, int] | None,
) -> None:
    call_origin = classify_call_origin(state.call_origin_segment)
    state.call_origin_segment = []
    usage_payload = _token_usage_payload(payload, stats)
    if usage_payload is None:
        return
    info, total_usage, last_usage = usage_payload

    cumulative_total = _cumulative_usage_total(total_usage, stats)
    if cumulative_total is None:
        return
    if cumulative_total <= state.last_cumulative_total:
        increment_stat(stats, "duplicate_cumulative_total")
        return

    effective_session_id = state.session_id or "unknown"
    state.session_info = state.session_info or index.get(effective_session_id)
    event = _build_token_count_event(
        path=path,
        line_number=line_number,
        timestamp=timestamp,
        session_id=effective_session_id,
        session_info=state.session_info,
        session_meta=state.session_meta,
        current_turn=state.current_turn,
        call_origin=call_origin,
        payload=payload,
        info=info,
        total_usage=total_usage,
        last_usage=last_usage,
        stats=stats,
    )
    if event is None:
        return
    _record_jsonl_usage_event(state, event, cumulative_total)


def _record_jsonl_usage_event(
    state: _JsonlParseState,
    event: UsageEvent,
    cumulative_total: int,
) -> None:
    state.last_cumulative_total = cumulative_total
    state.latest_record_id = event.record_id
    state.latest_event_timestamp = event.event_timestamp
    state.events.append(event)
    state.diagnostic_facts.extend(
        assign_record_id_to_diagnostic_facts(
            state.diagnostic_facts_segment, record_id=event.record_id
        )
    )
    state.diagnostic_facts_segment = ()


def _jsonl_envelope(
    raw_line: bytes, stats: MutableMapping[str, int] | None
) -> dict[str, Any] | None:
    try:
        line = raw_line.decode("utf-8")
        envelope = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        increment_stat(stats, "invalid_json")
        return None
    return envelope if isinstance(envelope, dict) else None


def _jsonl_payload(
    envelope: dict[str, Any], stats: MutableMapping[str, int] | None
) -> dict[str, Any] | None:
    payload = envelope.get("payload")
    if isinstance(payload, dict):
        return payload
    increment_stat(stats, "missing_payload")
    return None


def _turn_context_payload(
    entry_type: object, payload: dict[str, Any], timestamp: str
) -> dict[str, Any] | None:
    if entry_type != "turn_context":
        return None
    return {
        "turn_id": optional_str(payload.get("turn_id")),
        "turn_timestamp": timestamp,
        "cwd": optional_str(payload.get("cwd")),
        "model": optional_str(payload.get("model")),
        "effort": optional_str(payload.get("effort")),
        "current_date": optional_str(payload.get("current_date")),
        "timezone": optional_str(payload.get("timezone")),
    }


def _handle_non_token_event(
    *,
    envelope: dict[str, Any],
    entry_type: object,
    payload_type: object,
    line_number: int,
    call_origin_segment: list[CallOriginFlags],
    diagnostic_facts_segment: tuple[DiagnosticFact, ...],
    stats: MutableMapping[str, int] | None,
) -> tuple[bool, list[CallOriginFlags], tuple[DiagnosticFact, ...]]:
    if entry_type == "event_msg" and payload_type == "token_count":
        return False, call_origin_segment, diagnostic_facts_segment

    flags = event_flags_from_envelope(envelope)
    if flags.has_signal:
        call_origin_segment.append(flags)
    for fact in diagnostic_facts_from_envelope(envelope, line_number=line_number):
        diagnostic_facts_segment = add_diagnostic_fact(diagnostic_facts_segment, fact)
    if entry_type == "event_msg" and payload_type not in KNOWN_NON_TOKEN_EVENT_MSG_TYPES:
        increment_stat(stats, "unknown_event_shape")
    return True, call_origin_segment, diagnostic_facts_segment


def _token_usage_payload(
    payload: dict[str, Any], stats: MutableMapping[str, int] | None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None:
    info = payload.get("info")
    if not isinstance(info, dict):
        increment_stat(stats, "missing_info")
        return None
    total_usage = info.get("total_token_usage")
    last_usage = info.get("last_token_usage")
    if not isinstance(total_usage, dict):
        increment_stat(stats, "missing_total_token_usage")
        increment_stat(stats, "skipped_events")
        return None
    if not isinstance(last_usage, dict):
        increment_stat(stats, "missing_last_token_usage")
        increment_stat(stats, "skipped_events")
        return None
    return info, total_usage, last_usage


def _cumulative_usage_total(
    total_usage: dict[str, Any], stats: MutableMapping[str, int] | None
) -> int | None:
    try:
        return required_usage_int(
            total_usage,
            "total_tokens",
            stats=stats,
            missing_key="missing_cumulative_total",
        )
    except ValueError:
        increment_stat(stats, "skipped_events")
        return None


def _build_token_count_event(
    *,
    path: Path,
    line_number: int,
    timestamp: str,
    session_id: str,
    session_info: SessionInfo | None,
    session_meta: dict[str, str | None],
    current_turn: dict[str, Any],
    call_origin: dict[str, str],
    payload: dict[str, Any],
    info: dict[str, Any],
    total_usage: dict[str, Any],
    last_usage: dict[str, Any],
    stats: MutableMapping[str, int] | None,
) -> UsageEvent | None:
    try:
        return build_usage_event(
            path=path,
            line_number=line_number,
            event_timestamp=timestamp,
            session_id=session_id,
            session_info=session_info,
            session_meta=session_meta,
            current_turn=current_turn,
            call_origin=call_origin,
            model_context_window=nullable_int(
                info.get("model_context_window"),
                stats=stats,
                invalid_key="invalid_model_context_window",
            ),
            last_usage=last_usage,
            total_usage=total_usage,
            rate_limits=payload.get("rate_limits"),
            stats=stats,
        )
    except ValueError:
        increment_stat(stats, "skipped_events")
        return None
