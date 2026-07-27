"""One shared kernel application service for MCP, HTTP, and CLI."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .. import __version__
from ..allowance import AllowanceService
from ..allowance.rates import rate_card_status
from ..evidence import EvidenceService
from ..ingest import KernelIngestor, RefreshTrigger, refresh_request_hash
from ..live import GenerationJournal, LiveStream
from ..operational import (
    initialize_operational_database,
    load_cutover_control,
)
from ..query import QueryService
from .codec import evidence_request, json_value, query_request
from .jobs import JobReader
from .runtime import (
    CACHE_ROOT_ENV,
    CODEX_HOME_ENV,
    RuntimePaths,
    default_runtime_paths,
    discover_sources,
)

WorkerLauncher = Callable[[RuntimePaths], None]
WORKER_START_TIMEOUT_SECONDS = 5.0
_THREAD_LAUNCH_GUARD = threading.Lock()


class KernelApplication:
    """Stable adapter-independent use cases with JSON-safe outputs."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        worker_launcher: WorkerLauncher,
        source_provider: Callable[[Path], tuple[Path, ...]] = discover_sources,
    ) -> None:
        self.paths = paths
        self._launch_worker = worker_launcher
        self._sources = source_provider

    def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "usage_status": lambda: self.status(),
            "usage_refresh": lambda: self.refresh(
                wait_seconds=_number(arguments.get("wait_seconds", 0))
            ),
            "usage_query": lambda: self.query(arguments),
            "usage_evidence": lambda: self.evidence(arguments),
            "usage_allowance": lambda: self.allowance(arguments),
            "usage_job_status": lambda: self.job_status(
                _required_text(arguments, "job_id"),
                wait_seconds=_number(arguments.get("wait_seconds", 0)),
                include_result=_bool(arguments.get("include_result", False)),
            ),
        }
        try:
            handler = handlers[tool_name]
        except KeyError as exc:
            raise ValueError("unknown kernel tool") from exc
        return handler()

    def status(self) -> dict[str, Any]:
        operational = self.paths.kernel.operational
        rates = rate_card_status(self.paths.rate_card)
        if not operational.is_file():
            return {
                "version": __version__,
                "state": "absent",
                "generation": None,
                "publication_id": None,
                "refresh": None,
                "rate_card": rates,
            }
        control = load_cutover_control(operational)
        active = JobReader(operational).active()
        return {
            "version": __version__,
            "state": control.state.value,
            "generation": control.active_generation,
            "publication_id": control.integrity_digest,
            "refresh": json_value(active),
            "rate_card": rates,
        }

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_requests = payload.get("requests")
        if not isinstance(raw_requests, list):
            raise ValueError("requests must be an array")
        requests = tuple(
            query_request(item)
            for item in raw_requests
            if isinstance(item, dict)
        )
        if len(requests) != len(raw_requests):
            raise ValueError("every query request must be an object")
        results = QueryService(
            self.paths.kernel.operational
        ).execute_batch(requests)
        return {"results": json_value(results)}

    def evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = EvidenceService(
            self.paths.kernel.operational
        ).read(evidence_request(payload))
        return json_value(result)

    def allowance(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = _int(payload.get("limit", 100), "limit")
        cursor = _optional_text(payload.get("cursor"), "cursor")
        return AllowanceService(
            self.paths.kernel.operational,
            self.paths.rate_card,
        ).read(
            limit=limit,
            cursor=cursor,
        )

    def refresh(self, *, wait_seconds: float = 0) -> dict[str, Any]:
        operational = self.paths.kernel.operational
        sources = self._sources(self.paths.codex_home)
        request_hash = refresh_request_hash(list(sources))
        with _launch_guard(self.paths.cache_root):
            initialize_operational_database(operational)
            reader = JobReader(operational)
            active = reader.active()
            disposition = "started"
            if active is None:
                latest = reader.latest()
                self._launch_worker(self.paths)
                active = _await_worker_start(
                    reader,
                    previous_job_id=latest.job_id if latest else None,
                )
            else:
                disposition = (
                    "joined" if active.request_hash == request_hash else "busy"
                )
        reader = JobReader(operational)
        snapshot = reader.get(
            active.job_id,
            wait_seconds=wait_seconds,
            include_result=wait_seconds > 0,
        )
        return {
            "disposition": disposition,
            "job": json_value(snapshot),
        }

    def job_status(
        self,
        job_id: str,
        *,
        wait_seconds: float = 0,
        include_result: bool = False,
    ) -> dict[str, Any]:
        return json_value(
            JobReader(self.paths.kernel.operational).get(
                job_id,
                wait_seconds=wait_seconds,
                include_result=include_result,
            )
        )

    def live(
        self,
        *,
        last_event_id: int | None,
        limit: int,
        origin: str | None,
    ) -> tuple[str, ...]:
        from ..live import validate_loopback_origin

        validate_loopback_origin(origin)
        control = load_cutover_control(self.paths.kernel.operational)
        batch = LiveStream(
            GenerationJournal(self.paths.kernel.operational)
        ).read(
            last_event_id=last_event_id,
            limit=limit,
            active_generation=control.active_generation or 0,
            active_publication_id=control.integrity_digest,
        )
        return batch.to_sse()


def build_application(
    paths: RuntimePaths | None = None,
    *,
    worker_launcher: WorkerLauncher | None = None,
) -> KernelApplication:
    return KernelApplication(
        paths or default_runtime_paths(),
        worker_launcher=worker_launcher or launch_refresh_worker,
    )


def launch_refresh_worker(paths: RuntimePaths) -> None:
    environment = os.environ.copy()
    environment[CODEX_HOME_ENV] = str(paths.codex_home)
    environment[CACHE_ROOT_ENV] = str(paths.cache_root)
    package_root = str(Path(__file__).resolve().parents[3])
    inherited_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (package_root, inherited_path) if part
    )
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "codex_usage_tracker.kernel.interfaces.cli.main",
            "_refresh-worker",
        ],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def run_refresh_worker(paths: RuntimePaths | None = None) -> dict[str, Any]:
    runtime = paths or default_runtime_paths()
    sources = list(discover_sources(runtime.codex_home))
    result = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
        journal=GenerationJournal(runtime.kernel.operational),
    ).refresh(
        sources,
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id=f"interface-worker-{uuid.uuid4().hex}",
    )
    return json_value(result)


def _await_worker_start(
    reader: JobReader,
    *,
    previous_job_id: str | None,
) -> Any:
    deadline = time.monotonic() + WORKER_START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        snapshot = reader.latest()
        if snapshot is not None and snapshot.job_id != previous_job_id:
            return snapshot
        time.sleep(0.025)
    raise RuntimeError("refresh worker did not start")


@contextmanager
def _launch_guard(cache_root: Path) -> Iterator[None]:
    """Serialize the short active-check/worker-start gap across local callers."""

    cache_root.mkdir(parents=True, exist_ok=True)
    lock_path = cache_root / ".refresh-launch.lock"
    with _THREAD_LAUNCH_GUARD, lock_path.open("a+b") as lock:
        lock_path.chmod(0o600)
        try:
            import fcntl
        except ImportError:  # pragma: no cover - non-POSIX fallback
            yield
            return
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"{key} is invalid")
    return value.strip()


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("wait_seconds must be numeric")
    return float(value)


def _int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("include_result must be boolean")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value
