"""Generation-bound read-only execution for single and batched queries."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from ..content import open_content_snapshot
from ..database import open_read_snapshot
from ..operational import load_cutover_control
from .contracts import (
    MAX_BATCH_QUERIES,
    MAX_CURSOR_OFFSET,
    Operation,
    QueryRequest,
    QueryResult,
)
from .phases import ActivityFact, TokenFact, attribute_tokens, segment_phases
from .plans import PLAN_VERSION, compile_plan


class QueryService:
    """Execute bounded requests without initiating refresh or writes."""

    def __init__(
        self,
        operational_path: Path,
        *,
        content_path: Path | None = None,
    ) -> None:
        self._operational_path = operational_path.resolve()
        self._content_path = content_path.resolve() if content_path else None

    def execute(self, request: QueryRequest) -> QueryResult:
        return self.execute_batch((request,))[0]

    def execute_batch(
        self,
        requests: tuple[QueryRequest, ...],
    ) -> tuple[QueryResult, ...]:
        if not 1 <= len(requests) <= MAX_BATCH_QUERIES:
            raise ValueError(f"query batch must contain 1 to {MAX_BATCH_QUERIES} items")
        normalized = tuple(request.normalized() for request in requests)
        control = load_cutover_control(self._operational_path)
        path = control.active_kernel_path
        generation = control.active_generation
        if path is None or generation is None:
            raise ValueError("no active analytical generation")
        with ExitStack() as stack:
            analytical = stack.enter_context(open_read_snapshot(path))
            analytical.execute("PRAGMA query_only = ON")
            content = (
                stack.enter_context(open_content_snapshot(self._content_path))
                if any(request.dataset == "context" for request in normalized)
                and self._content_path is not None
                else None
            )
            if any(request.dataset == "context" for request in normalized) and (
                content is None
            ):
                raise ValueError("context composition database is not configured")
            results: list[QueryResult] = []
            for request in normalized:
                connection = (
                    content if request.dataset == "context" else analytical
                )
                if connection is None:
                    raise ValueError(
                        "context composition database is not configured"
                    )
                results.append(
                    self._execute_one(connection, request, generation)
                )
            return tuple(results)

    def _execute_one(
        self,
        connection: sqlite3.Connection,
        request: QueryRequest,
        generation: int,
    ) -> QueryResult:
        started = time.perf_counter()
        request_hash = _request_hash(request)
        offset = _decode_cursor(
            request.cursor,
            generation=generation,
            request_hash=request_hash,
            limit=request.limit,
        )
        if request.dataset == "phases":
            rows, matched, scanned = _phase_rows(
                connection,
                generation,
                request,
                offset,
            )
            plan_id = (
                f"phases.{Operation(request.operation).value}.v{PLAN_VERSION}"
            )
            coverage_counts: dict[str, int] = {}
        else:
            plan = compile_plan(request, generation=generation, offset=offset)
            raw_rows = connection.execute(plan.sql, plan.parameters).fetchall()
            if raw_rows:
                matched = int(raw_rows[0]["__matched_count"])
                scanned = int(raw_rows[0]["__scanned_count"])
            else:
                matched = int(
                    connection.execute(
                        plan.count_sql,
                        plan.count_parameters,
                    ).fetchone()[0]
                )
                scanned = int(
                    connection.execute(
                        plan.scan_sql,
                        plan.scan_parameters,
                    ).fetchone()[0]
                )
            coverage_counts = (
                {
                    key: int(value or 0)
                    for key, value in dict(
                        connection.execute(
                            plan.coverage_sql,
                            plan.coverage_parameters,
                        ).fetchone()
                    ).items()
                }
                if plan.coverage_sql
                else {}
            )
            rows = [
                {
                    key: value
                    for key, value in dict(row).items()
                    if not key.startswith("__")
                }
                for row in raw_rows
            ]
            plan_id = plan.plan_id
        truncated = len(rows) > request.limit
        returned = rows[: request.limit]
        next_cursor = (
            _encode_cursor(
                generation=generation,
                request_hash=request_hash,
                offset=offset + request.limit,
            )
            if truncated
            else None
        )
        selectors = _selectors(request.dataset, returned)
        grade, coverage = _result_coverage(
            request,
            generation=generation,
            scanned=scanned,
            matched=matched,
            counts=coverage_counts,
            content_metadata=(
                _content_metadata(connection)
                if request.dataset == "context"
                else None
            ),
        )
        return QueryResult(
            plan_id=plan_id,
            plan_version=PLAN_VERSION,
            generation=generation,
            dataset=request.dataset,
            operation=Operation(request.operation).value,
            normalized_scope={
                "dimensions": list(request.dimensions),
                "measures": list(request.measures),
                "filters": [
                    {
                        "field": item.field,
                        "operator": item.operator,
                        "value": item.value,
                    }
                    for item in request.filters
                ],
                "limit": request.limit,
                "offset": offset,
                "comparison": (
                    {
                        "current_start": request.comparison.current_start,
                        "current_end": request.comparison.current_end,
                        "previous_start": request.comparison.previous_start,
                        "previous_end": request.comparison.previous_end,
                    }
                    if request.comparison
                    else None
                ),
            },
            rows=tuple(returned),
            matched_count=matched,
            returned_count=len(returned),
            scanned_count=scanned,
            truncated=truncated,
            next_cursor=next_cursor,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            grade=grade,
            coverage=coverage,
            evidence_selectors=selectors,
        )


def _phase_rows(
    connection: sqlite3.Connection,
    generation: int,
    request: QueryRequest,
    offset: int,
) -> tuple[list[dict[str, Any]], int, int]:
    activity_scope, activity_parameters = _phase_scope(
        request,
        turn_sql="COALESCE(turns.source_turn_id_hash, activity_events.turn_id)",
        time_sql="activity_events.event_at",
    )
    activity_facts = [
        ActivityFact(
            event_at=str(row["event_at"]),
            event_kind=str(row["event_kind"]),
            turn_id=row["logical_turn_id"],
            thread_id=row["logical_thread_id"],
            activity_event_id=str(row["activity_event_id"]),
            safe_label=row["safe_label"],
        )
        for row in connection.execute(
            """
            SELECT activity_events.activity_event_id,
                   activity_events.event_at,
                   activity_events.event_kind,
                   activity_events.safe_label,
                   COALESCE(
                       turns.source_turn_id_hash,
                       activity_events.turn_id
                   ) AS logical_turn_id,
                   threads.logical_thread_id
            FROM activity_events
            JOIN threads USING (thread_id)
            LEFT JOIN turns ON turns.turn_id = activity_events.turn_id
            WHERE activity_events.generation <= ?
              AND """
            + activity_scope
            + """
            ORDER BY activity_events.event_at,
                     activity_events.activity_event_id
            """,
            (generation, *activity_parameters),
        )
    ]
    turn_scope, turn_parameters = _phase_scope(
        request,
        turn_sql="COALESCE(turns.source_turn_id_hash, turns.turn_id)",
        time_sql="turns.started_at",
    )
    turn_facts = [
        ActivityFact(
            event_at=str(row["started_at"]),
            event_kind="user_input",
            turn_id=str(row["logical_turn_id"]),
            thread_id=row["logical_thread_id"],
            activity_event_id=f"turn:{row['logical_turn_id']}",
        )
        for row in connection.execute(
            """
            SELECT COALESCE(
                       turns.source_turn_id_hash,
                       turns.turn_id
                   ) AS logical_turn_id,
                   turns.started_at,
                   threads.logical_thread_id
            FROM turns
            JOIN threads USING (thread_id)
            WHERE turns.first_generation <= ?
              AND turns.started_at IS NOT NULL
              AND """
            + turn_scope,
            (generation, *turn_parameters),
        )
    ]
    tool_scope, tool_parameters = _phase_scope(
        request,
        turn_sql="COALESCE(turns.source_turn_id_hash, tool_calls.turn_id)",
        time_sql="tool_calls.started_at",
    )
    tool_facts = [
        ActivityFact(
            event_at=str(row["started_at"]),
            event_kind="tool",
            turn_id=row["logical_turn_id"],
            thread_id=row["logical_thread_id"],
            activity_event_id=f"tool:{row['tool_call_id']}",
            safe_label=str(row["tool_name"]),
        )
        for row in connection.execute(
            """
            SELECT tool_calls.tool_call_id,
                   tool_calls.started_at,
                   tool_calls.tool_name,
                   COALESCE(
                       turns.source_turn_id_hash,
                       tool_calls.turn_id
                   ) AS logical_turn_id,
                   threads.logical_thread_id
            FROM tool_calls
            JOIN threads USING (thread_id)
            LEFT JOIN turns ON turns.turn_id = tool_calls.turn_id
            WHERE tool_calls.generation <= ?
              AND tool_calls.started_at IS NOT NULL
              AND """
            + tool_scope,
            (generation, *tool_parameters),
        )
    ]
    token_scope, token_parameters = _phase_scope(
        request,
        turn_sql="COALESCE(turns.source_turn_id_hash, model_calls.turn_id)",
        time_sql="model_calls.event_at",
    )
    token_facts = tuple(
        TokenFact(
            event_at=str(row["event_at"]),
            turn_id=row["logical_turn_id"],
            thread_id=row["logical_thread_id"],
            input_tokens=int(row["input_tokens"]),
            cached_input_tokens=int(row["cached_input_tokens"]),
            reasoning_tokens=int(row["reasoning_tokens"]),
            output_tokens=int(row["output_tokens"]),
        )
        for row in connection.execute(
            """
            SELECT model_calls.event_at,
                   COALESCE(
                       turns.source_turn_id_hash,
                       model_calls.turn_id
                   ) AS logical_turn_id,
                   threads.logical_thread_id,
                   model_calls.input_tokens,
                   model_calls.cached_input_tokens,
                   model_calls.reasoning_tokens,
                   model_calls.output_tokens
            FROM model_calls
            JOIN threads USING (thread_id)
            LEFT JOIN turns ON turns.turn_id = model_calls.turn_id
            WHERE model_calls.generation <= ?
              AND model_calls.duplicate_state = 'canonical'
              AND """
            + token_scope,
            (generation, *token_parameters),
        )
    )
    activity_facts.extend(turn_facts)
    activity_facts.extend(tool_facts)
    segments = attribute_tokens(
        segment_phases(tuple(activity_facts)),
        token_facts,
    )
    rows = [
        {
            "phase": segment.category,
            "thread": segment.thread_id,
            "turn": segment.turn_id,
            "activities": segment.activity_count,
            "started_at": segment.started_at,
            "ended_at": segment.ended_at,
            "basis": segment.basis,
            "confidence": segment.confidence,
            "segmenter_version": segment.segmenter_version,
            "input_tokens": segment.input_tokens,
            "uncached_input_tokens": segment.uncached_input_tokens,
            "cached_input_tokens": segment.cached_input_tokens,
            "reasoning_tokens": segment.reasoning_tokens,
            "output_tokens": segment.output_tokens,
            "total_tokens": segment.total_tokens,
            "token_attribution": segment.token_attribution,
        }
        for segment in segments
    ]
    ordered = _order_phase_rows(rows, request)
    page = ordered[offset : offset + request.limit + 1]
    projected = [_project_phase_row(row, request) for row in page]
    return projected, len(segments), len(activity_facts) + len(token_facts)


def _order_phase_rows(
    rows: list[dict[str, Any]],
    request: QueryRequest,
) -> list[dict[str, Any]]:
    stable = sorted(
        rows,
        key=lambda row: (
            str(row["started_at"]),
            str(row.get("thread") or ""),
            str(row.get("turn") or ""),
            str(row["phase"]),
        ),
    )
    order_by = request.order_by or (
        "event_at"
        if request.operation is Operation.TIMELINE
        else request.measures[0]
        if request.measures
        else request.dimensions[0]
        if request.dimensions
        else "event_at"
    )
    source_field = "started_at" if order_by == "event_at" else order_by
    return sorted(
        stable,
        key=lambda row: _phase_sort_key(row.get(source_field)),
        reverse=request.descending,
    )


def _phase_sort_key(value: Any) -> tuple[int, float, str]:
    if isinstance(value, (int, float)):
        return (0, float(value), "")
    if value is None:
        return (2, 0.0, "")
    return (1, 0.0, str(value))


def _project_phase_row(
    row: dict[str, Any],
    request: QueryRequest,
) -> dict[str, Any]:
    projected = {
        name: row["started_at"] if name == "event_at" else row[name]
        for name in (*request.dimensions, *request.measures)
    }
    projected.update(
        {
            "basis": row["basis"],
            "confidence": row["confidence"],
            "segmenter_version": row["segmenter_version"],
            "token_attribution": row["token_attribution"],
        }
    )
    return projected


def _result_coverage(
    request: QueryRequest,
    *,
    generation: int,
    scanned: int,
    matched: int,
    counts: dict[str, int],
    content_metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    total = matched if request.dataset == "phases" else scanned
    measures: dict[str, dict[str, Any]] = {}
    partial = False
    for measure in request.measures:
        observed = counts.get(f"observed_{measure}", total)
        missing = counts.get(f"missing_{measure}", 0)
        partial = partial or missing > 0
        measures[measure] = {
            "basis": _measure_basis(request.dataset, measure),
            "observed_count": observed,
            "missing_count": missing,
            "coverage_percent": (
                100.0 if total == 0 else 100.0 * observed / total
            ),
            "limitations": _measure_limitations(request.dataset, measure),
        }
        if request.dataset == "context" and measure == "estimated_tokens":
            measures[measure]["estimator"] = (
                content_metadata.get("estimator")
                if content_metadata is not None
                else None
            )
    grade = (
        "deterministic"
        if request.dataset == "phases"
        else "estimated"
        if request.dataset == "context"
        and "estimated_tokens" in request.measures
        and not partial
        else "partial"
        if partial
        else "exact"
    )
    coverage: dict[str, Any] = {
        "generation_bound": True,
        "canonical_calls_only": request.dataset == "calls",
        "raw_content": False,
        "phase_attribution": (
            "deterministic" if request.dataset == "phases" else None
        ),
        "measures": measures,
    }
    if request.dataset == "context":
        source_generation = (
            content_metadata.get("indexed_generation")
            if content_metadata is not None
            else None
        )
        coverage.update(
            {
                "observed_content_only": True,
                "source_generation": source_generation,
                "observed_through": (
                    content_metadata.get("observed_through")
                    if content_metadata is not None
                    else None
                ),
                "generation_lag": (
                    generation - source_generation
                    if isinstance(source_generation, int)
                    else None
                ),
                "unattributed_input_tokens": None,
                "unattributed_limitation": (
                    "billed input tokens cannot be safely attributed to "
                    "observed categories"
                ),
            }
        )
    return grade, coverage


def _measure_basis(dataset: str, measure: str) -> str:
    if dataset == "phases":
        return "deterministic_attribution"
    if dataset == "context" and measure == "observed_bytes":
        return "exact_observed_utf8_bytes"
    if dataset == "context" and measure == "estimated_tokens":
        return "tokenizer_estimate"
    if measure in {"uncached_input_tokens", "total_tokens"}:
        return "derived_exact"
    if measure in {
        "allowance_delta_percent",
        "allowance_burn_rate",
        "local_tokens_per_percentage_point",
        "local_calls_per_percentage_point",
        "local_turns_per_percentage_point",
    }:
        return "deterministic_adjacent_observations"
    if measure in {"cache_reuse", "context_pressure"}:
        return "derived_ratio"
    if measure in {"duration_ms", "output_bytes"}:
        return "upstream_observed"
    if measure in {
        "aborts",
        "activities",
        "allowance_observations",
        "calls",
        "compactions",
        "completions",
        "events",
        "threads",
        "tools",
        "turns",
    }:
        return "exact_count"
    return "upstream_reported"


def _measure_limitations(dataset: str, measure: str) -> list[str]:
    limitations: list[str] = []
    if dataset == "context" and measure == "observed_bytes":
        limitations.append(
            "observed payload bytes are not exact billed input tokens"
        )
    if dataset == "context" and measure == "estimated_tokens":
        limitations.append(
            "category tokens are estimates only when an explicit tokenizer is configured"
        )
    if measure == "reasoning_tokens":
        limitations.append(
            "reasoning tokens are reported separately; overlap with output "
            "tokens is not inferred"
        )
    if dataset == "phases" and measure != "activities":
        limitations.append(
            "tokens are assigned to the preceding or enclosing phase "
            "deterministically, not upstream-exact"
        )
    if measure in {"duration_ms", "output_bytes", "context_pressure"}:
        limitations.append("null upstream observations are excluded")
    if measure in {
        "allowance_delta_percent",
        "allowance_burn_rate",
        "local_tokens_per_percentage_point",
        "local_calls_per_percentage_point",
        "local_turns_per_percentage_point",
    }:
        limitations.extend(
            (
                "ratios require adjacent observations from one reset window",
                "locally observed usage is not causal billing attribution",
            )
        )
    return limitations


def _content_metadata(connection: sqlite3.Connection) -> dict[str, Any]:
    settings = connection.execute(
        """
        SELECT indexed_generation, estimator_id
        FROM content_settings
        WHERE singleton = 1
        """
    ).fetchone()
    observed = connection.execute(
        "SELECT MAX(event_at) FROM composition_events"
    ).fetchone()
    return {
        "indexed_generation": settings[0] if settings is not None else None,
        "estimator": (
            str(settings[1])
            if settings is not None and settings[1] is not None
            else None
        ),
        "observed_through": observed[0] if observed is not None else None,
    }


def _phase_scope(
    request: QueryRequest,
    *,
    turn_sql: str,
    time_sql: str,
) -> tuple[str, tuple[Any, ...]]:
    operators = {
        "eq": "=",
        "gte": ">=",
        "gt": ">",
        "lte": "<=",
        "lt": "<",
    }
    fields = {
        "thread": "threads.logical_thread_id",
        "turn": turn_sql,
        "event_at": time_sql,
    }
    clauses: list[str] = []
    parameters: list[Any] = []
    for item in request.filters:
        expression = fields[item.field]
        parameter_sql = "?"
        if item.field == "event_at":
            expression = f"julianday({expression})"
            parameter_sql = "julianday(?)"
        if item.operator == "in":
            values = item.value
            assert isinstance(values, tuple)
            clauses.append(
                f"{expression} IN "
                f"({', '.join(parameter_sql for _ in values)})"
            )
            parameters.extend(values)
        else:
            clauses.append(
                f"{expression} {operators[item.operator]} {parameter_sql}"
            )
            parameters.append(item.value)
    return " AND ".join(f"({clause})" for clause in clauses), tuple(parameters)


def _request_hash(request: QueryRequest) -> str:
    payload = {
        "dataset": request.dataset,
        "operation": Operation(request.operation).value,
        "dimensions": request.dimensions,
        "measures": request.measures,
        "filters": [
            (item.field, item.operator, item.value) for item in request.filters
        ],
        "order_by": request.order_by,
        "descending": request.descending,
        "limit": request.limit,
        "comparison": (
            (
                request.comparison.current_start,
                request.comparison.current_end,
                request.comparison.previous_start,
                request.comparison.previous_end,
            )
            if request.comparison
            else None
        ),
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _encode_cursor(*, generation: int, request_hash: str, offset: int) -> str:
    payload = json.dumps(
        {"g": generation, "h": request_hash, "o": offset},
        sort_keys=True,
        separators=(",", ":"),
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
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if (
            payload["g"] != generation
            or payload["h"] != request_hash
            or not isinstance(payload["o"], int)
            or payload["o"] < 0
            or payload["o"] > MAX_CURSOR_OFFSET - limit
        ):
            raise ValueError
        return int(payload["o"])
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("query cursor does not match request generation") from exc


def _selectors(
    dataset: str,
    rows: list[dict[str, Any]],
) -> tuple[str, ...]:
    fields = {
        "calls": (("call", "call"), ("thread", "thread"), ("turn", "turn")),
        "threads": (("thread", "thread"),),
        "turns": (("turn", "turn"), ("thread", "thread")),
        "tools": (
            ("tool_call", "tool"),
            ("thread", "thread"),
            ("turn", "turn"),
        ),
        "allowance": (("allowance", "allowance"),),
        "phases": (("thread", "thread"), ("turn", "turn")),
        "activities": (("thread", "thread"), ("turn", "turn")),
    }.get(dataset, ())
    selectors: list[str] = []
    for row in rows:
        for field, selector_kind in fields:
            value = row.get(field)
            selector = f"{selector_kind}:{value}" if value is not None else None
            if selector is not None and selector not in selectors:
                selectors.append(selector)
    return tuple(selectors)
