"""Candidate-heavy benchmark helpers for Compression Lab CP5."""

from __future__ import annotations

import hashlib
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.models import (
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    CompressionCandidate,
    EstimateRange,
)
from codex_usage_tracker.store.compression_candidates import replace_compression_candidates
from codex_usage_tracker.store.compression_publication import publish_compression_run
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    update_compression_run,
)

DEFAULT_MIN_IMPROVEMENT_PERCENT = 40.0


def benchmark_persistence(db_path: Path, *, rows: int) -> dict[str, Any]:
    """Compare CP1-compatible mapping writes with typed atomic publication."""
    candidate_count = min(10_000, max(5_000, rows // 20))
    candidates = tuple(_candidate(index) for index in range(candidate_count))
    mapping_db = _copy_database(db_path, "mapping")
    typed_db = _copy_database(db_path, "typed")
    try:
        _create_run(mapping_db, "benchmark-mapping")
        _create_run(typed_db, "benchmark-typed")

        mapping_started = time.perf_counter()
        replace_compression_candidates(
            mapping_db,
            run_id="benchmark-mapping",
            candidates=(candidate.as_dict() for candidate in candidates),
        )
        update_compression_run(
            mapping_db,
            run_id="benchmark-mapping",
            status="completed",
            progress_percent=100.0,
            stage="complete",
            completed_detectors=1,
            total_detectors=1,
            aggregate_profile={"candidate_count": candidate_count},
            public_profile={"candidate_count": candidate_count},
        )
        mapping_seconds = time.perf_counter() - mapping_started

        typed_started = time.perf_counter()
        publish_compression_run(
            typed_db,
            run_id="benchmark-typed",
            candidates=candidates,
            status="completed",
            completed_detectors=1,
            total_detectors=1,
            aggregate_profile={"candidate_count": candidate_count},
            public_profile={"candidate_count": candidate_count},
            source_generation=1,
        )
        typed_seconds = time.perf_counter() - typed_started

        mapping_fingerprint = _candidate_fingerprint(mapping_db)
        typed_fingerprint = _candidate_fingerprint(typed_db)
        improvement = 100.0 * (mapping_seconds - typed_seconds) / mapping_seconds
        return {
            "candidate_count": candidate_count,
            "mapping_seconds": round(mapping_seconds, 6),
            "typed_seconds": round(typed_seconds, 6),
            "improvement_percent": round(improvement, 3),
            "equivalent": mapping_fingerprint == typed_fingerprint,
            "candidate_fingerprint": typed_fingerprint,
        }
    finally:
        mapping_db.unlink(missing_ok=True)
        typed_db.unlink(missing_ok=True)


def persistence_threshold_failures(payload: dict[str, Any]) -> list[str]:
    benchmark = payload["candidate_persistence"]
    failures: list[str] = []
    if not bool(benchmark["equivalent"]):
        failures.append("candidate_persistence outputs differed")
    improvement = float(benchmark["improvement_percent"])
    if improvement < DEFAULT_MIN_IMPROVEMENT_PERCENT:
        failures.append(
            "candidate_persistence.improvement_percent "
            f"{improvement:.3f} was below {DEFAULT_MIN_IMPROVEMENT_PERCENT:.3f}"
        )
    return failures


def _copy_database(db_path: Path, label: str) -> Path:
    copy_path = db_path.with_name(f".{db_path.stem}-{label}-{uuid.uuid4().hex}.sqlite3")
    with sqlite3.connect(db_path) as source, sqlite3.connect(copy_path) as target:
        source.backup(target)
    return copy_path


def _create_run(db_path: Path, run_id: str) -> None:
    create_compression_run(
        db_path,
        run_id=run_id,
        source_revision="benchmark-revision",
        scope_hash="benchmark-scope",
        detector_set_version="benchmark-detectors",
        estimator_version="benchmark-estimator",
        compression_schema_version=1,
        scope={"include_archived": True},
        status="running",
    )


def _candidate(index: int) -> CompressionCandidate:
    candidate_id = f"benchmark_candidate_{index:06d}"
    record_id = f"benchmark_record_{index:06d}"
    likely = 20 + index % 11
    estimate = EstimateRange(low=10, likely=likely, high=40)
    draft = CandidateDraft(
        candidate_id=candidate_id,
        family="benchmark",
        pattern="Synthetic candidate persistence benchmark",
        pattern_key=f"benchmark:{index:06d}",
        detector_version="benchmark-v1",
        estimator_version="benchmark-v1",
        record_ids=(record_id,),
        thread_keys=(f"thread-{index % 50}",),
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
        confidence_reasons=("synthetic benchmark",),
        estimator_tier="benchmark",
        estimator_name="benchmark",
        estimator_assumptions=("synthetic only",),
        evidence_handles=({"record_id": record_id},),
        intervention={"family": "benchmark"},
        verification={"tool": "benchmark"},
    )
    return CompressionCandidate(draft=draft, adjusted_estimate=estimate)


def _candidate_fingerprint(db_path: Path) -> str:
    digest = hashlib.sha256()
    with sqlite3.connect(db_path) as conn:
        for row in conn.execute(
            """
            SELECT candidate_id, adjusted_low, adjusted_likely, adjusted_high
            FROM compression_candidates
            WHERE candidate_id LIKE 'benchmark_candidate_%'
            ORDER BY candidate_id
            """
        ):
            digest.update(repr(tuple(row)).encode())
        for row in conn.execute(
            """
            SELECT candidate_id, record_id, component, estimate_low, estimate_likely, estimate_high
            FROM compression_candidate_records
            WHERE candidate_id LIKE 'benchmark_candidate_%'
            ORDER BY candidate_id, record_id, component
            """
        ):
            digest.update(repr(tuple(row)).encode())
    return digest.hexdigest()
