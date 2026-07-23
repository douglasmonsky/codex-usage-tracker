"""Finding and recommendation contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, cast

from codex_usage_tracker.core.contracts.common import MetricValue, immutable_snapshot

ClaimType = Literal["observed", "derived", "estimated", "inferred", "recommended"]
FindingSeverity = Literal["info", "low", "medium", "high"]
FindingConfidence = Literal["exact", "high", "medium", "low", "unknown"]


@dataclass(frozen=True)
class RecommendationV1:
    """Action supported by one or more non-recommendation findings."""

    schema: Literal["codex-usage-tracker.recommendation.v1"] = field(
        default="codex-usage-tracker.recommendation.v1", init=False
    )
    recommendation_id: str
    action: str
    rationale: str
    supporting_claim_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "supporting_claim_ids", tuple(self.supporting_claim_ids))
        if not self.supporting_claim_ids:
            raise ValueError("recommendation requires a supporting claim")


@dataclass(frozen=True)
class FindingV1:
    """One typed analytical claim and its evidence references."""

    schema: Literal["codex-usage-tracker.finding.v1"] = field(
        default="codex-usage-tracker.finding.v1", init=False
    )
    finding_id: str
    title: str
    claim_type: ClaimType
    severity: FindingSeverity
    confidence: FindingConfidence
    statement: str
    metrics: Mapping[str, MetricValue]
    evidence_ids: tuple[str, ...]
    caveat_codes: tuple[str, ...]
    recommendation: RecommendationV1 | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "metrics",
            cast(Mapping[str, MetricValue], immutable_snapshot(self.metrics)),
        )
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        object.__setattr__(self, "caveat_codes", tuple(self.caveat_codes))


def validate_findings(findings: Sequence[FindingV1]) -> None:
    """Reject recommendations without a present non-recommended supporting claim."""
    supporting_ids = {
        finding.finding_id for finding in findings if finding.claim_type != "recommended"
    }
    for finding in findings:
        recommendation = finding.recommendation
        if finding.claim_type == "recommended" and recommendation is None:
            raise ValueError(f"recommended finding requires recommendation: {finding.finding_id}")
        if recommendation is None:
            continue
        if not set(recommendation.supporting_claim_ids) <= supporting_ids:
            raise ValueError(f"unsupported recommendation: {recommendation.recommendation_id}")
