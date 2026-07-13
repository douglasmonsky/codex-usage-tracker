"""Typed, atomic publication for completed Compression Lab runs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from itertools import chain, islice
from pathlib import Path
from typing import Any, Protocol

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store.compression_candidates import (
    _CANDIDATE_INSERT_SQL,
    _CLAIM_INSERT_SQL,
)
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db

_CACHEABLE_STATUSES = frozenset({"completed", "completed_with_warnings"})


class EstimateWrite(Protocol):
    @property
    def low(self) -> int: ...

    @property
    def likely(self) -> int: ...

    @property
    def high(self) -> int: ...


class ExposureWrite(Protocol):
    def as_dict(self) -> dict[str, int]: ...


class ClaimWrite(Protocol):
    @property
    def record_id(self) -> str: ...

    @property
    def component(self) -> str: ...

    @property
    def exposure_tokens(self) -> int: ...

    @property
    def estimate(self) -> EstimateWrite: ...


class CandidateDraftWrite(Protocol):
    @property
    def family(self) -> str: ...

    @property
    def pattern(self) -> str: ...

    @property
    def pattern_key(self) -> str: ...

    @property
    def confidence_grade(self) -> str: ...

    @property
    def confidence_score(self) -> float: ...

    @property
    def confidence_reasons(self) -> tuple[str, ...]: ...

    @property
    def observation_count(self) -> int: ...

    @property
    def observed_exposure(self) -> ExposureWrite: ...

    @property
    def gross_estimate(self) -> EstimateWrite: ...

    @property
    def detector_version(self) -> str: ...

    @property
    def estimator_version(self) -> str: ...

    @property
    def estimator_tier(self) -> str: ...

    @property
    def estimator_name(self) -> str: ...

    @property
    def estimator_assumptions(self) -> tuple[str, ...]: ...

    @property
    def evidence_handles(self) -> tuple[dict[str, Any], ...]: ...

    @property
    def intervention(self) -> dict[str, Any]: ...

    @property
    def verification(self) -> dict[str, Any]: ...

    @property
    def data_quality_warnings(self) -> tuple[str, ...]: ...

    @property
    def thread_keys(self) -> tuple[str, ...]: ...

    @property
    def first_seen(self) -> str | None: ...

    @property
    def last_seen(self) -> str | None: ...

    @property
    def claims(self) -> tuple[ClaimWrite, ...]: ...


class CandidateWrite(Protocol):
    @property
    def candidate_id(self) -> str: ...

    @property
    def draft(self) -> CandidateDraftWrite: ...

    @property
    def adjusted_estimate(self) -> EstimateWrite: ...

    @property
    def overlapping_candidate_ids(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class _RunCompletion:
    status: str
    completed_detectors: int
    total_detectors: int
    cache_reused: bool
    timing: Mapping[str, Any]
    error_summary: Mapping[str, Any]
    aggregate_profile: Mapping[str, Any]
    public_profile: Mapping[str, Any]
    source_generation: int


def publish_compression_run(
    db_path: Path = DEFAULT_DB_PATH,
    *,
    run_id: str,
    candidates: Iterable[CandidateWrite],
    status: str,
    completed_detectors: int,
    total_detectors: int,
    aggregate_profile: Mapping[str, Any],
    public_profile: Mapping[str, Any],
    source_generation: int,
    cache_reused: bool = False,
    timing: Mapping[str, Any] | None = None,
    error_summary: Mapping[str, Any] | None = None,
    supersede_run_id: str | None = None,
) -> int:
    """Atomically persist candidates, claims, and one cacheable profile."""
    if status not in _CACHEABLE_STATUSES:
        raise ValueError(f"publication status must be cacheable: {status}")
    ordered = sorted(
        candidates,
        key=lambda candidate: (-candidate.adjusted_estimate.likely, candidate.candidate_id),
    )
    completion = _RunCompletion(
        status=status,
        completed_detectors=completed_detectors,
        total_detectors=total_detectors,
        cache_reused=cache_reused,
        timing=timing or {},
        error_summary=error_summary or {},
        aggregate_profile=aggregate_profile,
        public_profile=public_profile,
        source_generation=source_generation,
    )
    with connect(db_path) as conn:
        init_db(conn)
        _replace_candidate_rows(
            conn,
            run_id=run_id,
            candidates=ordered,
            supersede_run_id=supersede_run_id or "",
        )
        _complete_run(conn, run_id=run_id, candidate_count=len(ordered), values=completion)
    return len(ordered)


def _replace_candidate_rows(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    candidates: list[CandidateWrite],
    supersede_run_id: str,
) -> None:
    if not _run_exists(conn, run_id):
        raise KeyError(f"unknown compression run: {run_id}")
    if supersede_run_id and supersede_run_id != run_id:
        _delete_run(conn, supersede_run_id)
    _delete_run_candidates(conn, run_id)
    _bounded_insert(
        conn,
        _CANDIDATE_INSERT_SQL,
        (
            _candidate_row(candidate, run_id=run_id, rank=rank)
            for rank, candidate in enumerate(candidates, 1)
        ),
        batch_size=25,
    )
    _bounded_insert(
        conn,
        _CLAIM_INSERT_SQL,
        (
            _claim_row(candidate.candidate_id, claim)
            for candidate in candidates
            for claim in candidate.draft.claims
        ),
        batch_size=100,
    )


def _complete_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    candidate_count: int,
    values: _RunCompletion,
) -> None:
    now = _utc_now()
    updated = conn.execute(
        """
        UPDATE compression_runs
        SET status = ?, progress_percent = 100.0, stage = 'complete',
            current_detector = NULL, completed_detectors = ?, total_detectors = ?,
            candidate_count = ?, cache_reused = ?, timing_json = ?,
            error_summary_json = ?, aggregate_profile_json = ?, public_profile_json = ?,
            source_generation = ?, completed_at = ?, last_accessed_at = ?
        WHERE run_id = ?
        """,
        (
            values.status,
            int(values.completed_detectors),
            int(values.total_detectors),
            candidate_count,
            int(values.cache_reused),
            _json_dump(values.timing),
            _json_dump(values.error_summary),
            _json_dump(values.aggregate_profile),
            _json_dump(values.public_profile),
            int(values.source_generation),
            now,
            now,
            run_id,
        ),
    )
    if updated.rowcount != 1:
        raise RuntimeError(f"compression run publication failed: {run_id}")


def _delete_run_candidates(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute(
        """
        DELETE FROM compression_candidate_records
        WHERE candidate_id IN (
            SELECT candidate_id FROM compression_candidates WHERE run_id = ?
        )
        """,
        (run_id,),
    )
    conn.execute("DELETE FROM compression_candidates WHERE run_id = ?", (run_id,))


def _candidate_row(candidate: CandidateWrite, *, run_id: str, rank: int) -> tuple[Any, ...]:
    draft = candidate.draft
    exposure = draft.observed_exposure.as_dict()
    gross = draft.gross_estimate
    adjusted = candidate.adjusted_estimate
    return (
        candidate.candidate_id,
        run_id,
        draft.family,
        draft.pattern,
        draft.pattern_key,
        rank,
        draft.confidence_grade,
        draft.confidence_score,
        draft.observation_count,
        sum(exposure.values()),
        _json_dump_int_items(tuple(exposure.items())),
        gross.low,
        gross.likely,
        gross.high,
        adjusted.low,
        adjusted.likely,
        adjusted.high,
        draft.detector_version,
        draft.estimator_version,
        draft.estimator_tier,
        draft.estimator_name,
        _json_dump_strings(draft.confidence_reasons),
        _json_dump_strings(draft.estimator_assumptions),
        _json_dump(draft.evidence_handles),
        _json_dump(draft.intervention),
        _json_dump(draft.verification),
        _json_dump_strings(draft.data_quality_warnings),
        _json_dump_strings(candidate.overlapping_candidate_ids),
        _json_dump_strings(draft.thread_keys),
        draft.first_seen,
        draft.last_seen,
    )


def _claim_row(candidate_id: str, claim: ClaimWrite) -> tuple[Any, ...]:
    return (
        candidate_id,
        claim.record_id,
        claim.component,
        claim.exposure_tokens,
        claim.estimate.low,
        claim.estimate.likely,
        claim.estimate.high,
        "supporting",
        _json_dump({"record_id": claim.record_id}),
    )


def _delete_run(conn: sqlite3.Connection, run_id: str) -> None:
    _delete_run_candidates(conn, run_id)
    conn.execute("DELETE FROM compression_runs WHERE run_id = ?", (run_id,))


def _run_exists(conn: sqlite3.Connection, run_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM compression_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        is not None
    )


def _bounded_insert(
    conn: sqlite3.Connection,
    single_row_sql: str,
    rows: Iterable[tuple[Any, ...]],
    *,
    batch_size: int,
) -> None:
    """Insert bounded batches without exceeding SQLite's conservative variable limit."""
    prefix, placeholder = single_row_sql.rsplit("VALUES", maxsplit=1)
    iterator = iter(rows)
    while batch := tuple(islice(iterator, batch_size)):
        values_sql = ",".join(placeholder.strip() for _ in batch)
        conn.execute(  # nosec B608 - SQL templates are fixed module constants.
            f"{prefix}VALUES {values_sql}",
            tuple(chain.from_iterable(batch)),
        )


def _json_dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@lru_cache(maxsize=4_096)
def _json_dump_strings(values: tuple[str, ...]) -> str:
    return _json_dump(values)


@lru_cache(maxsize=4_096)
def _json_dump_int_items(values: tuple[tuple[str, int], ...]) -> str:
    return _json_dump(dict(values))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
