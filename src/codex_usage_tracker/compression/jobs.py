"""Process-local asynchronous lifecycle for persistent Compression Lab runs."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.request import (
    PreparedCompressionRequest,
    prepare_compression_request,
)
from codex_usage_tracker.compression.run_builder import build_compression_run
from codex_usage_tracker.store.compression_runs import (
    create_compression_run,
    find_current_compression_profile,
    get_compression_run,
    update_compression_run,
)

CompressionBuilder = Callable[..., dict[str, Any]]
_ACTIVE_STATUSES = frozenset({"pending", "running"})


class CompressionJobRegistry:
    """Deduplicate active requests and launch one daemon worker per cold run."""

    def __init__(self, *, builder: CompressionBuilder = build_compression_run) -> None:
        self._builder = builder
        self._lock = threading.Lock()
        self._active_by_request: dict[tuple[str, str], str] = {}
        self._threads_by_run: dict[tuple[str, str], threading.Thread] = {}

    def start(
        self,
        db_path: Path,
        scope: CompressionScope,
        *,
        detector_families: Sequence[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Reserve and launch a run, or reuse an exact completed/active request."""
        normalized_path = Path(db_path)
        prepared = prepare_compression_request(
            normalized_path,
            scope,
            detector_families=None if detector_families is None else tuple(detector_families),
        )
        path_key = str(normalized_path.expanduser().resolve())
        request_key = (path_key, prepared.request_key)
        with self._lock:
            completed = _completed_job(normalized_path, prepared, force=force)
            if completed is not None:
                return completed
            active = _active_job(
                normalized_path,
                request_key,
                self._active_by_request,
            )
            if active is not None:
                return active
            run = _reserve_run(normalized_path, scope, prepared)
            run_id = str(run["run_id"])
            thread = self._worker_thread(
                normalized_path,
                scope,
                detector_families,
                force,
                prepared,
                request_key,
                run_id,
                path_key,
            )
            self._active_by_request[request_key] = run_id
            self._threads_by_run[(path_key, run_id)] = thread
            self._start_worker(thread, normalized_path, request_key, run_id, path_key)
            return _job_view(run, request_reused="none", worker_owned=True)

    def status(self, db_path: Path, run_id: str) -> dict[str, Any] | None:
        """Read persistent status and identify active rows not owned by this process."""
        normalized_path = Path(db_path)
        row = get_compression_run(normalized_path, run_id=run_id)
        if row is None:
            return None
        path_key = str(normalized_path.expanduser().resolve())
        with self._lock:
            worker_owned = (path_key, run_id) in self._threads_by_run
        if row["status"] in _ACTIVE_STATUSES and not worker_owned:
            return _interrupted_job(normalized_path, run_id, row)
        return _job_view(row, request_reused="none", worker_owned=worker_owned)

    def _worker_thread(
        self,
        db_path: Path,
        scope: CompressionScope,
        detector_families: Sequence[str] | None,
        force: bool,
        prepared: PreparedCompressionRequest,
        request_key: tuple[str, str],
        run_id: str,
        path_key: str,
    ) -> threading.Thread:
        return threading.Thread(
            target=self._run,
            kwargs={
                "db_path": db_path,
                "scope": scope,
                "detector_families": detector_families,
                "force": force,
                "prepared": prepared,
                "request_key": request_key,
                "run_id": run_id,
                "path_key": path_key,
            },
            name=f"compression-{run_id[-12:]}",
            daemon=True,
        )

    def _start_worker(
        self,
        thread: threading.Thread,
        db_path: Path,
        request_key: tuple[str, str],
        run_id: str,
        path_key: str,
    ) -> None:
        try:
            thread.start()
        except Exception as exc:
            self._active_by_request.pop(request_key, None)
            self._threads_by_run.pop((path_key, run_id), None)
            _mark_failed(db_path, run_id, "compression_worker_start_failed", exc)
            raise

    def _run(
        self,
        *,
        db_path: Path,
        scope: CompressionScope,
        detector_families: Sequence[str] | None,
        force: bool,
        prepared: PreparedCompressionRequest,
        request_key: tuple[str, str],
        run_id: str,
        path_key: str,
    ) -> None:
        try:
            profile = self._builder(
                db_path,
                scope,
                detector_families=detector_families,
                force=force,
                reserved_run_id=run_id,
                prepared_request=prepared,
            )
            _complete_active_run(db_path, run_id, profile)
        except Exception as exc:
            _mark_active_failed(db_path, run_id, exc)
        finally:
            with self._lock:
                _release_active_request(self._active_by_request, request_key, run_id)
                self._threads_by_run.pop((path_key, run_id), None)


def _completed_job(
    db_path: Path,
    prepared: PreparedCompressionRequest,
    *,
    force: bool,
) -> dict[str, Any] | None:
    if force:
        return None
    cached = find_current_compression_profile(db_path, **prepared.cache_lookup())
    if cached is None:
        return None
    run = get_compression_run(db_path, run_id=str(cached["run_id"]))
    return None if run is None else _job_view(run, "completed", worker_owned=False)


def _active_job(
    db_path: Path,
    request_key: tuple[str, str],
    active_by_request: dict[tuple[str, str], str],
) -> dict[str, Any] | None:
    active_run_id = active_by_request.get(request_key)
    if active_run_id is None:
        return None
    active = get_compression_run(db_path, run_id=active_run_id)
    if active is not None and active["status"] in _ACTIVE_STATUSES:
        return _job_view(active, "active", worker_owned=True)
    active_by_request.pop(request_key, None)
    return None


def _reserve_run(
    db_path: Path,
    scope: CompressionScope,
    prepared: PreparedCompressionRequest,
) -> dict[str, Any]:
    return create_compression_run(
        db_path,
        source_revision="",
        scope_hash=prepared.scope_hash,
        detector_set_version=prepared.detector_set_version,
        estimator_version=prepared.estimator_version,
        compression_schema_version=prepared.compression_schema_version,
        source_generation=prepared.source_generation,
        revision_key=prepared.revision_key,
        scope=scope.as_dict(),
        filters={"request_key": prepared.request_key},
    )


def _interrupted_job(
    db_path: Path,
    run_id: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    latest = get_compression_run(db_path, run_id=run_id)
    if latest is not None and latest["status"] not in _ACTIVE_STATUSES:
        return _job_view(latest, "none", worker_owned=False)
    interrupted = dict(row)
    interrupted["persisted_status"] = row["status"]
    interrupted["status"] = "interrupted"
    interrupted["error_summary"] = {"code": "compression_worker_not_owned"}
    return _job_view(interrupted, "none", worker_owned=False)


def _complete_active_run(db_path: Path, run_id: str, profile: dict[str, Any]) -> None:
    row = get_compression_run(db_path, run_id=run_id)
    if row is None or row["status"] not in _ACTIVE_STATUSES:
        return
    status = str(profile.get("status") or "completed")
    if status not in {"completed", "completed_with_warnings"}:
        status = "completed"
    update_compression_run(
        db_path,
        run_id=run_id,
        status=status,
        stage="complete",
        progress_percent=100,
        public_profile=profile,
    )


def _mark_active_failed(db_path: Path, run_id: str, exc: Exception) -> None:
    row = get_compression_run(db_path, run_id=run_id)
    if row is not None and row["status"] in _ACTIVE_STATUSES:
        _mark_failed(db_path, run_id, "compression_run_failed", exc)


def _mark_failed(db_path: Path, run_id: str, code: str, exc: Exception) -> None:
    update_compression_run(
        db_path,
        run_id=run_id,
        status="failed",
        stage="failed",
        error_summary={"code": code, "type": type(exc).__name__},
    )


def _release_active_request(
    active_by_request: dict[tuple[str, str], str],
    request_key: tuple[str, str],
    run_id: str,
) -> None:
    if active_by_request.get(request_key) == run_id:
        active_by_request.pop(request_key, None)


def _job_view(
    row: dict[str, Any],
    request_reused: str,
    *,
    worker_owned: bool,
) -> dict[str, Any]:
    result = dict(row)
    result["request_reused"] = request_reused
    result["worker_owned"] = worker_owned
    result["next_poll_ms"] = 0 if result["status"] not in _ACTIVE_STATUSES else 250
    return result


compression_jobs = CompressionJobRegistry()
