"""Pure conversion from structural parser events to schema-v1 fact rows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .discovery import SourcePlan
from .identity import canonical_fingerprint, stable_id
from .parser import ParsedBatch, ParserState, StructuralEvent

Row = dict[str, Any]


@dataclass(frozen=True)
class NormalizedBatch:
    threads: tuple[Row, ...]
    turns: tuple[Row, ...]
    model_calls: tuple[Row, ...]
    tool_calls: tuple[Row, ...]
    activities: tuple[Row, ...]
    allowances: tuple[Row, ...]
    parser_state_json: str
    latest_event_at: str | None


def normalize_batch(
    plan: SourcePlan,
    parsed: ParsedBatch,
    *,
    generation: int,
) -> NormalizedBatch:
    """Create deterministic rows without reading or writing SQLite."""

    threads: dict[str, Row] = {}
    turns: dict[str, Row] = {}
    calls: list[Row] = []
    tools: list[Row] = []
    activities: list[Row] = []
    allowances: list[Row] = []
    latest: str | None = None
    for event in parsed.events:
        thread_id = _thread_id(event, plan)
        turn_id = _turn_id(event, thread_id)
        threads.setdefault(
            thread_id,
            _thread_row(event, plan, thread_id, generation),
        )
        turns.setdefault(
            turn_id,
            _turn_row(event, thread_id, turn_id, generation),
        )
        latest = max(latest or event.timestamp, event.timestamp)
        if event.kind == "model_call":
            calls.append(_call_row(event, plan, thread_id, turn_id, generation))
        elif event.kind == "tool":
            tools.append(_tool_row(event, plan, thread_id, turn_id, generation))
        elif event.kind == "activity":
            activities.append(
                _activity_row(event, plan, thread_id, turn_id, generation)
            )
        elif event.kind == "allowance":
            allowances.append(
                _allowance_row(event, plan, thread_id, generation)
            )
    _apply_turn_counts(turns, calls, tools, activities)
    return NormalizedBatch(
        threads=tuple(threads.values()),
        turns=tuple(turns.values()),
        model_calls=tuple(calls),
        tool_calls=tuple(tools),
        activities=tuple(activities),
        allowances=tuple(allowances),
        parser_state_json=_state_json(parsed.final_state),
        latest_event_at=latest,
    )


def parser_state_from_json(payload: str | None) -> ParserState:
    """Restore only the bounded structural parser state."""

    if not payload:
        return ParserState()
    values = json.loads(payload)
    allowed = {field: values.get(field) for field in asdict(ParserState())}
    return ParserState(**allowed)


def _logical_thread_id(event: StructuralEvent) -> str:
    basis = event.session_id or "unknown-session"
    return stable_id("thr", basis)


def _thread_id(event: StructuralEvent, plan: SourcePlan) -> str:
    return stable_id(
        "srcthr",
        plan.observation.source_id,
        _logical_thread_id(event),
    )


def _turn_id(event: StructuralEvent, thread_id: str) -> str:
    basis = event.turn_id or f"ordinal:{event.turn_ordinal}"
    return stable_id("turn", thread_id, basis)


def _thread_row(
    event: StructuralEvent,
    plan: SourcePlan,
    thread_id: str,
    generation: int,
) -> Row:
    label = event.agent_nickname
    parent = (
        stable_id("thr", event.parent_session_id)
        if event.parent_session_id
        else None
    )
    return {
        "thread_id": thread_id,
        "source_id": plan.observation.source_id,
        "logical_thread_id": _logical_thread_id(event),
        "session_identity_hash": stable_id(
            "sess",
            event.session_id or "unknown-session",
        ),
        "display_label": label or f"Thread {thread_id[-8:]}",
        "created_at": event.timestamp,
        "updated_at": event.timestamp,
        "archive_state": "archived" if plan.observation.is_archived else "active",
        "parent_logical_thread_id": parent,
        "subagent_role": event.agent_role,
        "subagent_nickname": event.agent_nickname,
        "first_generation": generation,
        "last_generation": generation,
        "identity_basis": "session_parent" if event.parent_session_id else "session",
        "identity_confidence": "exact" if event.session_id else "unknown",
    }


def _turn_row(
    event: StructuralEvent,
    thread_id: str,
    turn_id: str,
    generation: int,
) -> Row:
    return {
        "turn_id": turn_id,
        "source_turn_id_hash": (
            stable_id("uturn", event.turn_id) if event.turn_id else None
        ),
        "thread_id": thread_id,
        "ordinal": event.turn_ordinal,
        "started_at": event.timestamp,
        "ended_at": event.timestamp,
        "status": "completed",
        "start_basis": "turn_context" if event.turn_id else "event_order",
        "completion_basis": "observed_event",
        "basis_confidence": "exact" if event.turn_id else "inferred",
        "first_source_offset": event.source_offset,
        "last_source_offset": event.source_offset,
        "model_call_count": 0,
        "tool_call_count": 0,
        "skill_count": 0,
        "compaction_count": 0,
        "patch_count": 0,
        "error_count": 0,
        "first_generation": generation,
        "last_generation": generation,
    }


def _call_row(
    event: StructuralEvent,
    plan: SourcePlan,
    thread_id: str,
    turn_id: str,
    generation: int,
) -> Row:
    canonical = canonical_fingerprint(
        {
            "timestamp": event.timestamp,
            "upstream_id": event.upstream_id,
            "model": event.model,
            "effort": event.effort,
            "service_tier": event.service_tier,
            "input": event.input_tokens,
            "cached": event.cached_input_tokens,
            "output": event.output_tokens,
            "reasoning": event.reasoning_tokens,
        }
    )
    return {
        "model_call_id": stable_id(
            "call",
            plan.observation.source_id,
            event.source_offset,
        ),
        "canonical_call_id": canonical,
        "source_id": plan.observation.source_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "event_at": event.timestamp,
        "turn_ordinal": event.turn_ordinal,
        "model": event.model,
        "effort": event.effort,
        "service_tier": event.service_tier,
        "origin": "subagent" if event.parent_session_id else "local",
        "context_window": event.context_window,
        "input_tokens": event.input_tokens,
        "cached_input_tokens": event.cached_input_tokens,
        "output_tokens": event.output_tokens,
        "reasoning_tokens": event.reasoning_tokens,
        "upstream_total_tokens": event.upstream_total_tokens,
        "duplicate_state": "unknown",
        "fingerprint_version": 1,
        "source_offset": event.source_offset,
        "generation": generation,
    }


def _tool_row(
    event: StructuralEvent,
    plan: SourcePlan,
    thread_id: str,
    turn_id: str,
    generation: int,
) -> Row:
    name = event.tool_name or "unknown"
    return {
        "tool_call_id": stable_id(
            "tool",
            plan.observation.source_id,
            event.source_offset,
            name,
        ),
        "source_id": plan.observation.source_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "tool_name": name,
        "server_name": event.server_name,
        "namespace": name.split("__", 1)[0] if "__" in name else None,
        "tool_category": "mcp" if event.server_name else "function",
        "started_at": event.timestamp,
        "ended_at": event.timestamp,
        "status": "completed",
        "output_bytes": None,
        "argument_shape": None,
        "first_source_offset": event.source_offset,
        "last_source_offset": event.source_offset,
        "generation": generation,
        "observation_confidence": "exact",
    }


def _activity_row(
    event: StructuralEvent,
    plan: SourcePlan,
    thread_id: str,
    turn_id: str,
    generation: int,
) -> Row:
    kind = event.activity_kind or "unknown"
    return {
        "activity_event_id": stable_id(
            "act",
            plan.observation.source_id,
            event.source_offset,
            kind,
        ),
        "source_id": plan.observation.source_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "event_kind": kind,
        "event_at": event.timestamp,
        "safe_label": event.activity_label,
        "category": kind,
        "source_offset": event.source_offset,
        "generation": generation,
    }


def _allowance_row(
    event: StructuralEvent,
    plan: SourcePlan,
    thread_id: str,
    generation: int,
) -> Row:
    window = event.allowance_window or "unknown"
    return {
        "allowance_observation_id": stable_id(
            "allow",
            plan.observation.source_id,
            event.source_offset,
            window,
        ),
        "source_id": plan.observation.source_id,
        "observed_at": event.timestamp,
        "window_kind": window,
        "limit_id": event.allowance_limit_id,
        "plan_type": event.allowance_plan_type,
        "used_percent": event.allowance_used_percent or 0.0,
        "duration_minutes": event.allowance_duration_minutes,
        "resets_at": event.allowance_resets_at,
        "model": event.model,
        "service_tier": event.service_tier,
        "source_model_call_id": stable_id(
            "call",
            plan.observation.source_id,
            event.source_offset,
        ),
        "generation": generation,
        "duplicate_state": "unknown",
        "provenance": "local_token_event",
        "validation_warnings": "[]",
    }


def _apply_turn_counts(
    turns: dict[str, Row],
    calls: list[Row],
    tools: list[Row],
    activities: list[Row],
) -> None:
    for call in calls:
        turns[str(call["turn_id"])]["model_call_count"] += 1
    for tool in tools:
        turns[str(tool["turn_id"])]["tool_call_count"] += 1
    for activity in activities:
        row = turns[str(activity["turn_id"])]
        kind = activity["event_kind"]
        if kind == "skill":
            row["skill_count"] += 1
        elif kind == "compaction":
            row["compaction_count"] += 1
        elif kind == "patch":
            row["patch_count"] += 1
        elif kind in {"rollback", "turn_aborted"}:
            row["error_count"] += 1


def _state_json(state: ParserState) -> str:
    return json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))
