from __future__ import annotations

from codex_usage_tracker.compression.estimators import (
    ESTIMATOR_POLICY_V1,
    estimate_candidate,
    percentile,
)
from codex_usage_tracker.compression.evidence import (
    CallEvidence,
    CompressionEvidenceSnapshot,
    EvidenceCoverage,
)
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    EstimateRange,
)


def test_percentile_uses_linear_interpolation() -> None:
    values = [20, 30, 40, 50]

    assert percentile(values, 0.25) == 27.5
    assert percentile(values, 0.50) == 35.0
    assert percentile(values, 0.75) == 42.5


def test_direct_estimator_uses_explicit_avoidable_tokens() -> None:
    draft = candidate_draft(
        evidence_handles=({"record_id": "target", "direct_avoidable_tokens": 40},)
    )

    estimated = estimate_candidate(draft, snapshot([call("target", uncached=100)]))

    assert estimated.gross_estimate == EstimateRange(34, 40, 46)
    assert estimated.estimator_tier == "direct"
    assert estimated.confidence_grade == "high"
    assert estimated.confidence_score >= 0.85


def test_matched_estimator_uses_comparable_call_percentiles() -> None:
    calls = [
        call("target", uncached=100),
        call("peer-1", uncached=20),
        call("peer-2", uncached=30),
        call("peer-3", uncached=40),
        call("peer-4", uncached=50),
    ]

    estimated = estimate_candidate(candidate_draft(), snapshot(calls))

    assert estimated.gross_estimate == EstimateRange(58, 65, 72)
    assert estimated.estimator_tier == "matched"
    assert estimated.estimator_name == "matched-component-percentiles"
    assert "4 comparable calls" in estimated.estimator_assumptions
    assert estimated.confidence_grade == "medium"


def test_fallback_estimator_is_bounded_and_downgrades_confidence() -> None:
    estimated = estimate_candidate(
        candidate_draft(),
        snapshot([call("target", uncached=100)]),
    )

    assert ESTIMATOR_POLICY_V1.version == "compression-estimator-v1"
    assert estimated.gross_estimate == EstimateRange(15, 35, 55)
    assert estimated.estimator_tier == "fallback"
    assert estimated.confidence_grade == "low"
    assert estimated.confidence_score <= 0.45
    assert estimated.gross_estimate.high <= estimated.observed_exposure.uncached_input


def candidate_draft(
    *,
    evidence_handles: tuple[dict[str, object], ...] = ({"record_id": "target"},),
) -> CandidateDraft:
    return CandidateDraft(
        candidate_id="cmp_target",
        family="stale_context",
        pattern="Large stale context",
        pattern_key="record:target",
        detector_version="stale-v1",
        estimator_version="unestimated",
        record_ids=("target",),
        thread_keys=("thread:one",),
        observation_count=1,
        observed_exposure=ComponentExposure(uncached_input=100),
        claims=(
            ComponentClaim(
                record_id="target",
                component="uncached_input",
                exposure_tokens=100,
                estimate=EstimateRange(0, 0, 0),
            ),
        ),
        gross_estimate=EstimateRange(0, 0, 0),
        confidence_grade="medium",
        confidence_score=0.6,
        confidence_reasons=("detector evidence",),
        estimator_tier="unestimated",
        estimator_name="unestimated",
        estimator_assumptions=(),
        evidence_handles=evidence_handles,
        intervention={"family": "fresh_handoff"},
        verification={"tool": "usage_compression_profile"},
    )


def snapshot(calls: list[CallEvidence]) -> CompressionEvidenceSnapshot:
    return CompressionEvidenceSnapshot(
        calls=tuple(calls),
        turns=(),
        tool_calls=(),
        command_runs=(),
        file_events=(),
        content_fragments=(),
        compactions=(),
        coverage=EvidenceCoverage(call_count=len(calls)),
        source_revision="revision-1",
    )


def call(record_id: str, *, uncached: int) -> CallEvidence:
    return CallEvidence(
        record_id=record_id,
        session_id=f"session-{record_id}",
        thread_key="thread:one" if record_id == "target" else f"thread:{record_id}",
        event_timestamp="2026-07-10T10:00:00+00:00",
        model="gpt-5.5",
        effort="high",
        is_archived=False,
        thread_call_index=1,
        previous_record_id=None,
        exposure=ComponentExposure(
            cached_input=800,
            uncached_input=uncached,
            output=100,
            reasoning_output=20,
        ),
        cache_ratio=0.8,
        context_window_percent=0.5,
    )
