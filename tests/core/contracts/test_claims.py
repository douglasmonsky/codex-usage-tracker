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


def test_recommended_finding_requires_recommendation_details() -> None:
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
    )

    with pytest.raises(ValueError, match="recommended finding requires recommendation"):
        validate_findings((_observed_finding(), recommended))


def test_claims_snapshot_mutable_mappings_and_sequences() -> None:
    supporting_claim_ids = ["finding-observed"]
    metrics = {"tokens": 1200}
    evidence_ids = ["evidence-1"]
    caveat_codes = ["estimate.partial"]
    recommendation = RecommendationV1(
        recommendation_id="recommendation-1",
        action="Start a fresh task.",
        rationale="Context is no longer useful.",
        supporting_claim_ids=supporting_claim_ids,  # type: ignore[arg-type]
    )
    finding = FindingV1(
        finding_id="finding-recommended",
        title="Start fresh",
        claim_type="recommended",
        severity="low",
        confidence="high",
        statement="Start a fresh task.",
        metrics=metrics,
        evidence_ids=evidence_ids,  # type: ignore[arg-type]
        caveat_codes=caveat_codes,  # type: ignore[arg-type]
        recommendation=recommendation,
    )
    expected = payload_mapping(finding)

    supporting_claim_ids.append("finding-other")
    metrics["tokens"] = 2400
    evidence_ids.append("evidence-2")
    caveat_codes.append("estimate.stale")

    assert payload_mapping(finding) == expected


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


def test_evidence_snapshots_nested_caller_inputs() -> None:
    selectors = {"record_id": "call-1"}
    metrics = {"tokens": 1200}
    dashboard_target = {"relative_url": "/calls/call-1", "filters": {"ids": ["call-1"]}}
    evidence = EvidenceV1(
        evidence_id="evidence-1",
        kind="call",
        label="Selected call",
        selectors=selectors,
        metrics=metrics,
        source_schema="codex-usage-tracker-call-v1",
        dashboard_target=dashboard_target,
    )
    expected = payload_mapping(evidence)

    selectors["record_id"] = "call-2"
    metrics["tokens"] = 2400
    dashboard_target["filters"]["ids"].append("call-2")

    assert payload_mapping(evidence) == expected
