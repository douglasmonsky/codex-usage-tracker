"""Shared application API for Compression Lab MCP and local callers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.jobs import CompressionJobRegistry, compression_jobs
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.payloads import (
    CANDIDATE_DETAIL_BUDGET_BYTES,
    compression_candidate_detail_payload,
    compression_candidate_page_payload,
    compression_error_payload,
    compression_profile_payload,
    compression_status_payload,
)
from codex_usage_tracker.compression.request import prepare_compression_request
from codex_usage_tracker.store.compression_candidates import (
    get_compression_candidate,
    list_compression_candidates,
)
from codex_usage_tracker.store.compression_runs import (
    find_current_compression_profile,
    get_compression_run,
)
from codex_usage_tracker.store.content_excerpts import list_content_excerpts

_TERMINAL_SUCCESS = frozenset({"completed", "completed_with_warnings"})
_EVIDENCE_MODES = frozenset({"handles", "summaries", "excerpts"})
_BOUNDED_QUERY_WINDOW = 250


def start_compression_analysis(
    db_path: Path,
    scope: CompressionScope,
    *,
    detector_families: Sequence[str] | None = None,
    refresh: bool = False,
    registry: CompressionJobRegistry = compression_jobs,
) -> dict[str, Any]:
    run = registry.start(
        db_path,
        scope,
        detector_families=detector_families,
        force=refresh,
    )
    return compression_status_payload(run)


def compression_status(
    db_path: Path,
    *,
    run_id: str,
    registry: CompressionJobRegistry = compression_jobs,
) -> dict[str, Any]:
    run = registry.status(db_path, run_id)
    if run is None:
        return _missing_run("status", run_id)
    return compression_status_payload(run)


def compression_profile(
    db_path: Path,
    *,
    run_id: str | None = None,
    scope: CompressionScope | None = None,
    detector_families: Sequence[str] | None = None,
) -> dict[str, Any]:
    run: dict[str, Any] | None
    if run_id:
        run = get_compression_run(db_path, run_id=run_id)
    else:
        normalized_scope = scope or CompressionScope()
        prepared = prepare_compression_request(
            db_path,
            normalized_scope,
            detector_families=None if detector_families is None else tuple(detector_families),
        )
        profile = find_current_compression_profile(db_path, **prepared.cache_lookup())
        run = (
            get_compression_run(db_path, run_id=str(profile["run_id"]))
            if profile is not None
            else None
        )
    if run is None:
        return _missing_run("profile", run_id)
    if run["status"] not in _TERMINAL_SUCCESS or not run.get("public_profile"):
        return compression_error_payload(
            kind="profile",
            code="compression_run_not_complete",
            message="The compression run has not published a completed profile.",
            next_tool="usage_compression_status",
            next_arguments={"run_id": str(run["run_id"])},
            run=run,
        )
    return compression_profile_payload(run)


def compression_candidates(
    db_path: Path,
    *,
    run_id: str,
    family: str | None = None,
    confidence_grade: str | None = None,
    model: str | None = None,
    thread: str | None = None,
    since: str | None = None,
    until: str | None = None,
    min_exposure: int = 0,
    min_likely_savings: int = 0,
    sort: str = "adjusted_likely",
    limit: int | None = 50,
    offset: int = 0,
    max_payload_bytes: int | None = None,
) -> dict[str, Any]:
    run = get_compression_run(db_path, run_id=run_id)
    if run is None:
        return _missing_run("candidate_page", run_id)
    if run["status"] not in _TERMINAL_SUCCESS:
        return compression_error_payload(
            kind="candidate_page",
            code="compression_run_not_complete",
            message="Candidates are available after the run completes.",
            next_tool="usage_compression_status",
            next_arguments={"run_id": run_id},
            run=run,
        )
    query_limit = _candidate_query_limit(limit, max_payload_bytes=max_payload_bytes)
    page = list_compression_candidates(
        db_path,
        run_id=run_id,
        family=family,
        confidence_grade=confidence_grade,
        model=model,
        thread=thread,
        since=since,
        until=until,
        min_exposure=min_exposure,
        min_likely_savings=min_likely_savings,
        sort=sort,
        limit=query_limit,
        offset=offset,
    )
    if query_limit != limit:
        page = dict(page)
        page["limit"] = None if limit in (None, 0) else max(1, int(limit))
    return compression_candidate_page_payload(run, page, max_bytes=max_payload_bytes)


def compression_candidate_detail(
    db_path: Path,
    *,
    candidate_id: str,
    evidence_mode: str = "handles",
    evidence_limit: int = 20,
    max_excerpt_chars: int = 400,
    max_payload_bytes: int = CANDIDATE_DETAIL_BUDGET_BYTES,
) -> dict[str, Any]:
    if evidence_mode not in _EVIDENCE_MODES:
        return compression_error_payload(
            kind="candidate_detail",
            code="invalid_evidence_mode",
            message="Evidence mode must be handles, summaries, or excerpts.",
            next_tool="usage_compression_candidate_detail",
            next_arguments={"candidate_id": candidate_id, "evidence_mode": "handles"},
        )
    candidate = get_compression_candidate(db_path, candidate_id=candidate_id)
    if candidate is None:
        return compression_error_payload(
            kind="candidate_detail",
            code="compression_candidate_not_found",
            message="No persisted compression candidate matched that ID.",
            next_tool="usage_compression_candidates",
        )
    run = get_compression_run(db_path, run_id=str(candidate["run_id"]))
    if run is None:
        return _missing_run("candidate_detail", str(candidate["run_id"]))
    limit = min(50, max(1, int(evidence_limit)))
    claims = [dict(row) for row in candidate.get("claims") or []][:limit]
    evidence = _candidate_evidence(
        db_path,
        candidate,
        claims,
        evidence_mode=evidence_mode,
        limit=limit,
        max_excerpt_chars=max_excerpt_chars,
    )
    return compression_candidate_detail_payload(
        run,
        candidate,
        evidence_mode=evidence_mode,
        claims=claims,
        evidence=evidence,
        max_bytes=max_payload_bytes,
    )


def _candidate_evidence(
    db_path: Path,
    candidate: dict[str, Any],
    claims: Sequence[dict[str, Any]],
    *,
    evidence_mode: str,
    limit: int,
    max_excerpt_chars: int,
) -> list[dict[str, Any]]:
    if evidence_mode == "handles":
        return [dict(row) for row in candidate.get("evidence_handles") or []][:limit]
    if evidence_mode == "summaries":
        return [
            {key: value for key, value in row.items() if key != "trace_handle"} for row in claims
        ]
    return list_content_excerpts(
        db_path,
        record_ids=[str(row.get("record_id") or "") for row in claims],
        limit=limit,
        max_excerpt_chars=max_excerpt_chars,
    )


def _missing_run(kind: str, run_id: str | None) -> dict[str, Any]:
    return compression_error_payload(
        kind=kind,
        code="compression_run_not_found",
        message="No persisted compression run matched that ID or current scope.",
        next_tool="usage_compression_start",
        next_arguments={} if run_id is None else {"previous_run_id": run_id},
    )


def _candidate_query_limit(limit: int | None, *, max_payload_bytes: int | None) -> int | None:
    if max_payload_bytes is None:
        return limit
    if limit in (None, 0):
        return _BOUNDED_QUERY_WINDOW
    return min(_BOUNDED_QUERY_WINDOW, max(1, int(limit)))
