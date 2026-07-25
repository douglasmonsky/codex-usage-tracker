"""Detached refresh worker startup with a bounded durable-job handshake."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from time import monotonic, sleep

from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.jobs.service import JobService
from codex_usage_tracker.store.analysis_job_repository import AnalysisJobRepository

DetachedRefreshLauncher = Callable[[str], None]

_STARTUP_ATTEMPTS = 2
_STARTUP_WINDOW_SECONDS = 0.25
_STARTUP_POLL_SECONDS = 0.01


def detached_refresh_launcher(
    *,
    request: RefreshRequest,
    codex_home: Path,
    db_path: Path,
    pricing_path: Path,
    job_service: JobService,
    enabled: bool,
) -> DetachedRefreshLauncher | None:
    """Build a launcher that confirms or safely retries worker startup."""

    repository = job_service.persistence
    if not enabled or not isinstance(repository, AnalysisJobRepository):
        return None

    def launch(job_id: str) -> None:
        command = [
            sys.executable,
            "-m",
            "codex_usage_tracker.application.refresh_worker",
            "--job-id",
            job_id,
            "--owner-id",
            repository.owner_id,
            "--job-db",
            str(repository.db_path),
            "--codex-home",
            str(codex_home),
            "--db",
            str(db_path),
            "--pricing",
            str(pricing_path),
            "--history",
            request.history,
            "--execution",
            request.execution,
        ]
        if request.aggregate_only:
            command.append("--aggregate-only")
        for _attempt in range(_STARTUP_ATTEMPTS):
            try:
                process = subprocess.Popen(  # noqa: S603 - fixed validated local module.
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                    start_new_session=True,
                )
            except OSError:
                continue
            deadline = monotonic() + _STARTUP_WINDOW_SECONDS
            while True:
                try:
                    row = repository.get(job_id, touch=False)
                except sqlite3.OperationalError:
                    row = None
                if row is not None and row.get("status") != "queued":
                    return
                if process.poll() is not None:
                    break
                if monotonic() >= deadline:
                    return
                sleep(_STARTUP_POLL_SECONDS)
        repository.update_status(
            job_id,
            state="failed",
            progress={"percent": 0, "stage": "failed"},
            error={
                "code": "refresh.worker_start_failed",
                "severity": "blocking",
                "message": "The detached refresh worker exited before claiming the job.",
                "remediation": "Retry usage_refresh; the prior job is safe to inspect.",
            },
        )

    return launch
