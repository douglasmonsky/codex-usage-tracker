"""Shared process-local lifecycle for dashboard analyses with persisted results."""

from __future__ import annotations

import copy
import secrets
import threading
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

ProgressReporter = Callable[..., None]
AnalysisWork = Callable[[ProgressReporter], Mapping[str, object] | None]
_ACTIVE_STATUSES = frozenset({"pending", "running"})


class AnalysisJobRegistry:
    """Run one background worker per semantic request and expose compact polling."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, object]] = {}
        self._active_by_request: dict[str, str] = {}

    def start(
        self,
        *,
        job_kind: str,
        request_key: str,
        source_revision: str,
        total_units: int | None,
        work: AnalysisWork,
        reload_endpoint: str | None = None,
    ) -> dict[str, object]:
        """Start work or reuse the active worker for an identical request."""
        with self._lock:
            active = self._active_job(request_key)
            if active is not None:
                return _job_view(active, request_reused="active")
            job_id = f"analysis_{secrets.token_urlsafe(12)}"
            now = _utc_now()
            job: dict[str, object] = {
                "schema": "codex-usage-tracker-analysis-job-v1",
                "job_id": job_id,
                "job_kind": job_kind,
                "status": "pending",
                "stage": "queued",
                "source_revision": source_revision,
                "created_at": now,
                "updated_at": now,
                "progress": _progress_payload(0, total_units, None),
                "result": None,
                "error": None,
                "_reload_endpoint": reload_endpoint,
            }
            self._jobs[job_id] = job
            self._active_by_request[request_key] = job_id
        thread = threading.Thread(
            target=self._run,
            kwargs={
                "job_id": job_id,
                "request_key": request_key,
                "work": work,
                "total_units": total_units,
            },
            name=f"analysis-{job_kind}-{job_id[-8:]}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:
            self._fail(job_id, request_key, "analysis_worker_start_failed", exc)
            raise
        return self.status(job_id)

    def status(self, job_id: str) -> dict[str, object]:
        """Return a detached status snapshot without mutating worker state."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return _missing_job(job_id)
            return _job_view(job, request_reused="none")

    def _run(
        self,
        *,
        job_id: str,
        request_key: str,
        work: AnalysisWork,
        total_units: int | None,
    ) -> None:
        self._update(job_id, status="running", stage="starting")

        def progress(
            *,
            stage: str,
            completed_units: int,
            total_units: int | None = total_units,
            current_unit: str | None = None,
        ) -> None:
            self._update_progress(
                job_id,
                stage=stage,
                completed_units=completed_units,
                total_units=total_units,
                current_unit=current_unit,
            )

        try:
            result = dict(work(progress) or {})
        except BaseException as exc:  # noqa: BLE001 - workers must publish terminal state.
            self._fail(job_id, request_key, "analysis_job_failed", exc)
            return
        self._complete(job_id, request_key, result, total_units)

    def _update_progress(
        self,
        job_id: str,
        *,
        stage: str,
        completed_units: int,
        total_units: int | None,
        current_unit: str | None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["status"] not in _ACTIVE_STATUSES:
                return
            previous = job["progress"]
            if not isinstance(previous, dict):
                raise RuntimeError("analysis job progress state is invalid")
            completed = max(int(previous["completed_units"]), max(0, int(completed_units)))
            job.update(
                status="running",
                stage=stage,
                progress=_progress_payload(completed, total_units, current_unit),
                updated_at=_utc_now(),
            )

    def _complete(
        self,
        job_id: str,
        request_key: str,
        result: dict[str, object],
        total_units: int | None,
    ) -> None:
        completed = 0 if total_units is None else total_units
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                previous = job["progress"]
                if not isinstance(previous, dict):
                    raise RuntimeError("analysis job progress state is invalid")
                completed = max(completed, int(previous["completed_units"]))
                job.update(
                    status="completed",
                    stage="complete",
                    progress=_progress_payload(completed, total_units or completed, None),
                    result=result,
                    updated_at=_utc_now(),
                )
            self._release(request_key, job_id)

    def _fail(
        self,
        job_id: str,
        request_key: str,
        code: str,
        exc: BaseException,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(
                    status="failed",
                    stage="failed",
                    error={"code": code, "type": type(exc).__name__},
                    updated_at=_utc_now(),
                )
            self._release(request_key, job_id)

    def _active_job(self, request_key: str) -> dict[str, object] | None:
        job_id = self._active_by_request.get(request_key)
        if job_id is None:
            return None
        job = self._jobs.get(job_id)
        if job is not None and job["status"] in _ACTIVE_STATUSES:
            return job
        self._active_by_request.pop(request_key, None)
        return None

    def _release(self, request_key: str, job_id: str) -> None:
        if self._active_by_request.get(request_key) == job_id:
            self._active_by_request.pop(request_key, None)

    def _update(self, job_id: str, **updates: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.update(updates)
            job["updated_at"] = _utc_now()


def _progress_payload(
    completed_units: int,
    total_units: int | None,
    current_unit: str | None,
) -> dict[str, object]:
    total = None if total_units is None else max(0, int(total_units))
    completed = max(0, int(completed_units))
    percent = None if not total else round(min(100.0, completed / total * 100), 3)
    return {
        "completed_units": completed,
        "total_units": total,
        "percent": percent,
        "current_unit": current_unit,
    }


def _job_view(job: Mapping[str, object], *, request_reused: str) -> dict[str, object]:
    payload = copy.deepcopy(dict(job))
    payload["cache"] = {"request_reused": request_reused}
    if payload["status"] in _ACTIVE_STATUSES:
        payload["next"] = {
            "action": "poll",
            "job_id": payload["job_id"],
            "poll_after_ms": 500,
        }
    elif payload["status"] == "completed":
        payload["next"] = {"action": "reload_persisted_results"}
        if reload_endpoint := payload.get("_reload_endpoint"):
            payload["next"]["endpoint"] = reload_endpoint
    else:
        payload["next"] = {"action": "retry"}
    payload.pop("_reload_endpoint", None)
    return payload


def _missing_job(job_id: str) -> dict[str, object]:
    return {
        "schema": "codex-usage-tracker-analysis-job-v1",
        "job_id": job_id,
        "status": "missing",
        "stage": "missing",
        "error": {"code": "analysis_job_not_found"},
        "next": {"action": "restart"},
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
