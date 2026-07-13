"""Versioned low/likely/high estimators for compression candidates."""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import TypeAlias

from codex_usage_tracker.compression.evidence import CompressionEvidenceSnapshot
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentName,
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
_GroupKey: TypeAlias = tuple[str | None, str | None, ComponentName]


@dataclass(frozen=True, slots=True)
class PeerDistribution:
    count: int
    p25: float
    p50: float
    p75: float


class EstimatorIndex:
    """Lazy component distributions shared by every candidate in one run."""

    def __init__(self, snapshot: CompressionEvidenceSnapshot) -> None:
        self._snapshot = snapshot
        self._calls = {call.record_id: call for call in snapshot.calls}
        self._content = (
            dict(snapshot.content_exposure_by_record)
            if snapshot.content_exposure_by_record
            else _content_totals(snapshot)
        )
        self._tool_output = (
            dict(snapshot.tool_output_exposure_by_record)
            if snapshot.tool_output_exposure_by_record
            else _tool_output_totals(snapshot)
        )
        self._groups: dict[ComponentName, dict[_GroupKey, tuple[int, ...]]] = {}
        self._threads: dict[ComponentName, dict[tuple[_GroupKey, str], tuple[int, ...]]] = {}
        self._peer_cache: dict[
            tuple[_GroupKey, tuple[str, ...], tuple[str, ...]], PeerDistribution
        ] = {}

    def component_exposure(self, record_id: str, component: ComponentName) -> int:
        call = self._calls.get(record_id)
        if call is None:
            return 0
        if component == "content_fragment":
            return self._content.get(record_id, 0)
        if component == "tool_output":
            return self._tool_output.get(record_id, 0)
        return call.exposure.value(component)

    def peers(self, draft: CandidateDraft, claim: ComponentClaim) -> PeerDistribution:
        target = self._calls.get(claim.record_id)
        if target is None:
            return PeerDistribution(0, 0, 0, 0)
        self._ensure_component(claim.component)
        group = (target.model, target.effort, claim.component)
        values = self._groups[claim.component].get(group, ())
        excluded_threads = tuple(sorted(set(draft.thread_keys)))
        cache_key: tuple[_GroupKey, tuple[str, ...], tuple[str, ...]] = (
            group,
            excluded_threads,
            (),
        )
        cached = self._peer_cache.get(cache_key)
        if cached is not None:
            return cached
        extra_records = () if excluded_threads else tuple(sorted(draft.record_ids))
        cache_key = (group, excluded_threads, extra_records)
        cached = self._peer_cache.get(cache_key)
        if cached is not None:
            return cached
        excluded = self._excluded_values(
            group,
            claim.component,
            excluded_threads,
            extra_records,
        )
        distribution = _remaining_distribution(values, excluded)
        self._peer_cache[cache_key] = distribution
        return distribution

    def _ensure_component(self, component: ComponentName) -> None:
        if component in self._groups:
            return
        grouped: dict[_GroupKey, list[int]] = defaultdict(list)
        threaded: dict[tuple[_GroupKey, str], list[int]] = defaultdict(list)
        for call in self._snapshot.calls:
            value = self.component_exposure(call.record_id, component)
            if value <= 0:
                continue
            group = (call.model, call.effort, component)
            grouped[group].append(value)
            threaded[(group, call.thread_key)].append(value)
        self._groups[component] = {key: tuple(sorted(values)) for key, values in grouped.items()}
        self._threads[component] = {key: tuple(sorted(values)) for key, values in threaded.items()}

    def _excluded_values(
        self,
        group: _GroupKey,
        component: ComponentName,
        thread_keys: tuple[str, ...],
        record_ids: tuple[str, ...],
    ) -> tuple[int, ...]:
        values = [
            value
            for thread_key in thread_keys
            for value in self._threads[component].get((group, thread_key), ())
        ]
        values.extend(self.component_exposure(record_id, component) for record_id in record_ids)
        return tuple(sorted(value for value in values if value > 0))


def build_estimator_index(snapshot: CompressionEvidenceSnapshot) -> EstimatorIndex:
    return EstimatorIndex(snapshot)


def estimate_candidate(
    draft: CandidateDraft,
    snapshot: CompressionEvidenceSnapshot,
    *,
    policy: EstimatorPolicy = ESTIMATOR_POLICY_V1,
    index: EstimatorIndex | None = None,
) -> CandidateDraft:
    """Estimate each component claim and return a reproducible candidate draft."""
    resolved_index = index or build_estimator_index(snapshot)
    results = [
        _estimate_claim(draft, claim, resolved_index, policy=policy) for claim in draft.claims
    ]
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
    index: EstimatorIndex,
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
    peers = index.peers(draft, claim)
    if peers.count >= policy.minimum_matched_peers:
        return (
            _matched_range(claim.exposure_tokens, peers),
            "matched",
            f"{peers.count} comparable calls",
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


def _matched_range(exposure: int, peers: PeerDistribution) -> EstimateRange:
    return EstimateRange(
        low=_bounded_round(exposure - peers.p75, exposure),
        likely=_bounded_round(exposure - peers.p50, exposure),
        high=_bounded_round(exposure - peers.p25, exposure),
    )


def _remaining_distribution(
    values: tuple[int, ...],
    excluded: tuple[int, ...],
) -> PeerDistribution:
    count = len(values) - len(excluded)
    if count <= 0:
        return PeerDistribution(0, 0, 0, 0)
    return PeerDistribution(
        count=count,
        p25=_remaining_percentile(values, excluded, 0.25, count),
        p50=_remaining_percentile(values, excluded, 0.50, count),
        p75=_remaining_percentile(values, excluded, 0.75, count),
    )


def _remaining_percentile(
    values: tuple[int, ...],
    excluded: tuple[int, ...],
    quantile: float,
    count: int,
) -> float:
    position = (count - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    lower_value = _remaining_value(values, excluded, lower)
    if lower == upper:
        return float(lower_value)
    upper_value = _remaining_value(values, excluded, upper)
    return lower_value + (upper_value - lower_value) * (position - lower)


def _remaining_value(
    values: tuple[int, ...],
    excluded: tuple[int, ...],
    index: int,
) -> int:
    low = 0
    high = len(values) - 1
    while low < high:
        middle = (low + high) // 2
        candidate = values[middle]
        remaining_at_or_below = bisect_right(values, candidate) - bisect_right(excluded, candidate)
        if remaining_at_or_below > index:
            high = middle
        else:
            low = middle + 1
    candidate = values[low]
    if bisect_right(values, candidate) - bisect_right(excluded, candidate) <= index:
        next_index = bisect_right(values, candidate)
        return values[next_index]
    if bisect_left(values, candidate) == bisect_right(values, candidate):
        raise RuntimeError("invalid estimator distribution")
    return candidate


def _content_totals(snapshot: CompressionEvidenceSnapshot) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for fragment in snapshot.content_fragments:
        totals[fragment.record_id] += fragment.estimated_tokens
    return dict(totals)


def _tool_output_totals(snapshot: CompressionEvidenceSnapshot) -> dict[str, int]:
    tool_totals: dict[str, int] = defaultdict(int)
    command_totals: dict[str, int] = defaultdict(int)
    for tool in snapshot.tool_calls:
        tool_totals[tool.record_id] += (tool.output_size_bytes + 3) // 4
    for command in snapshot.command_runs:
        command_totals[command.record_id] += (command.output_size_bytes + 3) // 4
    return {
        record_id: max(tool_totals.get(record_id, 0), command_totals.get(record_id, 0))
        for record_id in set(tool_totals).union(command_totals)
    }


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
