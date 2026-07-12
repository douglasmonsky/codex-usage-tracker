"""Versioned low/likely/high estimators for compression candidates."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from codex_usage_tracker.compression.evidence import CompressionEvidenceSnapshot
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    EstimateRange,
)


@dataclass(frozen=True, slots=True)
class EstimatorPolicy:
    version: str
    minimum_matched_peers: int
    direct_low_factor: float
    direct_high_factor: float
    fallback_fractions: dict[str, tuple[float, float, float]]
    default_fallback: tuple[float, float, float]


ESTIMATOR_POLICY_V1 = EstimatorPolicy(
    version="compression-estimator-v1",
    minimum_matched_peers=4,
    direct_low_factor=0.85,
    direct_high_factor=1.15,
    fallback_fractions={
        "stale_context": (0.15, 0.35, 0.55),
        "cache_break_resume": (0.10, 0.30, 0.50),
        "file_rediscovery": (0.20, 0.45, 0.70),
        "shell_retry": (0.15, 0.40, 0.65),
        "validation_repetition": (0.10, 0.30, 0.50),
        "tool_output_bloat": (0.20, 0.50, 0.75),
    },
    default_fallback=(0.10, 0.30, 0.50),
)

_TIER_ORDER = {"fallback": 0, "matched": 1, "direct": 2}


def estimate_candidate(
    draft: CandidateDraft,
    snapshot: CompressionEvidenceSnapshot,
    *,
    policy: EstimatorPolicy = ESTIMATOR_POLICY_V1,
) -> CandidateDraft:
    """Estimate each component claim and return a reproducible candidate draft."""
    results = [_estimate_claim(draft, claim, snapshot, policy=policy) for claim in draft.claims]
    claims = tuple(
        replace(claim, estimate=estimate)
        for claim, (estimate, _tier, _assumption) in zip(draft.claims, results, strict=True)
    )
    tier = min((result[1] for result in results), key=_TIER_ORDER.__getitem__)
    assumptions = tuple(dict.fromkeys(result[2] for result in results))
    gross = EstimateRange(
        low=sum(claim.estimate.low for claim in claims),
        likely=sum(claim.estimate.likely for claim in claims),
        high=sum(claim.estimate.high for claim in claims),
    )
    grade, score = _confidence(tier, draft.confidence_score)
    return replace(
        draft,
        claims=claims,
        gross_estimate=gross,
        estimator_version=policy.version,
        estimator_tier=tier,
        estimator_name=_estimator_name(tier),
        estimator_assumptions=assumptions,
        confidence_grade=grade,
        confidence_score=score,
        confidence_reasons=tuple(
            dict.fromkeys((*draft.confidence_reasons, f"{tier} estimator tier"))
        ),
    )


def percentile(values: list[int], quantile: float) -> float:
    """Return a linearly interpolated percentile over integer observations."""
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= quantile <= 1:
        raise ValueError("quantile must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _estimate_claim(
    draft: CandidateDraft,
    claim: ComponentClaim,
    snapshot: CompressionEvidenceSnapshot,
    *,
    policy: EstimatorPolicy,
) -> tuple[EstimateRange, str, str]:
    direct = _direct_tokens(draft, claim)
    if direct is not None:
        return (
            _direct_range(direct, claim.exposure_tokens, policy),
            "direct",
            "explicit avoidable-token evidence",
        )
    peers = _comparable_exposures(draft, claim, snapshot)
    if len(peers) >= policy.minimum_matched_peers:
        return (
            _matched_range(claim.exposure_tokens, peers),
            "matched",
            f"{len(peers)} comparable calls",
        )
    fractions = policy.fallback_fractions.get(draft.family, policy.default_fallback)
    return (
        _fraction_range(claim.exposure_tokens, fractions),
        "fallback",
        f"family fallback fractions {fractions}",
    )


def _direct_tokens(draft: CandidateDraft, claim: ComponentClaim) -> int | None:
    for handle in draft.evidence_handles:
        if handle.get("record_id") != claim.record_id:
            continue
        component = handle.get("component")
        if component not in (None, claim.component):
            continue
        value = handle.get("direct_avoidable_tokens")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return min(claim.exposure_tokens, max(0, int(round(value))))
    return None


def _comparable_exposures(
    draft: CandidateDraft,
    claim: ComponentClaim,
    snapshot: CompressionEvidenceSnapshot,
) -> list[int]:
    target = snapshot.call(claim.record_id)
    if target is None:
        return []
    excluded = set(draft.record_ids)
    peers = [
        snapshot.component_exposure(row.record_id, claim.component)
        for row in snapshot.calls
        if row.record_id not in excluded
        and row.thread_key not in draft.thread_keys
        and row.model == target.model
        and row.effort == target.effort
    ]
    return [value for value in peers if value > 0]


def _direct_range(
    direct: int,
    exposure: int,
    policy: EstimatorPolicy,
) -> EstimateRange:
    return EstimateRange(
        low=_bounded_round(direct * policy.direct_low_factor, exposure),
        likely=_bounded_round(direct, exposure),
        high=_bounded_round(direct * policy.direct_high_factor, exposure),
    )


def _matched_range(exposure: int, peers: list[int]) -> EstimateRange:
    return EstimateRange(
        low=_bounded_round(exposure - percentile(peers, 0.75), exposure),
        likely=_bounded_round(exposure - percentile(peers, 0.50), exposure),
        high=_bounded_round(exposure - percentile(peers, 0.25), exposure),
    )


def _fraction_range(
    exposure: int,
    fractions: tuple[float, float, float],
) -> EstimateRange:
    return EstimateRange(
        low=_bounded_round(exposure * fractions[0], exposure),
        likely=_bounded_round(exposure * fractions[1], exposure),
        high=_bounded_round(exposure * fractions[2], exposure),
    )


def _bounded_round(value: float, exposure: int) -> int:
    return min(exposure, max(0, int(round(value))))


def _confidence(tier: str, detector_score: float) -> tuple[str, float]:
    if tier == "direct":
        return "high", max(0.85, detector_score)
    if tier == "matched":
        return "medium", min(0.8, max(0.6, detector_score))
    return "low", min(0.45, detector_score)


def _estimator_name(tier: str) -> str:
    return {
        "direct": "direct-avoidable-evidence",
        "matched": "matched-component-percentiles",
        "fallback": "family-fallback-range",
    }[tier]
