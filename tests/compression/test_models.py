from __future__ import annotations

import pytest

from codex_usage_tracker.compression.identifiers import (
    stable_candidate_id,
    stable_scope_hash,
)
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    CompressionCandidate,
    CompressionScope,
    EstimateRange,
)


def test_estimate_range_requires_ordered_nonnegative_values() -> None:
    with pytest.raises(ValueError, match="0 <= low <= likely <= high"):
        EstimateRange(low=20, likely=10, high=30)
    with pytest.raises(ValueError, match="0 <= low <= likely <= high"):
        EstimateRange(low=-1, likely=0, high=1)


def test_component_exposure_tracks_supported_components() -> None:
    exposure = ComponentExposure(
        cached_input=100,
        uncached_input=200,
        output=30,
        reasoning_output=5,
        content_fragment=40,
        tool_output=50,
    )

    assert exposure.total == 425
    assert exposure.value("uncached_input") == 200
    assert exposure.as_dict() == {
        "cached_input": 100,
        "uncached_input": 200,
        "output": 30,
        "reasoning_output": 5,
        "content_fragment": 40,
        "tool_output": 50,
    }


def test_component_exposure_rejects_negative_values() -> None:
    with pytest.raises(ValueError, match="component exposure must be nonnegative"):
        ComponentExposure(tool_output=-1)


def test_scope_hash_is_stable_for_normalized_scope() -> None:
    scope = CompressionScope(
        since="2026-07-01T00:00:00Z",
        until="2026-07-11T00:00:00Z",
        thread="Usage Tracker",
        include_archived=True,
        model="gpt-5.6-sol",
        effort="high",
    )

    assert stable_scope_hash(scope) == stable_scope_hash(scope)
    assert stable_scope_hash(scope) != stable_scope_hash(
        CompressionScope(**{**scope.as_dict(), "include_archived": False})
    )


def test_candidate_id_is_deterministic_for_revision_scope_and_policy() -> None:
    arguments = {
        "source_revision": "rev-1",
        "scope_hash": "scope-1",
        "family": "file_rediscovery",
        "pattern_key": "path:abc",
        "detector_version": "file-v1",
        "estimator_version": "compression-estimator-v1",
    }

    candidate_id = stable_candidate_id(**arguments)

    assert candidate_id == stable_candidate_id(**arguments)
    assert candidate_id.startswith("cmp_")
    assert candidate_id != stable_candidate_id(**{**arguments, "source_revision": "rev-2"})


def test_candidate_draft_requires_unique_records_and_matching_claims() -> None:
    with pytest.raises(ValueError, match="record_ids must be unique"):
        candidate_draft(record_ids=("call-1", "call-1"))
    with pytest.raises(ValueError, match="claim record_id must belong to candidate"):
        candidate_draft(
            claims=(
                ComponentClaim(
                    record_id="call-2",
                    component="uncached_input",
                    exposure_tokens=100,
                    estimate=EstimateRange(10, 20, 30),
                ),
            )
        )


def test_final_candidate_cannot_exceed_gross_estimate() -> None:
    draft = candidate_draft()
    with pytest.raises(ValueError, match="adjusted estimate cannot exceed gross estimate"):
        CompressionCandidate(
            draft=draft,
            adjusted_estimate=EstimateRange(20, 50, 80),
        )


def candidate_draft(
    *,
    record_ids: tuple[str, ...] = ("call-1",),
    claims: tuple[ComponentClaim, ...] | None = None,
) -> CandidateDraft:
    return CandidateDraft(
        candidate_id="cmp_candidate",
        family="stale_context",
        pattern="Large context with little output",
        pattern_key="thread:one",
        detector_version="stale-v1",
        estimator_version="compression-estimator-v1",
        record_ids=record_ids,
        thread_keys=("thread:one",),
        observation_count=1,
        observed_exposure=ComponentExposure(uncached_input=100),
        claims=claims
        or (
            ComponentClaim(
                record_id="call-1",
                component="uncached_input",
                exposure_tokens=100,
                estimate=EstimateRange(10, 30, 50),
            ),
        ),
        gross_estimate=EstimateRange(10, 30, 50),
        confidence_grade="medium",
        confidence_score=0.6,
        confidence_reasons=("fallback estimator",),
        estimator_tier="fallback",
        estimator_name="stale-context-fallback",
        estimator_assumptions=("30 percent likely savings",),
        evidence_handles=({"record_id": "call-1"},),
        intervention={"family": "fresh_handoff"},
        verification={"tool": "usage_compression_profile"},
    )
