"""Pure conversion from structural parser events to schema-v1 fact rows."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
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
    thread_labels: dict[str, str] | None = None,
) -> NormalizedBatch:
    """Create deterministic rows without reading or writing SQLite."""

    threads: dict[str, Row] = {}
    turns: dict[str, Row] = {}
    calls: list[Row] = []
    tools: dict[str, Row] = {}
    activities: list[Row] = []
    allowances: list[Row] = []
    thread_ids: dict[
        tuple[str | None, str | None, str | None, str | None],
        str,
    ] = {}
    turn_ids: dict[tuple[str, str | None, int], str] = {}
    latest: str | None = None
    for event in parsed.events:
        thread_identity = (
            event.session_id,
            event.parent_session_id,
            event.agent_role,
            event.agent_nickname,
        )
        thread_id = thread_ids.get(thread_identity)
        if thread_id is None:
            thread_id = _thread_id(event, plan)
            thread_ids[thread_identity] = thread_id
        turn_identity = (thread_id, event.turn_id, event.turn_ordinal)
        turn_id = turn_ids.get(turn_identity)
        if turn_id is None:
            turn_id = _turn_id(event, thread_id)
            turn_ids[turn_identity] = turn_id
        if thread_id not in threads:
            threads[thread_id] = _thread_row(
                event,
                plan,
                thread_id,
                generation,
                thread_labels or {},
            )
        if turn_id not in turns:
            turns[turn_id] = _turn_row(
                event,
                thread_id,
                turn_id,
                generation,
            )
        latest = max(latest or event.timestamp, event.timestamp)
        if event.kind == "model_call":
            calls.append(_call_row(event, plan, thread_id, turn_id, generation))
        elif event.kind == "tool":
            tool = _tool_row(event, plan, thread_id, turn_id, generation)
            identifier = str(tool["tool_call_id"])
            tools[identifier] = _merge_tool_rows(tools.get(identifier), tool)
        elif event.kind == "activity":
            activities.append(_activity_row(event, plan, thread_id, turn_id, generation))
        elif event.kind == "allowance":
            allowances.append(_allowance_row(event, plan, thread_id, generation))
        _update_turn_span(turns[turn_id], event)
    _link_nearest_calls(tuple(tools.values()), calls)
    _apply_turn_counts(turns, calls, list(tools.values()), activities)
    return NormalizedBatch(
        threads=tuple(threads.values()),
        turns=tuple(turns.values()),
        model_calls=tuple(calls),
        tool_calls=tuple(tools.values()),
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
    thread_labels: dict[str, str],
) -> Row:
    label = thread_labels.get(event.session_id or "") or event.agent_nickname
    logical_thread_id = _logical_thread_id(event)
    parent = stable_id("thr", event.parent_session_id) if event.parent_session_id else None
    return {
        "thread_id": thread_id,
        "source_id": plan.observation.source_id,
        "logical_thread_id": logical_thread_id,
        "session_identity_hash": stable_id(
            "sess",
            event.session_id or "unknown-session",
        ),
        "display_label": label or f"Thread {logical_thread_id[-8:]}",
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
        "source_turn_id_hash": (stable_id("uturn", event.turn_id) if event.turn_id else None),
        "thread_id": thread_id,
        "ordinal": event.turn_ordinal,
        "started_at": event.turn_started_at or event.timestamp,
        "ended_at": None,
        "status": "open",
        "start_basis": "turn_context" if event.turn_id else "event_order",
        "completion_basis": None,
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
    tool_call_id = (
        stable_id(
            "tool",
            "upstream",
            event.tool_call_id,
        )
        if event.tool_call_id
        else stable_id(
            "tool",
            "structural",
            event.turn_id or "",
            event.timestamp,
            name,
            event.source_offset,
        )
    )
    ended_at = event.timestamp if event.tool_phase == "end" else None
    return {
        "tool_call_id": tool_call_id,
        "upstream_call_id_hash": (
            stable_id("upcall", event.tool_call_id) if event.tool_call_id else None
        ),
        "source_id": plan.observation.source_id,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "nearest_model_call_id": None,
        "tool_name": name,
        "server_name": event.server_name,
        "namespace": name.split("__", 1)[0] if "__" in name else None,
        "tool_category": "mcp" if event.server_name else "function",
        "operation": event.tool_operation or "unknown",
        "target_label": event.tool_target_label,
        "started_at": None if event.tool_phase == "end" else event.timestamp,
        "ended_at": ended_at,
        "duration_ms": None,
        "status": event.tool_status or "incomplete",
        "error_category": None,
        "output_bytes": event.tool_output_bytes,
        "argument_shape": event.tool_argument_shape,
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


def _update_turn_span(row: Row, event: StructuralEvent) -> None:
    if event.timestamp:
        row["ended_at"] = max(str(row["ended_at"] or ""), event.timestamp)
    if event.kind != "activity":
        return
    if event.activity_kind == "task":
        row["status"] = "completed"
        row["completion_basis"] = "observed_event"
        row["basis_confidence"] = "exact"
    elif event.activity_kind == "turn_aborted":
        row["status"] = "aborted"
        row["completion_basis"] = "observed_event"
        row["basis_confidence"] = "exact"
    elif event.activity_kind == "rollback":
        row["status"] = "rolled_back"
        row["completion_basis"] = "observed_event"
        row["basis_confidence"] = "exact"


def _merge_tool_rows(current: Row | None, observed: Row) -> Row:
    if current is None:
        return observed
    merged = dict(current)
    if current["tool_name"] == "unknown" and observed["tool_name"] != "unknown":
        for field in (
            "tool_name",
            "server_name",
            "namespace",
            "tool_category",
            "operation",
            "target_label",
            "argument_shape",
        ):
            merged[field] = observed[field]
    for field in ("started_at", "ended_at", "output_bytes"):
        if observed[field] is not None:
            merged[field] = observed[field]
    merged["status"] = observed["status"]
    merged["first_source_offset"] = min(
        int(current["first_source_offset"]),
        int(observed["first_source_offset"]),
    )
    merged["last_source_offset"] = max(
        int(current["last_source_offset"]),
        int(observed["last_source_offset"]),
    )
    merged["duration_ms"] = _duration_ms(
        merged["started_at"],
        merged["ended_at"],
    )
    return merged


def _link_nearest_calls(tools: tuple[Row, ...], calls: list[Row]) -> None:
    calls_by_turn: dict[str, list[Row]] = {}
    for call in calls:
        calls_by_turn.setdefault(str(call["turn_id"]), []).append(call)
    for candidates in calls_by_turn.values():
        candidates.sort(key=lambda item: (str(item["event_at"]), str(item["model_call_id"])))
    for tool in tools:
        candidates = calls_by_turn.get(str(tool["turn_id"]), [])
        boundary = str(tool["ended_at"] or tool["started_at"] or "")
        following = next(
            (call for call in candidates if str(call["event_at"]) >= boundary),
            None,
        )
        nearest = following or (candidates[-1] if candidates else None)
        if nearest is not None:
            tool["nearest_model_call_id"] = nearest["model_call_id"]


def _duration_ms(started_at: Any, ended_at: Any) -> float | None:
    if not isinstance(started_at, str) or not isinstance(ended_at, str):
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds() * 1000.0)


def _state_json(state: ParserState) -> str:
    return json.dumps(asdict(state), sort_keys=True, separators=(",", ":"))
