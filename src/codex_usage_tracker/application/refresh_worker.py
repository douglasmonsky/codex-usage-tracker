"""Detached durable worker for one core MCP refresh job."""

from __future__ import annotations

import argparse
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep

from codex_usage_tracker.application.refresh import (
    REFRESH_SCHEMA,
    RefreshPlan,
    _completed_payload,
    plan_refresh,
    refresh_usage_index,
)
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository

_PHASE_RANGES = {
    "planning": (0, 2),
    "discovering": (2, 7),
    "parsing": (7, 28),
    "upserting": (28, 52),
    "metadata": (52, 57),
    "derived_state": (57, 76),
    "indexing_content": (76, 84),
    "syncing_facts": (84, 92),
    "otel": (92, 96),
    "finalizing": (96, 99),
    "complete": (100, 100),
}
_JOB_STATUS_RETRY_SECONDS = 10.0
_JOB_STATUS_RETRY_INTERVAL_SECONDS = 0.05


def _update_job_status(
    repository: AnalysisJobRepository,
    job_id: str,
    *,
    state: str,
    progress: Mapping[str, object],
    result_schema: str | None = None,
    result: object = None,
    error: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Persist worker state through a transient sidecar writer collision."""

    deadline = monotonic() + _JOB_STATUS_RETRY_SECONDS
    while True:
        try:
            return repository.update_status(
                job_id,
                state=state,
                progress=progress,
                result_schema=result_schema,
                result=result,
                error=error,
            )
        except sqlite3.OperationalError as exc:
            transient = any(token in str(exc).lower() for token in ("locked", "busy"))
            if not transient or monotonic() >= deadline:
                raise
            sleep(_JOB_STATUS_RETRY_INTERVAL_SECONDS)


def run_refresh_worker(
    *,
    job_id: str,
    owner_id: str,
    job_db_path: Path,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    request: RefreshRequest,
) -> int:
    """Run one registered refresh and persist privacy-safe progress/results."""

    repository = AnalysisJobRepository(job_db_path, owner_id=owner_id)
    started = monotonic()
    progress_lock = threading.Lock()
    progress = _progress_payload("planning", 0, started=started)
    stop_heartbeat = threading.Event()

    def persist_progress() -> None:
        with progress_lock:
            snapshot = dict(progress)
        _update_job_status(repository, job_id, state="running", progress=snapshot)

    def heartbeat() -> None:
        while not stop_heartbeat.wait(5):
            with progress_lock:
                progress["elapsed_seconds"] = int(monotonic() - started)
                progress["heartbeat_at"] = _utc_now()
            persist_progress()

    def on_progress(payload: dict[str, object]) -> None:
        normalized = _normalize_progress(payload, started=started)
        with progress_lock:
            if _progress_percent(normalized) < _progress_percent(progress):
                normalized["percent"] = progress["percent"]
            for key in ("input_generation", "fixed_source_boundary"):
                if key not in normalized and key in progress:
                    normalized[key] = progress[key]
            progress.clear()
            progress.update(normalized)
        persist_progress()

    _update_job_status(repository, job_id, state="running", progress=progress)
    heartbeat_thread = threading.Thread(
        target=heartbeat,
        daemon=True,
        name=f"refresh-heartbeat-{job_id[:8]}",
    )
    heartbeat_thread.start()
    try:
        observed = plan_refresh(request, codex_home=codex_home, db_path=db_path)
        plan = RefreshPlan(
            "async",
            "explicit_async" if request.execution == "async" else observed.reason,
            observed.changed_source_files,
            observed.added_bytes,
        )
        input_generation = str(
            (repository.get(job_id, touch=False) or {}).get("source_revision", "source:none")
        )
        on_progress(
            {
                "phase": "planning",
                "status": "completed",
                "completed": 1,
                "total": 1,
                "input_generation": input_generation,
                "fixed_source_boundary": {
                    "changed_source_files": plan.changed_source_files,
                    "added_bytes": plan.added_bytes,
                    "newline_aligned": True,
                    "exclusive_end": True,
                },
            }
        )
        result = refresh_usage_index(
            codex_home=codex_home,
            db_path=db_path,
            include_archived=request.history == "all",
            aggregate_only=request.aggregate_only,
            progress_callback=on_progress,
        )
        completed = _completed_payload(
            request,
            result,
            plan,
            codex_home,
            db_path,
            pricing_path,
        )
        refresh_payload = completed.get("refresh")
        refresh_result = refresh_payload if isinstance(refresh_payload, dict) else {}
        freshness_payload = completed.get("freshness")
        freshness_result = freshness_payload if isinstance(freshness_payload, dict) else {}
        _update_job_status(
            repository,
            job_id,
            state="completed",
            progress={
                **_progress_payload("complete", 100, started=started),
                "input_generation": input_generation,
                "committed_output_generation": freshness_result.get("source_revision"),
                "fixed_source_boundary": refresh_result.get("fixed_source_boundary"),
                "tail_pending": refresh_result.get("tail_pending", False),
                "tail_pending_files": refresh_result.get("tail_pending_files", 0),
                "tail_pending_bytes": refresh_result.get("tail_pending_bytes", 0),
            },
            result_schema=REFRESH_SCHEMA,
            result=completed,
        )
    except Exception:  # noqa: BLE001 - persist only a bounded privacy-safe failure.
        _update_job_status(
            repository,
            job_id,
            state="failed",
            progress=_progress_payload(
                "failed",
                _progress_percent(progress),
                started=started,
            ),
            error={
                "code": "refresh.failed",
                "severity": "blocking",
                "message": "The refresh worker failed before completion.",
                "remediation": "Poll status, then retry usage_refresh after the lease expires.",
            },
        )
        return 1
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)
    return 0


def _normalize_progress(
    payload: Mapping[str, object],
    *,
    started: float,
) -> dict[str, object]:
    raw_phase = payload.get("phase")
    phase = str(raw_phase) if isinstance(raw_phase, str) else "running"
    lower, upper = _PHASE_RANGES.get(phase, (0, 99))
    raw_percent = payload.get("percent")
    local_percent = (
        float(raw_percent)
        if isinstance(raw_percent, int | float) and not isinstance(raw_percent, bool)
        else 0.0
    )
    status = payload.get("status")
    if status in {"completed", "skipped"}:
        local_percent = 100.0
    global_percent = min(99, round(lower + (upper - lower) * local_percent / 100))
    result = _progress_payload(phase, global_percent, started=started)
    for key in ("completed", "total", "parsed_events", "inserted_or_updated_events"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            result[key] = value
    input_generation = payload.get("input_generation")
    if isinstance(input_generation, str):
        result["input_generation"] = input_generation
    fixed_source_boundary = payload.get("fixed_source_boundary")
    if isinstance(fixed_source_boundary, Mapping):
        result["fixed_source_boundary"] = dict(fixed_source_boundary)
    return result


def _progress_payload(stage: str, percent: int, *, started: float) -> dict[str, object]:
    return {
        "percent": max(0, min(100, percent)),
        "stage": stage,
        "elapsed_seconds": int(monotonic() - started),
        "heartbeat_at": _utc_now(),
    }


def _progress_percent(payload: Mapping[str, object]) -> int:
    value = payload.get("percent")
    if isinstance(value, int) and not isinstance(value, bool):
        return max(0, min(100, value))
    return 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--owner-id", required=True)
    parser.add_argument("--job-db", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, required=True)
    parser.add_argument("--history", choices=("active", "all"), required=True)
    parser.add_argument("--execution", choices=("auto", "async"), required=True)
    parser.add_argument("--aggregate-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    return run_refresh_worker(
        job_id=args.job_id,
        owner_id=args.owner_id,
        job_db_path=args.job_db,
        codex_home=args.codex_home,
        db_path=args.db,
        pricing_path=args.pricing,
        request=RefreshRequest(
            history=args.history,
            aggregate_only=args.aggregate_only,
            execution=args.execution,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
