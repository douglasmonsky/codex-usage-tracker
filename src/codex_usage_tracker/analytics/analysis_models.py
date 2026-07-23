"""Typed request, estimate, and result models for usage analysis strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias, cast, get_args

from codex_usage_tracker.core.contracts import (
    AccountingContextV1,
    EvidenceV1,
    FindingV1,
    MessageV1,
)

if TYPE_CHECKING:
    from codex_usage_tracker.application.query_models import QueryFilters
    from codex_usage_tracker.application.requests import ExecutionMode, HistoryScope

AnalysisGoal: TypeAlias = Literal[
    "usage_spike",
    "token_waste",
    "context_bloat",
    "cache_failure",
    "subagent_cost",
    "fast_usage",
    "pricing_gaps",
    "thread_comparison",
    "model_effort_mix",
    "workflow_churn",
]
ANALYSIS_GOALS = cast(tuple[AnalysisGoal, ...], get_args(AnalysisGoal))


@dataclass(frozen=True)
class ComparisonWindow:
    since: str
    until: str

    def __post_init__(self) -> None:
        if not isinstance(self.since, str) or not isinstance(self.until, str):
            raise _request_validation_error("comparison window bounds must be strings")
        from codex_usage_tracker.application.query_validation import normalize_timestamp_window

        since, until = normalize_timestamp_window(
            self.since, self.until, field_prefix="comparison."
        )
        object.__setattr__(self, "since", cast(str, since))
        object.__setattr__(self, "until", cast(str, until))


def _query_filters_factory() -> QueryFilters:
    from codex_usage_tracker.application.query_models import QueryFilters

    return QueryFilters()


def _request_validation_error(message: str) -> ValueError:
    from codex_usage_tracker.application.errors import RequestValidationError

    return RequestValidationError(message)


@dataclass(frozen=True)
class AnalysisRequest:
    goal: AnalysisGoal
    filters: QueryFilters = field(default_factory=_query_filters_factory)
    history: HistoryScope = "active"
    evidence_limit: int = 8
    comparison: ComparisonWindow | None = None
    execution: ExecutionMode = "auto"

    def __post_init__(self) -> None:
        from codex_usage_tracker.application.query_models import QueryFilters

        if self.goal not in ANALYSIS_GOALS:
            raise _request_validation_error(f"unsupported analysis goal: {self.goal}")
        if not isinstance(self.filters, QueryFilters):
            raise _request_validation_error("filters must be QueryFilters")
        if self.history not in {"active", "all"}:
            raise _request_validation_error(f"unsupported history: {self.history}")
        if type(self.evidence_limit) is not int or not 1 <= self.evidence_limit <= 20:
            raise _request_validation_error("evidence_limit must be between 1 and 20")
        if self.comparison is not None and not isinstance(self.comparison, ComparisonWindow):
            raise _request_validation_error("comparison must be ComparisonWindow")
        if self.execution not in {"auto", "sync", "async"}:
            raise _request_validation_error(f"unsupported execution: {self.execution}")


@dataclass(frozen=True)
class WorkEstimate:
    strategy_id: str
    strategy_version: str
    estimated_work_units: int
    sync_work_ceiling: int
    evidence_records: int
    recommended_execution: Literal["sync", "async"]
    reason: str


@dataclass(frozen=True)
class AnalysisReportV2:
    schema: Literal["codex-usage-tracker.analysis.v2"] = field(
        default="codex-usage-tracker.analysis.v2", init=False
    )
    analysis_id: str
    goal: AnalysisGoal
    summary: str
    findings: tuple[FindingV1, ...]
    evidence: tuple[EvidenceV1, ...]
    methodology: tuple[str, ...]
    suggested_questions: tuple[str, ...]
    strategy_id: str
    strategy_version: str
    source_revision: str | None
    accounting: AccountingContextV1
    messages: tuple[MessageV1, ...]
    limitations: tuple[str, ...]
    dashboard_destinations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", tuple(self.findings))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "methodology", tuple(self.methodology))
        object.__setattr__(self, "suggested_questions", tuple(self.suggested_questions))
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "limitations", tuple(self.limitations))
        object.__setattr__(self, "dashboard_destinations", tuple(self.dashboard_destinations))
