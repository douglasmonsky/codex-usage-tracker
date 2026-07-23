"""Executable parity record for retiring the duplicate dashboard workbenches."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

import pytest

from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG
from codex_usage_tracker.analytics.analysis_models import (
    AnalysisGoal,
    AnalysisReportV2,
    AnalysisRequest,
    WorkEstimate,
)
from codex_usage_tracker.application.analyze import AnalysisRuntime
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.query_models import (
    DashboardTargetV2,
    QueryRequest,
    QueryResult,
)
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.core.contracts import FreshnessV1, ScopeV1
from codex_usage_tracker.evidence.models import EvidenceRequest
from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.interfaces.mcp.query_analysis_tools import (
    build_usage_analyze,
    build_usage_query,
)
from tests.application.fixtures.analysis_cases import synthetic_analysis_report

REPO_ROOT = Path(__file__).resolve().parents[2]
PARITY_RECORD = REPO_ROOT / "docs" / "dashboard-sunset-job-parity-v2.md"
PARITY_RECORD_PATTERN = re.compile(
    r"<!-- parity-record:start -->\s*```json\s*(\[.*\])\s*```\s*<!-- parity-record:end -->",
    re.DOTALL,
)
PARITY_CAVEAT = "Aggregate-only synthetic fixture; raw content is excluded."
DIAGNOSTIC_RECORD_ID = "d" * 64
History = Literal["active", "all"]


@dataclass(frozen=True)
class ParityCase:
    row_id: str
    legacy_job: str
    mode: Literal["analysis", "query"]
    fixtures: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    history: History
    destinations: tuple[str, ...]
    replacement: str
    owner: str
    decision: str


@dataclass(frozen=True)
class ParityObservation:
    evidence_ids: tuple[str, ...]
    history: str
    accounting: Mapping[str, object]
    caveats: tuple[str, ...]
    destinations: tuple[str, ...]


PARITY_CASES = (
    ParityCase(
        "diagnose-usage-drivers",
        "Diagnose usage drivers",
        "analysis",
        ("usage_spike",),
        ("evidence-usage_spike",),
        "active",
        ("evidence", "explore"),
        'usage_analyze(goal="usage_spike") then usage_evidence',
        "Analysis service maintainers",
        "Core analysis owns new work; the direct Investigate route remains a bookmark bridge.",
    ),
    ParityCase(
        "broad-token-waste",
        "Broad token waste",
        "analysis",
        ("token_waste",),
        ("evidence-token_waste",),
        "active",
        ("evidence", "explore"),
        'usage_analyze(goal="token_waste")',
        "Analysis service maintainers",
        "Finding evidence and Explore replace the duplicate ranked-workbench presentation.",
    ),
    ParityCase(
        "context-cache-analysis",
        "Context/cache analysis",
        "analysis",
        ("context_bloat", "cache_failure"),
        ("evidence-context_bloat", "evidence-cache_failure"),
        "all",
        ("evidence", "explore"),
        'usage_analyze(goal="context_bloat"|"cache_failure")',
        "Analysis service maintainers",
        "Both supported goals retain exact call evidence across all history.",
    ),
    ParityCase(
        "workflow-churn",
        "Repeated command/file churn",
        "analysis",
        ("workflow_churn",),
        ("evidence-workflow_churn",),
        "active",
        ("evidence", "explore"),
        'usage_analyze(goal="workflow_churn")',
        "Analysis service maintainers",
        "The finding replaces separate command and file aliases without changing evidence identity.",
    ),
    ParityCase(
        "report-selection",
        "Report selection and explanation",
        "analysis",
        ("usage_spike",),
        ("evidence-usage_spike",),
        "all",
        ("evidence", "explore"),
        'usage_analyze(goal="usage_spike") or usage_query',
        "Analysis and CLI maintainers",
        "Analysis owns explanations; query and existing CLI export own bounded automation.",
    ),
    ParityCase(
        "compression-ranking",
        "Compression candidate ranking",
        "analysis",
        ("token_waste",),
        ("evidence-token_waste",),
        "all",
        ("evidence", "explore"),
        'usage_analyze(goal="token_waste"); full-profile compression tools through 0.24.x',
        "Analysis service maintainers",
        "Exact compression ranking remains a tested full-profile compatibility operation through 0.24.x.",
    ),
    ParityCase(
        "diagnostic-facts",
        "Diagnostic fact browsing",
        "query",
        (f"query:call:{DIAGNOSTIC_RECORD_ID}",),
        (f"call:{DIAGNOSTIC_RECORD_ID}",),
        "all",
        ("explore",),
        'usage_query(entity="call", measures=["tokens"]) then usage_evidence',
        "Evidence Console maintainers",
        "Canonical query identity becomes the exact usage_evidence selector.",
    ),
    ParityCase(
        "subagent-analysis",
        "Subagent analysis",
        "analysis",
        ("subagent_cost",),
        ("evidence-subagent_cost",),
        "all",
        ("explore", "evidence"),
        'usage_query(entity="subagent") or usage_analyze(goal="subagent_cost")',
        "Analysis service maintainers",
        "Explore owns grouped rows and Evidence owns the selected canonical record.",
    ),
)


@pytest.mark.parametrize("case", PARITY_CASES, ids=lambda case: case.row_id)
def test_sunset_replacement_preserves_fixture_contract(case: ParityCase) -> None:
    observation = _observe(case)
    assert observation.evidence_ids == case.evidence_ids
    assert observation.history == case.history
    assert observation.accounting == _accounting(case.history)
    assert observation.caveats == (PARITY_CAVEAT,)
    assert set(observation.destinations) == set(case.destinations)

    signed = _signed_rows()[case.row_id]
    assert signed["legacy_job"] == case.legacy_job
    assert tuple(signed["fixture"]) == case.fixtures
    assert tuple(signed["expected_evidence_ids"]) == case.evidence_ids
    assert tuple(signed["actual_evidence_ids"]) == observation.evidence_ids
    assert signed["history_scope"] == observation.history
    assert signed["accounting_context"] == observation.accounting
    assert tuple(signed["caveats"]) == observation.caveats
    assert set(signed["evidence_destination"]) == set(observation.destinations)
    assert signed["replacement_tool_request"] == case.replacement
    assert signed["owner"] == case.owner
    assert signed["decision"] == case.decision
    assert signed["remove_in"] == "0.25.0"
    assert signed["result"] == "PASS"


def test_signed_record_covers_every_required_job_and_compatibility_operation() -> None:
    rows = _signed_rows()
    assert tuple(rows) == tuple(case.row_id for case in PARITY_CASES)
    assert len({row["legacy_job"] for row in rows.values()}) == 8

    full_tools = {spec.name for spec in tools_for_profile("full")}
    assert {
        "usage_compression_profile",
        "usage_compression_candidates",
        "usage_compression_candidate_detail",
    } <= full_tools


def _observe(case: ParityCase) -> ParityObservation:
    return _observe_query(case) if case.mode == "query" else _observe_analysis(case)


def _observe_analysis(case: ParityCase) -> ParityObservation:
    evidence_ids: list[str] = []
    destinations: set[str] = set()
    for fixture in case.fixtures:
        goal = cast(AnalysisGoal, fixture)
        payload = build_usage_analyze(
            goal=goal,
            history=case.history,
            execution="sync",
            runtime=_runtime(goal),
            context_builder=_context_builder,
        )
        result = cast(Mapping[str, object], payload["result"])
        evidence = cast(tuple[Mapping[str, object], ...], result["evidence"])
        evidence_ids.extend(str(item["evidence_id"]) for item in evidence)
        assert tuple(cast(tuple[str, ...], result["limitations"])) == (PARITY_CAVEAT,)
        assert payload["scope"] == _scope(case.history)
        assert payload["accounting"] == _accounting(case.history)
        destinations.update(
            str(cast(Mapping[str, object], target)["view"])
            for target in cast(tuple[Mapping[str, object], ...], payload["dashboard_targets"])
        )
    return ParityObservation(
        tuple(evidence_ids),
        case.history,
        _accounting(case.history),
        (PARITY_CAVEAT,),
        tuple(destinations),
    )


def _observe_query(case: ParityCase) -> ParityObservation:
    def query_service(request: QueryRequest, **_: object) -> QueryResult:
        assert request.history == case.history
        return QueryResult(
            entity="call",
            columns=("record_id", "tokens"),
            rows=({"record_id": DIAGNOSTIC_RECORD_ID, "tokens": 10},),
            next_cursor=None,
            total_matched=1,
            dashboard_target=DashboardTargetV2("explore", {"mode": "calls"}),
        )

    payload = build_usage_query(
        entity="call",
        measures=("tokens",),
        history=case.history,
        query_service=query_service,
        context_builder=_context_builder,
    )
    result = cast(Mapping[str, object], payload["result"])
    rows = cast(tuple[Mapping[str, object], ...], result["rows"])
    selector = EvidenceRequest("call", str(rows[0]["record_id"]), history=case.history)
    targets = cast(tuple[Mapping[str, object], ...], payload["dashboard_targets"])
    return ParityObservation(
        (f"call:{selector.selector_id}",),
        cast(str, cast(Mapping[str, object], payload["scope"])["history"]),
        cast(Mapping[str, object], payload["accounting"]),
        (str(cast(Mapping[str, object], payload["freshness"])["reason"]),),
        tuple(str(target["view"]) for target in targets),
    )


@dataclass(frozen=True)
class _ParityStrategy:
    goal: AnalysisGoal

    @property
    def strategy_id(self) -> str:
        return f"sunset-parity.{self.goal}"

    @property
    def strategy_version(self) -> str:
        return "1.0.0"

    def estimate(self, request: AnalysisRequest, _context: RequestContext) -> WorkEstimate:
        return WorkEstimate(
            self.strategy_id,
            self.strategy_version,
            1,
            8,
            request.evidence_limit,
            "sync",
            "bounded synthetic parity fixture",
        )

    def analyze(self, _request: AnalysisRequest, context: RequestContext) -> AnalysisReportV2:
        return replace(
            synthetic_analysis_report(self.goal, context),
            methodology=("Canonical aggregate evidence only.",),
            limitations=(PARITY_CAVEAT,),
        )


def _runtime(goal: AnalysisGoal) -> AnalysisRuntime:
    entry = replace(ANALYSIS_CATALOG[goal], strategy=_ParityStrategy(goal))
    return AnalysisRuntime(
        catalog=MappingProxyType({goal: entry}),
        pricing_fingerprint="pricing:parity",
        rate_card_fingerprint="rate-card:parity",
        thresholds_fingerprint="thresholds:parity",
        catalog_version="catalog:parity",
    )


def _context_builder(*, scope: RequestScope, **_: object) -> RequestContext:
    return RequestContext(
        "generation:23",
        FreshnessV1(None, "generation:23", None, "fresh", PARITY_CAVEAT, 300, None),
        ScopeV1(scope.since, scope.until, scope.history, "strict", {}),
        3,
        2,
        1,
        1.0,
        1.0,
        1.0,
    )


def _scope(history: History) -> dict[str, object]:
    return {
        "filters": {},
        "history": history,
        "privacy_mode": "strict",
        "schema": "codex-usage-tracker.scope.v1",
        "since": None,
        "until": None,
    }


def _accounting(history: History) -> dict[str, object]:
    return {
        "canonical_rows": 2,
        "copied_rows_excluded": 1,
        "credit_coverage": 1.0,
        "history_scope": history,
        "physical_rows": 3,
        "pricing_coverage": 1.0,
        "privacy_mode": "strict",
        "schema": "codex-usage-tracker.accounting-context.v1",
        "service_tier_coverage": 1.0,
    }


@lru_cache(maxsize=1)
def _signed_rows() -> dict[str, dict[str, Any]]:
    match = PARITY_RECORD_PATTERN.search(PARITY_RECORD.read_text(encoding="utf-8"))
    assert match is not None, "parity record must contain one signed JSON block"
    rows = json.loads(match.group(1))
    assert isinstance(rows, list)
    return {str(row["id"]): row for row in rows}
