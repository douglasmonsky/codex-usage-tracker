"""One shared kernel application service for MCP, HTTP, and CLI."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .. import __version__
from ..allowance import AllowanceService
from ..allowance.rates import rate_card_status
from ..content import content_status
from ..evidence import EvidenceService
from ..hydration import HydrationPreset
from ..ingest import KernelIngestor, RefreshTrigger, refresh_request_hash
from ..live import GenerationJournal, LiveStream
from ..models import CutoverControl
from ..operational import (
    initialize_operational_database,
    load_cutover_control,
    load_hydration_coverage,
    load_publication_snapshot,
)
from ..query import (
    QueryService,
    exploration_guidance,
    materialize_query_requests,
    query_template_context_keys,
    snapshot_query_template_context,
)
from ..query.contracts import MAX_QUERY_RESPONSE_BYTES
from ..thread_labels import load_thread_label_hashes, thread_label_revision
from .codec import evidence_request, json_value, query_request
from .jobs import JobReader
from .runtime import (
    CACHE_ROOT_ENV,
    CODEX_HOME_ENV,
    RuntimePaths,
    default_runtime_paths,
    discover_sources,
)

WorkerLauncher = Callable[[RuntimePaths, HydrationPreset], None]
WORKER_START_TIMEOUT_SECONDS = 5.0
HYDRATION_PRESET_ENV = "CODEX_USAGE_TRACKER_HYDRATION_PRESET"
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
        self._query_cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self._query_cache_lock = threading.Lock()

    def dispatch(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "usage_status": lambda: self.status(),
            "usage_refresh": lambda: self.refresh(
                wait_seconds=_number(arguments.get("wait_seconds", 0)),
                hydration_preset=_hydration_preset(arguments.get("preset")),
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
                "history_coverage": _empty_history_coverage(),
                "rate_card": rates,
                "content": content_status(self.paths.content),
            }
        control, history_coverage = load_publication_snapshot(operational)
        active = JobReader(operational).active()
        return {
            "version": __version__,
            "state": control.state.value,
            "generation": control.active_generation,
            "publication_id": control.integrity_digest,
            "refresh": json_value(active),
            "history_coverage": history_coverage,
            "rate_card": rates,
            "content": content_status(self.paths.content),
        }

    def query(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_requests = payload.get("requests")
        if not isinstance(raw_requests, list):
            raise ValueError("requests must be an array")
        include_guidance = _bool(payload.get("include_guidance", False))
        if any(not isinstance(item, dict) for item in raw_requests):
            raise ValueError("every query request must be an object")
        materialized, publication = _materialize_query_snapshot(
            raw_requests,
            self.paths.kernel.operational,
        )
        requests = tuple(query_request(item) for item in materialized)
        if not requests and not include_guidance:
            raise ValueError("query requires a query request or guidance")
        if requests and publication is None:
            publication = load_publication_snapshot(
                self.paths.kernel.operational
            )
        history_coverage = (
            publication[1]
            if publication is not None
            else _history_coverage(self.paths.kernel.operational)
        )
        cache_key = None
        if requests:
            assert publication is not None
            cache_key = _query_cache_key(
                publication[0],
                requests,
                history_coverage=history_coverage,
                content=self.paths.content,
                rate_card=self.paths.rate_card,
                thread_labels=self.paths.codex_home,
            )
        cached = self._cached_query(cache_key) if cache_key is not None else None
        cache_hit = cached is not None
        if cached is None:
            results = (
                QueryService(
                    self.paths.kernel.operational,
                    content_path=self.paths.content,
                    rate_card_path=self.paths.rate_card,
                    thread_labels=load_thread_label_hashes(
                        self.paths.codex_home,
                    ),
                    publication=publication,
                ).execute_batch(requests)
                if requests
                else ()
            )
            serialized_results = json_value(results)
            if cache_key is not None:
                self._store_query(cache_key, serialized_results)
        else:
            serialized_results = cached
        response = {"results": serialized_results}
        response["history_coverage"] = history_coverage
        if cache_key is not None:
            response["cache"] = {"hit": cache_hit, "key": cache_key}
        if include_guidance:
            response["guidance"] = exploration_guidance()
        response_size = len(
            json.dumps(
                response,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        if response_size > MAX_QUERY_RESPONSE_BYTES:
            raise ValueError("query response exceeds byte budget; lower request limits")
        return response

    def _cached_query(self, key: str) -> list[dict[str, Any]] | None:
        with self._query_cache_lock:
            cached = self._query_cache.get(key)
            if cached is None:
                return None
            self._query_cache.move_to_end(key)
            return copy.deepcopy(cached)

    def _store_query(self, key: str, results: list[dict[str, Any]]) -> None:
        with self._query_cache_lock:
            self._query_cache[key] = copy.deepcopy(results)
            self._query_cache.move_to_end(key)
            while len(self._query_cache) > 32:
                self._query_cache.popitem(last=False)

    def evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = EvidenceService(
            self.paths.kernel.operational,
            thread_labels=load_thread_label_hashes(
                self.paths.codex_home,
            ),
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

    def refresh(
        self,
        *,
        wait_seconds: float = 0,
        hydration_preset: HydrationPreset | None = None,
    ) -> dict[str, Any]:
        operational = self.paths.kernel.operational
        selected_preset = _selected_hydration_preset(
            operational,
            requested=hydration_preset,
        )
        sources = self._sources(self.paths.codex_home)
        request_hash = refresh_request_hash(
            list(sources),
            hydration_preset=selected_preset,
        )
        with _launch_guard(self.paths.cache_root):
            initialize_operational_database(operational)
            reader = JobReader(operational)
            active = reader.active()
            disposition = "started"
            if active is None:
                latest = reader.latest()
                self._launch_worker(self.paths, selected_preset)
                active = _await_worker_start(
                    reader,
                    previous_job_id=latest.job_id if latest else None,
                )
            else:
                disposition = "joined" if active.request_hash == request_hash else "busy"
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
        batch = LiveStream(GenerationJournal(self.paths.kernel.operational)).read(
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


def launch_refresh_worker(
    paths: RuntimePaths,
    hydration_preset: HydrationPreset,
) -> None:
    environment = os.environ.copy()
    environment[CODEX_HOME_ENV] = str(paths.codex_home)
    environment[CACHE_ROOT_ENV] = str(paths.cache_root)
    environment[HYDRATION_PRESET_ENV] = hydration_preset.value
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


def run_refresh_worker(
    paths: RuntimePaths | None = None,
    *,
    hydration_preset: HydrationPreset | None = None,
) -> dict[str, Any]:
    runtime = paths or default_runtime_paths()
    selected_preset = hydration_preset or _selected_hydration_preset(
        runtime.kernel.operational,
        requested=_hydration_preset(os.environ.get(HYDRATION_PRESET_ENV)),
    )
    sources = list(discover_sources(runtime.codex_home))
    result = KernelIngestor(
        runtime.kernel.analytical,
        runtime.kernel.operational,
        journal=GenerationJournal(runtime.kernel.operational),
    ).refresh(
        sources,
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id=f"interface-worker-{uuid.uuid4().hex}",
        hydration_preset=selected_preset,
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


def _hydration_preset(value: Any) -> HydrationPreset | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("preset must be a string")
    try:
        return HydrationPreset(value)
    except ValueError as exc:
        raise ValueError("preset must be recent_30d, recent_90d, or complete") from exc


def _selected_hydration_preset(
    operational: Path,
    *,
    requested: HydrationPreset | None,
) -> HydrationPreset:
    if requested is not None:
        return requested
    if operational.is_file():
        active = load_hydration_coverage(operational)["preset"]
        if isinstance(active, str):
            return HydrationPreset(active)
    return HydrationPreset.RECENT_30D


def _empty_history_coverage() -> dict[str, object]:
    return {
        "preset": None,
        "captured_at": None,
        "cutoff_at": None,
        "complete_history": False,
        "coverage_revision": None,
        "cataloged_source_count": 0,
        "hydrated_source_count": 0,
        "deferred_source_count": 0,
        "cataloged_bytes": 0,
        "hydrated_bytes": 0,
        "deferred_bytes": 0,
        "uncertain_source_count": 0,
    }


def _history_coverage(operational: Path) -> dict[str, object]:
    if not operational.is_file():
        return _empty_history_coverage()
    return load_hydration_coverage(operational)


def _materialize_query_snapshot(
    raw_requests: list[dict[str, Any]],
    operational_path: Path,
) -> tuple[
    tuple[dict[str, Any], ...],
    tuple[CutoverControl, dict[str, object]] | None,
]:
    required_context = query_template_context_keys(raw_requests)
    if not required_context:
        return materialize_query_requests(raw_requests), None
    publication = load_publication_snapshot(operational_path)
    context = snapshot_query_template_context(
        publication,
        required_keys=required_context,
    )
    return (
        materialize_query_requests(raw_requests, context=context),
        publication,
    )


def _query_cache_key(
    control: CutoverControl,
    requests: tuple[Any, ...],
    *,
    history_coverage: dict[str, object],
    content: Path,
    rate_card: Path,
    thread_labels: Path,
) -> str:
    payload = {
        "generation": control.active_generation,
        "publication_id": control.integrity_digest,
        "active_kernel_path": str(control.active_kernel_path),
        "coverage_revision": history_coverage["coverage_revision"],
        "requests": [json_value(request.normalized()) for request in requests],
        "content": content_status(content),
        "rate_card": rate_card_status(rate_card),
        "thread_labels": thread_label_revision(thread_labels),
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).hexdigest()
    )


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
