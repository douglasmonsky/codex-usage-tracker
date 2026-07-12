from __future__ import annotations

import pytest

from codex_usage_tracker.compression.attribution import (
    AttributionError,
    allocate_overlaps,
    build_capacity_ledger,
    portfolio_estimate,
    validate_candidate_claims,
)
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    EstimateRange,
)


def test_repeated_events_do_not_duplicate_whole_call_capacity() -> None:
    ledger = build_capacity_ledger(
        [
            {"record_id": "call-1", "uncached_input_tokens": 1000},
            {"record_id": "call-1", "uncached_input_tokens": 1000},
        ]
    )

    assert ledger.capacity("call-1", "uncached_input") == 1000
    assert ledger.record_ids == ("call-1",)


def test_capacity_ledger_keeps_token_components_separate() -> None:
    ledger = build_capacity_ledger(
        [
            {
                "record_id": "call-1",
                "cached_input_tokens": 500,
                "uncached_input_tokens": 200,
                "output_tokens": 30,
                "reasoning_output_tokens": 10,
                "content_fragment_tokens": 40,
                "tool_output_tokens": 50,
            }
        ]
    )

    assert ledger.capacity("call-1", "cached_input") == 500
    assert ledger.capacity("call-1", "tool_output") == 50


def test_validation_rejects_unknown_records_and_over_capacity_claims() -> None:
    ledger = build_capacity_ledger([{"record_id": "call-1", "uncached_input_tokens": 100}])

    with pytest.raises(AttributionError, match="unknown record_id"):
        validate_candidate_claims((candidate("a", "call-2", EstimateRange(1, 2, 3)),), ledger)
    with pytest.raises(AttributionError, match="exceeds record component capacity"):
        validate_candidate_claims(
            (candidate("a", "call-1", EstimateRange(50, 100, 101), exposure=200),),
            ledger,
        )


def test_overlap_allocation_caps_portfolio_at_unique_capacity() -> None:
    ledger = build_capacity_ledger([{"record_id": "call-1", "uncached_input_tokens": 1000}])
    drafts = (
        candidate("a", "call-1", EstimateRange(200, 600, 800), exposure=1000),
        candidate("b", "call-1", EstimateRange(200, 600, 800), exposure=1000),
    )

    adjusted = allocate_overlaps(drafts, ledger)

    assert portfolio_estimate(adjusted) == EstimateRange(low=400, likely=1000, high=1000)
    assert [row.adjusted_estimate for row in adjusted] == [
        EstimateRange(200, 500, 500),
        EstimateRange(200, 500, 500),
    ]
    assert adjusted[0].overlapping_candidate_ids == ("b",)
    assert adjusted[1].overlapping_candidate_ids == ("a",)


def test_overlap_rounding_is_deterministic_and_preserves_capacity() -> None:
    ledger = build_capacity_ledger([{"record_id": "call-1", "uncached_input_tokens": 10}])
    drafts = tuple(
        candidate(candidate_id, "call-1", EstimateRange(1, 7, 7), exposure=10)
        for candidate_id in ("c", "a", "b")
    )

    adjusted = allocate_overlaps(drafts, ledger)

    assert [row.candidate_id for row in adjusted] == ["a", "b", "c"]
    assert [row.adjusted_estimate.likely for row in adjusted] == [4, 3, 3]
    assert portfolio_estimate(adjusted).likely == 10


def test_disjoint_candidates_keep_their_gross_estimates() -> None:
    ledger = build_capacity_ledger(
        [
            {"record_id": "call-1", "uncached_input_tokens": 100},
            {"record_id": "call-2", "uncached_input_tokens": 100},
        ]
    )
    drafts = (
        candidate("a", "call-1", EstimateRange(10, 20, 30)),
        candidate("b", "call-2", EstimateRange(20, 30, 40)),
    )

    adjusted = allocate_overlaps(drafts, ledger)

    assert [row.adjusted_estimate for row in adjusted] == [
        EstimateRange(10, 20, 30),
        EstimateRange(20, 30, 40),
    ]
    assert portfolio_estimate(adjusted) == EstimateRange(30, 50, 70)


def candidate(
    candidate_id: str,
    record_id: str,
    estimate: EstimateRange,
    *,
    exposure: int = 100,
) -> CandidateDraft:
    claim = ComponentClaim(
        record_id=record_id,
        component="uncached_input",
        exposure_tokens=exposure,
        estimate=estimate,
    )
    return CandidateDraft(
        candidate_id=candidate_id,
        family="stale_context",
        pattern="Large context with little output",
        pattern_key=candidate_id,
        detector_version="stale-v1",
        estimator_version="compression-estimator-v1",
        record_ids=(record_id,),
        thread_keys=("thread:one",),
        observation_count=1,
        observed_exposure=ComponentExposure(uncached_input=exposure),
        claims=(claim,),
        gross_estimate=estimate,
        confidence_grade="medium",
        confidence_score=0.6,
        confidence_reasons=("synthetic fixture",),
        estimator_tier="fallback",
        estimator_name="stale-context-fallback",
        estimator_assumptions=("fixture",),
        evidence_handles=({"record_id": record_id},),
        intervention={"family": "fresh_handoff"},
        verification={"tool": "usage_compression_profile"},
    )
