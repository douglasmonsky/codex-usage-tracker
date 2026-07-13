"""Pure overlap-aware what-if simulation for persisted compression candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from codex_usage_tracker.compression.attribution import (
    CapacityLedger,
    allocate_claim_ranges,
    allocate_overlaps,
    portfolio_estimate,
)
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    ComponentName,
    CompressionCandidate,
    EstimateRange,
)


@dataclass(frozen=True, slots=True)
class SimulationResult:
    """Deterministic selected-candidate portfolio and calculation trace."""

    selected_candidate_ids: tuple[str, ...]
    gross_estimate: EstimateRange
    overlap_adjusted_estimate: EstimateRange
    unique_eligible_capacity_tokens: int
    overlap_group_count: int
    candidates: tuple[dict[str, Any], ...]
    groups: tuple[dict[str, Any], ...]
    verification_plan: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "candidate_count": len(self.selected_candidate_ids),
            "gross_estimate": self.gross_estimate.as_dict(),
            "overlap_adjusted_estimate": self.overlap_adjusted_estimate.as_dict(),
            "unique_eligible_capacity_tokens": self.unique_eligible_capacity_tokens,
            "overlap_group_count": self.overlap_group_count,
            "candidates": [dict(row) for row in self.candidates],
            "groups": [dict(row) for row in self.groups],
            "verification_plan": [dict(row) for row in self.verification_plan],
        }


def simulate_candidate_portfolio(
    candidate_records: Sequence[Mapping[str, Any]],
    capacities: Mapping[tuple[str, str], int],
) -> SimulationResult:
    """Reallocate selected persisted candidates without double-counting capacity."""
    ordered_records = sorted(candidate_records, key=_candidate_id)
    drafts = tuple(_candidate_draft(record) for record in ordered_records)
    ledger = _capacity_ledger(drafts, capacities)
    allocated = tuple(allocate_overlaps(drafts, ledger))
    groups = _trace_groups(drafts, ledger)
    return SimulationResult(
        selected_candidate_ids=tuple(candidate.candidate_id for candidate in allocated),
        gross_estimate=_sum_ranges(draft.gross_estimate for draft in drafts),
        overlap_adjusted_estimate=portfolio_estimate(allocated),
        unique_eligible_capacity_tokens=sum(ledger.capacities.values()),
        overlap_group_count=sum(1 for group in groups if len(group["claims"]) > 1),
        candidates=_candidate_results(ordered_records, allocated),
        groups=groups,
        verification_plan=_verification_plan(ordered_records),
    )


def _candidate_draft(record: Mapping[str, Any]) -> CandidateDraft:
    claims = tuple(_claim(row) for row in _mapping_rows(record.get("claims")))
    confidence = _mapping(record.get("confidence"))
    estimator = _mapping(record.get("estimator"))
    return CandidateDraft(
        candidate_id=_candidate_id(record),
        family=_text(record, "family"),
        pattern=_text(record, "pattern"),
        pattern_key=_text(record, "pattern_key"),
        detector_version=_text(record, "detector_version"),
        estimator_version=_text(estimator, "version"),
        record_ids=tuple(sorted({claim.record_id for claim in claims})),
        thread_keys=_text_values(record.get("thread_keys")),
        observation_count=_integer(record.get("observation_count")),
        observed_exposure=_component_exposure(record.get("observed_exposure")),
        claims=claims,
        gross_estimate=_estimate(record.get("gross_estimate")),
        confidence_grade=_text(confidence, "grade", default="unknown"),
        confidence_score=_float(confidence.get("score")),
        confidence_reasons=_text_values(confidence.get("reasons")),
        estimator_tier=_text(estimator, "tier", default="unknown"),
        estimator_name=_text(estimator, "name", default="unknown"),
        estimator_assumptions=_text_values(estimator.get("assumptions")),
        evidence_handles=tuple(_mapping_rows(record.get("evidence_handles"))),
        intervention=_mapping(record.get("intervention")),
        verification=_mapping(record.get("verification")),
        first_seen=_optional_text(record.get("first_seen")),
        last_seen=_optional_text(record.get("last_seen")),
        data_quality_warnings=_text_values(record.get("data_quality_warnings")),
    )


def _capacity_ledger(
    drafts: Sequence[CandidateDraft],
    capacities: Mapping[tuple[str, str], int],
) -> CapacityLedger:
    selected_keys: set[tuple[str, ComponentName]] = {
        (claim.record_id, claim.component) for draft in drafts for claim in draft.claims
    }
    ledger_capacities: dict[tuple[str, ComponentName], int] = {}
    for key in sorted(selected_keys):
        if key in capacities:
            ledger_capacities[key] = max(0, int(capacities[key]))
    return CapacityLedger(ledger_capacities)


def _trace_groups(
    drafts: Sequence[CandidateDraft],
    ledger: CapacityLedger,
) -> tuple[dict[str, Any], ...]:
    grouped: dict[
        tuple[str, ComponentName],
        list[tuple[str, EstimateRange]],
    ] = defaultdict(list)
    for draft in drafts:
        for claim in draft.claims:
            grouped[(claim.record_id, claim.component)].append((draft.candidate_id, claim.estimate))
    return tuple(
        _trace_group(key, sorted(claims), ledger.capacity(*key))
        for key, claims in sorted(grouped.items())
    )


def _trace_group(
    key: tuple[str, ComponentName],
    claims: list[tuple[str, EstimateRange]],
    capacity: int,
) -> dict[str, Any]:
    allocations = allocate_claim_ranges(claims, capacity)
    return {
        "record_id": key[0],
        "component": key[1],
        "capacity_tokens": capacity,
        "claims": [
            {
                "candidate_id": candidate_id,
                "gross_estimate": estimate.as_dict(),
                "adjusted_estimate": allocations[candidate_id].as_dict(),
            }
            for candidate_id, estimate in claims
        ],
    }


def _candidate_results(
    records: Sequence[Mapping[str, Any]],
    candidates: Sequence[CompressionCandidate],
) -> tuple[dict[str, Any], ...]:
    records_by_id = {_candidate_id(record): record for record in records}
    return tuple(
        {
            "candidate_id": candidate.candidate_id,
            "family": candidate.draft.family,
            "gross_estimate": candidate.draft.gross_estimate.as_dict(),
            "persisted_adjusted_estimate": _estimate(
                records_by_id[candidate.candidate_id].get("adjusted_estimate")
            ).as_dict(),
            "simulated_adjusted_estimate": candidate.adjusted_estimate.as_dict(),
            "overlapping_candidate_ids": list(candidate.overlapping_candidate_ids),
        }
        for candidate in candidates
    )


def _verification_plan(
    records: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "candidate_id": _candidate_id(record),
            "intervention": _mapping(record.get("intervention")),
            "verification": _mapping(record.get("verification")),
        }
        for record in records
    )


def _claim(row: Mapping[str, Any]) -> ComponentClaim:
    component = cast(ComponentName, _text(row, "component"))
    return ComponentClaim(
        record_id=_text(row, "record_id"),
        component=component,
        exposure_tokens=_integer(row.get("exposure_tokens")),
        estimate=_estimate(row.get("estimate")),
    )


def _component_exposure(value: Any) -> ComponentExposure:
    exposure = _mapping(value)
    return ComponentExposure(
        cached_input=_integer(exposure.get("cached_input")),
        uncached_input=_integer(exposure.get("uncached_input")),
        output=_integer(exposure.get("output")),
        reasoning_output=_integer(exposure.get("reasoning_output")),
        content_fragment=_integer(exposure.get("content_fragment")),
        tool_output=_integer(exposure.get("tool_output")),
    )


def _sum_ranges(estimates: Iterable[EstimateRange]) -> EstimateRange:
    rows = tuple(estimates)
    return EstimateRange(
        low=sum(estimate.low for estimate in rows),
        likely=sum(estimate.likely for estimate in rows),
        high=sum(estimate.high for estimate in rows),
    )


def _estimate(value: Any) -> EstimateRange:
    estimate = _mapping(value)
    return EstimateRange(
        low=_integer(estimate.get("low")),
        likely=_integer(estimate.get("likely")),
        high=_integer(estimate.get("high")),
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _candidate_id(record: Mapping[str, Any]) -> str:
    return _text(record, "candidate_id")


def _text(value: Mapping[str, Any], key: str, *, default: str = "") -> str:
    item = value.get(key)
    return default if item is None else str(item)


def _text_values(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(sorted(str(item) for item in value))


def _integer(value: Any) -> int:
    return int(value) if value is not None else 0


def _float(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)
