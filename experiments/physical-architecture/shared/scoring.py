from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import Enum

from .canonical import canonical_sha256


class ScoringContractError(ValueError):
    pass


class ScoreDimension(str, Enum):
    ORDINARY_TAIL = "ordinary_tail_latency_write_amplification"
    COLD_BUILD = "cold_build_expansion_latency"
    QUERY_EFFICIENCY = "named_query_evidence_mcp_payload_efficiency"
    STORAGE = "database_index_wal_size"
    CRASH_RECOVERY = "crash_recovery_lifecycle_simplicity"
    EVIDENCE_STABILITY = "evidence_stability_selector_cost"
    OPERABILITY = "implementation_complexity_operability"


SCORE_WEIGHTS = {
    ScoreDimension.ORDINARY_TAIL: 25,
    ScoreDimension.COLD_BUILD: 20,
    ScoreDimension.QUERY_EFFICIENCY: 15,
    ScoreDimension.STORAGE: 15,
    ScoreDimension.CRASH_RECOVERY: 10,
    ScoreDimension.EVIDENCE_STABILITY: 10,
    ScoreDimension.OPERABILITY: 5,
}


@dataclass(frozen=True)
class DistributionSummary:
    sample_count: int
    median: Decimal
    p95: Decimal
    maximum: Decimal
    coefficient_of_variation: Decimal


def distribution_summary(values: Iterable[int | Decimal]) -> DistributionSummary:
    ordered = sorted(Decimal(value) for value in values)
    if len(ordered) < 5:
        raise ScoringContractError("performance distributions require five unprofiled runs")
    count = len(ordered)
    middle = count // 2
    median = ordered[middle] if count % 2 else (ordered[middle - 1] + ordered[middle]) / Decimal(2)
    p95_index = ((95 * count + 99) // 100) - 1
    mean = sum(ordered, Decimal(0)) / Decimal(count)
    variance = sum((value - mean) ** 2 for value in ordered) / Decimal(count)
    with localcontext() as context:
        context.prec = 28
        coefficient = Decimal(0) if mean == 0 else variance.sqrt() / abs(mean)
    return DistributionSummary(
        sample_count=count,
        median=median,
        p95=ordered[p95_index],
        maximum=ordered[-1],
        coefficient_of_variation=coefficient.quantize(
            Decimal("0.000000001"),
            rounding=ROUND_HALF_EVEN,
        ),
    )


@dataclass(frozen=True)
class DimensionCost:
    dimension: ScoreDimension
    value: Decimal
    source_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.value < 0:
            raise ScoringContractError("dimension cost must be nonnegative")
        if not self.source_case_ids:
            raise ScoringContractError("dimension cost must name its source cases")
        if len(set(self.source_case_ids)) != len(self.source_case_ids):
            raise ScoringContractError("dimension source case IDs must be unique")
        if self.source_case_ids != tuple(sorted(self.source_case_ids)):
            raise ScoringContractError("dimension source case IDs must be sorted")


@dataclass(frozen=True)
class CandidateScoreInput:
    candidate_id: str
    fixture_manifest_digest: str
    fixture_oracle_digest: str
    code_commit: str
    scale: str
    costs: tuple[DimensionCost, ...]

    def __post_init__(self) -> None:
        if self.candidate_id not in {"A", "C", "D"}:
            raise ScoringContractError("score input candidate must be A, C, or D")
        dimensions = {cost.dimension for cost in self.costs}
        if dimensions != set(ScoreDimension) or len(self.costs) != len(ScoreDimension):
            raise ScoringContractError("score input must contain each weighted dimension once")
        for digest in (self.fixture_manifest_digest, self.fixture_oracle_digest):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ScoringContractError("score fixture digests must be SHA-256")
        if len(self.code_commit) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_commit
        ):
            raise ScoringContractError("score code commit must be a full SHA-1 object ID")
        if self.scale not in {"standard", "production", "growth"}:
            raise ScoringContractError("score scale must be standard, production, or growth")

    @property
    def digest(self) -> str:
        return canonical_sha256(
            {
                "schema": "codex-usage-tracker.physical-bakeoff-score-input.v1",
                "candidate_id": self.candidate_id,
                "fixture_manifest_digest": self.fixture_manifest_digest,
                "fixture_oracle_digest": self.fixture_oracle_digest,
                "code_commit": self.code_commit,
                "scale": self.scale,
                "costs": [
                    {
                        "dimension": cost.dimension.value,
                        "value": str(cost.value),
                        "source_case_ids": cost.source_case_ids,
                    }
                    for cost in sorted(self.costs, key=lambda item: item.dimension.value)
                ],
            }
        )


@dataclass(frozen=True)
class RankedCandidate:
    candidate_id: str
    weighted_score: Decimal
    dimension_scores: tuple[tuple[ScoreDimension, Decimal], ...]
    input_digest: str


def rank_candidates(inputs: Iterable[CandidateScoreInput]) -> tuple[RankedCandidate, ...]:
    candidates = tuple(sorted(inputs, key=lambda item: item.candidate_id))
    if not candidates:
        raise ScoringContractError("at least one candidate score input is required")
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise ScoringContractError("candidate score inputs contain duplicate candidates")
    fixtures = {
        (candidate.fixture_manifest_digest, candidate.fixture_oracle_digest, candidate.scale)
        for candidate in candidates
    }
    if len(fixtures) != 1:
        raise ScoringContractError("candidate score inputs must use identical fixture and scale")

    costs_by_candidate = {
        candidate.candidate_id: {cost.dimension: cost.value for cost in candidate.costs}
        for candidate in candidates
    }
    scores: dict[str, dict[ScoreDimension, Decimal]] = {
        candidate.candidate_id: {} for candidate in candidates
    }
    for dimension in ScoreDimension:
        values = [costs_by_candidate[candidate.candidate_id][dimension] for candidate in candidates]
        minimum = min(values)
        maximum = max(values)
        for candidate in candidates:
            value = costs_by_candidate[candidate.candidate_id][dimension]
            if maximum == minimum:
                score = Decimal(100)
            else:
                score = (maximum - value) * Decimal(100) / (maximum - minimum)
            scores[candidate.candidate_id][dimension] = score.quantize(
                Decimal("0.000001"),
                rounding=ROUND_HALF_EVEN,
            )

    ranked: list[RankedCandidate] = []
    for candidate in candidates:
        dimension_scores = tuple(
            (dimension, scores[candidate.candidate_id][dimension]) for dimension in ScoreDimension
        )
        weighted = sum(
            (
                score * Decimal(SCORE_WEIGHTS[dimension]) / Decimal(100)
                for dimension, score in dimension_scores
            ),
            Decimal(0),
        ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
        ranked.append(
            RankedCandidate(
                candidate_id=candidate.candidate_id,
                weighted_score=weighted,
                dimension_scores=dimension_scores,
                input_digest=candidate.digest,
            )
        )
    return tuple(sorted(ranked, key=lambda item: (-item.weighted_score, item.candidate_id)))
