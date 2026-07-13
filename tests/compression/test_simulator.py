from __future__ import annotations

import json
from collections.abc import Mapping

from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    ComponentName,
    CompressionCandidate,
    EstimateRange,
)
from codex_usage_tracker.compression.simulator import simulate_candidate_portfolio


def test_simulation_is_deterministic_for_candidate_order() -> None:
    first = _candidate("candidate-b", record_id="record-1", component="uncached_input")
    second = _candidate("candidate-a", record_id="record-1", component="uncached_input")

    capacities = _capacities(first, second)
    left = simulate_candidate_portfolio([first, second], capacities).as_dict()
    right = simulate_candidate_portfolio([second, first], capacities).as_dict()

    assert json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    assert left["selected_candidate_ids"] == ["candidate-a", "candidate-b"]


def test_shared_claims_never_exceed_unique_component_capacity() -> None:
    candidates = [
        _candidate("candidate-a", record_id="record-1", component="uncached_input"),
        _candidate("candidate-b", record_id="record-1", component="uncached_input"),
    ]
    result = simulate_candidate_portfolio(candidates, _capacities(*candidates)).as_dict()

    assert result["gross_estimate"] == {"low": 80, "likely": 120, "high": 160}
    assert result["overlap_adjusted_estimate"] == {"low": 80, "likely": 100, "high": 100}
    assert result["unique_eligible_capacity_tokens"] == 100
    assert result["overlap_group_count"] == 1
    assert result["groups"][0]["capacity_tokens"] == 100
    assert sum(claim["adjusted_estimate"]["high"] for claim in result["groups"][0]["claims"]) == 100


def test_disjoint_claims_retain_gross_estimates() -> None:
    candidates = [
        _candidate("candidate-a", record_id="record-1", component="uncached_input"),
        _candidate("candidate-b", record_id="record-2", component="uncached_input"),
    ]
    result = simulate_candidate_portfolio(candidates, _capacities(*candidates)).as_dict()

    assert result["overlap_adjusted_estimate"] == result["gross_estimate"]
    assert result["unique_eligible_capacity_tokens"] == 200
    assert result["overlap_group_count"] == 0


def test_subset_simulation_reclaims_capacity_from_unselected_candidates() -> None:
    selected = _candidate(
        "candidate-a",
        record_id="record-1",
        component="uncached_input",
        persisted_adjusted=EstimateRange(low=10, likely=20, high=30),
    )

    result = simulate_candidate_portfolio([selected], _capacities(selected)).as_dict()

    assert result["candidates"][0]["persisted_adjusted_estimate"] == {
        "low": 10,
        "likely": 20,
        "high": 30,
    }
    assert result["candidates"][0]["simulated_adjusted_estimate"] == {
        "low": 40,
        "likely": 60,
        "high": 80,
    }


def test_trace_groups_and_claims_are_lexically_sorted() -> None:
    candidates = [
        _candidate("candidate-z", record_id="record-z", component="output"),
        _candidate("candidate-b", record_id="record-a", component="cached_input"),
        _candidate("candidate-a", record_id="record-a", component="cached_input"),
    ]
    result = simulate_candidate_portfolio(candidates, _capacities(*candidates)).as_dict()

    assert [(group["record_id"], group["component"]) for group in result["groups"]] == [
        ("record-a", "cached_input"),
        ("record-z", "output"),
    ]
    assert [claim["candidate_id"] for claim in result["groups"][0]["claims"]] == [
        "candidate-a",
        "candidate-b",
    ]


def test_full_record_capacity_preserves_disjoint_tool_outputs_on_one_record() -> None:
    candidates = [
        _candidate("tool-a", record_id="record-1", component="tool_output"),
        _candidate("tool-b", record_id="record-1", component="tool_output"),
    ]

    result = simulate_candidate_portfolio(
        candidates,
        {("record-1", "tool_output"): 200},
    ).as_dict()

    assert result["overlap_adjusted_estimate"] == result["gross_estimate"]
    assert result["groups"][0]["capacity_tokens"] == 200


def _candidate(
    candidate_id: str,
    *,
    record_id: str,
    component: ComponentName,
    persisted_adjusted: EstimateRange | None = None,
) -> dict[str, object]:
    estimate = EstimateRange(low=40, likely=60, high=80)
    claim = ComponentClaim(
        record_id=record_id,
        component=component,
        exposure_tokens=100,
        estimate=estimate,
    )
    exposure = _exposure(component)
    draft = CandidateDraft(
        candidate_id=candidate_id,
        family="stale_context",
        pattern="Synthetic compression opportunity",
        pattern_key=f"pattern:{candidate_id}",
        detector_version="stale-v1",
        estimator_version="estimator-v1",
        record_ids=(record_id,),
        thread_keys=("thread-1",),
        observation_count=1,
        observed_exposure=exposure,
        claims=(claim,),
        gross_estimate=estimate,
        confidence_grade="medium",
        confidence_score=0.7,
        confidence_reasons=("synthetic evidence",),
        estimator_tier="fallback",
        estimator_name="synthetic-estimator",
        estimator_assumptions=("test assumption",),
        evidence_handles=({"record_id": record_id},),
        intervention={"family": "fresh_handoff"},
        verification={"tool": "usage_compression_profile"},
    )
    candidate = CompressionCandidate(
        draft=draft,
        adjusted_estimate=persisted_adjusted or estimate,
    )
    return candidate.as_dict()


def _exposure(component: ComponentName) -> ComponentExposure:
    return ComponentExposure(
        cached_input=100 if component == "cached_input" else 0,
        uncached_input=100 if component == "uncached_input" else 0,
        output=100 if component == "output" else 0,
        reasoning_output=100 if component == "reasoning_output" else 0,
        content_fragment=100 if component == "content_fragment" else 0,
        tool_output=100 if component == "tool_output" else 0,
    )


def _capacities(*records: dict[str, object]) -> dict[tuple[str, str], int]:
    capacities: dict[tuple[str, str], int] = {}
    for record in records:
        claims = record.get("claims")
        if not isinstance(claims, list):
            continue
        for claim in claims:
            if not isinstance(claim, Mapping):
                continue
            key = (str(claim.get("record_id")), str(claim.get("component")))
            exposure = int(str(claim.get("exposure_tokens") or 0))
            capacities[key] = max(capacities.get(key, 0), exposure)
    return capacities
