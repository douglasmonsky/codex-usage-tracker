from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from codex_usage_tracker.analytics import analysis_catalog as catalog_module
from codex_usage_tracker.analytics.analysis_catalog import ANALYSIS_CATALOG
from codex_usage_tracker.analytics.analysis_models import AnalysisRequest, ComparisonWindow
from codex_usage_tracker.analytics.strategies.protocol import AnalysisStrategy
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.query_models import QueryFilters
from codex_usage_tracker.core.contracts import FreshnessV1, ScopeV1


def _context(
    *,
    state: str = "fresh",
    pricing_coverage: float | None = 1.0,
    service_tier_coverage: float | None = 0.8,
) -> RequestContext:
    return RequestContext(
        source_revision="generation:7",
        freshness=FreshnessV1(
            latest_indexed_event_at="2026-07-22T12:00:00Z",
            source_revision="generation:7",
            refresh_completed_at="2026-07-22T12:00:00Z",
            state=state,  # type: ignore[arg-type]
            reason=None,
            threshold_seconds=300,
            recommended_refresh_action=None,
        ),
        scope=ScopeV1(
            since=None,
            until=None,
            history="active",
            privacy_mode="strict",
            filters={},
        ),
        physical_rows=120,
        canonical_rows=100,
        copied_rows_excluded=20,
        pricing_coverage=pricing_coverage,
        credit_coverage=0.9,
        service_tier_coverage=service_tier_coverage,
    )


def test_strategies_satisfy_protocol_and_estimate_deterministically() -> None:
    context = _context()
    for goal, entry in ANALYSIS_CATALOG.items():
        request = AnalysisRequest(goal=goal, filters=QueryFilters(), evidence_limit=5)
        assert isinstance(entry.strategy, AnalysisStrategy)
        first = entry.strategy.estimate(request, context)
        second = entry.strategy.estimate(request, context)
        assert first == second
        assert first.strategy_id == entry.strategy.strategy_id
        assert first.strategy_version == entry.strategy.strategy_version
        assert first.estimated_work_units > 0
        assert first.sync_work_ceiling == entry.sync_work_ceiling
        assert first.evidence_records <= entry.max_evidence_records
        with pytest.raises(FrozenInstanceError):
            first.estimated_work_units = 0  # type: ignore[misc]


def test_estimate_never_calls_builders_refresh_or_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("estimate invoked an execution dependency")

    monkeypatch.setattr(
        catalog_module.agentic_reports, "build_agentic_investigation_report", unexpected
    )
    monkeypatch.setattr(catalog_module.report_api, "build_hypothesis_test_report", unexpected)
    monkeypatch.setattr(catalog_module.subagent_reports, "build_subagent_usage_report", unexpected)
    monkeypatch.setattr(
        catalog_module.recommendation_api, "build_recommendations_report", unexpected
    )
    monkeypatch.setattr(catalog_module.recommendation_api, "refresh_usage_index", unexpected)

    for goal, entry in ANALYSIS_CATALOG.items():
        entry.strategy.estimate(
            AnalysisRequest(goal=goal, filters=QueryFilters()),
            _context(),
        )


def test_analyze_delegates_only_when_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def builder(**kwargs: object) -> object:
        calls.append(kwargs)
        return SimpleNamespace(
            payload={
                "schema": "codex-usage-tracker-agentic-investigation-v1",
                "summary": {"top_finding": "Existing aggregate signal"},
            }
        )

    monkeypatch.setattr(
        catalog_module.agentic_reports, "build_agentic_investigation_report", builder
    )
    strategy = ANALYSIS_CATALOG["token_waste"].strategy
    report = strategy.analyze(
        AnalysisRequest(goal="token_waste", filters=QueryFilters(), evidence_limit=3),
        _context(),
    )

    assert len(calls) == 1
    assert report.strategy_id == strategy.strategy_id
    assert report.strategy_version == strategy.strategy_version
    assert report.summary == "Existing aggregate signal"
    assert report.findings == ()
    assert report.evidence == ()


@pytest.mark.parametrize(
    ("goal", "context"),
    [
        ("token_waste", _context(state="stale")),
        ("pricing_gaps", _context(pricing_coverage=None)),
        ("fast_usage", _context(service_tier_coverage=0.0)),
    ],
)
def test_missing_or_stale_facts_return_documented_nonfabricated_fallback(
    monkeypatch: pytest.MonkeyPatch, goal: str, context: RequestContext
) -> None:
    def unexpected(**_kwargs: object) -> object:
        raise AssertionError("fallback invoked a legacy builder")

    monkeypatch.setattr(
        catalog_module.agentic_reports, "build_agentic_investigation_report", unexpected
    )
    monkeypatch.setattr(
        catalog_module.recommendation_api, "build_recommendations_report", unexpected
    )
    monkeypatch.setattr(catalog_module.report_api, "build_hypothesis_test_report", unexpected)
    monkeypatch.setattr(catalog_module.recommendation_api, "refresh_usage_index", unexpected)
    entry = ANALYSIS_CATALOG[goal]
    report = entry.strategy.analyze(
        AnalysisRequest(goal=goal, filters=QueryFilters()),  # type: ignore[arg-type]
        context,
    )

    assert report.summary == entry.missing_fact_fallback
    assert report.findings == ()
    assert report.evidence == ()
    assert report.messages[0].code == "analysis_facts_unavailable"
    assert report.messages[0].severity == "warning"


@pytest.mark.parametrize("goal", ["usage_spike", "thread_comparison"])
def test_compatibility_comparisons_fail_closed_without_two_window_algorithm(
    monkeypatch: pytest.MonkeyPatch, goal: str
) -> None:
    def unexpected(**_kwargs: object) -> object:
        raise AssertionError("comparison fallback invoked a one-window builder")

    monkeypatch.setattr(catalog_module.report_api, "build_hypothesis_test_report", unexpected)
    report = ANALYSIS_CATALOG[goal].strategy.analyze(
        AnalysisRequest(
            goal=goal,  # type: ignore[arg-type]
            filters=QueryFilters(since="2026-07-09T00:00:00Z", until="2026-07-15T00:00:00Z"),
            comparison=ComparisonWindow(since="2026-07-01T00:00:00Z", until="2026-07-07T00:00:00Z"),
        ),
        _context(),
    )

    assert report.findings == ()
    assert report.evidence == ()
    assert report.messages[0].code == "analysis_facts_unavailable"
    assert "comparison_algorithm" in report.messages[0].message
