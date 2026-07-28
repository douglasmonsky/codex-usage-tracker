"""Typed adapter-independent query request and response contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any

MAX_BATCH_QUERIES = 8
MAX_DIMENSIONS = 3
MAX_FILTERS = 8
MAX_LIMIT = 500
MAX_MEASURES = 8
MAX_CURSOR_OFFSET = 1_000_000
MAX_QUERY_RESPONSE_BYTES = 1_000_000


class Operation(str, Enum):
    ROWS = "rows"
    AGGREGATE = "aggregate"
    SHARE = "share"
    COMPARISON = "comparison"
    DISTRIBUTION = "distribution"
    TIME_SERIES = "time_series"
    TIMELINE = "timeline"


@dataclass(frozen=True)
class Filter:
    field: str
    operator: str
    value: str | int | float | tuple[str | int | float, ...]

    def normalized(self) -> Filter:
        field = self.field.strip().lower()
        operator = self.operator.strip().lower()
        if not field or operator not in {"eq", "in", "gte", "gt", "lte", "lt"}:
            raise ValueError("query filter is not allowlisted")
        value = self.value
        if operator == "in":
            if not isinstance(value, tuple) or not value or len(value) > 25:
                raise ValueError("in filter requires 1 to 25 values")
            value = tuple(sorted(set(value), key=str))
        elif isinstance(value, tuple):
            raise ValueError("scalar filter cannot use multiple values")
        return Filter(field, operator, value)


@dataclass(frozen=True)
class ComparisonWindow:
    """Two explicit half-open periods used by a comparison plan."""

    current_start: str
    current_end: str
    previous_start: str
    previous_end: str

    def normalized(self) -> ComparisonWindow:
        values = tuple(
            value.strip()
            for value in (
                self.current_start,
                self.current_end,
                self.previous_start,
                self.previous_end,
            )
        )
        parsed = tuple(_timestamp(value) for value in values)
        current_start, current_end, previous_start, previous_end = parsed
        if current_start >= current_end or previous_start >= previous_end:
            raise ValueError("comparison windows must have positive duration")
        if max(current_start, previous_start) < min(current_end, previous_end):
            raise ValueError("comparison windows must not overlap")
        canonical = tuple(_utc_timestamp(value) for value in parsed)
        return ComparisonWindow(*canonical)


@dataclass(frozen=True)
class QueryRequest:
    dataset: str
    operation: Operation | str
    dimensions: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    filters: tuple[Filter, ...] = ()
    order_by: str | None = None
    descending: bool = True
    limit: int = 100
    cursor: str | None = None
    comparison: ComparisonWindow | None = None
    allow_partial: bool = False

    def normalized(self) -> QueryRequest:
        from .catalog import validate_request

        try:
            operation = Operation(self.operation)
        except ValueError as exc:
            raise ValueError("query operation is not allowlisted") from exc
        dimensions = _unique_names(self.dimensions, "dimension", MAX_DIMENSIONS)
        measures = _unique_names(self.measures, "measure", MAX_MEASURES)
        if not 1 <= self.limit <= MAX_LIMIT:
            raise ValueError(f"query limit must be between 1 and {MAX_LIMIT}")
        if len(self.filters) > MAX_FILTERS:
            raise ValueError(f"query supports at most {MAX_FILTERS} filters")
        filters = tuple(
            sorted(
                (item.normalized() for item in self.filters),
                key=lambda item: (item.field, item.operator, repr(item.value)),
            )
        )
        order_by = self.order_by.strip().lower() if self.order_by else None
        comparison = self.comparison.normalized() if self.comparison else None
        normalized = replace(
            self,
            dataset=self.dataset.strip().lower(),
            operation=operation,
            dimensions=dimensions,
            measures=measures,
            filters=filters,
            order_by=order_by,
            cursor=self.cursor.strip() if self.cursor else None,
            comparison=comparison,
        )
        validate_request(normalized)
        return normalized


@dataclass(frozen=True)
class QueryResult:
    plan_id: str
    plan_version: int
    generation: int
    dataset: str
    operation: str
    normalized_scope: dict[str, Any]
    rows: tuple[dict[str, Any], ...]
    matched_count: int
    returned_count: int
    scanned_count: int | None
    truncated: bool
    next_cursor: str | None
    elapsed_ms: float
    grade: str
    coverage: dict[str, Any]
    evidence_selectors: tuple[str, ...]


def _unique_names(
    values: tuple[str, ...],
    label: str,
    maximum: int,
) -> tuple[str, ...]:
    normalized = tuple(sorted({value.strip().lower() for value in values}))
    if any(not value for value in normalized):
        raise ValueError(f"query {label} cannot be empty")
    if len(normalized) > maximum:
        raise ValueError(f"query supports at most {maximum} {label}s")
    return normalized


def _timestamp(value: str) -> datetime:
    if not value:
        raise ValueError("comparison timestamp cannot be empty")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("comparison timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("comparison timestamp must include a timezone")
    return parsed


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
