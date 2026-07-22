from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType
from typing import cast

import pytest

from codex_usage_tracker.analytics.analysis_catalog import (
    ANALYSIS_CATALOG,
    ANALYSIS_GOALS,
    SUPPORTED_DASHBOARD_DESTINATIONS,
    build_analysis_catalog,
)
from codex_usage_tracker.analytics.analysis_models import (
    AnalysisGoal,
    AnalysisRequest,
    ComparisonWindow,
)
from codex_usage_tracker.application import requests
from codex_usage_tracker.application.query_models import QueryFilters

EXPECTED_GOALS = {
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
}


def test_catalog_is_exact_exhaustive_and_import_explicit() -> None:
    assert isinstance(ANALYSIS_CATALOG, MappingProxyType)
    assert set(ANALYSIS_GOALS) == EXPECTED_GOALS
    assert set(ANALYSIS_CATALOG) == EXPECTED_GOALS
    assert len({id(entry.strategy) for entry in ANALYSIS_CATALOG.values()}) == 10
    assert len({entry.strategy.strategy_id for entry in ANALYSIS_CATALOG.values()}) == 10
    assert all(entry.goal == entry.strategy.goal for entry in ANALYSIS_CATALOG.values())


def test_catalog_metadata_is_bounded_immutable_and_documented() -> None:
    for entry in ANALYSIS_CATALOG.values():
        assert entry.required_facts
        assert isinstance(entry.required_facts, tuple)
        assert isinstance(entry.optional_facts, tuple)
        assert 1 <= entry.max_evidence_records <= 20
        assert entry.sync_work_ceiling > 0
        assert entry.dashboard_destinations
        assert set(entry.dashboard_destinations) <= SUPPORTED_DASHBOARD_DESTINATIONS
        assert entry.missing_fact_fallback.strip()
        assert entry.implementation_status == "compatibility"
        assert entry.strategy.strategy_id.startswith("compatibility.")
        assert entry.strategy.strategy_version == "1.0.0"
        with pytest.raises(FrozenInstanceError):
            entry.max_evidence_records = 0  # type: ignore[misc]


def test_registration_rejects_duplicate_and_missing_goals() -> None:
    entries = tuple(ANALYSIS_CATALOG.values())
    with pytest.raises(ValueError, match="duplicate analysis goal"):
        build_analysis_catalog((*entries, entries[0]))
    with pytest.raises(ValueError, match="missing analysis goals"):
        build_analysis_catalog(entries[:-1])


def test_analysis_request_is_authoritative_typed_and_frozen() -> None:
    request = AnalysisRequest(
        goal="usage_spike",
        filters=QueryFilters(model="gpt-5.5"),
        comparison=ComparisonWindow(since="2026-07-01T00:00:00Z", until="2026-07-08T00:00:00Z"),
    )

    assert requests.AnalysisRequest is AnalysisRequest
    assert request.evidence_limit == 8
    assert request.execution == "auto"
    with pytest.raises(FrozenInstanceError):
        request.goal = "token_waste"  # type: ignore[misc]
    with pytest.raises(ValueError, match="unsupported analysis goal"):
        AnalysisRequest(
            goal=cast(AnalysisGoal, "arbitrary"),
            filters=QueryFilters(),
        )
    with pytest.raises(ValueError, match="evidence_limit"):
        AnalysisRequest(goal="usage_spike", filters=QueryFilters(), evidence_limit=0)
