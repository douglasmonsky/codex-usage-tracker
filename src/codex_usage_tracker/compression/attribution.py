"""Bounded record-component attribution for compression candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from codex_usage_tracker.compression.models import (
    COMPONENT_NAMES,
    CandidateDraft,
    ComponentName,
    CompressionCandidate,
    EstimateRange,
)

_ROW_COMPONENT_FIELDS: dict[ComponentName, str] = {
    "cached_input": "cached_input_tokens",
    "uncached_input": "uncached_input_tokens",
    "output": "output_tokens",
    "reasoning_output": "reasoning_output_tokens",
    "content_fragment": "content_fragment_tokens",
    "tool_output": "tool_output_tokens",
}


class AttributionError(ValueError):
    """Raised when candidate claims violate the capacity ledger."""


@dataclass(frozen=True, slots=True)
class CapacityLedger:
    """Unique token capacity keyed by record and component."""

    capacities: dict[tuple[str, ComponentName], int]

    @property
    def record_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record_id for record_id, _component in self.capacities}))

    def capacity(self, record_id: str, component: ComponentName) -> int:
        return self.capacities.get((record_id, component), 0)


def build_capacity_ledger(rows: Iterable[dict[str, Any]]) -> CapacityLedger:
    """Build unique record capacities without multiplying repeated event rows."""
    capacities: dict[tuple[str, ComponentName], int] = {}
    for row in rows:
        record_id = str(row.get("record_id") or "")
        if not record_id:
            raise AttributionError("capacity row requires record_id")
        cached = _nonnegative_int(row.get("cached_input_tokens"))
        input_tokens = _nonnegative_int(row.get("input_tokens"))
        derived_uncached = max(0, input_tokens - cached)
        for component in COMPONENT_NAMES:
            field = _ROW_COMPONENT_FIELDS[component]
            value = _nonnegative_int(row.get(field))
            if component == "uncached_input" and row.get(field) is None:
                value = derived_uncached
            key = (record_id, component)
            capacities[key] = max(capacities.get(key, 0), value)
    return CapacityLedger(capacities)


def validate_candidate_claims(
    drafts: Iterable[CandidateDraft],
    ledger: CapacityLedger,
) -> None:
    """Validate candidate claims against unique record-component capacity."""
    seen_candidates: set[str] = set()
    known_records = set(ledger.record_ids)
    for draft in drafts:
        if draft.candidate_id in seen_candidates:
            raise AttributionError(f"duplicate candidate_id: {draft.candidate_id}")
        seen_candidates.add(draft.candidate_id)
        seen_claims: set[tuple[str, ComponentName]] = set()
        for claim in draft.claims:
            if claim.record_id not in known_records:
                raise AttributionError(f"unknown record_id in candidate claim: {claim.record_id}")
            claim_key = (claim.record_id, claim.component)
            if claim_key in seen_claims:
                raise AttributionError(
                    "candidate must combine duplicate record component claims before allocation"
                )
            seen_claims.add(claim_key)
            capacity = ledger.capacity(claim.record_id, claim.component)
            if claim.exposure_tokens > capacity or claim.estimate.high > capacity:
                raise AttributionError(
                    "candidate claim exceeds record component capacity: "
                    f"{claim.record_id}/{claim.component}"
                )


def allocate_overlaps(
    drafts: Iterable[CandidateDraft],
    ledger: CapacityLedger,
) -> list[CompressionCandidate]:
    """Allocate competing claims without exceeding unique component capacity."""
    ordered = sorted(drafts, key=lambda draft: draft.candidate_id)
    validate_candidate_claims(ordered, ledger)
    grouped_claims = _group_claims(ordered)
    overlaps: dict[str, set[str]] = defaultdict(set)
    adjusted: dict[str, list[int]] = {draft.candidate_id: [0, 0, 0] for draft in ordered}

    for (record_id, component), claims in grouped_claims.items():
        _apply_group_allocation(
            claims=claims,
            capacity=ledger.capacity(record_id, component),
            adjusted=adjusted,
            overlaps=overlaps,
        )

    return [
        CompressionCandidate(
            draft=draft,
            adjusted_estimate=EstimateRange(*adjusted[draft.candidate_id]),
            overlapping_candidate_ids=tuple(sorted(overlaps[draft.candidate_id])),
        )
        for draft in ordered
    ]


def portfolio_estimate(candidates: Iterable[CompressionCandidate]) -> EstimateRange:
    """Sum overlap-adjusted candidate estimates."""
    rows = list(candidates)
    return EstimateRange(
        low=sum(row.adjusted_estimate.low for row in rows),
        likely=sum(row.adjusted_estimate.likely for row in rows),
        high=sum(row.adjusted_estimate.high for row in rows),
    )


def _group_claims(
    drafts: list[CandidateDraft],
) -> dict[tuple[str, ComponentName], list[tuple[str, EstimateRange]]]:
    grouped: dict[tuple[str, ComponentName], list[tuple[str, EstimateRange]]] = defaultdict(list)
    for draft in drafts:
        for claim in draft.claims:
            grouped[(claim.record_id, claim.component)].append((draft.candidate_id, claim.estimate))
    return grouped


def _apply_group_allocation(
    *,
    claims: list[tuple[str, EstimateRange]],
    capacity: int,
    adjusted: dict[str, list[int]],
    overlaps: dict[str, set[str]],
) -> None:
    allocations = _allocate_claim_ranges(claims, capacity)
    active_ids = sorted(candidate_id for candidate_id, estimate in claims if estimate.high > 0)
    _record_overlaps(active_ids, overlaps)
    for candidate_id, estimate in allocations.items():
        _add_estimate(adjusted[candidate_id], estimate)


def _record_overlaps(active_ids: list[str], overlaps: dict[str, set[str]]) -> None:
    if len(active_ids) < 2:
        return
    for candidate_id in active_ids:
        overlaps[candidate_id].update(other for other in active_ids if other != candidate_id)


def _add_estimate(total: list[int], estimate: EstimateRange) -> None:
    total[0] += estimate.low
    total[1] += estimate.likely
    total[2] += estimate.high


def _allocate_claim_ranges(
    claims: list[tuple[str, EstimateRange]],
    capacity: int,
) -> dict[str, EstimateRange]:
    current = {candidate_id: 0 for candidate_id, _estimate in claims}
    bounds: list[dict[str, int]] = []
    for attribute in ("low", "likely", "high"):
        targets = {
            candidate_id: int(getattr(estimate, attribute)) for candidate_id, estimate in claims
        }
        remaining = max(0, capacity - sum(current.values()))
        desired = {
            candidate_id: max(0, target - current[candidate_id])
            for candidate_id, target in targets.items()
        }
        increments = _allocate_amounts(desired, remaining)
        current = {
            candidate_id: current[candidate_id] + increments[candidate_id]
            for candidate_id in current
        }
        bounds.append(dict(current))
    return {
        candidate_id: EstimateRange(
            low=bounds[0][candidate_id],
            likely=bounds[1][candidate_id],
            high=bounds[2][candidate_id],
        )
        for candidate_id in sorted(current)
    }


def _allocate_amounts(desired: dict[str, int], capacity: int) -> dict[str, int]:
    total = sum(desired.values())
    if total <= capacity:
        return dict(desired)
    if capacity <= 0 or total <= 0:
        return {candidate_id: 0 for candidate_id in desired}
    allocated = {
        candidate_id: amount * capacity // total for candidate_id, amount in desired.items()
    }
    remainder = capacity - sum(allocated.values())
    priority = sorted(
        desired,
        key=lambda candidate_id: (
            -(desired[candidate_id] * capacity % total),
            candidate_id,
        ),
    )
    for candidate_id in priority[:remainder]:
        allocated[candidate_id] += 1
    return allocated


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
