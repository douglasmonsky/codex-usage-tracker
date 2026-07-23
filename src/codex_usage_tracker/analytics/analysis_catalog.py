"""Import-explicit compatibility catalog for canonical analysis goals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from types import MappingProxyType
from typing import Literal, cast

from codex_usage_tracker.analytics.analysis_models import (
    ANALYSIS_GOALS,
    AnalysisGoal,
    AnalysisReportV2,
    AnalysisRequest,
    WorkEstimate,
)
from codex_usage_tracker.analytics.strategies.protocol import AnalysisStrategy
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.errors import RequestValidationError
from codex_usage_tracker.core.contracts import MessageV1
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_PROJECTS_PATH,
)
from codex_usage_tracker.recommendation_engine import api as recommendation_api
from codex_usage_tracker.recommendation_engine.query import RecommendationFactsUnavailableError
from codex_usage_tracker.reports import agentic as agentic_reports
from codex_usage_tracker.reports import api as report_api
from codex_usage_tracker.reports import subagent_usage as subagent_reports

SUPPORTED_DASHBOARD_DESTINATIONS = frozenset(
    {
        "home",
        "explore",
        "limits",
        "evidence",
    }
)
CompatibilityDelegate = Literal["agentic", "hypothesis", "subagent", "recommendations"]


@dataclass(frozen=True)
class AnalysisCatalogEntry:
    goal: AnalysisGoal
    strategy: AnalysisStrategy
    required_facts: tuple[str, ...]
    optional_facts: tuple[str, ...]
    max_evidence_records: int
    sync_work_ceiling: int
    dashboard_destinations: tuple[str, ...]
    missing_fact_fallback: str
    implementation_status: Literal["compatibility"] = "compatibility"


@dataclass(frozen=True)
class _CompatibilityStrategy:
    goal: AnalysisGoal
    strategy_id: str
    strategy_version: str
    delegate: CompatibilityDelegate

    def estimate(self, request: AnalysisRequest, context: RequestContext) -> WorkEstimate:
        _require_matching_goal(self.goal, request.goal)
        entry = ANALYSIS_CATALOG[self.goal]
        selected_evidence = min(request.evidence_limit, entry.max_evidence_records)
        filter_count = sum(
            getattr(request.filters, item.name) is not None for item in fields(request.filters)
        )
        work_units = (
            1
            + min(context.canonical_rows, entry.max_evidence_records)
            + filter_count
            + (2 if request.comparison is not None else 0)
        )
        recommended = "sync" if work_units <= entry.sync_work_ceiling else "async"
        return WorkEstimate(
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            estimated_work_units=work_units,
            sync_work_ceiling=entry.sync_work_ceiling,
            evidence_records=selected_evidence,
            recommended_execution=recommended,
            reason=(
                f"{work_units} deterministic work units against "
                f"a synchronous ceiling of {entry.sync_work_ceiling}."
            ),
        )

    def analyze(self, request: AnalysisRequest, context: RequestContext) -> AnalysisReportV2:
        _require_matching_goal(self.goal, request.goal)
        entry = ANALYSIS_CATALOG[self.goal]
        missing = _missing_facts(entry, request, context)
        if missing:
            return _fallback_report(entry, context, missing)
        try:
            legacy = _run_compatibility_delegate(self.delegate, request, context)
        except (FileNotFoundError, RecommendationFactsUnavailableError) as exc:
            return _fallback_report(entry, context, (type(exc).__name__,))
        return _legacy_report(entry, context, legacy)


def _entry(
    goal: AnalysisGoal,
    delegate: CompatibilityDelegate,
    required: tuple[str, ...],
    optional: tuple[str, ...],
    destinations: tuple[str, ...],
    evidence: int = 8,
    ceiling: int = 16,
) -> AnalysisCatalogEntry:
    strategy = _CompatibilityStrategy(
        goal=goal,
        strategy_id=f"compatibility.{goal}",
        strategy_version="1.0.0",
        delegate=delegate,
    )
    return AnalysisCatalogEntry(
        goal=goal,
        strategy=strategy,
        required_facts=required,
        optional_facts=optional,
        max_evidence_records=evidence,
        sync_work_ceiling=ceiling,
        dashboard_destinations=destinations,
        missing_fact_fallback=(
            f"Analysis for {goal.replace('_', ' ')} is unavailable because required local facts "
            "are missing or stale; no conclusion was generated."
        ),
    )


_CANONICAL = ("canonical_usage",)
_COMPARISON = ("canonical_usage", "comparison_window", "comparison_algorithm")
_DIAGNOSTIC = ("diagnostic_facts",)
_PRICING = ("pricing_coverage",)

_CATALOG_ENTRIES = (
    _entry(
        "usage_spike",
        "hypothesis",
        _COMPARISON,
        ("pricing_coverage", "subagent_facts"),
        ("evidence", "explore"),
        10,
        18,
    ),
    _entry(
        "token_waste",
        "agentic",
        _CANONICAL,
        ("recommendation_facts", "diagnostic_facts"),
        ("evidence", "explore"),
    ),
    _entry("context_bloat", "agentic", _CANONICAL, _DIAGNOSTIC, ("evidence", "explore")),
    _entry("cache_failure", "agentic", _CANONICAL, _DIAGNOSTIC, ("evidence", "explore")),
    _entry(
        "subagent_cost",
        "subagent",
        _CANONICAL,
        ("pricing_coverage", "credit_coverage"),
        ("explore", "evidence"),
        10,
        18,
    ),
    _entry(
        "fast_usage",
        "hypothesis",
        ("canonical_usage", "service_tier_coverage"),
        _PRICING,
        ("limits", "evidence"),
    ),
    _entry(
        "pricing_gaps",
        "recommendations",
        ("canonical_usage", "pricing_coverage"),
        ("credit_coverage", "recommendation_facts"),
        ("home", "explore"),
    ),
    _entry(
        "thread_comparison", "hypothesis", _COMPARISON, _PRICING, ("explore", "evidence"), 10, 18
    ),
    _entry(
        "model_effort_mix",
        "hypothesis",
        _CANONICAL,
        ("pricing_coverage", "service_tier_coverage"),
        ("home", "explore"),
    ),
    _entry("workflow_churn", "agentic", _CANONICAL, _DIAGNOSTIC, ("evidence", "explore")),
)


def build_analysis_catalog(
    entries: Iterable[AnalysisCatalogEntry],
) -> Mapping[AnalysisGoal, AnalysisCatalogEntry]:
    registered: dict[AnalysisGoal, AnalysisCatalogEntry] = {}
    strategy_ids: set[str] = set()
    for entry in entries:
        if entry.goal in registered:
            raise ValueError(f"duplicate analysis goal: {entry.goal}")
        if entry.strategy.strategy_id in strategy_ids:
            raise ValueError(f"duplicate analysis strategy id: {entry.strategy.strategy_id}")
        if entry.strategy.goal != entry.goal:
            raise ValueError(f"strategy goal mismatch: {entry.goal}")
        if not entry.required_facts or not 1 <= entry.max_evidence_records <= 20:
            raise ValueError(f"invalid analysis fact or evidence bounds: {entry.goal}")
        if entry.sync_work_ceiling <= 0:
            raise ValueError(f"invalid synchronous work ceiling: {entry.goal}")
        if (
            not entry.dashboard_destinations
            or not set(entry.dashboard_destinations) <= SUPPORTED_DASHBOARD_DESTINATIONS
        ):
            raise ValueError(f"unsupported dashboard destination: {entry.goal}")
        if not entry.missing_fact_fallback.strip():
            raise ValueError(f"missing analysis fallback: {entry.goal}")
        if not entry.strategy.strategy_id or not entry.strategy.strategy_version:
            raise ValueError(f"unstable analysis strategy metadata: {entry.goal}")
        registered[entry.goal] = entry
        strategy_ids.add(entry.strategy.strategy_id)
    missing = set(ANALYSIS_GOALS) - set(registered)
    extra = set(registered) - set(ANALYSIS_GOALS)
    if missing:
        raise ValueError(f"missing analysis goals: {sorted(missing)}")
    if extra:
        raise ValueError(f"unsupported analysis goals: {sorted(extra)}")
    return MappingProxyType(registered)


ANALYSIS_CATALOG = build_analysis_catalog(_CATALOG_ENTRIES)


def _missing_facts(
    entry: AnalysisCatalogEntry, request: AnalysisRequest, context: RequestContext
) -> tuple[str, ...]:
    missing: list[str] = []
    if context.freshness.state in {"stale", "empty", "unknown"}:
        missing.append("fresh_index")
    facts = {
        "canonical_usage": context.canonical_rows > 0,
        "comparison_window": request.comparison is not None,
        "comparison_algorithm": False,
        "pricing_coverage": context.pricing_coverage is not None,
        "credit_coverage": context.credit_coverage is not None,
        "service_tier_coverage": (
            context.service_tier_coverage is not None and context.service_tier_coverage > 0
        ),
    }
    missing.extend(fact for fact in entry.required_facts if not facts.get(fact, False))
    return tuple(dict.fromkeys(missing))


def _run_compatibility_delegate(
    delegate: CompatibilityDelegate, request: AnalysisRequest, context: RequestContext
) -> object:
    common = {
        "since": request.filters.since,
        "until": request.filters.until,
        "include_archived": request.history == "all",
        "evidence_limit": request.evidence_limit,
        "privacy_mode": context.scope.privacy_mode,
    }
    if delegate == "agentic":
        legacy_goal = {
            "context_bloat": "token_waste",
            "cache_failure": "cache_failure",
            "workflow_churn": "workflow_churn",
        }.get(request.goal, "token_waste")
        return agentic_reports.build_agentic_investigation_report(
            db_path=DEFAULT_DB_PATH,
            pricing_path=DEFAULT_PRICING_PATH,
            allowance_path=DEFAULT_ALLOWANCE_PATH,
            projects_path=DEFAULT_PROJECTS_PATH,
            goal=legacy_goal,
            thread=request.filters.thread_key,
            **common,
        )
    if delegate == "subagent":
        return subagent_reports.build_subagent_usage_report(
            db_path=DEFAULT_DB_PATH,
            pricing_path=DEFAULT_PRICING_PATH,
            since=request.filters.since,
            parent_thread=request.filters.parent_thread_key,
            agent_role=request.filters.subagent_role,
            subagent_type=request.filters.subagent_type,
            include_archived=request.history == "all",
            limit=request.evidence_limit,
            privacy_mode=context.scope.privacy_mode,
        )
    if delegate == "recommendations":
        return recommendation_api.build_recommendations_report(
            db_path=DEFAULT_DB_PATH,
            pricing_path=DEFAULT_PRICING_PATH,
            allowance_path=DEFAULT_ALLOWANCE_PATH,
            projects_path=DEFAULT_PROJECTS_PATH,
            model=request.filters.model,
            effort=request.filters.effort,
            thread=request.filters.thread_key,
            project=request.filters.project,
            limit=request.evidence_limit,
            **{key: common[key] for key in ("since", "until", "include_archived", "privacy_mode")},
        )
    return report_api.build_hypothesis_test_report(
        db_path=DEFAULT_DB_PATH,
        pricing_path=DEFAULT_PRICING_PATH,
        allowance_path=DEFAULT_ALLOWANCE_PATH,
        projects_path=DEFAULT_PROJECTS_PATH,
        question=f"Analyze {request.goal.replace('_', ' ')} using local aggregate facts.",
        thread=request.filters.thread_key,
        **common,
    )


def _legacy_report(
    entry: AnalysisCatalogEntry, context: RequestContext, legacy: object
) -> AnalysisReportV2:
    payload = _legacy_payload(legacy)
    source_schema = str(payload.get("schema") or payload.get("schema_id") or "legacy-report")
    summary = payload.get("summary")
    top_finding = summary.get("top_finding") if isinstance(summary, Mapping) else None
    statement = (
        top_finding
        if isinstance(top_finding, str) and top_finding
        else f"Compatibility delegate completed with {source_schema}."
    )
    return AnalysisReportV2(
        analysis_id=_analysis_id(entry, context),
        goal=entry.goal,
        summary=statement,
        findings=(),
        evidence=(),
        methodology=(f"Delegated to existing {source_schema} calculations without changing them.",),
        suggested_questions=(),
        strategy_id=entry.strategy.strategy_id,
        strategy_version=entry.strategy.strategy_version,
        source_revision=context.source_revision,
        accounting=context.accounting,
        messages=(),
        limitations=(),
        dashboard_destinations=entry.dashboard_destinations,
    )


def _fallback_report(
    entry: AnalysisCatalogEntry, context: RequestContext, missing: tuple[str, ...]
) -> AnalysisReportV2:
    return AnalysisReportV2(
        analysis_id=_analysis_id(entry, context),
        goal=entry.goal,
        summary=entry.missing_fact_fallback,
        findings=(),
        evidence=(),
        methodology=("No analysis algorithm ran because required facts were unavailable.",),
        suggested_questions=(),
        strategy_id=entry.strategy.strategy_id,
        strategy_version=entry.strategy.strategy_version,
        source_revision=context.source_revision,
        accounting=context.accounting,
        messages=(
            MessageV1(
                code="analysis_facts_unavailable",
                severity="warning",
                message=f"Unavailable facts: {', '.join(missing)}.",
                remediation="Run usage_refresh explicitly if newer local facts are required.",
            ),
        ),
        limitations=("Required local facts were unavailable or stale.",),
        dashboard_destinations=entry.dashboard_destinations,
    )


def _legacy_payload(legacy: object) -> Mapping[str, object]:
    payload = getattr(legacy, "payload", legacy)
    if callable(payload):
        payload = payload()
    return cast(Mapping[str, object], payload) if isinstance(payload, Mapping) else {}


def _analysis_id(entry: AnalysisCatalogEntry, context: RequestContext) -> str:
    return f"{entry.strategy.strategy_id}:{context.source_revision or 'unavailable'}"


def _require_matching_goal(expected: AnalysisGoal, actual: AnalysisGoal) -> None:
    if expected != actual:
        raise RequestValidationError(f"strategy for {expected} cannot analyze {actual}")
