"""Static query allowlists and SQL expression catalog."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from ..allowance.service import ALLOWANCE_BASE_SQL
from .contracts import (
    MAX_BATCH_QUERIES,
    MAX_DIMENSIONS,
    MAX_FILTERS,
    MAX_LIMIT,
    MAX_MEASURES,
    MAX_QUERY_RESPONSE_BYTES,
    Operation,
    QueryRequest,
)


@dataclass(frozen=True)
class DatasetSpec:
    base_sql: str
    generation_sql: str
    time_sql: str | None
    stable_id_sql: str
    dimensions: dict[str, str]
    row_measures: dict[str, str]
    aggregate_measures: dict[str, str]
    filter_fields: dict[str, str]
    operations: frozenset[Operation]
    coverage_fields: dict[str, str] = field(default_factory=dict)
    base_generation_parameters: int = 0


_COMMON_OPERATIONS = frozenset(
    {
        Operation.ROWS,
        Operation.AGGREGATE,
        Operation.DISTRIBUTION,
        Operation.TIMELINE,
    }
)
_CALL_OPERATIONS = _COMMON_OPERATIONS | {
    Operation.SHARE,
    Operation.COMPARISON,
    Operation.TIME_SERIES,
}
_CONTEXT_OPERATIONS = frozenset(
    {
        Operation.AGGREGATE,
        Operation.DISTRIBUTION,
        Operation.SHARE,
    }
)
_THREAD_LABEL_SQL = """
(
    SELECT resolved_thread_label(
        candidate_threads.session_identity_hash,
        candidate_threads.display_label
    )
    FROM threads AS candidate_threads
    WHERE candidate_threads.logical_thread_id = threads.logical_thread_id
    ORDER BY candidate_threads.archive_state = 'active' DESC,
             candidate_threads.last_generation DESC,
             candidate_threads.thread_key
    LIMIT 1
)
"""
_CANONICAL_THREAD_SQL = """
(
    threads.thread_key = (
        SELECT candidate_threads.thread_key
        FROM threads AS candidate_threads
        WHERE candidate_threads.logical_thread_id = threads.logical_thread_id
          AND candidate_threads.first_generation <= ?
        ORDER BY candidate_threads.archive_state = 'active' DESC,
                 candidate_threads.last_generation DESC,
                 candidate_threads.thread_key
        LIMIT 1
    )
)
"""
_CANONICAL_TOOL_SQL = f"""
(
    (
        nearest_call.model_call_id IS NOT NULL
        AND nearest_call.duplicate_state = 'canonical'
    )
    OR (
        nearest_call.model_call_id IS NULL
        AND {_CANONICAL_THREAD_SQL}
    )
)
"""
_CANONICAL_TURN_SQL = """
(
    turns.turn_key = (
        SELECT candidate_turns.turn_key
        FROM turns AS candidate_turns
        JOIN threads AS candidate_threads
          ON candidate_threads.thread_key = candidate_turns.thread_key
        WHERE COALESCE(
                  candidate_turns.source_turn_id_hash,
                  candidate_turns.turn_id
              ) = COALESCE(turns.source_turn_id_hash, turns.turn_id)
          AND candidate_turns.first_generation <= ?
        ORDER BY candidate_threads.archive_state = 'active' DESC,
                 candidate_turns.last_generation DESC,
                 candidate_turns.turn_key
        LIMIT 1
    )
)
"""
_TURN_BASE_SQL = """
(
    SELECT stored_turns.*,
           COALESCE(completion.status, stored_turns.status)
               AS effective_status,
           COALESCE(
               completion.completion_basis,
               stored_turns.completion_basis
           ) AS effective_completion_basis,
           COALESCE(completion.ended_at, stored_turns.ended_at)
               AS effective_ended_at
    FROM turns AS stored_turns
    LEFT JOIN (
        SELECT ranked.turn_id,
               ranked.event_at AS ended_at,
               'observed_event' AS completion_basis,
               CASE ranked.event_kind
                   WHEN 'task' THEN 'completed'
                   WHEN 'turn_aborted' THEN 'aborted'
                   ELSE 'rolled_back'
               END AS status
        FROM (
            SELECT activity_events.turn_id,
                   activity_events.event_at,
                   activity_events.event_kind,
                   ROW_NUMBER() OVER (
                       PARTITION BY activity_events.turn_id
                       ORDER BY activity_events.event_at DESC,
                                activity_events.activity_event_id DESC
                   ) AS rank
            FROM activity_events
            WHERE activity_events.generation <= ?
              AND activity_events.event_kind IN (
                  'task',
                  'turn_aborted',
                  'rollback'
              )
        ) AS ranked
        WHERE ranked.rank = 1
    ) AS completion ON completion.turn_id = stored_turns.turn_id
) AS turns
JOIN threads ON threads.thread_id = turns.thread_id
"""

_CALL_DIMENSIONS = {
    "call": "model_calls.canonical_call_id",
    "generation": "model_calls.generation",
    "thread": "threads.logical_thread_id",
    "thread_label": _THREAD_LABEL_SQL,
    "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
    "project": "threads.project_label",
    "model": "model_calls.model",
    "effort": "model_calls.effort",
    "service_tier": "model_calls.service_tier",
    "origin": "model_calls.origin",
    "agent_role": "threads.subagent_role",
    "event_at": "model_calls.event_at",
    "time_day": "substr(model_calls.event_at, 1, 10)",
    "time_hour": "substr(model_calls.event_at, 1, 13) || ':00:00Z'",
}
_CALL_ROWS = {
    "calls": "1",
    "input_tokens": "model_calls.input_tokens",
    "uncached_input_tokens": ("model_calls.input_tokens - model_calls.cached_input_tokens"),
    "cached_input_tokens": "model_calls.cached_input_tokens",
    "reasoning_tokens": "model_calls.reasoning_tokens",
    "output_tokens": "model_calls.output_tokens",
    "total_tokens": "model_calls.input_tokens + model_calls.output_tokens",
    "configured_cost_usd": (
        "configured_cost_usd("
        "model_calls.model, model_calls.input_tokens, "
        "model_calls.cached_input_tokens, model_calls.output_tokens)"
    ),
    "estimated_credits": (
        "estimated_credits("
        "model_calls.model, model_calls.input_tokens, "
        "model_calls.cached_input_tokens, model_calls.output_tokens)"
    ),
    "cache_reuse": (
        "CASE WHEN model_calls.input_tokens = 0 THEN 0.0 "
        "ELSE 1.0 * model_calls.cached_input_tokens / model_calls.input_tokens END"
    ),
    "context_pressure": (
        "CASE WHEN model_calls.context_window IS NULL THEN NULL "
        "ELSE 1.0 * model_calls.input_tokens / model_calls.context_window END"
    ),
}
_CALL_AGGREGATES = {
    "calls": "COUNT(*)",
    "input_tokens": "SUM(model_calls.input_tokens)",
    "uncached_input_tokens": ("SUM(model_calls.input_tokens - model_calls.cached_input_tokens)"),
    "cached_input_tokens": "SUM(model_calls.cached_input_tokens)",
    "reasoning_tokens": "SUM(model_calls.reasoning_tokens)",
    "output_tokens": "SUM(model_calls.output_tokens)",
    "total_tokens": "SUM(model_calls.input_tokens + model_calls.output_tokens)",
    "configured_cost_usd": (
        "SUM(configured_cost_usd("
        "model_calls.model, model_calls.input_tokens, "
        "model_calls.cached_input_tokens, model_calls.output_tokens))"
    ),
    "estimated_credits": (
        "SUM(estimated_credits("
        "model_calls.model, model_calls.input_tokens, "
        "model_calls.cached_input_tokens, model_calls.output_tokens))"
    ),
    "cache_reuse": (
        "CASE WHEN SUM(model_calls.input_tokens) = 0 THEN 0.0 "
        "ELSE 1.0 * SUM(model_calls.cached_input_tokens) "
        "/ SUM(model_calls.input_tokens) END"
    ),
    "context_pressure": (
        "CASE WHEN SUM(COALESCE(model_calls.context_window, 0)) = 0 THEN NULL "
        "ELSE 1.0 * SUM(model_calls.input_tokens) "
        "/ SUM(model_calls.context_window) END"
    ),
}

DATASETS: dict[str, DatasetSpec] = {
    "calls": DatasetSpec(
        base_sql=(
            "model_calls "
            "JOIN threads ON threads.thread_id = model_calls.thread_id "
            "LEFT JOIN turns ON turns.turn_id = model_calls.turn_id"
        ),
        generation_sql=(
            "model_calls.generation <= ? AND model_calls.duplicate_state = 'canonical'"
        ),
        time_sql="model_calls.event_at",
        stable_id_sql="model_calls.canonical_call_id",
        dimensions=_CALL_DIMENSIONS,
        row_measures=_CALL_ROWS,
        aggregate_measures=_CALL_AGGREGATES,
        filter_fields={
            **_CALL_DIMENSIONS,
            "event_at": "model_calls.event_at",
        },
        operations=_CALL_OPERATIONS,
        coverage_fields={
            "context_pressure": "model_calls.context_window",
            "configured_cost_usd": (
                "configured_cost_usd("
                "model_calls.model, model_calls.input_tokens, "
                "model_calls.cached_input_tokens, model_calls.output_tokens)"
            ),
            "estimated_credits": (
                "estimated_credits("
                "model_calls.model, model_calls.input_tokens, "
                "model_calls.cached_input_tokens, model_calls.output_tokens)"
            ),
        },
    ),
    "tools": DatasetSpec(
        base_sql=(
            "tool_calls "
            "JOIN threads ON threads.thread_id = tool_calls.thread_id "
            "LEFT JOIN turns ON turns.turn_id = tool_calls.turn_id "
            "LEFT JOIN model_calls AS nearest_call "
            "ON nearest_call.model_call_id = tool_calls.nearest_model_call_id "
            "AND nearest_call.generation <= tool_calls.generation"
        ),
        generation_sql=("tool_calls.generation <= ? AND " + _CANONICAL_TOOL_SQL),
        time_sql="tool_calls.started_at",
        stable_id_sql="tool_calls.tool_call_id",
        dimensions={
            "tool": "tool_calls.tool_name",
            "operation": "tool_calls.operation",
            "target": "tool_calls.target_label",
            "server": "tool_calls.server_name",
            "namespace": "tool_calls.namespace",
            "category": "tool_calls.tool_category",
            "status": "tool_calls.status",
            "impact_grade": (
                "CASE WHEN nearest_call.model_call_id IS NULL "
                "THEN 'structural_only' "
                "ELSE 'deterministic_adjacent_call' END"
            ),
            "thread": "threads.logical_thread_id",
            "thread_label": _THREAD_LABEL_SQL,
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "turn_ordinal": "turns.ordinal",
            "tool_call": "tool_calls.tool_call_id",
            "event_at": "tool_calls.started_at",
            "time_day": "substr(tool_calls.started_at, 1, 10)",
            "time_hour": ("substr(tool_calls.started_at, 1, 13) || ':00:00Z'"),
        },
        row_measures={
            "tools": "1",
            "duration_ms": "tool_calls.duration_ms",
            "output_bytes": "tool_calls.output_bytes",
            "adjacent_uncached_input_tokens": (
                "nearest_call.input_tokens - nearest_call.cached_input_tokens"
            ),
            "adjacent_cached_input_tokens": "nearest_call.cached_input_tokens",
            "adjacent_reasoning_tokens": "nearest_call.reasoning_tokens",
            "adjacent_output_tokens": "nearest_call.output_tokens",
            "adjacent_total_tokens": ("nearest_call.input_tokens + nearest_call.output_tokens"),
        },
        aggregate_measures={
            "tools": "COUNT(*)",
            "duration_ms": "SUM(tool_calls.duration_ms)",
            "output_bytes": "SUM(tool_calls.output_bytes)",
            "adjacent_uncached_input_tokens": (
                "SUM(nearest_call.input_tokens - nearest_call.cached_input_tokens)"
            ),
            "adjacent_cached_input_tokens": "SUM(nearest_call.cached_input_tokens)",
            "adjacent_reasoning_tokens": "SUM(nearest_call.reasoning_tokens)",
            "adjacent_output_tokens": "SUM(nearest_call.output_tokens)",
            "adjacent_total_tokens": (
                "SUM(nearest_call.input_tokens + nearest_call.output_tokens)"
            ),
        },
        filter_fields={
            "tool": "tool_calls.tool_name",
            "operation": "tool_calls.operation",
            "target": "tool_calls.target_label",
            "server": "tool_calls.server_name",
            "namespace": "tool_calls.namespace",
            "category": "tool_calls.tool_category",
            "status": "tool_calls.status",
            "thread": "threads.logical_thread_id",
            "thread_label": _THREAD_LABEL_SQL,
            "started_at": "tool_calls.started_at",
        },
        operations=_COMMON_OPERATIONS,
        coverage_fields={
            "duration_ms": "tool_calls.duration_ms",
            "output_bytes": "tool_calls.output_bytes",
            "adjacent_uncached_input_tokens": "nearest_call.input_tokens",
            "adjacent_cached_input_tokens": "nearest_call.input_tokens",
            "adjacent_reasoning_tokens": "nearest_call.input_tokens",
            "adjacent_output_tokens": "nearest_call.input_tokens",
            "adjacent_total_tokens": "nearest_call.input_tokens",
        },
        base_generation_parameters=2,
    ),
    "context": DatasetSpec(
        base_sql="composition_events",
        generation_sql="composition_events.generation <= ?",
        time_sql="composition_events.event_at",
        stable_id_sql="composition_events.event_id",
        dimensions={
            "context_event": "composition_events.event_id",
            "category": "composition_events.category",
            "thread": "composition_events.logical_thread_id",
            "turn": "composition_events.turn_id",
            "event_at": "composition_events.event_at",
            "time_day": "substr(composition_events.event_at, 1, 10)",
        },
        row_measures={
            "events": "1",
            "observed_bytes": "composition_events.observed_bytes",
            "estimated_tokens": "composition_events.estimated_tokens",
        },
        aggregate_measures={
            "events": "COUNT(*)",
            "observed_bytes": "SUM(composition_events.observed_bytes)",
            "estimated_tokens": "SUM(composition_events.estimated_tokens)",
        },
        filter_fields={
            "category": "composition_events.category",
            "thread": "composition_events.logical_thread_id",
            "turn": "composition_events.turn_id",
            "event_at": "composition_events.event_at",
        },
        operations=_CONTEXT_OPERATIONS,
        coverage_fields={
            "estimated_tokens": "composition_events.estimated_tokens",
        },
    ),
    "activities": DatasetSpec(
        base_sql=(
            "activity_events "
            "JOIN threads ON threads.thread_id = activity_events.thread_id "
            "LEFT JOIN turns ON turns.turn_id = activity_events.turn_id"
        ),
        generation_sql="activity_events.generation <= ?",
        time_sql="activity_events.event_at",
        stable_id_sql="activity_events.activity_event_id",
        dimensions={
            "activity": "activity_events.event_kind",
            "category": "activity_events.category",
            "thread": "threads.logical_thread_id",
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "event_at": "activity_events.event_at",
            "time_day": "substr(activity_events.event_at, 1, 10)",
        },
        row_measures={"activities": "1"},
        aggregate_measures={
            "activities": "COUNT(*)",
            "completions": ("SUM(CASE WHEN activity_events.event_kind = 'task' THEN 1 ELSE 0 END)"),
            "aborts": (
                "SUM(CASE WHEN activity_events.event_kind IN "
                "('rollback', 'turn_aborted') THEN 1 ELSE 0 END)"
            ),
            "compactions": (
                "SUM(CASE WHEN activity_events.event_kind = 'compaction' THEN 1 ELSE 0 END)"
            ),
        },
        filter_fields={
            "activity": "activity_events.event_kind",
            "category": "activity_events.category",
            "thread": "threads.logical_thread_id",
            "event_at": "activity_events.event_at",
        },
        operations=_COMMON_OPERATIONS,
    ),
    "allowance": DatasetSpec(
        base_sql=ALLOWANCE_BASE_SQL,
        generation_sql="1 = 1",
        time_sql="allowance_intervals.observed_at",
        stable_id_sql="allowance_intervals.allowance_observation_id",
        dimensions={
            "allowance": "allowance_intervals.allowance_observation_id",
            "window": "allowance_intervals.window_kind",
            "plan": "allowance_intervals.plan_type",
            "model": "allowance_intervals.model",
            "service_tier": "allowance_intervals.service_tier",
            "event_at": "allowance_intervals.observed_at",
            "time_day": "substr(allowance_intervals.observed_at, 1, 10)",
        },
        row_measures={
            "allowance_observations": "1",
            "allowance_used_percent": "allowance_intervals.used_percent",
            "allowance_remaining_percent": ("allowance_intervals.remaining_percent"),
            "allowance_delta_percent": ("allowance_intervals.delta_used_percent"),
            "allowance_burn_rate": ("allowance_intervals.percentage_points_per_hour"),
            "local_total_tokens": "allowance_intervals.local_total_tokens",
            "local_uncached_input_tokens": ("allowance_intervals.local_uncached_input_tokens"),
            "local_cached_input_tokens": ("allowance_intervals.local_cached_input_tokens"),
            "local_reasoning_tokens": ("allowance_intervals.local_reasoning_tokens"),
            "local_output_tokens": ("allowance_intervals.local_output_tokens"),
            "local_calls": "allowance_intervals.local_calls",
            "local_turns": "allowance_intervals.local_turns",
            "local_tokens_per_percentage_point": (
                "allowance_intervals.local_tokens_per_percentage_point"
            ),
            "local_calls_per_percentage_point": (
                "allowance_intervals.local_calls_per_percentage_point"
            ),
            "local_turns_per_percentage_point": (
                "allowance_intervals.local_turns_per_percentage_point"
            ),
        },
        aggregate_measures={},
        filter_fields={
            "window": "allowance_intervals.window_kind",
            "plan": "allowance_intervals.plan_type",
            "observed_at": "allowance_intervals.observed_at",
        },
        operations=frozenset({Operation.ROWS, Operation.TIMELINE}),
        coverage_fields={
            "allowance_delta_percent": ("allowance_intervals.delta_used_percent"),
            "allowance_burn_rate": ("allowance_intervals.percentage_points_per_hour"),
            "local_tokens_per_percentage_point": (
                "allowance_intervals.local_tokens_per_percentage_point"
            ),
            "local_calls_per_percentage_point": (
                "allowance_intervals.local_calls_per_percentage_point"
            ),
            "local_turns_per_percentage_point": (
                "allowance_intervals.local_turns_per_percentage_point"
            ),
        },
        base_generation_parameters=3,
    ),
    "threads": DatasetSpec(
        base_sql="threads",
        generation_sql=("threads.first_generation <= ? AND " + _CANONICAL_THREAD_SQL),
        time_sql="threads.updated_at",
        stable_id_sql="threads.logical_thread_id",
        dimensions={
            "thread": "threads.logical_thread_id",
            "thread_label": _THREAD_LABEL_SQL,
            "project": "threads.project_label",
            "agent_role": "threads.subagent_role",
            "agent_type": "threads.subagent_type",
            "archive_state": "threads.archive_state",
            "event_at": "threads.updated_at",
        },
        row_measures={"threads": "1"},
        aggregate_measures={"threads": "COUNT(DISTINCT threads.logical_thread_id)"},
        filter_fields={
            "thread": "threads.logical_thread_id",
            "project": "threads.project_label",
            "agent_role": "threads.subagent_role",
            "archive_state": "threads.archive_state",
        },
        operations=_COMMON_OPERATIONS,
        base_generation_parameters=2,
    ),
    "turns": DatasetSpec(
        base_sql=_TURN_BASE_SQL,
        generation_sql=("turns.first_generation <= ? AND " + _CANONICAL_TURN_SQL),
        time_sql="turns.started_at",
        stable_id_sql="turns.turn_id",
        dimensions={
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "thread": "threads.logical_thread_id",
            "thread_label": _THREAD_LABEL_SQL,
            "turn_ordinal": "turns.ordinal",
            "completion_basis": "turns.effective_completion_basis",
            "status": "turns.effective_status",
            "event_at": "turns.started_at",
            "time_day": "substr(turns.started_at, 1, 10)",
        },
        row_measures={
            "turns": "1",
            "duration_ms": (
                "MAX(0.0, (julianday(turns.effective_ended_at) - "
                "julianday(turns.started_at)) * 86400000.0)"
            ),
        },
        aggregate_measures={
            "turns": "COUNT(*)",
            "duration_ms": (
                "SUM(MAX(0.0, (julianday(turns.effective_ended_at) - "
                "julianday(turns.started_at)) * 86400000.0))"
            ),
        },
        filter_fields={
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "thread": "threads.logical_thread_id",
            "status": "turns.effective_status",
            "started_at": "turns.started_at",
        },
        operations=_COMMON_OPERATIONS,
        base_generation_parameters=3,
        coverage_fields={"duration_ms": "turns.ended_at"},
    ),
}

_PHASE_GUIDANCE = {
    "operations": ("rows", "timeline"),
    "dimensions": ("event_at", "phase", "thread", "turn"),
    "measures": (
        "activities",
        "cached_input_tokens",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "total_tokens",
        "uncached_input_tokens",
    ),
    "filters": ("event_at", "thread", "turn"),
    "requires_scope_filter": True,
    "scope_filter_templates": {
        "thread": ({"field": "thread", "operator": "eq", "value": "$thread"},),
        "turn": ({"field": "turn", "operator": "eq", "value": "$turn"},),
        "time_window": (
            {"field": "event_at", "operator": "gte", "value": "$start"},
            {"field": "event_at", "operator": "lt", "value": "$end"},
        ),
    },
}

_FILTER_GRAMMAR = {
    "required_keys": ("field", "operator", "value"),
    "scalar_operators": ("eq", "gte", "gt", "lte", "lt"),
    "set_operator": {
        "name": "in",
        "value_type": "array",
        "min_items": 1,
        "max_items": 25,
    },
}

_CONCENTRATION_REQUEST = {
    "dataset": "calls",
    "operation": "share",
    "dimensions": ["thread"],
    "measures": [
        "calls",
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
        "total_tokens",
        "configured_cost_usd",
        "estimated_credits",
    ],
    "order_by": "total_tokens",
    "descending": True,
    "limit": 25,
}
_TOP_THREADS_EXACT_REQUEST = {
    "dataset": "calls",
    "operation": "share",
    "dimensions": ["thread"],
    "measures": [
        "calls",
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
        "total_tokens",
    ],
    "order_by": "total_tokens",
    "descending": True,
    "limit": 5,
}
_TOP_THREADS_COST_REQUEST = {
    "dataset": "calls",
    "operation": "share",
    "dimensions": ["thread"],
    "measures": [
        "total_tokens",
        "configured_cost_usd",
        "estimated_credits",
    ],
    "order_by": "total_tokens",
    "descending": True,
    "limit": 5,
}

_GUIDED_TEMPLATES: dict[str, dict[str, Any]] = {
    "allowance": {
        "kind": "query_template",
        "label": "Allowance movement and local efficiency",
        "evidence_policy": "after_ranking",
        "requests": [
            {
                "dataset": "allowance",
                "operation": "rows",
                "dimensions": ["allowance", "window", "event_at"],
                "measures": [
                    "allowance_used_percent",
                    "allowance_delta_percent",
                    "allowance_burn_rate",
                    "local_total_tokens",
                    "local_calls",
                    "local_turns",
                ],
                "order_by": "event_at",
                "descending": True,
                "limit": 25,
            },
            {
                "dataset": "allowance",
                "operation": "rows",
                "dimensions": ["allowance", "window", "event_at"],
                "measures": [
                    "local_uncached_input_tokens",
                    "local_cached_input_tokens",
                    "local_reasoning_tokens",
                    "local_output_tokens",
                ],
                "order_by": "event_at",
                "descending": True,
                "limit": 25,
            },
        ],
    },
    "concentration": {
        "kind": "query_template",
        "label": "Usage concentration by thread",
        "evidence_policy": "after_ranking",
        "requests": [deepcopy(_CONCENTRATION_REQUEST)],
    },
    "context_composition": {
        "kind": "query_template",
        "label": "Observed context composition by category",
        "evidence_policy": "aggregate_only",
        "requests": [
            {
                "dataset": "context",
                "operation": "share",
                "dimensions": ["category"],
                "measures": ["events", "observed_bytes", "estimated_tokens"],
                "order_by": "observed_bytes",
                "descending": True,
                "limit": 25,
            }
        ],
    },
    "latest_incremental_change": {
        "kind": "query_template",
        "label": "Latest committed generation change",
        "evidence_policy": "after_ranking",
        "anchor": "active_generation",
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["generation"],
                "measures": ["calls", "total_tokens"],
                "filters": [
                    {
                        "field": "generation",
                        "operator": "eq",
                        "value": "$latest_generation",
                    }
                ],
                "order_by": "generation",
                "descending": True,
                "limit": 1,
            },
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["thread", "thread_label"],
                "measures": ["calls", "total_tokens"],
                "filters": [
                    {
                        "field": "generation",
                        "operator": "eq",
                        "value": "$latest_generation",
                    }
                ],
                "order_by": "total_tokens",
                "descending": True,
                "limit": 1,
            },
        ],
    },
    "model_effort": {
        "kind": "query_template",
        "label": "Model and reasoning-effort mix",
        "evidence_policy": "after_ranking",
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["model", "effort"],
                "measures": [
                    "calls",
                    "uncached_input_tokens",
                    "cached_input_tokens",
                    "reasoning_tokens",
                    "output_tokens",
                    "total_tokens",
                    "configured_cost_usd",
                    "estimated_credits",
                ],
                "order_by": "total_tokens",
                "descending": True,
                "limit": 25,
            }
        ],
    },
    "period_comparison": {
        "kind": "query_template",
        "label": "Current period versus previous period",
        "evidence_policy": "after_ranking",
        "parameters": (
            "current_start",
            "current_end",
            "previous_start",
            "previous_end",
        ),
        "requests": [
            {
                "dataset": "calls",
                "operation": "comparison",
                "dimensions": ["model"],
                "measures": ["calls", "total_tokens"],
                "order_by": "total_tokens",
                "descending": True,
                "limit": 25,
                "comparison": {
                    "current_start": "$current_start",
                    "current_end": "$current_end",
                    "previous_start": "$previous_start",
                    "previous_end": "$previous_end",
                },
            }
        ],
    },
    "subagents": {
        "kind": "query_template",
        "label": "Parent and subagent usage",
        "evidence_policy": "after_ranking",
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["agent_role"],
                "measures": ["calls", "total_tokens"],
                "order_by": "total_tokens",
                "descending": True,
                "limit": 25,
            }
        ],
    },
    "top_threads": {
        "kind": "query_template",
        "label": "Top threads by exact total token usage",
        "evidence_policy": "after_ranking",
        "requests": [
            deepcopy(_TOP_THREADS_EXACT_REQUEST),
            deepcopy(_TOP_THREADS_COST_REQUEST),
        ],
    },
    "tools": {
        "kind": "query_template",
        "label": "Tool-call volume, duration, and output",
        "evidence_policy": "after_ranking",
        "requests": [
            {
                "dataset": "tools",
                "operation": "aggregate",
                "dimensions": ["category", "tool"],
                "measures": ["tools", "duration_ms", "output_bytes"],
                "order_by": "tools",
                "descending": True,
                "limit": 25,
            },
            {
                "dataset": "tools",
                "operation": "rows",
                "dimensions": ["tool_call", "operation", "target"],
                "measures": [
                    "duration_ms",
                    "output_bytes",
                    "adjacent_uncached_input_tokens",
                    "adjacent_cached_input_tokens",
                    "adjacent_reasoning_tokens",
                    "adjacent_output_tokens",
                    "adjacent_total_tokens",
                ],
                "order_by": "adjacent_total_tokens",
                "descending": True,
                "limit": 25,
            },
        ],
    },
    "turns": {
        "kind": "query_template",
        "label": "Turn count and elapsed time by thread",
        "evidence_policy": "after_ranking",
        "requests": [
            {
                "dataset": "turns",
                "operation": "aggregate",
                "dimensions": ["thread"],
                "measures": ["turns", "duration_ms"],
                "order_by": "duration_ms",
                "descending": True,
                "limit": 25,
            }
        ],
    },
    "week_over_week": {
        "kind": "query_template",
        "label": "Latest seven days versus the preceding seven days",
        "evidence_policy": "aggregate_only",
        "anchor": "latest_indexed_event",
        "requests": [
            {
                "dataset": "calls",
                "operation": "comparison",
                "dimensions": [],
                "measures": ["total_tokens"],
                "order_by": "total_tokens",
                "descending": True,
                "limit": 1,
                "comparison": {
                    "current_start": "$current_start",
                    "current_end": "$current_end",
                    "previous_start": "$previous_start",
                    "previous_end": "$previous_end",
                },
            }
        ],
    },
    "weekly_drivers": {
        "kind": "query_template",
        "label": "Top threads in the latest seven-day window",
        "evidence_policy": "after_ranking",
        "anchor": "latest_indexed_event",
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["thread", "thread_label"],
                "measures": ["calls", "total_tokens"],
                "filters": [
                    {
                        "field": "event_at",
                        "operator": "gte",
                        "value": "$current_start",
                    },
                    {
                        "field": "event_at",
                        "operator": "lte",
                        "value": "$latest_event_at",
                    },
                ],
                "order_by": "total_tokens",
                "descending": True,
                "limit": 5,
            }
        ],
    },
}
_TEMPLATE_CONTEXT_KEYS = {
    "latest_incremental_change": frozenset({"latest_generation"}),
    "week_over_week": frozenset(
        {
            "current_end",
            "current_start",
            "previous_end",
            "previous_start",
        }
    ),
    "weekly_drivers": frozenset({"current_start", "latest_event_at"}),
}

_DATASET_DEFAULT_REQUESTS = {
    "activities": {
        "dataset": "activities",
        "operation": "aggregate",
        "dimensions": ["category"],
        "measures": ["activities", "completions", "aborts"],
        "order_by": "activities",
        "descending": True,
        "limit": 25,
    },
    "allowance": _GUIDED_TEMPLATES["allowance"]["requests"][0],
    "calls": _GUIDED_TEMPLATES["concentration"]["requests"][0],
    "context": _GUIDED_TEMPLATES["context_composition"]["requests"][0],
    "threads": {
        "dataset": "threads",
        "operation": "aggregate",
        "dimensions": ["project"],
        "measures": ["threads"],
        "order_by": "threads",
        "descending": True,
        "limit": 25,
    },
    "tools": _GUIDED_TEMPLATES["tools"]["requests"][0],
    "turns": _GUIDED_TEMPLATES["turns"]["requests"][0],
}


def exploration_guidance() -> dict[str, Any]:
    """Return compact static metadata and non-interpretive query templates."""

    datasets: dict[str, dict[str, Any]] = {
        name: {
            "operations": sorted(operation.value for operation in spec.operations),
            "dimensions": sorted(spec.dimensions),
            "measures": sorted(set(spec.row_measures) | set(spec.aggregate_measures)),
            "filters": sorted(spec.filter_fields),
        }
        for name, spec in sorted(DATASETS.items())
    }
    for name, default_request in _DATASET_DEFAULT_REQUESTS.items():
        datasets[name]["default_request"] = deepcopy(default_request)
    datasets["phases"] = deepcopy(_PHASE_GUIDANCE)
    return {
        "schema": "codex-usage-tracker.query-guidance.v1",
        "limits": {
            "max_batch_queries": MAX_BATCH_QUERIES,
            "max_dimensions_per_query": MAX_DIMENSIONS,
            "max_filters_per_query": MAX_FILTERS,
            "max_measures_per_query": MAX_MEASURES,
            "max_rows_per_query": MAX_LIMIT,
            "max_response_bytes": MAX_QUERY_RESPONSE_BYTES,
        },
        "filter_grammar": deepcopy(_FILTER_GRAMMAR),
        "datasets": datasets,
        "templates": deepcopy(_GUIDED_TEMPLATES),
    }


def materialize_query_requests(
    raw_requests: list[dict[str, Any]],
    *,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Expand closed named templates into their deterministic typed requests."""

    materialized: list[dict[str, Any]] = []
    for raw_request in raw_requests:
        if "template" not in raw_request:
            materialized.append(deepcopy(raw_request))
            continue
        unexpected = sorted(set(raw_request) - {"template", "parameters"})
        if unexpected:
            raise ValueError("query template request has unexpected fields")
        template_name = raw_request.get("template")
        if not isinstance(template_name, str):
            raise ValueError("query template must be a string")
        template = _GUIDED_TEMPLATES.get(template_name)
        if template is None:
            raise ValueError("query template is not allowlisted")
        parameters = raw_request.get("parameters", {})
        expected = set(template.get("parameters", ()))
        if not isinstance(parameters, dict) or set(parameters) != expected:
            raise ValueError("query template parameters are invalid")
        required_context = _TEMPLATE_CONTEXT_KEYS.get(template_name, frozenset())
        available_context = context or {}
        if not required_context <= available_context.keys():
            raise ValueError("query template context is unavailable")
        resolved_parameters = {
            **parameters,
            **{
                key: available_context[key]
                for key in required_context
            },
        }
        resolved_requests = [
            _resolve_template_value(item, resolved_parameters)
            for item in template["requests"]
        ]
        for resolved_request in resolved_requests:
            resolved_request["allow_partial"] = True
        materialized.extend(resolved_requests)
    if len(materialized) > MAX_BATCH_QUERIES:
        raise ValueError(
            f"query supports at most {MAX_BATCH_QUERIES} materialized requests"
        )
    return tuple(materialized)


def query_template_context_keys(
    raw_requests: list[dict[str, Any]],
) -> frozenset[str]:
    """Return the snapshot facts required by the selected named templates."""

    return frozenset().union(
        *(
            _TEMPLATE_CONTEXT_KEYS.get(str(item.get("template")), frozenset())
            for item in raw_requests
        )
    )


def query_template_context_required(
    raw_requests: list[dict[str, Any]],
) -> bool:
    """Return whether a named request needs generation-bound snapshot facts."""

    return bool(query_template_context_keys(raw_requests))


def _resolve_template_value(value: Any, parameters: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return deepcopy(parameters[value[1:]])
    if isinstance(value, dict):
        return {
            key: _resolve_template_value(item, parameters)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_template_value(item, parameters) for item in value]
    return deepcopy(value)


def validate_request(request: QueryRequest) -> None:
    spec = DATASETS.get(request.dataset)
    if request.dataset == "phases":
        _validate_phases(request)
        return
    if spec is None:
        raise ValueError("query dataset is not allowlisted")
    if request.operation not in spec.operations:
        raise ValueError("query operation is not supported for dataset")
    _validate_fields(request, spec)
    _validate_operation_shape(request, spec)


def _validate_fields(request: QueryRequest, spec: DatasetSpec) -> None:
    unknown_dimensions = set(request.dimensions) - spec.dimensions.keys()
    measures = _measure_catalog(request, spec)
    unknown_measures = set(request.measures) - measures.keys()
    unknown_filters = {item.field for item in request.filters} - spec.filter_fields.keys()
    if unknown_dimensions or unknown_measures or unknown_filters:
        raise ValueError("query field is not allowlisted for dataset")
    available_order = set(request.dimensions) | set(request.measures)
    if request.order_by and request.order_by not in available_order:
        raise ValueError("query order field is not selected")


def _measure_catalog(
    request: QueryRequest,
    spec: DatasetSpec,
) -> dict[str, str]:
    aggregate_operations = {
        Operation.AGGREGATE,
        Operation.SHARE,
        Operation.COMPARISON,
        Operation.DISTRIBUTION,
        Operation.TIME_SERIES,
    }
    return (
        spec.aggregate_measures if request.operation in aggregate_operations else spec.row_measures
    )


def _validate_operation_shape(
    request: QueryRequest,
    spec: DatasetSpec,
) -> None:
    if (
        request.operation
        in {
            Operation.AGGREGATE,
            Operation.SHARE,
            Operation.COMPARISON,
            Operation.DISTRIBUTION,
            Operation.TIME_SERIES,
        }
        and not request.measures
    ):
        raise ValueError("aggregate query requires at least one measure")
    if request.operation is Operation.SHARE and (
        len(request.dimensions) != 1 or not request.measures
    ):
        raise ValueError("share requires one dimension and at least one measure")
    if request.operation is Operation.COMPARISON:
        if request.comparison is None or spec.time_sql is None or not request.measures:
            raise ValueError("comparison requires a timed dataset, measures, and two windows")
        unsupported = set(request.measures) - {
            "calls",
            "input_tokens",
            "uncached_input_tokens",
            "cached_input_tokens",
            "reasoning_tokens",
            "output_tokens",
            "total_tokens",
        }
        if request.dataset != "calls" or unsupported:
            raise ValueError("comparison supports exact additive call measures only")
    elif request.comparison is not None:
        raise ValueError("comparison windows require the comparison operation")
    if request.operation is Operation.TIME_SERIES and not {"time_day", "time_hour"} & set(
        request.dimensions
    ):
        raise ValueError("time series requires time_day or time_hour dimension")
    if request.operation is Operation.TIMELINE and "event_at" not in request.dimensions:
        raise ValueError("timeline requires event_at dimension")
    if request.operation is Operation.DISTRIBUTION and not request.dimensions:
        raise ValueError("distribution requires at least one dimension")


def _validate_phases(request: QueryRequest) -> None:
    if request.operation not in {Operation.ROWS, Operation.TIMELINE}:
        raise ValueError("phases supports rows or timeline")
    if set(request.dimensions) - {"phase", "thread", "turn", "event_at"}:
        raise ValueError("query field is not allowlisted for phases")
    if set(request.measures) - {
        "activities",
        "input_tokens",
        "uncached_input_tokens",
        "cached_input_tokens",
        "reasoning_tokens",
        "output_tokens",
        "total_tokens",
    }:
        raise ValueError("query field is not allowlisted for phases")
    if {item.field for item in request.filters} - {"thread", "turn", "event_at"}:
        raise ValueError("query field is not allowlisted for phases")
    if not request.filters:
        raise ValueError("phase timeline requires a bounded scope filter")
    if request.operation is Operation.TIMELINE and "event_at" not in request.dimensions:
        raise ValueError("phase timeline requires event_at dimension")
    available_order = set(request.dimensions) | set(request.measures)
    if request.order_by and request.order_by not in available_order:
        raise ValueError("query order field is not selected")
