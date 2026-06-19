"""Parse Codex JSONL session logs into aggregate usage records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codex_usage_tracker.call_origin import (
    CallOriginFlags,
    classify_call_origin,
    event_flags_from_envelope,
)
from codex_usage_tracker.diagnostic_facts import (
    add_diagnostic_fact,
    assign_record_id_to_diagnostic_facts,
    diagnostic_fact_from_json,
    diagnostic_fact_to_json,
    diagnostic_facts_from_envelope,
)
from codex_usage_tracker.models import DiagnosticFact, SessionInfo, UsageEvent
from codex_usage_tracker.paths import DEFAULT_CODEX_HOME

SESSION_ID_RE = re.compile(
    r"rollout-[^-]+-[0-9T:-]+-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.jsonl$"
)

PARSER_ADAPTER_VERSION = "codex-jsonl-v1"
PARSER_DIAGNOSTIC_KEYS = (
    "invalid_json",
    "missing_payload",
    "unknown_filename_format",
    "unknown_event_shape",
    "missing_info",
    "missing_last_token_usage",
    "missing_total_token_usage",
    "missing_cumulative_total",
    "duplicate_cumulative_total",
    "invalid_integer",
    "partial_field_count",
    "invalid_model_context_window",
    "skipped_events",
)

KNOWN_NON_TOKEN_EVENT_MSG_TYPES = frozenset({
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
})


@dataclass(frozen=True)
class ParserAdapter:
    """Versioned parser adapter for one Codex log format family."""

    version: str = PARSER_ADAPTER_VERSION

    def parse_file(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        return self.parse_file_with_state(
            path,
            session_index=session_index,
            stats=stats,
        ).events

    def parse_file_with_state(
        self,
        path: Path,
        session_index: dict[str, SessionInfo] | None = None,
        stats: MutableMapping[str, int] | None = None,
        *,
        start_byte: int = 0,
        start_line: int = 0,
        initial_state: ParserState | None = None,
    ) -> ParsedUsageFile:
        return _parse_codex_jsonl_v1(
            path,
            session_index=session_index,
            stats=stats,
            start_byte=start_byte,
            start_line=start_line,
            initial_state=initial_state,
        )


DEFAULT_PARSER_ADAPTER = ParserAdapter()


@dataclass(frozen=True)
class ParserState:
    """Aggregate-only parser cursor for continuing append-only JSONL parsing."""

    session_id: str | None = None
    session_meta: dict[str, str | None] = field(default_factory=dict)
    current_turn: dict[str, Any] = field(default_factory=dict)
    last_cumulative_total: int = -1
    call_origin_segment: tuple[CallOriginFlags, ...] = ()
    diagnostic_facts_segment: tuple[DiagnosticFact, ...] = ()
    latest_record_id: str | None = None
    latest_event_timestamp: str | None = None


@dataclass(frozen=True)
class ParsedUsageFile:
    """Parsed aggregate usage events plus the final parser cursor."""

    events: list[UsageEvent]
    diagnostic_facts: list[DiagnosticFact]
    state: ParserState


def load_session_index(codex_home: Path = DEFAULT_CODEX_HOME) -> dict[str, SessionInfo]:
    """Load Codex thread names without reading transcript content."""

    index_path = codex_home / "session_index.jsonl"
    sessions: dict[str, SessionInfo] = {}
    if not index_path.exists():
        return sessions

    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            session_id = payload.get("id")
            if not isinstance(session_id, str):
                continue
            sessions[session_id] = SessionInfo(
                session_id=session_id,
                thread_name=_optional_str(payload.get("thread_name")),
                updated_at=_optional_str(payload.get("updated_at")),
            )
    return sessions


def find_session_logs(
    codex_home: Path = DEFAULT_CODEX_HOME, include_archived: bool = False
) -> list[Path]:
    """Find local Codex JSONL logs."""

    paths = list((codex_home / "sessions").glob("**/*.jsonl"))
    if include_archived:
        paths.extend((codex_home / "archived_sessions").glob("*.jsonl"))
    return sorted(path for path in paths if path.is_file())


def parse_usage_events(
    paths: Iterable[Path],
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse all provided logs into aggregate usage events."""

    index = session_index or {}
    events: list[UsageEvent] = []
    for path in paths:
        events.extend(parse_usage_events_from_file(path, index, stats=stats))
    return events


def parse_usage_events_from_file(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    """Parse one Codex JSONL log without storing raw message content."""

    return DEFAULT_PARSER_ADAPTER.parse_file(path, session_index=session_index, stats=stats)


def parse_usage_events_from_file_with_state(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
    stats: MutableMapping[str, int] | None = None,
    *,
    start_byte: int = 0,
    start_line: int = 0,
    initial_state: ParserState | None = None,
) -> ParsedUsageFile:
    """Parse one Codex JSONL log and return an aggregate-only continuation cursor."""

    return DEFAULT_PARSER_ADAPTER.parse_file_with_state(
        path,
        session_index=session_index,
        stats=stats,
        start_byte=start_byte,
        start_line=start_line,
        initial_state=initial_state,
    )


def parser_state_from_json(raw: str | None) -> ParserState | None:
    """Decode a persisted aggregate-only parser cursor."""

    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    segment = payload.get("call_origin_segment")
    if not isinstance(segment, list):
        segment = []
    diagnostic_segment = payload.get("diagnostic_facts_segment")
    if not isinstance(diagnostic_segment, list):
        diagnostic_segment = []
    return ParserState(
        session_id=_optional_str(payload.get("session_id")),
        session_meta=_string_dict(payload.get("session_meta")),
        current_turn=_string_dict(payload.get("current_turn")),
        last_cumulative_total=_json_int(payload.get("last_cumulative_total"), -1),
        call_origin_segment=tuple(_call_origin_flags_from_json(item) for item in segment),
        diagnostic_facts_segment=tuple(
            fact
            for fact in (
                diagnostic_fact_from_json(item) for item in diagnostic_segment
            )
            if fact is not None
        ),
        latest_record_id=_optional_str(payload.get("latest_record_id")),
        latest_event_timestamp=_optional_str(payload.get("latest_event_timestamp")),
    )


def parser_state_to_json(state: ParserState) -> str:
    """Encode an aggregate-only parser cursor for source-file refresh metadata."""

    return json.dumps(
        {
            "version": 1,
            "session_id": state.session_id,
            "session_meta": state.session_meta,
            "current_turn": state.current_turn,
            "last_cumulative_total": state.last_cumulative_total,
            "call_origin_segment": [
                {
                    "user_message": flags.user_message,
                    "compaction": flags.compaction,
                    "tool_result": flags.tool_result,
                    "codex_activity": flags.codex_activity,
                }
                for flags in state.call_origin_segment
            ],
            "diagnostic_facts_segment": [
                diagnostic_fact_to_json(fact) for fact in state.diagnostic_facts_segment
            ],
            "latest_record_id": state.latest_record_id,
            "latest_event_timestamp": state.latest_event_timestamp,
        },
        sort_keys=True,
    )


def inspect_log(
    path: Path,
    session_index: dict[str, SessionInfo] | None = None,
) -> dict[str, object]:
    """Return aggregate-only parser observations for one log without DB writes."""

    stats = empty_parser_diagnostics()
    events = parse_usage_events_from_file(path, session_index=session_index, stats=stats)
    session_ids = sorted({event.session_id for event in events})
    models = sorted({event.model for event in events if event.model})
    efforts = sorted({event.effort for event in events if event.effort})
    first_event = events[0] if events else None
    last_event = events[-1] if events else None
    return {
        "path": str(path),
        "adapter": DEFAULT_PARSER_ADAPTER.version,
        "file_session_id": _session_id_from_path(path),
        "event_count": len(events),
        "session_ids": session_ids,
        "models": models,
        "efforts": efforts,
        "first_event_timestamp": first_event.event_timestamp if first_event else None,
        "last_event_timestamp": last_event.event_timestamp if last_event else None,
        "diagnostics": compact_parser_diagnostics(stats),
        "events": [
            {
                "record_id": event.record_id,
                "line_number": event.line_number,
                "event_timestamp": event.event_timestamp,
                "session_id": event.session_id,
                "turn_id": event.turn_id,
                "model": event.model,
                "effort": event.effort,
                "input_tokens": event.input_tokens,
                "cached_input_tokens": event.cached_input_tokens,
                "uncached_input_tokens": event.uncached_input_tokens,
                "output_tokens": event.output_tokens,
                "reasoning_output_tokens": event.reasoning_output_tokens,
                "total_tokens": event.total_tokens,
                "cumulative_total_tokens": event.cumulative_total_tokens,
                "is_archived": event.is_archived,
                "thread_key": event.thread_key,
            }
            for event in events
        ],
    }


def empty_parser_diagnostics() -> dict[str, int]:
    """Return all parser diagnostic counters initialized to zero."""

    return {key: 0 for key in PARSER_DIAGNOSTIC_KEYS}


def compact_parser_diagnostics(stats: MutableMapping[str, int]) -> dict[str, int]:
    """Return non-zero parser diagnostics in stable key order."""

    return {key: int(stats.get(key, 0)) for key in PARSER_DIAGNOSTIC_KEYS if stats.get(key, 0)}


def _parse_codex_jsonl_v1(
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
    file_session_id = _session_id_from_path(path)
    if not file_session_id and start_byte <= 0:
        _increment_stat(stats, "unknown_filename_format")
    previous_state = initial_state or ParserState()
    session_id = previous_state.session_id or file_session_id
    session_info = index.get(session_id) if session_id else None
    current_turn: dict[str, Any] = dict(previous_state.current_turn)
    session_meta: dict[str, str | None] = (
        dict(previous_state.session_meta)
        if previous_state.session_meta
        else _empty_session_metadata()
    )
    last_cumulative_total = previous_state.last_cumulative_total
    events: list[UsageEvent] = []
    diagnostic_facts: list[DiagnosticFact] = []
    call_origin_segment: list[CallOriginFlags] = list(previous_state.call_origin_segment)
    diagnostic_facts_segment = previous_state.diagnostic_facts_segment
    latest_record_id = previous_state.latest_record_id
    latest_event_timestamp = previous_state.latest_event_timestamp

    with path.open("rb") as handle:
        if start_byte > 0:
            handle.seek(start_byte)
        for line_number, raw_line in enumerate(handle, start_line + 1):
            try:
                line = raw_line.decode("utf-8")
                envelope = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                _increment_stat(stats, "invalid_json")
                continue

            payload = envelope.get("payload")
            if not isinstance(payload, dict):
                _increment_stat(stats, "missing_payload")
                continue

            entry_type = envelope.get("type")
            timestamp = _optional_str(envelope.get("timestamp")) or ""

            if entry_type == "session_meta":
                if not session_id:
                    session_id = _optional_str(payload.get("id"))
                    session_info = index.get(session_id or "")
                session_meta = _session_metadata(payload, index)
                continue

            if entry_type == "turn_context":
                current_turn = {
                    "turn_id": _optional_str(payload.get("turn_id")),
                    "turn_timestamp": timestamp,
                    "cwd": _optional_str(payload.get("cwd")),
                    "model": _optional_str(payload.get("model")),
                    "effort": _optional_str(payload.get("effort")),
                    "current_date": _optional_str(payload.get("current_date")),
                    "timezone": _optional_str(payload.get("timezone")),
                }
                continue

            payload_type = payload.get("type")
            if entry_type != "event_msg" or payload_type != "token_count":
                flags = event_flags_from_envelope(envelope)
                if flags.has_signal:
                    call_origin_segment.append(flags)
                for fact in diagnostic_facts_from_envelope(
                    envelope,
                    line_number=line_number,
                ):
                    diagnostic_facts_segment = add_diagnostic_fact(
                        diagnostic_facts_segment,
                        fact,
                    )
                if entry_type == "event_msg" and payload_type not in KNOWN_NON_TOKEN_EVENT_MSG_TYPES:
                    _increment_stat(stats, "unknown_event_shape")
                continue

            call_origin = classify_call_origin(call_origin_segment)
            call_origin_segment = []
            info = payload.get("info")
            if not isinstance(info, dict):
                _increment_stat(stats, "missing_info")
                continue

            total_usage = info.get("total_token_usage")
            last_usage = info.get("last_token_usage")
            if not isinstance(total_usage, dict):
                _increment_stat(stats, "missing_total_token_usage")
                _increment_stat(stats, "skipped_events")
                continue
            if not isinstance(last_usage, dict):
                _increment_stat(stats, "missing_last_token_usage")
                _increment_stat(stats, "skipped_events")
                continue

            try:
                cumulative_total = _required_usage_int(
                    total_usage,
                    "total_tokens",
                    stats=stats,
                    missing_key="missing_cumulative_total",
                )
            except ValueError:
                _increment_stat(stats, "skipped_events")
                continue
            if cumulative_total <= last_cumulative_total:
                _increment_stat(stats, "duplicate_cumulative_total")
                continue

            effective_session_id = session_id or "unknown"
            session_info = session_info or index.get(effective_session_id)
            try:
                event = _build_event(
                    path=path,
                    line_number=line_number,
                    event_timestamp=timestamp,
                    session_id=effective_session_id,
                    session_info=session_info,
                    session_meta=session_meta,
                    current_turn=current_turn,
                    call_origin=call_origin,
                    model_context_window=_nullable_int(
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
                _increment_stat(stats, "skipped_events")
                continue
            last_cumulative_total = cumulative_total
            latest_record_id = event.record_id
            latest_event_timestamp = event.event_timestamp
            events.append(event)
            diagnostic_facts.extend(
                assign_record_id_to_diagnostic_facts(
                    diagnostic_facts_segment,
                    record_id=event.record_id,
                )
            )
            diagnostic_facts_segment = ()

    return ParsedUsageFile(
        events=events,
        diagnostic_facts=diagnostic_facts,
        state=ParserState(
            session_id=session_id,
            session_meta=session_meta,
            current_turn=current_turn,
            last_cumulative_total=last_cumulative_total,
            call_origin_segment=tuple(call_origin_segment),
            diagnostic_facts_segment=diagnostic_facts_segment,
            latest_record_id=latest_record_id,
            latest_event_timestamp=latest_event_timestamp,
        ),
    )


def _build_event(
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
    stats: MutableMapping[str, int] | None = None,
) -> UsageEvent:
    input_tokens = _required_usage_int(last_usage, "input_tokens", stats=stats)
    cached_input_tokens = _required_usage_int(last_usage, "cached_input_tokens", stats=stats)
    output_tokens = _required_usage_int(last_usage, "output_tokens", stats=stats)
    reasoning_output_tokens = _required_usage_int(
        last_usage, "reasoning_output_tokens", stats=stats
    )
    total_tokens = _required_usage_int(last_usage, "total_tokens", stats=stats)
    cumulative_total_tokens = _required_usage_int(
        total_usage,
        "total_tokens",
        stats=stats,
        missing_key="missing_cumulative_total",
    )
    observed_usage = _observed_usage_from_rate_limits(rate_limits, stats=stats)
    record_id = _record_id(
        session_id=session_id,
        turn_id=_optional_str(current_turn.get("turn_id")),
        event_timestamp=event_timestamp,
        cumulative_total_tokens=cumulative_total_tokens,
        total_tokens=total_tokens,
    )
    return UsageEvent(
        record_id=record_id,
        session_id=session_id,
        thread_name=session_info.thread_name if session_info else None,
        session_updated_at=session_info.updated_at if session_info else None,
        event_timestamp=event_timestamp,
        source_file=str(path),
        line_number=line_number,
        turn_id=_optional_str(current_turn.get("turn_id")),
        turn_timestamp=_optional_str(current_turn.get("turn_timestamp")),
        cwd=_optional_str(current_turn.get("cwd")),
        model=_optional_str(current_turn.get("model")),
        effort=_optional_str(current_turn.get("effort")),
        current_date=_optional_str(current_turn.get("current_date")),
        timezone=_optional_str(current_turn.get("timezone")),
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
        cumulative_input_tokens=_required_usage_int(total_usage, "input_tokens", stats=stats),
        cumulative_cached_input_tokens=_required_usage_int(
            total_usage, "cached_input_tokens", stats=stats
        ),
        cumulative_output_tokens=_required_usage_int(total_usage, "output_tokens", stats=stats),
        cumulative_reasoning_output_tokens=_required_usage_int(
            total_usage, "reasoning_output_tokens", stats=stats
        ),
        cumulative_total_tokens=cumulative_total_tokens,
        **observed_usage,
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
        "rate_limit_plan_type": _optional_str(value.get("plan_type")),
        "rate_limit_limit_id": _optional_str(value.get("limit_id")),
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
        f"rate_limit_{prefix}_window_minutes": _nullable_int(
            value.get("window_minutes"),
            stats=stats,
        ),
        f"rate_limit_{prefix}_resets_at": _nullable_int(
            value.get("resets_at"),
            stats=stats,
        ),
    }


def _session_metadata(
    payload: dict[str, Any],
    session_index: dict[str, SessionInfo],
) -> dict[str, str | None]:
    source = payload.get("source")
    metadata = _empty_session_metadata()
    metadata["thread_source"] = _optional_str(payload.get("thread_source"))
    if not isinstance(source, dict):
        return metadata

    subagent = source.get("subagent")
    if not isinstance(subagent, dict):
        return metadata

    other = _optional_str(subagent.get("other"))
    if other:
        metadata["subagent_type"] = other
        return metadata

    thread_spawn = subagent.get("thread_spawn")
    if isinstance(thread_spawn, dict):
        metadata["subagent_type"] = "thread_spawn"
        metadata["agent_role"] = _optional_str(thread_spawn.get("agent_role"))
        metadata["agent_nickname"] = _optional_str(thread_spawn.get("agent_nickname"))
        parent_session_id = _optional_str(thread_spawn.get("parent_thread_id"))
        metadata["parent_session_id"] = parent_session_id
        if parent_session_id:
            parent_info = session_index.get(parent_session_id)
            if parent_info:
                metadata["parent_thread_name"] = parent_info.thread_name
                metadata["parent_session_updated_at"] = parent_info.updated_at
    return metadata


def _empty_session_metadata() -> dict[str, str | None]:
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


def _session_id_from_path(path: Path) -> str | None:
    match = SESSION_ID_RE.search(path.name)
    if not match:
        return None
    return match.group(1)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _string_dict(value: object) -> dict[str, str | None]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item if isinstance(item, str) else None
        for key, item in value.items()
        if isinstance(key, str)
    }


def _json_int(value: object, default: int) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _call_origin_flags_from_json(value: object) -> CallOriginFlags:
    if not isinstance(value, dict):
        return CallOriginFlags()
    return CallOriginFlags(
        user_message=value.get("user_message") is True,
        compaction=value.get("compaction") is True,
        tool_result=value.get("tool_result") is True,
        codex_activity=value.get("codex_activity") is True,
    )


def _nullable_int(
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
        _increment_stat(stats, invalid_key)
        if invalid_key != "partial_field_count":
            _increment_stat(stats, "partial_field_count")
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
        _increment_stat(stats, invalid_key)
        if invalid_key != "partial_field_count":
            _increment_stat(stats, "partial_field_count")
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


def _required_usage_int(
    values: dict[str, Any],
    key: str,
    *,
    stats: MutableMapping[str, int] | None = None,
    missing_key: str = "partial_field_count",
) -> int:
    if key not in values or values.get(key) is None:
        _increment_stat(stats, missing_key)
        if missing_key != "partial_field_count":
            _increment_stat(stats, "partial_field_count")
        raise ValueError(f"missing required integer field: {key}")
    try:
        return _strict_int(values.get(key))
    except ValueError:
        _increment_stat(stats, "invalid_integer")
        _increment_stat(stats, "partial_field_count")
        raise


def _increment_stat(stats: MutableMapping[str, int] | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1
