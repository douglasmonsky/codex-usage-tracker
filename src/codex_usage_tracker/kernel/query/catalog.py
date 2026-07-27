"""Static query allowlists and SQL expression catalog."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import Operation, QueryRequest


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

_CALL_DIMENSIONS = {
    "call": "model_calls.canonical_call_id",
    "thread": "threads.logical_thread_id",
    "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
    "project": "threads.project_label",
    "model": "model_calls.model",
    "effort": "model_calls.effort",
    "service_tier": "model_calls.service_tier",
    "origin": "model_calls.origin",
    "agent_role": "threads.subagent_role",
    "event_at": "model_calls.event_at",
    "time_day": "substr(model_calls.event_at, 1, 10)",
}
_CALL_ROWS = {
    "calls": "1",
    "input_tokens": "model_calls.input_tokens",
    "uncached_input_tokens": (
        "model_calls.input_tokens - model_calls.cached_input_tokens"
    ),
    "cached_input_tokens": "model_calls.cached_input_tokens",
    "reasoning_tokens": "model_calls.reasoning_tokens",
    "output_tokens": "model_calls.output_tokens",
    "total_tokens": "model_calls.input_tokens + model_calls.output_tokens",
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
    "uncached_input_tokens": (
        "SUM(model_calls.input_tokens - model_calls.cached_input_tokens)"
    ),
    "cached_input_tokens": "SUM(model_calls.cached_input_tokens)",
    "reasoning_tokens": "SUM(model_calls.reasoning_tokens)",
    "output_tokens": "SUM(model_calls.output_tokens)",
    "total_tokens": "SUM(model_calls.input_tokens + model_calls.output_tokens)",
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
            "model_calls.generation <= ? "
            "AND model_calls.duplicate_state = 'canonical'"
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
        coverage_fields={"context_pressure": "model_calls.context_window"},
    ),
    "tools": DatasetSpec(
        base_sql=(
            "tool_calls "
            "JOIN threads ON threads.thread_id = tool_calls.thread_id "
            "LEFT JOIN turns ON turns.turn_id = tool_calls.turn_id"
        ),
        generation_sql="tool_calls.generation <= ?",
        time_sql="tool_calls.started_at",
        stable_id_sql="tool_calls.tool_call_id",
        dimensions={
            "tool": "tool_calls.tool_name",
            "server": "tool_calls.server_name",
            "namespace": "tool_calls.namespace",
            "category": "tool_calls.tool_category",
            "status": "tool_calls.status",
            "thread": "threads.logical_thread_id",
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "tool_call": "tool_calls.tool_call_id",
            "event_at": "tool_calls.started_at",
            "time_day": "substr(tool_calls.started_at, 1, 10)",
        },
        row_measures={
            "tools": "1",
            "duration_ms": "tool_calls.duration_ms",
            "output_bytes": "tool_calls.output_bytes",
        },
        aggregate_measures={
            "tools": "COUNT(*)",
            "duration_ms": "SUM(tool_calls.duration_ms)",
            "output_bytes": "SUM(tool_calls.output_bytes)",
        },
        filter_fields={
            "tool": "tool_calls.tool_name",
            "server": "tool_calls.server_name",
            "namespace": "tool_calls.namespace",
            "category": "tool_calls.tool_category",
            "status": "tool_calls.status",
            "thread": "threads.logical_thread_id",
            "started_at": "tool_calls.started_at",
        },
        operations=_COMMON_OPERATIONS,
        coverage_fields={
            "duration_ms": "tool_calls.duration_ms",
            "output_bytes": "tool_calls.output_bytes",
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
            "completions": (
                "SUM(CASE WHEN activity_events.event_kind = 'task' THEN 1 ELSE 0 END)"
            ),
            "aborts": (
                "SUM(CASE WHEN activity_events.event_kind IN "
                "('rollback', 'turn_aborted') THEN 1 ELSE 0 END)"
            ),
            "compactions": (
                "SUM(CASE WHEN activity_events.event_kind = 'compaction' "
                "THEN 1 ELSE 0 END)"
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
        base_sql="allowance_observations",
        generation_sql=(
            "allowance_observations.generation <= ? "
            "AND allowance_observations.duplicate_state = 'canonical'"
        ),
        time_sql="allowance_observations.observed_at",
        stable_id_sql="allowance_observations.allowance_observation_id",
        dimensions={
            "allowance": "allowance_observations.allowance_observation_id",
            "window": "allowance_observations.window_kind",
            "plan": "allowance_observations.plan_type",
            "model": "allowance_observations.model",
            "service_tier": "allowance_observations.service_tier",
            "event_at": "allowance_observations.observed_at",
            "time_day": "substr(allowance_observations.observed_at, 1, 10)",
        },
        row_measures={
            "allowance_observations": "1",
            "allowance_used_percent": "allowance_observations.used_percent",
        },
        aggregate_measures={
            "allowance_observations": "COUNT(*)",
            "allowance_used_percent": "MAX(allowance_observations.used_percent)",
        },
        filter_fields={
            "window": "allowance_observations.window_kind",
            "plan": "allowance_observations.plan_type",
            "observed_at": "allowance_observations.observed_at",
        },
        operations=_COMMON_OPERATIONS,
    ),
    "threads": DatasetSpec(
        base_sql="threads",
        generation_sql="threads.first_generation <= ?",
        time_sql="threads.updated_at",
        stable_id_sql="threads.logical_thread_id",
        dimensions={
            "thread": "threads.logical_thread_id",
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
    ),
    "turns": DatasetSpec(
        base_sql=(
            "turns JOIN threads ON threads.thread_id = turns.thread_id"
        ),
        generation_sql="turns.first_generation <= ?",
        time_sql="turns.started_at",
        stable_id_sql="turns.turn_id",
        dimensions={
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "thread": "threads.logical_thread_id",
            "status": "turns.status",
            "event_at": "turns.started_at",
            "time_day": "substr(turns.started_at, 1, 10)",
        },
        row_measures={
            "turns": "1",
            "duration_ms": (
                "MAX(0.0, (julianday(turns.ended_at) - "
                "julianday(turns.started_at)) * 86400000.0)"
            ),
        },
        aggregate_measures={
            "turns": "COUNT(*)",
            "duration_ms": (
                "SUM(MAX(0.0, (julianday(turns.ended_at) - "
                "julianday(turns.started_at)) * 86400000.0))"
            ),
        },
        filter_fields={
            "turn": "COALESCE(turns.source_turn_id_hash, turns.turn_id)",
            "thread": "threads.logical_thread_id",
            "status": "turns.status",
            "started_at": "turns.started_at",
        },
        operations=_COMMON_OPERATIONS,
        coverage_fields={"duration_ms": "turns.ended_at"},
    ),
}


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
        spec.aggregate_measures
        if request.operation in aggregate_operations
        else spec.row_measures
    )


def _validate_operation_shape(
    request: QueryRequest,
    spec: DatasetSpec,
) -> None:
    if request.operation in {
        Operation.AGGREGATE,
        Operation.SHARE,
        Operation.COMPARISON,
        Operation.DISTRIBUTION,
        Operation.TIME_SERIES,
    } and not request.measures:
        raise ValueError("aggregate query requires at least one measure")
    if request.operation is Operation.SHARE and (
        len(request.dimensions) != 1 or not request.measures
    ):
        raise ValueError("share requires one dimension and at least one measure")
    if request.operation is Operation.COMPARISON:
        if request.comparison is None or spec.time_sql is None or not request.measures:
            raise ValueError(
                "comparison requires a timed dataset, measures, and two windows"
            )
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
            raise ValueError(
                "comparison supports exact additive call measures only"
            )
    elif request.comparison is not None:
        raise ValueError("comparison windows require the comparison operation")
    if (
        request.operation is Operation.TIME_SERIES
        and "time_day" not in request.dimensions
    ):
        raise ValueError("time series requires time_day dimension")
    if (
        request.operation is Operation.TIMELINE
        and "event_at" not in request.dimensions
    ):
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
    if (
        request.operation is Operation.TIMELINE
        and "event_at" not in request.dimensions
    ):
        raise ValueError("phase timeline requires event_at dimension")
    available_order = set(request.dimensions) | set(request.measures)
    if request.order_by and request.order_by not in available_order:
        raise ValueError("query order field is not selected")
