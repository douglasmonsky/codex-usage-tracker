"""Compact aggregate profiles for completed Compression Lab runs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from codex_usage_tracker.compression.attribution import portfolio_estimate
from codex_usage_tracker.compression.estimators import EstimatorIndex
from codex_usage_tracker.compression.evidence import CompressionEvidenceSnapshot
from codex_usage_tracker.compression.models import (
    CompressionCandidate,
    EstimateRange,
)

PROFILE_SCHEMA = "codex-usage-compression-profile-v1"


def build_profile(
    *,
    run_id: str,
    status: str,
    snapshot: CompressionEvidenceSnapshot,
    candidates: Sequence[CompressionCandidate],
    scope: Mapping[str, Any],
    warnings: Sequence[Mapping[str, Any]],
    cache_mode: str,
    duration_ms: int,
    record_manifest: Mapping[str, Mapping[str, str]],
    estimator_index: EstimatorIndex,
) -> dict[str, Any]:
    """Build the stored aggregate profile, including a private cache manifest."""
    portfolio = portfolio_estimate(candidates)
    ordered = sorted(
        candidates,
        key=lambda row: (
            -row.adjusted_estimate.likely,
            -row.draft.confidence_score,
            row.candidate_id,
        ),
    )
    return {
        "schema": PROFILE_SCHEMA,
        "run_id": run_id,
        "status": status,
        "source_revision": snapshot.source_revision,
        "scope": dict(scope),
        "candidate_count": len(candidates),
        "observed_exposure": _observed_exposure(snapshot, estimator_index),
        "portfolio_estimate": portfolio.as_dict(),
        "families": _family_summaries(candidates),
        "top_candidate_ids": [row.candidate_id for row in ordered[:5]],
        "coverage": snapshot.coverage.as_dict(),
        "cache": {"mode": cache_mode, "reused": cache_mode != "cold"},
        "duration_ms": max(0, int(duration_ms)),
        "content_mode": "indexed" if snapshot.coverage.content_index_enabled else "aggregate",
        "includes_indexed_content": bool(snapshot.coverage.content_index_enabled),
        "includes_raw_fragments": False,
        "warnings": [dict(warning) for warning in warnings],
        "caveats": (
            "Savings are heuristic ranges, not an OpenAI usage ledger.",
            "Observed exposure is not automatically avoidable waste.",
        ),
        "_cache_manifest": {
            record_id: dict(metadata) for record_id, metadata in record_manifest.items()
        },
    }


def public_profile(
    stored_profile: Mapping[str, Any],
    *,
    cache_mode: str | None = None,
) -> dict[str, Any]:
    """Return a compact profile without private incremental-cache metadata."""
    profile = {key: value for key, value in stored_profile.items() if not str(key).startswith("_")}
    if cache_mode is not None:
        profile["cache"] = {"mode": cache_mode, "reused": cache_mode != "cold"}
    return profile


def _observed_exposure(
    snapshot: CompressionEvidenceSnapshot,
    estimator_index: EstimatorIndex,
) -> dict[str, int]:
    call_components = {
        "cached_input": sum(row.exposure.cached_input for row in snapshot.calls),
        "uncached_input": sum(row.exposure.uncached_input for row in snapshot.calls),
        "output": sum(row.exposure.output for row in snapshot.calls),
        "reasoning_output": sum(row.exposure.reasoning_output for row in snapshot.calls),
    }
    record_ids = {row.record_id for row in snapshot.calls}
    call_components["content_fragment"] = sum(
        estimator_index.component_exposure(record_id, "content_fragment")
        for record_id in record_ids
    )
    call_components["tool_output"] = sum(
        estimator_index.component_exposure(record_id, "tool_output") for record_id in record_ids
    )
    call_components["total"] = sum(call_components.values())
    return call_components


def _family_summaries(
    candidates: Sequence[CompressionCandidate],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[CompressionCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.draft.family].append(candidate)
    return [
        {
            "family": family,
            "candidate_count": len(rows),
            "adjusted_estimate": _sum_estimates([row.adjusted_estimate for row in rows]).as_dict(),
        }
        for family, rows in sorted(grouped.items())
    ]


def _sum_estimates(estimates: Sequence[EstimateRange]) -> EstimateRange:
    return EstimateRange(
        low=sum(row.low for row in estimates),
        likely=sum(row.likely for row in estimates),
        high=sum(row.high for row in estimates),
    )
