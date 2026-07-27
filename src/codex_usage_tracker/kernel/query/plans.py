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
    parameters = (generation, *filter_parameters)
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
    dimensions = [
        f"{spec.dimensions[name]} AS {name}" for name in request.dimensions
    ]
    measures_catalog = (
        spec.aggregate_measures if aggregate else spec.row_measures
    )
    measures = [
        f"{measures_catalog[name]} AS {name}" for name in request.measures
    ]
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
        " GROUP BY " + ", ".join(spec.dimensions[name] for name in request.dimensions)
        if aggregate and request.dimensions
        else ""
    )
    base_query = (
        f"SELECT {', '.join(selected)} FROM {spec.base_sql} "
        f"WHERE {predicate_sql}{group_sql}"
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
    tie_breakers = [
        name
        for name in (*request.dimensions, *request.measures)
        if name != order_name
    ]
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
                (
                    f"SUM(CASE WHEN {expression} IS NULL THEN 1 ELSE 0 END) "
                    f"AS missing_{measure}"
                ),
            )
        )
    return (
        f"SELECT {', '.join(selected)} FROM {spec.base_sql} "
        f"WHERE {predicate_sql}"
    )


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
    dimensions = [
        f"{spec.dimensions[name]} AS {name}" for name in request.dimensions
    ]
    row_measures = [
        f"{spec.row_measures[name]} AS {name}" for name in request.measures
    ]
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
        previous = (
            f"SUM(CASE WHEN comparison_period = 'previous' THEN {measure} ELSE 0 END)"
        )
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
    group_sql = (
        " GROUP BY " + ", ".join(request.dimensions)
        if request.dimensions
        else ""
    )
    base_query = (
        f"WITH scoped AS ({scoped}) "
        f"SELECT {', '.join(selected)} FROM scoped{group_sql}"
    )
    order_name = (
        f"current_{request.order_by}"
        if request.order_by in request.measures
        else request.order_by
    ) or f"current_{request.measures[0]}"
    direction = "DESC" if request.descending else "ASC"
    tie_breakers = ", ".join(
        f"{dimension} ASC" for dimension in request.dimensions
    )
    order_sql = f"{order_name} {direction}"
    if tie_breakers:
        order_sql = f"{order_sql}, {tie_breakers}"
    sql = f"{base_query} ORDER BY {order_sql} LIMIT ? OFFSET ?"
    count_sql = f"SELECT COUNT(*) FROM ({base_query}) AS matched"
    scan_sql = (
        f"SELECT COUNT(*) FROM {spec.base_sql} "
        f"WHERE {predicate_sql}"
    )
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
            sql.append(
                f"{expression} IN "
                f"({', '.join(parameter_sql for _ in values)})"
            )
            parameters.extend(values)
        else:
            sql.append(
                f"{expression} {operators[item.operator]} {parameter_sql}"
            )
            parameters.append(item.value)
    return sql, tuple(parameters)
