"""Shared detector contract and candidate construction helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from codex_usage_tracker.compression.evidence import CompressionEvidenceSnapshot
from codex_usage_tracker.compression.identifiers import (
    stable_candidate_id,
    stable_scope_hash,
)
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    ComponentName,
    CompressionScope,
    EstimateRange,
)

UNESTIMATED_VERSION = "unestimated"
ZERO_ESTIMATE = EstimateRange(0, 0, 0)


class CompressionDetector(Protocol):
    """Detect one family of attributable compression opportunities."""

    family: str
    version: str

    def detect(
        self,
        snapshot: CompressionEvidenceSnapshot,
        scope: CompressionScope,
    ) -> list[CandidateDraft]: ...


def build_candidate(
    *,
    snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    family: str,
    pattern: str,
    pattern_key: str,
    detector_version: str,
    claims: Iterable[tuple[str, ComponentName, int]],
    observation_count: int,
    confidence_grade: str,
    confidence_score: float,
    confidence_reasons: Iterable[str],
    evidence_handles: Iterable[Mapping[str, Any]],
    intervention: Mapping[str, Any],
    verification: Mapping[str, Any],
    first_seen: str | None = None,
    last_seen: str | None = None,
    data_quality_warnings: Iterable[str] = (),
) -> CandidateDraft:
    """Build a deterministic, component-bounded unestimated candidate."""
    aggregated = _aggregate_claims(claims)
    if not aggregated:
        raise ValueError("candidate requires at least one positive component claim")
    component_claims = tuple(
        ComponentClaim(
            record_id=record_id,
            component=component,
            exposure_tokens=exposure,
            estimate=ZERO_ESTIMATE,
        )
        for (record_id, component), exposure in sorted(aggregated.items())
    )
    record_ids = tuple(sorted({claim.record_id for claim in component_claims}))
    call_by_record = {call.record_id: call for call in snapshot.calls}
    thread_keys = tuple(
        sorted(
            {
                call_by_record[record_id].thread_key
                for record_id in record_ids
                if record_id in call_by_record
            }
        )
    )
    exposure_by_component: dict[ComponentName, int] = defaultdict(int)
    for claim in component_claims:
        exposure_by_component[claim.component] += claim.exposure_tokens
    observed_exposure = ComponentExposure(**exposure_by_component)
    return CandidateDraft(
        candidate_id=stable_candidate_id(
            source_revision=snapshot.source_revision,
            scope_hash=stable_scope_hash(scope),
            family=family,
            pattern_key=pattern_key,
            detector_version=detector_version,
            estimator_version=UNESTIMATED_VERSION,
        ),
        family=family,
        pattern=pattern,
        pattern_key=pattern_key,
        detector_version=detector_version,
        estimator_version=UNESTIMATED_VERSION,
        record_ids=record_ids,
        thread_keys=thread_keys,
        observation_count=observation_count,
        observed_exposure=observed_exposure,
        claims=component_claims,
        gross_estimate=ZERO_ESTIMATE,
        confidence_grade=confidence_grade,
        confidence_score=confidence_score,
        confidence_reasons=tuple(confidence_reasons),
        estimator_tier="pending",
        estimator_name="pending",
        estimator_assumptions=(),
        evidence_handles=tuple(dict(handle) for handle in evidence_handles),
        intervention=dict(intervention),
        verification=dict(verification),
        first_seen=first_seen,
        last_seen=last_seen,
        data_quality_warnings=tuple(data_quality_warnings),
    )


def _aggregate_claims(
    claims: Iterable[tuple[str, ComponentName, int]],
) -> dict[tuple[str, ComponentName], int]:
    aggregated: dict[tuple[str, ComponentName], int] = defaultdict(int)
    for record_id, component, exposure in claims:
        if exposure > 0:
            aggregated[(record_id, component)] += exposure
    return dict(aggregated)
