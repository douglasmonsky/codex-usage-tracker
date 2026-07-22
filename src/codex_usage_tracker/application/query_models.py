"""Typed canonical query models and immutable allowlist capabilities."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, TypeAlias

from codex_usage_tracker.application.errors import RequestValidationError

QueryEntity: TypeAlias = Literal[
    "call", "thread", "project", "model", "effort", "origin", "service_tier", "subagent"
]
QueryMeasure: TypeAlias = Literal[
    "tokens",
    "uncached_tokens",
    "cached_tokens",
    "output_tokens",
    "reasoning_tokens",
    "estimated_cost",
    "estimated_credits",
    "call_count",
    "duration",
    "cache_ratio",
    "context_pressure",
]
QueryOrder: TypeAlias = Literal["asc", "desc"]
HistoryScope: TypeAlias = Literal["active", "all"]

ALL_QUERY_MEASURES: frozenset[str] = frozenset(
    {
        "tokens",
        "uncached_tokens",
        "cached_tokens",
        "output_tokens",
        "reasoning_tokens",
        "estimated_cost",
        "estimated_credits",
        "call_count",
        "duration",
        "cache_ratio",
        "context_pressure",
    }
)


@dataclass(frozen=True)
class QueryEntityCapability:
    measures: frozenset[str]
    group_by: frozenset[str]
    identity: str


def _capability(identity: str, *group_by: str) -> QueryEntityCapability:
    return QueryEntityCapability(ALL_QUERY_MEASURES, frozenset(group_by), identity)


QUERY_ENTITY_CAPABILITIES: Mapping[str, QueryEntityCapability] = MappingProxyType(
    {
        "call": QueryEntityCapability(
            ALL_QUERY_MEASURES - {"call_count"}, frozenset(), "record_id"
        ),
        "thread": _capability("thread", "model", "effort", "origin", "service_tier", "subagent"),
        "project": _capability("project", "model", "effort", "origin", "service_tier", "subagent"),
        "model": _capability("model", "effort", "origin", "service_tier", "subagent"),
        "effort": _capability("effort", "model", "origin", "service_tier", "subagent"),
        "origin": _capability("origin", "model", "effort", "service_tier", "subagent"),
        "service_tier": _capability("service_tier", "model", "effort", "origin", "subagent"),
        "subagent": _capability(
            "subagent", "model", "effort", "origin", "service_tier", "subagent_type"
        ),
    }
)


@dataclass(frozen=True)
class QueryFilters:
    since: str | None = None
    until: str | None = None
    range: str | None = None
    model: str | None = None
    effort: str | None = None
    thread_key: str | None = None
    project: str | None = None
    origin: str | None = None
    service_tier: str | None = None
    subagent_role: str | None = None
    subagent_type: str | None = None
    parent_thread_key: str | None = None


@dataclass(frozen=True)
class QueryRequest:
    entity: QueryEntity
    measures: tuple[QueryMeasure, ...]
    filters: QueryFilters = field(default_factory=QueryFilters)
    group_by: tuple[str, ...] = ()
    order_by: str | None = None
    order: QueryOrder = "desc"
    limit: int = 20
    cursor: str | None = None
    history: HistoryScope = "active"

    def __post_init__(self) -> None:
        if not str(self.entity).strip():
            raise RequestValidationError("entity must not be empty")
        if not self.measures:
            raise RequestValidationError("measures must not be empty")
        if type(self.limit) is not int:
            raise RequestValidationError("limit must be an integer")
        if not 1 <= self.limit <= 200:
            raise RequestValidationError("limit must be between 1 and 200")
        if self.order not in {"asc", "desc"}:
            raise RequestValidationError(f"unsupported order: {self.order}")
        if self.history not in {"active", "all"}:
            raise RequestValidationError(f"unsupported history: {self.history}")
        object.__setattr__(self, "measures", tuple(self.measures))
        object.__setattr__(self, "group_by", tuple(self.group_by))


@dataclass(frozen=True)
class DashboardTargetV2:
    view: str
    arguments: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryResult:
    schema: Literal["codex-usage-tracker.query.v2"] = field(
        default="codex-usage-tracker.query.v2", init=False
    )
    entity: QueryEntity
    columns: tuple[str, ...]
    rows: tuple[dict[str, object], ...]
    next_cursor: str | None
    total_matched: int | None
    dashboard_target: DashboardTargetV2 | None
