from __future__ import annotations

import pytest

from codex_usage_tracker.core.contracts import EvidenceV1, FindingV1, RecommendationV1
from codex_usage_tracker.core.contracts.claims import validate_findings
from codex_usage_tracker.core.contracts.serialization import payload_mapping


def _observed_finding() -> FindingV1:
    return FindingV1(
        finding_id="finding-observed",
        title="Observed increase",
        claim_type="observed",
        severity="medium",
        confidence="exact",
        statement="Uncached input increased.",
        metrics={"tokens": 1200},
        evidence_ids=("evidence-1",),
        caveat_codes=(),
    )


def test_recommendation_requires_a_supporting_claim_id() -> None:
    with pytest.raises(ValueError, match="supporting claim"):
        RecommendationV1(
            recommendation_id="recommendation-1",
            action="Start a fresh task.",
            rationale="Context is no longer useful.",
            supporting_claim_ids=(),
        )


def test_recommendation_must_reference_a_present_non_recommended_finding() -> None:
    recommendation = RecommendationV1(
        recommendation_id="recommendation-1",
        action="Start a fresh task.",
        rationale="Context is no longer useful.",
        supporting_claim_ids=("finding-missing",),
    )
    recommended = FindingV1(
        finding_id="finding-recommended",
        title="Start fresh",
        claim_type="recommended",
        severity="low",
        confidence="high",
        statement="Start a fresh task.",
        metrics={},
        evidence_ids=("evidence-1",),
        caveat_codes=(),
        recommendation=recommendation,
    )

    with pytest.raises(ValueError, match="unsupported recommendation"):
        validate_findings((_observed_finding(), recommended))


def test_evidence_serialization_is_sorted_and_finite() -> None:
    evidence = EvidenceV1(
        evidence_id="evidence-1",
        kind="call",
        label="Selected call",
        selectors={"record_id": "call-1", "scope": "active"},
        metrics={"tokens": 1200, "cache_ratio": 0.5},
        source_schema="codex-usage-tracker-call-v1",
        dashboard_target=None,
    )

    payload = payload_mapping(evidence)

    assert list(payload) == sorted(payload)
    assert list(payload["metrics"]) == ["cache_ratio", "tokens"]

    invalid = EvidenceV1(
        evidence_id="evidence-invalid",
        kind="call",
        label="Invalid call",
        selectors={},
        metrics={"tokens": float("inf")},
        source_schema="codex-usage-tracker-call-v1",
        dashboard_target=None,
    )
    with pytest.raises(ValueError, match="finite"):
        payload_mapping(invalid)
