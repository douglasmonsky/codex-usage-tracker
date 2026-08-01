"""Bounded SQL page execution for CK-08R2 direct runtime plans."""

from __future__ import annotations

import json
import resource
import sqlite3
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..domain.plan_operands import PlanRequest
from .compiler import request_digest as plan_request_digest
from .contracts import MAX_PAGE_LIMIT, canonical_json_bytes, canonical_json_value

PAGE_EXECUTOR_SCHEMA = "codex-usage-tracker.page-executor-benchmark.v2"
PAGE_EXECUTOR_VERSION = 2
SUPPORTED_DIRECT_PLAN_IDS = frozenset(
    {
        "data_health",
        "latest_publication_delta",
    }
)

_UNSUPPORTED_ORDERS = MappingProxyType(
    {
        "allowance_interval_events": "event_time_asc,event_kind_asc,logical_id_asc",
        "allowance_movement": "observation_time_asc,allowance_observation_id_asc",
        "cache_reuse_candidates": "total_input_tokens_desc,logical_id_asc",
        "context_pressure_trajectory": "context_pressure_desc,session_id_asc",
        "current_usage": "window_start_asc",
        "evidence_timeline": "event_time_asc,event_kind_asc,logical_id_asc",
        "first_action_mutation": "event_time_asc,logical_id_asc",
        "model_effort_mix": "total_tokens_desc,model_profile_id_asc",
        "parent_subagent_usage": "family_inclusive_tokens_desc,session_id_asc",
        "period_drivers": "absolute_contribution_desc,logical_id_asc",
        "pricing_coverage": "unpriced_tokens_desc,model_profile_id_asc",
        "project_family_usage": "total_tokens_desc,logical_id_asc",
        "resource_hotspots": "operation_count_desc,resource_id_asc",
        "tool_family_behavior": "calls_desc,tool_name_asc",
        "top_sessions": "total_tokens_desc,session_id_asc",
        "top_valued_entities": "configured_value_desc,logical_id_asc",
        "turn_completion_efficiency": "total_tokens_desc,session_id_asc",
        "uncached_input_jumps": "input_delta_desc,call_id_asc",
        "weekly_review": "section_order_asc,metric_order_asc,logical_id_asc",
    }
)


class PhysicalPageError(RuntimeError):
    """A physical page request is malformed or cannot execute safely."""


class PhysicalPlanGapError(PhysicalPageError):
    """A named plan has no admitted bounded direct-page implementation."""


@dataclass(frozen=True, slots=True)
class PageExecutionRequest:
    """The frozen CK-08R0 physical page request plus typed plan parameters."""

    plan_id: str
    plan_version: int
    publication_id: str
    request_digest: str
    complete_order: tuple[str, ...]
    page_size: int
    cursor_order: tuple[Any, ...] | None
    include_exact_count: bool = False
    parameters: Mapping[str, Any] = MappingProxyType({})

    def __post_init__(self) -> None:
        for label, value in (
            ("plan_id", self.plan_id),
            ("publication_id", self.publication_id),
            ("request_digest", self.request_digest),
        ):
            if not isinstance(value, str) or not value:
                raise PhysicalPageError(f"{label} must be non-empty text")
        if (
            len(self.request_digest) != 64
            or any(character not in "0123456789abcdef" for character in self.request_digest)
        ):
            raise PhysicalPageError("request_digest must be a lowercase SHA-256 digest")
        if (
            isinstance(self.plan_version, bool)
            or not isinstance(self.plan_version, int)
            or self.plan_version < 1
        ):
            raise PhysicalPageError("plan_version must be a positive integer")
        if (
            isinstance(self.page_size, bool)
            or not isinstance(self.page_size, int)
            or not 1 <= self.page_size <= MAX_PAGE_LIMIT
        ):
            raise PhysicalPageError(
                f"page_size must be between 1 and {MAX_PAGE_LIMIT}"
            )
        if (
            not isinstance(self.complete_order, tuple)
            or not self.complete_order
            or any(not isinstance(item, str) or not item for item in self.complete_order)
        ):
            raise PhysicalPageError("complete_order must be a non-empty tuple")
        if self.cursor_order is not None and not isinstance(self.cursor_order, tuple):
            raise PhysicalPageError("cursor_order must be a tuple or null")
        if not isinstance(self.include_exact_count, bool):
            raise PhysicalPageError("include_exact_count must be a boolean")
        if not isinstance(self.parameters, Mapping):
            raise PhysicalPageError("parameters must be a mapping")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class ExplainRow:
    """One stable SQLite EXPLAIN QUERY PLAN record."""

    select_id: int
    order: int
    from_id: int
    detail: str


@dataclass(frozen=True, slots=True)
class PageExecutionResult:
    """One bounded physical page plus stage-separated execution evidence."""

    rows: tuple[Mapping[str, Any], ...]
    returned_rows: int
    has_more: bool
    next_order: tuple[Any, ...] | None
    exact_count: int | None
    sql: str
    parameters: tuple[Any, ...]
    explain: tuple[ExplainRow, ...]
    stage_measurements: Mapping[str, float | int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stage_measurements",
            MappingProxyType(dict(self.stage_measurements)),
        )


@dataclass(frozen=True, slots=True)
class _BoundStatement:
    sql: str
    parameters: tuple[Any, ...]
    count_sql: str
    count_parameters: tuple[Any, ...]
    anchor_sql: str
    anchor_parameters: tuple[Any, ...]
    json_fields: tuple[str, ...]
    order_fields: tuple[str, ...]


def physical_gap(plan_id: str) -> str:
    """Return the exact fail-closed physical/index gap for an unsupported plan."""

    if plan_id == "resource_hotspots":
        return (
            "database-v1 resource indexes cannot satisfy complete "
            "operation_count_desc,resource_id_asc aggregate order without "
            "a complete scan and temporary sort"
        )
    order = _UNSUPPORTED_ORDERS.get(plan_id)
    if order is None:
        return "plan is not an admitted CK-08R2 direct-page candidate"
    return f"no R0-approved direct database-v1 binding for complete {order} order"


def _require_query_snapshot(connection: sqlite3.Connection) -> None:
    if not isinstance(connection, sqlite3.Connection):
        raise PhysicalPageError("page executor requires a SQLite connection")
    if not connection.in_transaction:
        raise PhysicalPageError("page executor requires one caller-owned read snapshot")
    row = connection.execute("PRAGMA query_only").fetchone()
    if row is None or int(row[0]) != 1:
        raise PhysicalPageError("page executor requires PRAGMA query_only=1")


def _bind_data_health(request: PageExecutionRequest) -> _BoundStatement:
    if request.complete_order != ("publication_committed_at_desc",):
        raise PhysicalPageError("data_health complete order does not match authority")
    allowed = {"as_of_us", "scope", "window"}
    unknown = set(request.parameters) - allowed
    if unknown:
        raise PhysicalPageError(f"data_health parameters are unsupported: {sorted(unknown)}")
    as_of_us = request.parameters.get("as_of_us")
    if isinstance(as_of_us, bool) or not isinstance(as_of_us, int):
        raise PhysicalPageError("data_health requires integer as_of_us")
    cursor_value: int | None = None
    if request.cursor_order is not None:
        if (
            len(request.cursor_order) != 1
            or isinstance(request.cursor_order[0], bool)
            or not isinstance(request.cursor_order[0], int)
        ):
            raise PhysicalPageError("data_health cursor order is malformed")
        cursor_value = request.cursor_order[0]
    sql = """
        SELECT p.committed_at_us AS _order_committed_at_us,
               (
                   SELECT json_group_object(
                       c.capability_id,
                       json(CASE WHEN c.observed_entity_count > 0
                                 THEN 'true' ELSE 'false' END)
                   )
                     FROM publication_capability_coverage AS c
                    WHERE c.publication_id = p.publication_id
               ) AS capabilities,
               ? - p.observed_through_us AS freshness_age_us,
               p.guaranteed_complete_from_us,
               p.indexed_from_us,
               (
                   SELECT json_group_object(e.entity_kind, e.entity_count)
                     FROM publication_entity_counts AS e
                    WHERE e.publication_id = p.publication_id
               ) AS measurements,
               json_object(
                   'basis', (
                       SELECT c.grade
                         FROM publication_capability_coverage AS c
                        WHERE c.publication_id = p.publication_id
                          AND c.capability_id = 'valuation'
                   ),
                   'priced_calls', (
                       SELECT c.eligible_entity_count - c.unavailable_entity_count
                         FROM publication_capability_coverage AS c
                        WHERE c.publication_id = p.publication_id
                          AND c.capability_id = 'valuation'
                   )
               ) AS valuation_coverage
          FROM publication_head AS h
          JOIN publications AS p ON p.publication_id = h.publication_id
         WHERE h.singleton = 1
           AND p.status = 'committed'
           AND p.publication_id = ?
           AND (? IS NULL OR p.committed_at_us < ?)
         ORDER BY p.committed_at_us DESC
         LIMIT ?
    """
    parameters = (
        as_of_us,
        request.publication_id,
        cursor_value,
        cursor_value,
        request.page_size + 1,
    )
    return _BoundStatement(
        sql=sql,
        parameters=parameters,
        count_sql=(
            "SELECT COUNT(*) FROM publication_head AS h "
            "JOIN publications AS p ON p.publication_id = h.publication_id "
            "WHERE h.singleton = 1 AND p.status = 'committed' "
            "AND p.publication_id = ?"
        ),
        count_parameters=(request.publication_id,),
        anchor_sql=(
            "SELECT 1 FROM publication_head AS h "
            "JOIN publications AS p ON p.publication_id = h.publication_id "
            "WHERE h.singleton = 1 AND p.status = 'committed' "
            "AND p.publication_id = ? AND p.committed_at_us = ?"
        ),
        anchor_parameters=(request.publication_id, cursor_value),
        json_fields=("capabilities", "measurements", "valuation_coverage"),
        order_fields=("_order_committed_at_us",),
    )


def _bind_latest_publication_delta(request: PageExecutionRequest) -> _BoundStatement:
    expected_order = ("change_kind_asc", "logical_id_asc")
    if request.complete_order != expected_order:
        raise PhysicalPageError(
            "latest_publication_delta complete order does not match authority"
        )
    if set(request.parameters) - {"entity_kind", "limit"}:
        raise PhysicalPageError("latest_publication_delta parameters are unsupported")
    # The accepted v1 derivation summarizes the publication-level delta and
    # does not filter that singleton for either optional catalog hint.
    cursor_kind: str | None = None
    cursor_id: str | None = None
    if request.cursor_order is not None:
        if (
            len(request.cursor_order) != 2
            or any(not isinstance(item, str) for item in request.cursor_order)
        ):
            raise PhysicalPageError("latest_publication_delta cursor order is malformed")
        cursor_kind, cursor_id = request.cursor_order
    logical_id = (
        "'publication-delta:' || substr("
        "d.publication_id, length('publication:') + 1)"
    )
    sql = f"""
        SELECT '' AS _order_change_kind,
               {logical_id} AS _order_logical_id,
               d.corrected_count,
               d.inserted_count,
               d.recanonicalized_count,
               d.removed_count,
               d.terminalized_count,
               COALESCE(d.uncached_input_token_delta, 0)
               + COALESCE(d.cached_input_token_delta, 0)
               + COALESCE(d.reasoning_token_delta, 0)
               + COALESCE(d.output_token_delta, 0) AS token_delta
          FROM publication_head AS h
          JOIN publication_deltas AS d ON d.publication_id = h.publication_id
         WHERE h.singleton = 1
           AND d.publication_id = ?
           AND (
               ? IS NULL
               OR '' > ?
               OR ('' = ? AND {logical_id} > ?)
           )
         ORDER BY _order_change_kind ASC, _order_logical_id ASC
         LIMIT ?
    """
    parameters = (
        request.publication_id,
        cursor_kind,
        cursor_kind,
        cursor_kind,
        cursor_id,
        request.page_size + 1,
    )
    return _BoundStatement(
        sql=sql,
        parameters=parameters,
        count_sql=(
            "SELECT COUNT(*) FROM publication_head AS h "
            "JOIN publication_deltas AS d ON d.publication_id = h.publication_id "
            "WHERE h.singleton = 1 AND d.publication_id = ?"
        ),
        count_parameters=(request.publication_id,),
        anchor_sql=(
            "SELECT 1 FROM publication_head AS h "
            "JOIN publication_deltas AS d ON d.publication_id = h.publication_id "
            "WHERE h.singleton = 1 AND d.publication_id = ? "
            f"AND '' = ? AND {logical_id} = ?"
        ),
        anchor_parameters=(request.publication_id, cursor_kind, cursor_id),
        json_fields=(),
        order_fields=("_order_change_kind", "_order_logical_id"),
    )


_BINDERS = MappingProxyType(
    {
        "data_health": _bind_data_health,
        "latest_publication_delta": _bind_latest_publication_delta,
    }
)


def _rss_bytes() -> int:
    rss = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return rss if sys.platform == "darwin" else rss * 1024


def _explain(
    connection: sqlite3.Connection,
    sql: str,
    parameters: Sequence[Any],
) -> tuple[ExplainRow, ...]:
    return tuple(
        ExplainRow(int(row[0]), int(row[1]), int(row[2]), str(row[3]))
        for row in connection.execute("EXPLAIN QUERY PLAN " + sql, tuple(parameters))
    )


def _decode_row(
    row: sqlite3.Row | Sequence[Any],
    columns: Sequence[str],
    json_fields: frozenset[str],
) -> tuple[dict[str, Any], tuple[Any, ...]]:
    raw = dict(zip(columns, tuple(row), strict=True))
    order = tuple(raw.pop(name) for name in columns if name.startswith("_order_"))
    for field in json_fields:
        value = raw.get(field)
        if not isinstance(value, str):
            raise PhysicalPageError(f"{field} must be encoded canonical JSON")
        decoded = json.loads(value)
        if not isinstance(decoded, Mapping):
            raise PhysicalPageError(f"{field} must decode to an object")
        raw[field] = decoded
    return canonical_json_value(raw), tuple(
        canonical_json_value(value) for value in order
    )


class PhysicalPageExecutor:
    """Execute only R2-supported direct plans from one query-only snapshot."""

    def execute(
        self,
        connection: sqlite3.Connection,
        request: PageExecutionRequest,
        plan_request: PlanRequest,
    ) -> PageExecutionResult:
        _require_query_snapshot(connection)
        if not isinstance(request, PageExecutionRequest):
            raise PhysicalPageError("page request must be PageExecutionRequest")
        if not isinstance(plan_request, PlanRequest) or plan_request.plan_id != request.plan_id:
            raise PhysicalPageError("typed plan request does not match page request")
        if plan_request_digest(plan_request) != request.request_digest:
            raise PhysicalPageError("typed plan request digest does not match page request")
        if canonical_json_value(request.parameters) != canonical_json_value(
            plan_request.parameters
        ):
            raise PhysicalPageError(
                "page request parameters do not match typed plan request"
            )
        binder = _BINDERS.get(request.plan_id)
        if binder is None:
            raise PhysicalPlanGapError(
                f"physical_plan_unimplemented: plan_id={request.plan_id}; "
                f"gap={physical_gap(request.plan_id)}; projection_added=false"
            )

        bind_started = time.perf_counter_ns()
        statement = binder(request)
        explain = _explain(connection, statement.sql, statement.parameters)
        bind_ms = (time.perf_counter_ns() - bind_started) / 1_000_000

        sql_started = time.perf_counter_ns()
        if request.cursor_order is not None:
            anchor = connection.execute(
                statement.anchor_sql,
                statement.anchor_parameters,
            ).fetchone()
            if anchor is None:
                raise PhysicalPageError(
                    "cursor key is stale or replaced; restart from the first page"
                )
        cursor = connection.execute(statement.sql, statement.parameters)
        columns = tuple(item[0] for item in cursor.description or ())
        encoded_rows = cursor.fetchmany(request.page_size + 1)
        exact_count = None
        if request.include_exact_count:
            count_row = connection.execute(
                statement.count_sql,
                statement.count_parameters,
            ).fetchone()
            if count_row is None:
                raise PhysicalPageError("exact count query returned no row")
            exact_count = int(count_row[0])
        sql_ms = (time.perf_counter_ns() - sql_started) / 1_000_000

        decode_started = time.perf_counter_ns()
        decoded = tuple(
            _decode_row(row, columns, frozenset(statement.json_fields))
            for row in encoded_rows
        )
        decode_ms = (time.perf_counter_ns() - decode_started) / 1_000_000

        assembly_started = time.perf_counter_ns()
        has_more = len(decoded) > request.page_size
        selected = decoded[: request.page_size]
        rows = tuple(item[0] for item in selected)
        next_order = selected[-1][1] if has_more and selected else None
        assembly_ms = (time.perf_counter_ns() - assembly_started) / 1_000_000

        serialization_started = time.perf_counter_ns()
        response_bytes = len(
            canonical_json_bytes(
                {
                    "exact_count": exact_count,
                    "has_more": has_more,
                    "next_order": next_order,
                    "rows": rows,
                }
            )
        )
        serialization_ms = (
            time.perf_counter_ns() - serialization_started
        ) / 1_000_000
        measurements: dict[str, float | int] = {
            "request_bind_ms": bind_ms,
            "sql_execute_ms": sql_ms,
            "row_decode_ms": decode_ms,
            "result_assembly_ms": assembly_ms,
            "serialize_ms": serialization_ms,
            "response_bytes": response_bytes,
            "rows_examined": len(encoded_rows),
            "rows_decoded": len(decoded),
            "peak_rss_bytes": _rss_bytes(),
        }
        return PageExecutionResult(
            rows=rows,
            returned_rows=len(rows),
            has_more=has_more,
            next_order=next_order,
            exact_count=exact_count,
            sql=statement.sql,
            parameters=statement.parameters,
            explain=explain,
            stage_measurements=measurements,
        )


__all__ = [
    "ExplainRow",
    "PAGE_EXECUTOR_SCHEMA",
    "PAGE_EXECUTOR_VERSION",
    "PageExecutionRequest",
    "PageExecutionResult",
    "PhysicalPageError",
    "PhysicalPageExecutor",
    "PhysicalPlanGapError",
    "SUPPORTED_DIRECT_PLAN_IDS",
    "physical_gap",
]
