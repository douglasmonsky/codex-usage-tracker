"""Synchronous, cache-aware Compression Lab analysis builder."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.attribution import (
    COMPONENT_NAMES,
    CapacityLedger,
    allocate_overlaps,
)
from codex_usage_tracker.compression.detector_protocol import CompressionDetector
from codex_usage_tracker.compression.detector_registry import DETECTOR_SET_VERSION, select_detectors
from codex_usage_tracker.compression.estimators import (
    ESTIMATOR_POLICY_V1,
    EstimatorIndex,
    build_estimator_index,
    estimate_candidate,
)
from codex_usage_tracker.compression.evidence import CompressionEvidenceSnapshot
from codex_usage_tracker.compression.identifiers import stable_candidate_variant_id
from codex_usage_tracker.compression.models import (
    CandidateDraft,
    CompressionScope,
)
from codex_usage_tracker.compression.profile import build_profile, public_profile
from codex_usage_tracker.compression.request import (
    COMPRESSION_SCHEMA_VERSION,
    PreparedCompressionRequest,
    prepare_compression_request,
)
from codex_usage_tracker.compression.run_cache import (
    incremental_inputs,
    latest_compatible_run,
)
from codex_usage_tracker.compression.streaming_evidence import (
    load_fact_compression_evidence,
)
from codex_usage_tracker.store.compression_publication import publish_compression_run
from codex_usage_tracker.store.compression_revisions import (
    current_compression_revision_vector,
)
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    find_compression_run,
    find_current_compression_profile,
    update_compression_run,
)

ProgressCallback = Callable[[dict[str, Any]], None]


def build_compression_run(
    db_path: Path,
    scope: CompressionScope,
    progress_callback: ProgressCallback | None = None,
    detector_families: Sequence[str] | None = None,
    force: bool = False,
    reserved_run_id: str | None = None,
    prepared_request: PreparedCompressionRequest | None = None,
) -> dict[str, Any]:
    """Build, persist, and return one compact compression profile."""
    started = time.perf_counter()
    request = prepared_request or prepare_compression_request(
        db_path,
        scope,
        detector_families=None if detector_families is None else tuple(detector_families),
        detector_selector=select_detectors,
    )
    detectors = request.detectors
    detector_version = request.detector_set_version
    scope_hash = request.scope_hash
    source_generation = request.source_generation
    run_id = reserved_run_id
    warnings: list[dict[str, Any]] = []
    try:
        cached_profile = _reuse_before_evidence(
            db_path,
            request,
            progress_callback,
            force=force,
            reserved_run_id=run_id,
        )
        if cached_profile is not None:
            return cached_profile

        loaded_evidence = load_fact_compression_evidence(db_path, scope)
        snapshot = loaded_evidence.snapshot
        current_manifest = loaded_evidence.record_manifest
        cache_identity = _cache_identity(snapshot, scope_hash, detector_version)
        exact = find_compression_run(db_path, **cache_identity)
        exact_profile = _reuse_exact_after_evidence(
            db_path,
            exact,
            progress_callback,
            force=force,
            reserved_run_id=run_id,
        )
        if exact_profile is not None:
            return exact_profile

        previous = _previous_compatible_run(
            db_path,
            scope_hash=scope_hash,
            detector_version=detector_version,
            force=force,
        )
        if run_id is None:
            run = create_compression_run(
                db_path,
                **cache_identity,
                scope=scope.as_dict(),
                source_generation=source_generation,
                coverage=snapshot.coverage.as_dict(),
                status="running",
                revision_key=request.revision_key,
            )
            run_id = str(run["run_id"])
        else:
            reserved = update_compression_run(
                db_path,
                run_id=run_id,
                status="running",
                source_revision=snapshot.source_revision,
                source_generation=source_generation,
                revision_key=request.revision_key,
                coverage=snapshot.coverage.as_dict(),
            )
            if reserved is None:
                raise KeyError(f"unknown reserved compression run: {run_id}")
        _progress(
            db_path,
            run_id,
            progress_callback,
            stage="evidence_loaded",
            percent=10.0,
            records_examined=len(snapshot.calls),
            total_detectors=len(detectors),
        )
        reused, detector_snapshot, cache_mode = incremental_inputs(
            db_path,
            snapshot=snapshot,
            current_manifest=current_manifest,
            previous=previous,
            scope=scope,
        )
        estimator_index = build_estimator_index(snapshot)
        detected = _run_detectors(
            db_path=db_path,
            run_id=run_id,
            snapshot=snapshot,
            detector_snapshot=detector_snapshot,
            scope=scope,
            detectors=detectors,
            estimator_index=estimator_index,
            progress_callback=progress_callback,
            warnings=warnings,
        )
        drafts = _namespace_candidate_ids([*reused, *detected], detector_version)
        _progress(
            db_path,
            run_id,
            progress_callback,
            stage="attribution",
            percent=82.0,
        )
        candidates = allocate_overlaps(drafts, _capacity_ledger(snapshot, estimator_index))
        _progress(
            db_path,
            run_id,
            progress_callback,
            stage="profile",
            percent=97.0,
        )
        status = _completed_status(warnings)
        duration_ms = round((time.perf_counter() - started) * 1000)
        stored_profile = build_profile(
            run_id=run_id,
            status=status,
            snapshot=snapshot,
            candidates=candidates,
            scope=scope.as_dict(),
            warnings=warnings,
            cache_mode=cache_mode,
            duration_ms=duration_ms,
            record_manifest=current_manifest,
            estimator_index=estimator_index,
        )
        compact_profile = public_profile(stored_profile)
        _progress(
            db_path,
            run_id,
            progress_callback,
            stage="persistence",
            percent=98.0,
        )
        publish_compression_run(
            db_path,
            run_id=run_id,
            candidates=candidates,
            status=status,
            completed_detectors=len(detectors) - len(warnings),
            total_detectors=len(detectors),
            cache_reused=cache_mode == "incremental",
            timing={"duration_ms": duration_ms},
            error_summary={"detector_errors": warnings},
            aggregate_profile=stored_profile,
            public_profile=compact_profile,
            source_generation=source_generation,
            supersede_run_id=_superseded_run_id(exact, force=force),
        )
        _emit(
            progress_callback,
            stage="complete",
            progress_percent=100.0,
            cache_reused=cache_mode == "incremental",
        )
        return compact_profile
    except Exception as exc:
        if run_id is not None:
            update_compression_run(
                db_path,
                run_id=run_id,
                status="failed",
                stage="failed",
                error_summary={"code": "compression_run_failed", "type": type(exc).__name__},
            )
        raise


def _reuse_before_evidence(
    db_path: Path,
    request: PreparedCompressionRequest,
    progress_callback: ProgressCallback | None,
    *,
    force: bool,
    reserved_run_id: str | None,
) -> dict[str, Any] | None:
    if reserved_run_id is not None:
        update_compression_run(
            db_path,
            run_id=reserved_run_id,
            status="running",
            stage="loading_evidence",
            progress_percent=1,
            total_detectors=len(request.detectors),
        )
        return None
    cached = _fast_cached_profile(
        db_path,
        revision_key=request.revision_key,
        detector_families=request.detector_families,
        scope_hash=request.scope_hash,
        detector_version=request.detector_set_version,
        force=force,
    )
    if cached is not None:
        _emit(
            progress_callback,
            stage="complete",
            progress_percent=100.0,
            cache_reused=True,
        )
    return cached


def _reuse_exact_after_evidence(
    db_path: Path,
    exact: dict[str, Any] | None,
    progress_callback: ProgressCallback | None,
    *,
    force: bool,
    reserved_run_id: str | None,
) -> dict[str, Any] | None:
    if exact is None or force:
        return None
    profile = public_profile(exact["aggregate_profile"], cache_mode="exact")
    if reserved_run_id is not None:
        update_compression_run(
            db_path,
            run_id=reserved_run_id,
            status="completed",
            stage="complete",
            progress_percent=100,
            cache_reused=True,
            public_profile=profile,
            revision_key=f"alias:{reserved_run_id}",
        )
    _emit(
        progress_callback,
        stage="complete",
        progress_percent=100.0,
        cache_reused=True,
    )
    return profile


def _fast_cached_profile(
    db_path: Path,
    *,
    revision_key: str,
    detector_families: Sequence[str],
    scope_hash: str,
    detector_version: str,
    force: bool,
) -> dict[str, Any] | None:
    if force:
        return None
    cached_profile = find_current_compression_profile(
        db_path,
        revision_key=revision_key,
        scope_hash=scope_hash,
        detector_set_version=detector_version,
        estimator_version=ESTIMATOR_POLICY_V1.version,
        compression_schema_version=COMPRESSION_SCHEMA_VERSION,
    )
    if cached_profile is None:
        return None
    current_revision = current_compression_revision_vector(
        db_path,
        detector_families=detector_families,
        estimator_revision=ESTIMATOR_POLICY_V1.version,
    )
    if current_revision.cache_key != revision_key:
        return None
    return public_profile(cached_profile, cache_mode="exact")


def _previous_compatible_run(
    db_path: Path,
    *,
    scope_hash: str,
    detector_version: str,
    force: bool,
) -> dict[str, Any] | None:
    if force:
        return None
    return latest_compatible_run(
        db_path,
        scope_hash=scope_hash,
        detector_set_version=detector_version,
        estimator_version=ESTIMATOR_POLICY_V1.version,
        schema_version=COMPRESSION_SCHEMA_VERSION,
    )


def _superseded_run_id(exact: dict[str, Any] | None, *, force: bool) -> str | None:
    return str(exact["run_id"]) if exact is not None and force else None


def _completed_status(warnings: Sequence[dict[str, Any]]) -> str:
    return "completed_with_warnings" if warnings else "completed"


def _run_detectors(
    *,
    db_path: Path,
    run_id: str,
    snapshot: CompressionEvidenceSnapshot,
    detector_snapshot: CompressionEvidenceSnapshot,
    scope: CompressionScope,
    detectors: Sequence[CompressionDetector],
    estimator_index: EstimatorIndex,
    progress_callback: ProgressCallback | None,
    warnings: list[dict[str, Any]],
) -> list[CandidateDraft]:
    drafts: list[CandidateDraft] = []
    total = len(detectors)
    for index, detector in enumerate(detectors, start=1):
        percent = 10.0 + (index / max(1, total)) * 65.0
        try:
            detected = detector.detect(detector_snapshot, scope)
            drafts.extend(
                estimate_candidate(row, snapshot, index=estimator_index) for row in detected
            )
        except Exception as exc:
            warnings.append(
                {
                    "family": detector.family,
                    "code": "detector_failed",
                    "error_type": type(exc).__name__,
                }
            )
        _progress(
            db_path,
            run_id,
            progress_callback,
            stage="detectors",
            percent=percent,
            current_detector=detector.family,
            completed_detectors=index,
            total_detectors=total,
        )
    return drafts


def _capacity_ledger(
    snapshot: CompressionEvidenceSnapshot,
    estimator_index: EstimatorIndex,
):
    capacities = {}
    for call in snapshot.calls:
        for component in COMPONENT_NAMES:
            exposure = estimator_index.component_exposure(call.record_id, component)
            if exposure > 0:
                capacities[(call.record_id, component)] = exposure
    return CapacityLedger(capacities)


def _namespace_candidate_ids(
    drafts: list[CandidateDraft],
    detector_set_version: str,
) -> list[CandidateDraft]:
    if detector_set_version == DETECTOR_SET_VERSION:
        return drafts
    return [
        replace(
            draft,
            candidate_id=stable_candidate_variant_id(
                candidate_id=draft.candidate_id,
                detector_set_version=detector_set_version,
            ),
        )
        for draft in drafts
    ]


def _cache_identity(
    snapshot: CompressionEvidenceSnapshot,
    scope_hash: str,
    detector_set_version: str,
) -> dict[str, Any]:
    return {
        "source_revision": snapshot.source_revision,
        "scope_hash": scope_hash,
        "detector_set_version": detector_set_version,
        "estimator_version": ESTIMATOR_POLICY_V1.version,
        "compression_schema_version": COMPRESSION_SCHEMA_VERSION,
    }


def _progress(
    db_path: Path,
    run_id: str,
    callback: ProgressCallback | None,
    *,
    stage: str,
    percent: float,
    **metadata: Any,
) -> None:
    update_compression_run(
        db_path,
        run_id=run_id,
        stage=stage,
        progress_percent=percent,
        **metadata,
    )
    _emit(callback, stage=stage, progress_percent=percent, **metadata)


def _emit(callback: ProgressCallback | None, **payload: Any) -> None:
    if callback is None:
        return
    try:
        callback(dict(payload))
    except Exception:
        return
