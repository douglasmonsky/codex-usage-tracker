"""Stable internal contracts for compression analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ComponentName = Literal[
    "cached_input",
    "uncached_input",
    "output",
    "reasoning_output",
    "content_fragment",
    "tool_output",
]

COMPONENT_NAMES: tuple[ComponentName, ...] = (
    "cached_input",
    "uncached_input",
    "output",
    "reasoning_output",
    "content_fragment",
    "tool_output",
)


@dataclass(frozen=True, slots=True)
class EstimateRange:
    """Ordered low, likely, and high token estimate."""

    low: int
    likely: int
    high: int

    def __post_init__(self) -> None:
        if not 0 <= self.low <= self.likely <= self.high:
            raise ValueError("estimate range requires 0 <= low <= likely <= high")

    def as_dict(self) -> dict[str, int]:
        return {"low": self.low, "likely": self.likely, "high": self.high}

    def bounded_by(self, other: EstimateRange) -> bool:
        return self.low <= other.low and self.likely <= other.likely and self.high <= other.high


@dataclass(frozen=True, slots=True)
class ComponentExposure:
    """Observed token exposure separated by attributable component."""

    cached_input: int = 0
    uncached_input: int = 0
    output: int = 0
    reasoning_output: int = 0
    content_fragment: int = 0
    tool_output: int = 0

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.as_dict().values()):
            raise ValueError("component exposure must be nonnegative")

    @property
    def total(self) -> int:
        return sum(self.as_dict().values())

    def value(self, component: ComponentName) -> int:
        if component not in COMPONENT_NAMES:
            raise ValueError(f"unsupported token component: {component}")
        return int(getattr(self, component))

    def as_dict(self) -> dict[str, int]:
        return {component: int(getattr(self, component)) for component in COMPONENT_NAMES}


@dataclass(frozen=True, slots=True)
class ComponentClaim:
    """One candidate's claim against one record and token component."""

    record_id: str
    component: ComponentName
    exposure_tokens: int
    estimate: EstimateRange

    def __post_init__(self) -> None:
        if not self.record_id:
            raise ValueError("claim record_id is required")
        if self.component not in COMPONENT_NAMES:
            raise ValueError(f"unsupported token component: {self.component}")
        if self.exposure_tokens < 0:
            raise ValueError("claim exposure_tokens must be nonnegative")
        if self.estimate.high > self.exposure_tokens:
            raise ValueError("claim estimate cannot exceed exposure")

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "component": self.component,
            "exposure_tokens": self.exposure_tokens,
            "estimate": self.estimate.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class CompressionScope:
    """Normalized filters defining one reproducible compression analysis."""

    since: str | None = None
    until: str | None = None
    thread: str | None = None
    include_archived: bool = False
    model: str | None = None
    effort: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "since": self.since,
            "until": self.until,
            "thread": self.thread,
            "include_archived": self.include_archived,
            "model": self.model,
            "effort": self.effort,
        }


@dataclass(frozen=True, slots=True)
class CandidateDraft:
    """Detector output before overlap allocation."""

    candidate_id: str
    family: str
    pattern: str
    pattern_key: str
    detector_version: str
    estimator_version: str
    record_ids: tuple[str, ...]
    thread_keys: tuple[str, ...]
    observation_count: int
    observed_exposure: ComponentExposure
    claims: tuple[ComponentClaim, ...]
    gross_estimate: EstimateRange
    confidence_grade: str
    confidence_score: float
    confidence_reasons: tuple[str, ...]
    estimator_tier: str
    estimator_name: str
    estimator_assumptions: tuple[str, ...]
    evidence_handles: tuple[dict[str, Any], ...]
    intervention: dict[str, Any]
    verification: dict[str, Any]
    first_seen: str | None = None
    last_seen: str | None = None
    data_quality_warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.family or not self.pattern_key:
            raise ValueError("candidate identity fields are required")
        if not self.record_ids:
            raise ValueError("candidate requires at least one record_id")
        if len(set(self.record_ids)) != len(self.record_ids):
            raise ValueError("candidate record_ids must be unique")
        if len(set(self.thread_keys)) != len(self.thread_keys):
            raise ValueError("candidate thread_keys must be unique")
        if self.observation_count < 1:
            raise ValueError("candidate observation_count must be positive")
        if not 0 <= self.confidence_score <= 1:
            raise ValueError("candidate confidence_score must be between 0 and 1")
        for claim in self.claims:
            if claim.record_id not in self.record_ids:
                raise ValueError("claim record_id must belong to candidate record_ids")
        claim_total = EstimateRange(
            low=sum(claim.estimate.low for claim in self.claims),
            likely=sum(claim.estimate.likely for claim in self.claims),
            high=sum(claim.estimate.high for claim in self.claims),
        )
        if claim_total != self.gross_estimate:
            raise ValueError("candidate gross_estimate must equal the sum of component claims")

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "family": self.family,
            "pattern": self.pattern,
            "pattern_key": self.pattern_key,
            "detector_version": self.detector_version,
            "estimator_version": self.estimator_version,
            "record_ids": list(self.record_ids),
            "thread_keys": list(self.thread_keys),
            "observation_count": self.observation_count,
            "observed_exposure": self.observed_exposure.as_dict(),
            "claims": [claim.as_dict() for claim in self.claims],
            "gross_estimate": self.gross_estimate.as_dict(),
            "confidence": {
                "grade": self.confidence_grade,
                "score": self.confidence_score,
                "reasons": list(self.confidence_reasons),
            },
            "estimator": {
                "tier": self.estimator_tier,
                "name": self.estimator_name,
                "version": self.estimator_version,
                "assumptions": list(self.estimator_assumptions),
            },
            "evidence_handles": list(self.evidence_handles),
            "intervention": dict(self.intervention),
            "verification": dict(self.verification),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "data_quality_warnings": list(self.data_quality_warnings),
        }


@dataclass(frozen=True, slots=True)
class CompressionCandidate:
    """Candidate after overlap-aware allocation."""

    draft: CandidateDraft
    adjusted_estimate: EstimateRange
    overlapping_candidate_ids: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.adjusted_estimate.bounded_by(self.draft.gross_estimate):
            raise ValueError("adjusted estimate cannot exceed gross estimate")
        if len(set(self.overlapping_candidate_ids)) != len(self.overlapping_candidate_ids):
            raise ValueError("overlapping_candidate_ids must be unique")

    @property
    def candidate_id(self) -> str:
        return self.draft.candidate_id

    def as_dict(self) -> dict[str, Any]:
        payload = self.draft.as_dict()
        payload["adjusted_estimate"] = self.adjusted_estimate.as_dict()
        payload["overlapping_candidate_ids"] = list(self.overlapping_candidate_ids)
        return payload
