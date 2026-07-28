"""Compile normalized requests into static-expression named SQL plans."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .catalog import DATASETS, DatasetSpec
from .contracts import Filter, Operation, QueryRequest

PLAN_VERSION = 1


@dataclass(frozen=True)
class CompiledPlan:
    plan_id: str
    sql: str
    count_sql: str
    scan_sql: str
    coverage_sql: str | None
    parameters: tuple[Any, ...]
    count_parameters: tuple[Any, ...]
    scan_parameters: tuple[Any, ...]
    coverage_parameters: tuple[Any, ...]
    offset: int


def compile_plan(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
) -> CompiledPlan:
    rollup = _compile_thread_rollup(
        request,
        generation=generation,
        offset=offset,
    )
    if rollup is not None:
        return rollup
    rollup = _compile_model_effort_rollup(
        request,
        generation=generation,
        offset=offset,
    )
    if rollup is not None:
        return rollup
    rollup = _compile_time_rollup(
        request,
        generation=generation,
        offset=offset,
    )
    if rollup is not None:
        return rollup
    rollup = _compile_tool_operation_rollup(
        request,
        generation=generation,
        offset=offset,
    )
    if rollup is not None:
        return rollup
    rollup = _compile_global_rollup(
        request,
        generation=generation,
        offset=offset,
    )
    if rollup is not None:
        return rollup
    spec = DATASETS[request.dataset]
    if request.operation is Operation.COMPARISON:
        return _compile_comparison(
            request,
            spec=spec,
            generation=generation,
            offset=offset,
        )
    where_sql, filter_parameters = _filters(spec, request.filters)
    predicates = [spec.generation_sql, *where_sql]
    predicate_sql = " AND ".join(f"({item})" for item in predicates)
    base_parameters = (generation,) * spec.base_generation_parameters
    generation_parameters = () if spec.base_generation_parameters else (generation,)
    parameters = (*base_parameters, *generation_parameters, *filter_parameters)
    base_query = _base_query(request, spec, predicate_sql)
    order_sql = _order_sql(request, spec)
    sql = f"{base_query} ORDER BY {order_sql} LIMIT ? OFFSET ?"
    count_sql = f"SELECT COUNT(*) FROM ({base_query}) AS matched"
    scan_sql = f"SELECT COUNT(*) FROM {spec.base_sql} WHERE {predicate_sql}"
    coverage_sql = _coverage_sql(request, spec, predicate_sql)
    operation = Operation(request.operation)
    return CompiledPlan(
        plan_id=f"{request.dataset}.{operation.value}.v{PLAN_VERSION}",
        sql=sql,
        count_sql=count_sql,
        scan_sql=scan_sql,
        coverage_sql=coverage_sql,
        parameters=(*parameters, request.limit + 1, offset),
        count_parameters=parameters,
        scan_parameters=parameters,
        coverage_parameters=parameters if coverage_sql else (),
        offset=offset,
    )


def _compile_thread_rollup(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
) -> CompiledPlan | None:
    operation = Operation(request.operation)
    if (
        request.dataset != "calls"
        or operation not in {Operation.AGGREGATE, Operation.SHARE}
        or request.dimensions != ("thread",)
        or request.filters
        or request.comparison is not None
    ):
        return None
    expressions = {
        "calls": "rollup.calls",
        "input_tokens": "rollup.input_tokens",
        "uncached_input_tokens": ("rollup.input_tokens - rollup.cached_input_tokens"),
        "cached_input_tokens": "rollup.cached_input_tokens",
        "output_tokens": "rollup.output_tokens",
        "reasoning_tokens": "rollup.reasoning_tokens",
        "total_tokens": "rollup.input_tokens + rollup.output_tokens",
    }
    if any(measure not in expressions for measure in request.measures):
        return None
    selected = [
        "threads.logical_thread_id AS thread",
        (f"{DATASETS['calls'].dimensions['thread_label']} AS thread_label"),
        *(f"{expressions[measure]} AS {measure}" for measure in request.measures),
        "COUNT(*) OVER () AS __matched_count",
        "COUNT(*) OVER () AS __scanned_count",
    ]
    base_query = (
        f"SELECT {', '.join(selected)} "
        "FROM rollup_thread AS rollup "
        "JOIN threads USING (thread_key) "
        "WHERE rollup.generation = ?"
    )
    if operation is Operation.SHARE:
        share_columns = ", ".join(
            f"CASE WHEN SUM({measure}) OVER () = 0 THEN 0.0 "
            f"ELSE 1.0 * {measure} / SUM({measure}) OVER () END "
            f"AS share_{measure}"
            for measure in request.measures
        )
        base_query = f"SELECT grouped.*, {share_columns} FROM ({base_query}) AS grouped"
    order_name = request.order_by or (request.measures[0] if request.measures else "thread")
    direction = "DESC" if request.descending else "ASC"
    sql = f"{base_query} ORDER BY {order_name} {direction}, thread ASC LIMIT ? OFFSET ?"
    count_sql = "SELECT COUNT(*) FROM rollup_thread WHERE generation = ?"
    return CompiledPlan(
        plan_id=f"calls.{operation.value}.rollup_thread.v{PLAN_VERSION}",
        sql=sql,
        count_sql=count_sql,
        scan_sql=count_sql,
        coverage_sql=None,
        parameters=(generation, request.limit + 1, offset),
        count_parameters=(generation,),
        scan_parameters=(generation,),
        coverage_parameters=(),
        offset=offset,
    )


def _compile_model_effort_rollup(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
) -> CompiledPlan | None:
    operation = Operation(request.operation)
    allowed_dimensions = {"model", "effort", "service_tier"}
    if (
        request.dataset != "calls"
        or operation not in {Operation.AGGREGATE, Operation.SHARE}
        or not request.dimensions
        or not set(request.dimensions) <= allowed_dimensions
        or request.filters
        or request.comparison is not None
    ):
        return None
    dimensions = {
        "model": "rollup.model",
        "effort": "NULLIF(rollup.effort, '')",
        "service_tier": "NULLIF(rollup.service_tier, '')",
    }
    return _token_rollup_plan(
        request,
        generation=generation,
        offset=offset,
        table="rollup_model_effort",
        plan_name="rollup_model_effort",
        dimensions=dimensions,
        group_rows=True,
    )


def _compile_global_rollup(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
) -> CompiledPlan | None:
    if (
        request.dataset != "calls"
        or Operation(request.operation) is not Operation.AGGREGATE
        or request.dimensions
        or request.filters
        or request.comparison is not None
    ):
        return None
    return _token_rollup_plan(
        request,
        generation=generation,
        offset=offset,
        table="rollup_global",
        plan_name="rollup_global",
        dimensions={},
    )


def _compile_time_rollup(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
) -> CompiledPlan | None:
    if (
        request.dataset != "calls"
        or Operation(request.operation) is not Operation.TIME_SERIES
        or request.dimensions not in {("time_day",), ("time_hour",)}
        or request.filters
        or request.comparison is not None
    ):
        return None
    dimension = request.dimensions[0]
    band_kind = "day" if dimension == "time_day" else "hour"
    return _token_rollup_plan(
        request,
        generation=generation,
        offset=offset,
        table="rollup_time_band",
        plan_name="rollup_time_band",
        dimensions={dimension: "rollup.band_start"},
        predicate_sql="rollup.band_kind = ?",
        predicate_parameters=(band_kind,),
    )


def _compile_tool_operation_rollup(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
) -> CompiledPlan | None:
    if (
        request.dataset != "tools"
        or Operation(request.operation) is not Operation.AGGREGATE
        or not request.dimensions
        or not set(request.dimensions) <= {"operation", "target"}
        or request.filters
        or request.comparison is not None
    ):
        return None
    measures = {"tools": "rollup.calls"}
    if any(measure not in measures for measure in request.measures):
        return None
    dimensions = {
        "operation": "rollup.operation",
        "target": "NULLIF(rollup.target_label, '')",
    }
    group_by = ", ".join(dimensions[dimension] for dimension in request.dimensions)
    selected = [
        *(f"{dimensions[dimension]} AS {dimension}" for dimension in request.dimensions),
        *(f"SUM({measures[measure]}) AS {measure}" for measure in request.measures),
        "COUNT(*) OVER () AS __matched_count",
        "COUNT(*) OVER () AS __scanned_count",
    ]
    base_query = (
        f"SELECT {', '.join(selected)} "
        "FROM rollup_tool_operation AS rollup "
        f"WHERE rollup.generation = ? GROUP BY {group_by}"
    )
    order_name = request.order_by or (
        request.measures[0] if request.measures else request.dimensions[0]
    )
    direction = "DESC" if request.descending else "ASC"
    tie_breakers = ", ".join(f"{dimension} ASC" for dimension in request.dimensions)
    sql = f"{base_query} ORDER BY {order_name} {direction}, {tie_breakers} LIMIT ? OFFSET ?"
    count_sql = (
        "SELECT COUNT(*) FROM ("
        "SELECT 1 FROM rollup_tool_operation AS rollup "
        f"WHERE rollup.generation = ? GROUP BY {group_by}"
        ") AS grouped"
    )
    return CompiledPlan(
        plan_id=f"tools.aggregate.rollup_tool_operation.v{PLAN_VERSION}",
        sql=sql,
        count_sql=count_sql,
        scan_sql=count_sql,
        coverage_sql=None,
        parameters=(generation, request.limit + 1, offset),
        count_parameters=(generation,),
        scan_parameters=(generation,),
        coverage_parameters=(),
        offset=offset,
    )


def _token_rollup_plan(
    request: QueryRequest,
    *,
    generation: int,
    offset: int,
    table: str,
    plan_name: str,
    dimensions: dict[str, str],
    predicate_sql: str | None = None,
    predicate_parameters: tuple[Any, ...] = (),
    group_rows: bool = False,
) -> CompiledPlan | None:
    measures = {
        "calls": "rollup.calls",
        "input_tokens": "rollup.input_tokens",
        "uncached_input_tokens": ("rollup.input_tokens - rollup.cached_input_tokens"),
        "cached_input_tokens": "rollup.cached_input_tokens",
        "output_tokens": "rollup.output_tokens",
        "reasoning_tokens": "rollup.reasoning_tokens",
        "total_tokens": "rollup.input_tokens + rollup.output_tokens",
    }
    if any(measure not in measures for measure in request.measures):
        return None
    selected_dimensions = [
        *(f"{dimensions[dimension]} AS {dimension}" for dimension in request.dimensions),
    ]
    selected_measures = [
        (
            f"SUM({measures[measure]}) AS {measure}"
            if group_rows
            else f"{measures[measure]} AS {measure}"
        )
        for measure in request.measures
    ]
    selected = [
        *selected_dimensions,
        *selected_measures,
        "COUNT(*) OVER () AS __matched_count",
        "COUNT(*) OVER () AS __scanned_count",
    ]
    predicates = "rollup.generation = ?"
    if predicate_sql is not None:
        predicates = f"{predicates} AND ({predicate_sql})"
    group_sql = (
        " GROUP BY " + ", ".join(dimensions[dimension] for dimension in request.dimensions)
        if group_rows
        else ""
    )
    base_query = (
        f"SELECT {', '.join(selected)} FROM {table} AS rollup WHERE {predicates}{group_sql}"
    )
    operation = Operation(request.operation)
    if operation is Operation.SHARE:
        share_columns = ", ".join(
            f"CASE WHEN SUM({measure}) OVER () = 0 THEN 0.0 "
            f"ELSE 1.0 * {measure} / SUM({measure}) OVER () END "
            f"AS share_{measure}"
            for measure in request.measures
        )
        base_query = f"SELECT grouped.*, {share_columns} FROM ({base_query}) AS grouped"
    order_name = request.order_by or (
        request.measures[0]
        if request.measures
        else request.dimensions[0]
        if request.dimensions
        else "__matched_count"
    )
    direction = "DESC" if request.descending else "ASC"
    tie_breakers = ", ".join(f"{dimension} ASC" for dimension in request.dimensions)
    ordering = f"{order_name} {direction}"
    if tie_breakers:
        ordering = f"{ordering}, {tie_breakers}"
    sql = f"{base_query} ORDER BY {ordering} LIMIT ? OFFSET ?"
    if group_rows:
        count_sql = (
            "SELECT COUNT(*) FROM ("
            f"SELECT 1 FROM {table} AS rollup "
            f"WHERE {predicates}{group_sql}"
            ") AS grouped"
        )
    else:
        count_sql = f"SELECT COUNT(*) FROM {table} AS rollup WHERE {predicates}"
    base_parameters = (generation, *predicate_parameters)
    return CompiledPlan(
        plan_id=(f"calls.{operation.value}.{plan_name}.v{PLAN_VERSION}"),
        sql=sql,
        count_sql=count_sql,
        scan_sql=count_sql,
        coverage_sql=None,
        parameters=(*base_parameters, request.limit + 1, offset),
        count_parameters=base_parameters,
        scan_parameters=base_parameters,
        coverage_parameters=(),
        offset=offset,
    )


def _base_query(
    request: QueryRequest,
    spec: DatasetSpec,
    predicate_sql: str,
) -> str:
    aggregate = Operation(request.operation) in {
        Operation.AGGREGATE,
        Operation.SHARE,
        Operation.DISTRIBUTION,
        Operation.TIME_SERIES,
    }
    dimensions = [f"{spec.dimensions[name]} AS {name}" for name in request.dimensions]
    if (
        "thread" in request.dimensions
        and "thread_label" not in request.dimensions
        and "thread_label" in spec.dimensions
    ):
        dimensions.append(f"{spec.dimensions['thread_label']} AS thread_label")
    measures_catalog = spec.aggregate_measures if aggregate else spec.row_measures
    measures = [f"{measures_catalog[name]} AS {name}" for name in request.measures]
    selected = dimensions + measures
    if not selected:
        selected = [f"{spec.stable_id_sql} AS record_id"]
    if aggregate:
        selected.extend(
            (
                "COUNT(*) OVER () AS __matched_count",
                "SUM(COUNT(*)) OVER () AS __scanned_count",
            )
        )
    else:
        selected.extend(
            (
                "COUNT(*) OVER () AS __matched_count",
                "COUNT(*) OVER () AS __scanned_count",
            )
        )
    group_sql = (
        " GROUP BY "
        + ", ".join(
            (
                *(spec.dimensions[name] for name in request.dimensions),
                *(
                    (spec.dimensions["thread_label"],)
                    if (
                        "thread" in request.dimensions
                        and "thread_label" not in request.dimensions
                        and "thread_label" in spec.dimensions
                    )
                    else ()
                ),
            )
        )
        if aggregate and request.dimensions
        else ""
    )
    base_query = (
        f"SELECT {', '.join(selected)} FROM {spec.base_sql} WHERE {predicate_sql}{group_sql}"
    )
    if request.operation is Operation.SHARE:
        share_columns = ", ".join(
            f"CASE WHEN SUM({name}) OVER () = 0 THEN 0.0 "
            f"ELSE 1.0 * {name} / SUM({name}) OVER () END AS share_{name}"
            for name in request.measures
        )
        base_query = f"SELECT grouped.*, {share_columns} FROM ({base_query}) AS grouped"
    return base_query


def _order_sql(request: QueryRequest, spec: DatasetSpec) -> str:
    operation = Operation(request.operation)
    order_name = request.order_by or _default_order(request, operation)
    direction = "DESC" if request.descending else "ASC"
    tie_breakers = [name for name in (*request.dimensions, *request.measures) if name != order_name]
    ordering = [
        f"{order_name} {direction}",
        *(f"{name} ASC" for name in tie_breakers),
    ]
    if Operation(request.operation) in {Operation.ROWS, Operation.TIMELINE}:
        ordering.append(f"{spec.stable_id_sql} ASC")
    return ", ".join(ordering)


def _default_order(request: QueryRequest, operation: Operation) -> str:
    if operation is Operation.TIMELINE:
        return "event_at"
    if operation is Operation.TIME_SERIES:
        return "time_day"
    if request.measures:
        return request.measures[0]
    if request.dimensions:
        return request.dimensions[0]
    return "record_id"


def _coverage_sql(
    request: QueryRequest,
    spec: DatasetSpec,
    predicate_sql: str,
) -> str | None:
    fields = {
        measure: spec.coverage_fields[measure]
        for measure in request.measures
        if measure in spec.coverage_fields
    }
    if not fields:
        return None
    selected = ["COUNT(*) AS coverage_total"]
    for measure, expression in fields.items():
        selected.extend(
            (
                (
                    f"SUM(CASE WHEN {expression} IS NOT NULL THEN 1 ELSE 0 END) "
                    f"AS observed_{measure}"
                ),
                (f"SUM(CASE WHEN {expression} IS NULL THEN 1 ELSE 0 END) AS missing_{measure}"),
            )
        )
    return f"SELECT {', '.join(selected)} FROM {spec.base_sql} WHERE {predicate_sql}"


def _compile_comparison(
    request: QueryRequest,
    *,
    spec: DatasetSpec,
    generation: int,
    offset: int,
) -> CompiledPlan:
    comparison = request.comparison
    assert comparison is not None
    assert spec.time_sql is not None
    where_sql, filter_parameters = _filters(spec, request.filters)
    ranges = (
        f"((julianday({spec.time_sql}) >= julianday(?) "
        f"AND julianday({spec.time_sql}) < julianday(?)) OR "
        f"(julianday({spec.time_sql}) >= julianday(?) "
        f"AND julianday({spec.time_sql}) < julianday(?)))"
    )
    predicates = [spec.generation_sql, *where_sql, ranges]
    predicate_sql = " AND ".join(f"({item})" for item in predicates)
    parameters = (
        generation,
        *filter_parameters,
        comparison.current_start,
        comparison.current_end,
        comparison.previous_start,
        comparison.previous_end,
    )
    dimensions = [f"{spec.dimensions[name]} AS {name}" for name in request.dimensions]
    row_measures = [f"{spec.row_measures[name]} AS {name}" for name in request.measures]
    scoped = (
        f"SELECT {', '.join([*dimensions, *row_measures])}, "
        f"CASE WHEN julianday({spec.time_sql}) >= julianday(?) "
        f"AND julianday({spec.time_sql}) < julianday(?) "
        "THEN 'current' ELSE 'previous' END AS comparison_period "
        f"FROM {spec.base_sql} WHERE {predicate_sql}"
    )
    scoped_parameters = (
        comparison.current_start,
        comparison.current_end,
        *parameters,
    )
    selected = list(request.dimensions)
    for measure in request.measures:
        current = f"SUM(CASE WHEN comparison_period = 'current' THEN {measure} ELSE 0 END)"
        previous = f"SUM(CASE WHEN comparison_period = 'previous' THEN {measure} ELSE 0 END)"
        selected.extend(
            (
                f"{current} AS current_{measure}",
                f"{previous} AS previous_{measure}",
                f"{current} - {previous} AS change_{measure}",
                (
                    f"CASE WHEN {previous} = 0 THEN NULL ELSE "
                    f"100.0 * ({current} - {previous}) / {previous} END "
                    f"AS change_percent_{measure}"
                ),
            )
        )
    selected.extend(
        (
            "COUNT(*) OVER () AS __matched_count",
            "SUM(COUNT(*)) OVER () AS __scanned_count",
        )
    )
    group_sql = " GROUP BY " + ", ".join(request.dimensions) if request.dimensions else ""
    base_query = f"WITH scoped AS ({scoped}) SELECT {', '.join(selected)} FROM scoped{group_sql}"
    order_name = (
        f"current_{request.order_by}" if request.order_by in request.measures else request.order_by
    ) or f"current_{request.measures[0]}"
    direction = "DESC" if request.descending else "ASC"
    tie_breakers = ", ".join(f"{dimension} ASC" for dimension in request.dimensions)
    order_sql = f"{order_name} {direction}"
    if tie_breakers:
        order_sql = f"{order_sql}, {tie_breakers}"
    sql = f"{base_query} ORDER BY {order_sql} LIMIT ? OFFSET ?"
    count_sql = f"SELECT COUNT(*) FROM ({base_query}) AS matched"
    scan_sql = f"SELECT COUNT(*) FROM {spec.base_sql} WHERE {predicate_sql}"
    return CompiledPlan(
        plan_id=f"{request.dataset}.comparison.v{PLAN_VERSION}",
        sql=sql,
        count_sql=count_sql,
        scan_sql=scan_sql,
        coverage_sql=None,
        parameters=(*scoped_parameters, request.limit + 1, offset),
        count_parameters=scoped_parameters,
        scan_parameters=parameters,
        coverage_parameters=(),
        offset=offset,
    )


def _filters(
    spec: DatasetSpec,
    filters: tuple[Filter, ...],
) -> tuple[list[str], tuple[Any, ...]]:
    sql: list[str] = []
    parameters: list[Any] = []
    operators = {
        "eq": "=",
        "gte": ">=",
        "gt": ">",
        "lte": "<=",
        "lt": "<",
    }
    for item in filters:
        expression = spec.filter_fields[item.field]
        parameter_sql = "?"
        if item.field in {"event_at", "started_at", "observed_at"}:
            expression = f"julianday({expression})"
            parameter_sql = "julianday(?)"
        if item.operator == "in":
            values = item.value
            assert isinstance(values, tuple)
            sql.append(f"{expression} IN ({', '.join(parameter_sql for _ in values)})")
            parameters.extend(values)
        else:
            sql.append(f"{expression} {operators[item.operator]} {parameter_sql}")
            parameters.append(item.value)
    return sql, tuple(parameters)
