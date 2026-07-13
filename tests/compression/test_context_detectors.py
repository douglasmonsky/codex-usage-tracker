from __future__ import annotations

from codex_usage_tracker.compression.context_detectors import (
    CacheBreakResumeDetector,
    StaleContextDetector,
)
from codex_usage_tracker.compression.models import CompressionScope, EstimateRange
from tests.compression.compression_helpers import call, snapshot


def test_stale_context_claims_only_uncached_input() -> None:
    evidence = snapshot(
        calls=(
            call(
                "stale",
                uncached=2_000,
                output=100,
                context_percent=0.8,
            ),
        )
    )
    detector = StaleContextDetector(
        min_uncached_input_tokens=1_000,
        max_output_tokens=200,
        min_context_window_percent=0.5,
    )

    candidates = detector.detect(evidence, CompressionScope())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.family == "stale_context"
    assert candidate.observed_exposure.uncached_input == 2_000
    assert candidate.observed_exposure.output == 0
    assert candidate.observed_exposure.reasoning_output == 0
    assert candidate.claims[0].component == "uncached_input"
    assert candidate.claims[0].estimate == EstimateRange(0, 0, 0)
    assert candidate.candidate_id.startswith("cmp_")
    assert detector.detect(evidence, CompressionScope())[0].candidate_id == candidate.candidate_id


def test_cache_break_requires_a_high_cache_predecessor_and_claims_current_uncached() -> None:
    evidence = snapshot(
        calls=(
            call("warm", uncached=100, cache_ratio=0.9, index=1),
            call(
                "cold-resume",
                uncached=2_500,
                cache_ratio=0.2,
                previous="warm",
                index=2,
            ),
        )
    )
    detector = CacheBreakResumeDetector(
        min_uncached_input_tokens=1_000,
        max_cache_ratio=0.4,
        min_previous_cache_ratio=0.8,
    )

    candidates = detector.detect(evidence, CompressionScope())

    assert [candidate.family for candidate in candidates] == ["cache_break_resume"]
    assert candidates[0].record_ids == ("cold-resume",)
    assert candidates[0].claims[0].exposure_tokens == 2_500
    assert candidates[0].evidence_handles[0]["previous_record_id"] == "warm"


def test_context_detectors_do_not_emit_weak_evidence() -> None:
    evidence = snapshot(calls=(call("ordinary", uncached=100, output=500),))

    assert StaleContextDetector().detect(evidence, CompressionScope()) == []
    assert CacheBreakResumeDetector().detect(evidence, CompressionScope()) == []
