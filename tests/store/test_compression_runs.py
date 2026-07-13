from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    CompressionCandidate,
    EstimateRange,
)
from codex_usage_tracker.store.compression_candidates import (
    get_compression_candidate,
    list_compression_candidates,
    replace_compression_candidates,
)
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    delete_stale_compression_runs,
    find_compression_run,
    get_compression_run,
    update_compression_run,
)


class CacheKey(TypedDict):
    source_revision: str
    scope_hash: str
    detector_set_version: str
    estimator_version: str
    compression_schema_version: int
    scope: dict[str, bool]


def test_exact_cache_key_reuses_only_completed_run(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    created = create_compression_run(
        db_path,
        run_id="run-1",
        **cache_key("rev-1"),
    )

    assert created["status"] == "pending"
    assert find_compression_run(db_path, **cache_key("rev-1")) is None

    completed = update_compression_run(
        db_path,
        run_id="run-1",
        status="completed",
        progress_percent=100,
        stage="complete",
        aggregate_profile={"likely_savings": 321},
    )

    assert completed is not None
    assert completed["aggregate_profile"] == {"likely_savings": 321}
    cached = find_compression_run(db_path, **cache_key("rev-1"))
    assert cached is not None
    assert cached["run_id"] == "run-1"
    assert find_compression_run(db_path, **cache_key("rev-2")) is None


def test_run_updates_preserve_monotonic_progress(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(db_path, run_id="run-1", **cache_key("rev-1"))

    update_compression_run(db_path, run_id="run-1", progress_percent=60, stage="detectors")
    run = update_compression_run(
        db_path,
        run_id="run-1",
        progress_percent=20,
        stage="stale-update",
    )

    assert run is not None
    assert run["progress_percent"] == 60
    assert run["stage"] == "stale-update"


def test_candidate_replace_lists_compact_rows_and_reconstructs_detail(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    create_compression_run(db_path, run_id="run-1", **cache_key("rev-1"))
    candidates = [
        candidate("cmp_low", likely=30).as_dict(),
        candidate("cmp_high", likely=80).as_dict(),
    ]

    assert replace_compression_candidates(db_path, run_id="run-1", candidates=candidates) == 2
    assert replace_compression_candidates(db_path, run_id="run-1", candidates=candidates) == 2

    page = list_compression_candidates(
        db_path,
        run_id="run-1",
        min_likely_savings=50,
        limit=10,
    )
    assert page["total"] == 1
    assert page["rows"][0]["candidate_id"] == "cmp_high"
    assert "claims" not in page["rows"][0]
    assert "evidence_handles" not in page["rows"][0]

    detail = get_compression_candidate(db_path, candidate_id="cmp_high")
    assert detail is not None
    assert detail["claims"] == [
        {
            "record_id": "record-cmp_high",
            "component": "uncached_input",
            "exposure_tokens": 100,
            "estimate": {"low": 10, "likely": 80, "high": 90},
            "evidence_role": "supporting",
            "trace_handle": {"record_id": "record-cmp_high"},
        }
    ]
    assert detail["overlapping_candidate_ids"] == ["cmp_other"]

    replace_compression_candidates(
        db_path,
        run_id="run-1",
        candidates=[candidate("cmp_new", likely=40).as_dict()],
    )
    assert get_compression_candidate(db_path, candidate_id="cmp_high") is None
    run = get_compression_run(db_path, run_id="run-1")
    assert run is not None
    assert run["candidate_count"] == 1


def test_delete_stale_runs_leaves_active_and_recent_runs(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    create_compression_run(
        db_path,
        run_id="old-complete",
        status="completed",
        created_at=old,
        **cache_key("rev-old"),
    )
    create_compression_run(
        db_path,
        run_id="old-running",
        status="running",
        created_at=old,
        **cache_key("rev-running"),
    )
    create_compression_run(db_path, run_id="recent", **cache_key("rev-recent"))

    assert delete_stale_compression_runs(db_path, before=cutoff) == 1
    assert get_compression_run(db_path, run_id="old-complete") is None
    assert get_compression_run(db_path, run_id="old-running") is not None
    assert get_compression_run(db_path, run_id="recent") is not None


def cache_key(source_revision: str) -> CacheKey:
    return {
        "source_revision": source_revision,
        "scope_hash": "scope-1",
        "detector_set_version": "detectors-v1",
        "estimator_version": "estimator-v1",
        "compression_schema_version": 1,
        "scope": {"include_archived": False},
    }


def candidate(candidate_id: str, *, likely: int) -> CompressionCandidate:
    estimate = EstimateRange(low=10, likely=likely, high=90)
    record_id = f"record-{candidate_id}"
    draft = CandidateDraft(
        candidate_id=candidate_id,
        family="stale_context",
        pattern="Large context with little output",
        pattern_key=f"thread:{candidate_id}",
        detector_version="stale-v1",
        estimator_version="estimator-v1",
        record_ids=(record_id,),
        thread_keys=("thread-1",),
        observation_count=1,
        observed_exposure=ComponentExposure(uncached_input=100),
        claims=(
            ComponentClaim(
                record_id=record_id,
                component="uncached_input",
                exposure_tokens=100,
                estimate=estimate,
            ),
        ),
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
        first_seen="2026-07-01T00:00:00+00:00",
        last_seen="2026-07-02T00:00:00+00:00",
    )
    return CompressionCandidate(
        draft=draft,
        adjusted_estimate=estimate,
        overlapping_candidate_ids=("cmp_other",),
    )
