"""Generation-consistent logical-selector evidence reads."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

from ..database import open_read_snapshot
from ..operational import load_cutover_control
from .contracts import (
    EvidenceRequest,
    EvidenceResult,
    EvidenceSelector,
    EvidenceView,
)

EVIDENCE_PLAN_VERSION = 1


@dataclass(frozen=True)
class _Resolution:
    thread_id: str | None = None
    turn_id: str | None = None
    model_call_id: str | None = None
    tool_call_id: str | None = None
    allowance_id: str | None = None


@dataclass(frozen=True)
class _EvidencePlan:
    sql: str
    count_sql: str
    parameters: tuple[Any, ...]


class EvidenceService:
    """Resolve stable logical selectors into bounded privacy-safe rows."""

    def __init__(self, operational_path: Path) -> None:
        self._operational_path = operational_path.resolve()

    def read(self, request: EvidenceRequest) -> EvidenceResult:
        normalized = request.normalized()
        selector = _selector(normalized)
        view = EvidenceView(normalized.view)
        control = load_cutover_control(self._operational_path)
        path = control.active_kernel_path
        generation = control.active_generation
        if path is None or generation is None:
            raise ValueError("no active analytical generation")
        request_hash = _request_hash(
            selector,
            view,
            normalized.live,
            normalized.limit,
        )
        offset = _decode_cursor(
            normalized.cursor,
            generation=generation,
            request_hash=request_hash,
            limit=normalized.limit,
        )
        with open_read_snapshot(path) as connection:
            connection.execute("PRAGMA query_only = ON")
            resolution = _resolve(connection, selector, generation)
            plan = _compile_plan(
                selector,
                resolution,
                view,
                generation,
                normalized.limit,
                offset,
            )
            raw_rows = connection.execute(plan.sql, plan.parameters).fetchall()
            matched = int(
                connection.execute(
                    plan.count_sql,
                    plan.parameters[:-2],
                ).fetchone()[0]
            )
        rows = [dict(row) for row in raw_rows]
        truncated = len(rows) > normalized.limit
        returned = rows[: normalized.limit]
        next_cursor = (
            _encode_cursor(
                generation=generation,
                request_hash=request_hash,
                offset=offset + normalized.limit,
            )
            if truncated
            else None
        )
        return EvidenceResult(
            generation=generation,
            selector=selector.value,
            view=view.value,
            rows=tuple(returned),
            matched_count=matched,
            returned_count=len(returned),
            truncated=truncated,
            next_cursor=next_cursor,
            destination=_destination(selector, view, normalized.live),
            live=normalized.live,
            grade="exact",
            coverage={
                "basis": "foundational_facts",
                "generation_bound": True,
                "logical_selector": True,
                "content_included": False,
            },
        )


def _resolve(
    connection: sqlite3.Connection,
    selector: EvidenceSelector,
    generation: int,
) -> _Resolution:
    statements = {
        "thread": (
            """
            SELECT thread_id, NULL, NULL, NULL, NULL
            FROM threads
            WHERE logical_thread_id = ? AND first_generation <= ?
            ORDER BY first_generation
            LIMIT 1
            """,
            (selector.logical_id, generation),
        ),
        "turn": (
            """
            SELECT thread_id, turn_id, NULL, NULL, NULL
            FROM turns
            WHERE COALESCE(source_turn_id_hash, turn_id) = ?
              AND first_generation <= ?
            ORDER BY first_generation
            LIMIT 1
            """,
            (selector.logical_id, generation),
        ),
        "call": (
            """
            SELECT thread_id, turn_id, model_call_id, NULL, NULL
            FROM model_calls
            WHERE canonical_call_id = ? AND generation <= ?
            ORDER BY duplicate_state = 'canonical' DESC, generation DESC
            LIMIT 1
            """,
            (selector.logical_id, generation),
        ),
        "tool": (
            """
            SELECT thread_id, turn_id, nearest_model_call_id, tool_call_id, NULL
            FROM tool_calls
            WHERE tool_call_id = ? AND generation <= ?
            LIMIT 1
            """,
            (selector.logical_id, generation),
        ),
        "allowance": (
            """
            SELECT model_calls.thread_id, model_calls.turn_id,
                   allowance_observations.source_model_call_id,
                   NULL, allowance_observations.allowance_observation_id
            FROM allowance_observations
            LEFT JOIN model_calls
              ON model_calls.model_call_id =
                 allowance_observations.source_model_call_id
            WHERE allowance_observations.allowance_observation_id = ?
              AND allowance_observations.generation <= ?
            LIMIT 1
            """,
            (selector.logical_id, generation),
        ),
    }
    sql, parameters = statements[selector.kind]
    row = connection.execute(sql, parameters).fetchone()
    if row is None:
        raise ValueError("evidence selector was not found")
    return _Resolution(*row)


def _compile_plan(
    selector: EvidenceSelector,
    resolution: _Resolution,
    view: EvidenceView,
    generation: int,
    limit: int,
    offset: int,
) -> _EvidencePlan:
    if view is EvidenceView.SUMMARY:
        sql, parameters = _summary_plan(selector, generation)
    elif view is EvidenceView.CALLS:
        sql, parameters = _calls_plan(resolution, generation)
    elif view is EvidenceView.TOOLS:
        sql, parameters = _tools_plan(resolution, generation)
    elif view is EvidenceView.ACTIVITIES:
        sql, parameters = _activities_plan(selector, resolution, generation)
    elif view is EvidenceView.ALLOWANCE:
        sql, parameters = _allowance_plan(resolution, generation)
    else:
        sql, parameters = _timeline_plan(selector, resolution, generation)
    paged = (
        f"SELECT * FROM ({sql}) AS evidence_rows "
        f"ORDER BY {_order_by(view)} LIMIT ? OFFSET ?"
    )
    count = f"SELECT COUNT(*) FROM ({sql}) AS evidence_rows"
    return _EvidencePlan(
        sql=paged,
        count_sql=count,
        parameters=(*parameters, limit + 1, offset),
    )


def _summary_plan(
    selector: EvidenceSelector,
    generation: int,
) -> tuple[str, tuple[Any, ...]]:
    plans = {
        "thread": (
            """
            SELECT logical_thread_id AS thread, display_label, project_label,
                   created_at, updated_at, archive_state,
                   parent_logical_thread_id, subagent_type, subagent_role
            FROM threads
            WHERE logical_thread_id = ? AND first_generation <= ?
            ORDER BY first_generation
            """,
            (selector.logical_id, generation),
        ),
        "turn": (
            """
            SELECT COALESCE(turns.source_turn_id_hash, turns.turn_id) AS turn,
                   threads.logical_thread_id AS thread, turns.ordinal,
                   turns.started_at, turns.ended_at, turns.status,
                   turns.model_call_count, turns.tool_call_count,
                   turns.skill_count, turns.compaction_count,
                   turns.patch_count, turns.error_count
            FROM turns JOIN threads USING (thread_id)
            WHERE COALESCE(turns.source_turn_id_hash, turns.turn_id) = ?
              AND turns.first_generation <= ?
            """,
            (selector.logical_id, generation),
        ),
        "call": (
            _CALLS_SQL + " AND model_calls.canonical_call_id = ?",
            (generation, selector.logical_id),
        ),
        "tool": (
            _TOOLS_SQL + " AND tool_calls.tool_call_id = ?",
            (generation, selector.logical_id),
        ),
        "allowance": (
            _ALLOWANCE_SQL
            + " AND allowance_observations.allowance_observation_id = ?",
            (generation, selector.logical_id),
        ),
    }
    return plans[selector.kind]


def _calls_plan(
    resolution: _Resolution,
    generation: int,
) -> tuple[str, tuple[Any, ...]]:
    clause, value = _scope_clause(
        resolution,
        thread="model_calls.thread_id",
        turn="model_calls.turn_id",
        call="model_calls.model_call_id",
    )
    return _CALLS_SQL + " AND " + clause, (generation, value)


def _tools_plan(
    resolution: _Resolution,
    generation: int,
) -> tuple[str, tuple[Any, ...]]:
    clause, value = _scope_clause(
        resolution,
        thread="tool_calls.thread_id",
        turn="tool_calls.turn_id",
        call="tool_calls.nearest_model_call_id",
        tool="tool_calls.tool_call_id",
    )
    return _TOOLS_SQL + " AND " + clause, (generation, value)


def _activities_plan(
    selector: EvidenceSelector,
    resolution: _Resolution,
    generation: int,
) -> tuple[str, tuple[Any, ...]]:
    if selector.kind not in {"thread", "turn"}:
        raise ValueError("activities view requires a thread or turn selector")
    if resolution.turn_id is not None:
        clause, value = "activity_events.turn_id = ?", resolution.turn_id
    elif resolution.thread_id is not None:
        clause, value = "activity_events.thread_id = ?", resolution.thread_id
    else:
        raise ValueError("selector has no activity evidence")
    return _ACTIVITIES_SQL + " AND " + clause, (generation, value)


def _allowance_plan(
    resolution: _Resolution,
    generation: int,
) -> tuple[str, tuple[Any, ...]]:
    if resolution.allowance_id is None:
        raise ValueError("allowance view requires an allowance selector")
    return (
        _ALLOWANCE_SQL + " AND allowance_observations.allowance_observation_id = ?",
        (generation, resolution.allowance_id),
    )


def _timeline_plan(
    selector: EvidenceSelector,
    resolution: _Resolution,
    generation: int,
) -> tuple[str, tuple[Any, ...]]:
    if resolution.allowance_id is not None:
        return _allowance_plan(resolution, generation)
    call_clause, call_value = _scope_clause(
        resolution,
        thread="model_calls.thread_id",
        turn="model_calls.turn_id",
        call="model_calls.model_call_id",
    )
    tool_clause, tool_value = _scope_clause(
        resolution,
        thread="tool_calls.thread_id",
        turn="tool_calls.turn_id",
        call="tool_calls.nearest_model_call_id",
        tool="tool_calls.tool_call_id",
    )
    include_activities = selector.kind in {"thread", "turn"}
    if include_activities:
        activity_clause, activity_value = _activity_scope(resolution)
        activity_sql = f"""
            UNION ALL
            SELECT 'activity:' || activity_events.activity_event_id,
                   activity_events.event_at, activity_events.event_kind,
                   NULL, activity_events.safe_label, activity_events.category,
                   NULL, NULL, NULL, NULL, NULL,
                   activity_events.generation
            FROM activity_events
            WHERE activity_events.generation <= ? AND {activity_clause}
        """
        activity_parameters: tuple[Any, ...] = (generation, activity_value)
    else:
        activity_sql = ""
        activity_parameters = ()
    sql = f"""
        SELECT 'call:' || model_calls.canonical_call_id AS event_id,
               model_calls.event_at, 'model_call' AS event_kind,
               'call:' || model_calls.canonical_call_id AS selector,
               model_calls.model AS safe_label, 'model_call' AS category,
               model_calls.input_tokens - model_calls.cached_input_tokens
                   AS uncached_input_tokens,
               model_calls.cached_input_tokens, model_calls.reasoning_tokens,
               model_calls.output_tokens, NULL AS status,
               model_calls.generation
        FROM model_calls
        WHERE model_calls.generation <= ?
          AND model_calls.duplicate_state = 'canonical'
          AND {call_clause}
        UNION ALL
        SELECT 'tool:' || tool_calls.tool_call_id,
               COALESCE(tool_calls.started_at, tool_calls.ended_at),
               'tool_call', 'tool:' || tool_calls.tool_call_id,
               tool_calls.tool_name, tool_calls.tool_category,
               NULL, NULL, NULL, NULL, tool_calls.status,
               tool_calls.generation
        FROM tool_calls
        WHERE tool_calls.generation <= ? AND {tool_clause}
        {activity_sql}
    """
    return (
        sql,
        (
            generation,
            call_value,
            generation,
            tool_value,
            *activity_parameters,
        ),
    )


def _order_by(view: EvidenceView) -> str:
    return {
        EvidenceView.SUMMARY: "1",
        EvidenceView.CALLS: "event_at, call",
        EvidenceView.TOOLS: "COALESCE(started_at, ended_at), tool",
        EvidenceView.ACTIVITIES: "event_at, activity",
        EvidenceView.ALLOWANCE: "observed_at, allowance",
        EvidenceView.TIMELINE: "event_at, event_id",
    }[view]


def _scope_clause(
    resolution: _Resolution,
    *,
    thread: str,
    turn: str,
    call: str,
    tool: str | None = None,
) -> tuple[str, str]:
    if tool is not None and resolution.tool_call_id is not None:
        return f"{tool} = ?", resolution.tool_call_id
    if resolution.model_call_id is not None:
        return f"{call} = ?", resolution.model_call_id
    if resolution.turn_id is not None:
        return f"{turn} = ?", resolution.turn_id
    if resolution.thread_id is not None:
        return f"{thread} = ?", resolution.thread_id
    raise ValueError("selector has no evidence scope")


def _activity_scope(resolution: _Resolution) -> tuple[str, str]:
    if resolution.turn_id is not None:
        return "activity_events.turn_id = ?", resolution.turn_id
    if resolution.thread_id is not None:
        return "activity_events.thread_id = ?", resolution.thread_id
    raise ValueError("selector has no activity evidence")


_CALLS_SQL = """
SELECT model_calls.canonical_call_id AS call,
       threads.logical_thread_id AS thread,
       COALESCE(turns.source_turn_id_hash, turns.turn_id) AS turn,
       model_calls.event_at, model_calls.model, model_calls.effort,
       model_calls.service_tier, model_calls.origin,
       model_calls.input_tokens - model_calls.cached_input_tokens
           AS uncached_input_tokens,
       model_calls.cached_input_tokens, model_calls.reasoning_tokens,
       model_calls.output_tokens,
       model_calls.input_tokens + model_calls.output_tokens AS total_tokens,
       model_calls.generation
FROM model_calls
JOIN threads USING (thread_id)
LEFT JOIN turns ON turns.turn_id = model_calls.turn_id
WHERE model_calls.generation <= ?
  AND model_calls.duplicate_state = 'canonical'
"""

_TOOLS_SQL = """
SELECT tool_calls.tool_call_id AS tool,
       threads.logical_thread_id AS thread,
       COALESCE(turns.source_turn_id_hash, turns.turn_id) AS turn,
       tool_calls.tool_name, tool_calls.server_name, tool_calls.namespace,
       tool_calls.tool_category, tool_calls.started_at, tool_calls.ended_at,
       tool_calls.duration_ms, tool_calls.status, tool_calls.error_category,
       tool_calls.output_bytes, tool_calls.observation_confidence,
       tool_calls.generation
FROM tool_calls
JOIN threads USING (thread_id)
LEFT JOIN turns ON turns.turn_id = tool_calls.turn_id
WHERE tool_calls.generation <= ?
"""

_ACTIVITIES_SQL = """
SELECT activity_events.activity_event_id AS activity,
       threads.logical_thread_id AS thread,
       COALESCE(turns.source_turn_id_hash, turns.turn_id) AS turn,
       activity_events.event_kind, activity_events.event_at,
       activity_events.safe_label, activity_events.category,
       activity_events.generation
FROM activity_events
JOIN threads USING (thread_id)
LEFT JOIN turns ON turns.turn_id = activity_events.turn_id
WHERE activity_events.generation <= ?
"""

_ALLOWANCE_SQL = """
SELECT allowance_observations.allowance_observation_id AS allowance,
       allowance_observations.observed_at,
       allowance_observations.window_kind,
       allowance_observations.limit_id,
       allowance_observations.plan_type,
       allowance_observations.used_percent,
       allowance_observations.duration_minutes,
       allowance_observations.resets_at,
       allowance_observations.model,
       allowance_observations.service_tier,
       allowance_observations.provenance,
       allowance_observations.validation_warnings,
       allowance_observations.generation
FROM allowance_observations
WHERE allowance_observations.generation <= ?
"""


def _selector(request: EvidenceRequest) -> EvidenceSelector:
    if not isinstance(request.selector, EvidenceSelector):
        raise TypeError("normalized evidence selector is invalid")
    return request.selector


def _destination(
    selector: EvidenceSelector,
    view: EvidenceView,
    live: bool,
) -> str:
    query = urlencode(
        {"selector": selector.value, "view": view.value, "live": int(live)}
    )
    return f"/evidence/{quote(selector.value, safe='')}?{query}"


def _request_hash(
    selector: EvidenceSelector,
    view: EvidenceView,
    live: bool,
    limit: int,
) -> str:
    payload = json.dumps(
        {
            "selector": selector.value,
            "view": view.value,
            "live": live,
            "limit": limit,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _encode_cursor(*, generation: int, request_hash: str, offset: int) -> str:
    payload = json.dumps(
        {"g": generation, "h": request_hash, "o": offset},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(
    cursor: str | None,
    *,
    generation: int,
    request_hash: str,
    limit: int,
) -> int:
    if cursor is None:
        return 0
    try:
        payload = json.loads(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        )
        offset = payload["o"]
        if (
            payload["g"] != generation
            or payload["h"] != request_hash
            or not isinstance(offset, int)
            or offset < limit
            or offset > 1_000_000
            or offset % limit
        ):
            raise ValueError
        return offset
    except (
        binascii.Error,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "evidence cursor does not match selector generation"
        ) from exc
