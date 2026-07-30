"""Collect canonical, path-safe Agent Perf evidence for CK-04."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any

import psutil  # type: ignore[import-untyped]

from .agent_perf import AgentPerfContractError, AgentPerfWorkload, load_agent_perf_workload
from .canonical import canonical_json_bytes, canonical_sha256
from .fixture import FixtureBundle, FixtureContractError, load_fixture_bundle

_EVIDENCE_SCHEMA = "codex-usage-tracker.ck04-agent-perf-evidence.v1"
_AGENT_PERF_LABEL = "ck04-candidate-a-standard"
_CANDIDATE_INCLUDE = "experiments/physical-architecture/candidate_a"
_RESULT_FIELDS = frozenset(
    {
        "artifact_sha256",
        "candidate_id",
        "manifest_digest",
        "oracle_digest",
        "parser_workers",
        "physical_cores",
        "publication_id",
        "workload_matrix_digest",
        "workload_id",
    }
)
_MAX_CAPTURE_BYTES = 1_048_576
_MAX_HOTSPOTS = 20
_CANONICAL_RUN_ROOT = Path("/tmp/codex-usage-tracker-ck04-agent-perf-v1")


class AgentPerfEvidenceError(ValueError):
    """Raised when CK-04 Agent Perf evidence cannot be collected safely."""


@dataclass(frozen=True)
class ProcessCapture:
    """Bounded observations from one owned process tree."""

    exit_code: int
    observed_processes: int
    process_tree_cpu_ns: int
    stderr: bytes
    stdout: bytes
    wall_time_ns: int


@dataclass(frozen=True)
class AgentPerfEvidenceBuild:
    """Canonical evidence written by the collector."""

    canonical_bytes: bytes
    payload: dict[str, object]


ProcessRunner = Callable[
    [tuple[str, ...]],
    ProcessCapture,
]


def _read_bounded(stream: Any, destination: bytearray) -> None:
    while True:
        chunk = stream.read(65_536)
        if not chunk:
            return
        remaining = _MAX_CAPTURE_BYTES - len(destination)
        if remaining > 0:
            destination.extend(chunk[:remaining])


def _owned_process_runner(
    argv: tuple[str, ...],
    *,
    cwd: Path,
    environment: dict[str, str],
) -> ProcessCapture:
    """Run one no-shell command and observe only its descendant process tree."""

    started = time.perf_counter_ns()
    process = subprocess.Popen(  # noqa: S603 - argv is a frozen, validated contract
        argv,
        cwd=cwd,
        env=environment,
        shell=False,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:  # pragma: no cover
        raise AgentPerfEvidenceError("process pipes were not created")

    stdout = bytearray()
    stderr = bytearray()
    readers = (
        threading.Thread(target=_read_bounded, args=(process.stdout, stdout), daemon=True),
        threading.Thread(target=_read_bounded, args=(process.stderr, stderr), daemon=True),
    )
    for reader in readers:
        reader.start()

    root = psutil.Process(process.pid)
    observed_cpu_ns: dict[int, int] = {}
    while process.poll() is None:
        try:
            owned = (root, *root.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            owned = ()
        for item in owned:
            try:
                cpu = item.cpu_times()
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            observed_cpu_ns[item.pid] = max(
                observed_cpu_ns.get(item.pid, 0),
                int((cpu.user + cpu.system) * 1_000_000_000),
            )
        time.sleep(0.01)

    for reader in readers:
        reader.join()
    return ProcessCapture(
        exit_code=int(process.returncode),
        observed_processes=max(1, len(observed_cpu_ns)),
        process_tree_cpu_ns=sum(observed_cpu_ns.values()),
        stderr=bytes(stderr),
        stdout=bytes(stdout),
        wall_time_ns=time.perf_counter_ns() - started,
    )


def _package_version(python: Path, distribution: str) -> str:
    completed = subprocess.run(  # noqa: S603 - interpreter is an explicit input
        (
            str(python),
            "-c",
            f"import importlib.metadata as m; print(m.version({distribution!r}))",
        ),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _pinned_tool_versions(agent_perf_executable: Path) -> dict[str, str]:
    try:
        first_line = agent_perf_executable.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeDecodeError, IndexError) as error:
        raise AgentPerfEvidenceError("agent-perf executable is not readable") from error
    if not first_line.startswith("#!"):
        raise AgentPerfEvidenceError("agent-perf executable has no Python interpreter")
    # Preserve the uv-tool environment path. Resolving its interpreter symlink
    # would discard the environment-specific site-packages and metadata.
    agent_perf_python = Path(first_line[2:])
    try:
        psutil_version = importlib.metadata.version("psutil")
        scalene_version = importlib.metadata.version("scalene")
    except importlib.metadata.PackageNotFoundError as error:
        raise AgentPerfEvidenceError("declared profiling tools are unavailable") from error
    return {
        "agent_perf": _package_version(agent_perf_python, "agent-perf"),
        "psutil": psutil_version,
        "scalene": scalene_version,
    }


def _require_standard_contract(
    workload: AgentPerfWorkload,
    fixture: FixtureBundle,
    versions: Mapping[str, str],
) -> None:
    if workload.candidate_id != "A":
        raise AgentPerfEvidenceError("collector supports only frozen Candidate A evidence")
    if (
        fixture.profile != "standard"
        or fixture.fixture_revision != workload.fixture_revision
        or fixture.manifest_digest != workload.fixture_manifest_digest
        or fixture.oracle_digest != workload.fixture_oracle_digest
    ):
        raise AgentPerfEvidenceError("collector requires the exact standard synthetic fixture")
    format_policy = fixture.manifest.get("format_policy")
    if not isinstance(format_policy, Mapping) or format_policy.get("content_bodies") is not False:
        raise AgentPerfEvidenceError("fixture is not structural-only synthetic metadata")
    if versions != {
        "agent_perf": "0.1.0",
        "psutil": "7.2.2",
        "scalene": "2.3.0",
    }:
        raise AgentPerfEvidenceError(
            "collector requires Agent Perf 0.1.0, psutil 7.2.2, and Scalene 2.3.0"
        )


def _load_result(path: Path, workload: AgentPerfWorkload) -> tuple[dict[str, object], str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AgentPerfEvidenceError("candidate result is not readable JSON") from error
    if not isinstance(payload, dict) or set(payload) != _RESULT_FIELDS:
        raise AgentPerfEvidenceError("candidate result fields differ from the frozen contract")
    expected = {
        "candidate_id": "A",
        "manifest_digest": workload.fixture_manifest_digest,
        "oracle_digest": workload.fixture_oracle_digest,
        "parser_workers": 1,
        "workload_matrix_digest": workload.workload_matrix_digest,
        "workload_id": workload.workload_id,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise AgentPerfEvidenceError("candidate result identity differs from the frozen workload")
    for name in ("artifact_sha256",):
        value = payload.get(name)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)
        ):
            raise AgentPerfEvidenceError(f"candidate result {name} is not SHA-256")
    if not isinstance(payload.get("physical_cores"), int) or int(payload["physical_cores"]) < 1:
        raise AgentPerfEvidenceError("candidate result physical_cores is invalid")
    publication_id = payload.get("publication_id")
    if not isinstance(publication_id, str) or not publication_id:
        raise AgentPerfEvidenceError("candidate result publication_id is invalid")
    return payload, canonical_sha256(payload)


def _run_record(
    *,
    sample_id: str,
    capture: ProcessCapture,
    result_identity: str,
) -> dict[str, object]:
    return {
        "observed_processes": capture.observed_processes,
        "process_tree_cpu_ns": capture.process_tree_cpu_ns,
        "result_identity_sha256": result_identity,
        "run_id": sample_id,
        "stderr_bytes": len(capture.stderr),
        "stderr_sha256": hashlib.sha256(capture.stderr).hexdigest(),
        "stdout_bytes": len(capture.stdout),
        "stdout_sha256": hashlib.sha256(capture.stdout).hexdigest(),
        "wall_time_ns": capture.wall_time_ns,
    }


@contextmanager
def _canonical_run_paths(
    *,
    scratch_root: Path,
    fixture_root: Path,
    python_executable: Path,
) -> Any:
    """Expose run inputs through stable, non-private command coordinates."""

    scratch_root.mkdir(parents=True, exist_ok=False)
    (scratch_root / "fixture").symlink_to(fixture_root.resolve(), target_is_directory=True)
    (scratch_root / "python").symlink_to(python_executable.resolve())
    try:
        _CANONICAL_RUN_ROOT.symlink_to(scratch_root.resolve(), target_is_directory=True)
    except FileExistsError as error:
        raise AgentPerfEvidenceError("canonical Agent Perf run alias already exists") from error
    try:
        yield
    finally:
        with suppress(FileNotFoundError):
            _CANONICAL_RUN_ROOT.unlink()


def _relative_candidate_source(repository_root: Path, source: object) -> str:
    if not isinstance(source, str):
        raise AgentPerfEvidenceError("Agent Perf hotspot source is invalid")
    try:
        relative = Path(source).resolve().relative_to(repository_root.resolve())
    except ValueError as error:
        raise AgentPerfEvidenceError("Agent Perf hotspot escaped the repository") from error
    posix = PurePosixPath(relative.as_posix())
    if not posix.as_posix().startswith(f"{_CANDIDATE_INCLUDE}/"):
        raise AgentPerfEvidenceError("Agent Perf hotspot escaped Candidate A")
    return posix.as_posix()


def _normalized_profile(
    *,
    repository_root: Path,
    state_root: Path,
    capture: ProcessCapture,
) -> tuple[str, dict[str, object]]:
    try:
        launch = json.loads(capture.stdout.decode("utf-8"))
        run_id = launch["run_id"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise AgentPerfEvidenceError("Agent Perf did not return a run identity") from error
    if not isinstance(run_id, str) or not run_id:
        raise AgentPerfEvidenceError("Agent Perf returned an invalid run identity")
    normalized_path = state_root / "runs" / run_id / "normalized.json"
    try:
        normalized = json.loads(normalized_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AgentPerfEvidenceError("Agent Perf normalized artifact is unavailable") from error
    if not isinstance(normalized, dict):
        raise AgentPerfEvidenceError("Agent Perf normalized artifact is not an object")
    required = {
        "exit_code": 0,
        "label": _AGENT_PERF_LABEL,
        "profiler": "scalene",
        "profiler_version": "2.3.0",
        "root": str(repository_root.resolve()),
        "run_id": run_id,
        "runtime": "python",
        "schema_version": 1,
        "status": "complete",
    }
    if any(normalized.get(key) != value for key, value in required.items()):
        raise AgentPerfEvidenceError("Agent Perf normalized artifact differs from the frozen run")
    raw_hotspots = normalized.get("hotspots")
    if not isinstance(raw_hotspots, list):
        raise AgentPerfEvidenceError("Agent Perf hotspots are unavailable")
    hotspots: list[dict[str, object]] = []
    for rank, hotspot in enumerate(raw_hotspots[:_MAX_HOTSPOTS], start=1):
        if not isinstance(hotspot, dict):
            raise AgentPerfEvidenceError("Agent Perf hotspot is invalid")
        symbol = hotspot.get("function")
        share = hotspot.get("total_share")
        if not isinstance(symbol, str) or not symbol or not isinstance(share, (int, float)):
            raise AgentPerfEvidenceError("Agent Perf hotspot attribution is invalid")
        percent = Decimal(str(share)) * 100
        hotspots.append(
            {
                "python_cpu_percent": format(percent.normalize(), "f"),
                "rank": rank,
                "source": _relative_candidate_source(repository_root, hotspot.get("source_path")),
                "symbol": symbol,
            }
        )
    return run_id, {
        "hotspots": hotspots,
        "mapping": "source coordinates reported by Agent Perf normalized output",
        "mode": "cpu",
        "profile_is_attribution_only": True,
        "unsupported_telemetry": {
            "native_cpu": "not reported by Agent Perf normalized schema v1",
            "peak_rss": "not reported by Agent Perf normalized schema v1",
        },
    }


def collect_agent_perf_evidence(
    *,
    repository_root: Path,
    workload_path: Path,
    fixture_root: Path,
    destination: Path,
    python_executable: Path,
    agent_perf_executable: Path,
    scratch_root: Path,
    process_runner: Callable[..., ProcessCapture] = _owned_process_runner,
) -> AgentPerfEvidenceBuild:
    """Run five direct builds and one identical profiled build, then write evidence."""

    if destination.exists():
        raise AgentPerfEvidenceError(f"evidence destination already exists: {destination.name}")
    try:
        workload = load_agent_perf_workload(workload_path)
        fixture = load_fixture_bundle(fixture_root)
    except (AgentPerfContractError, FixtureContractError) as error:
        raise AgentPerfEvidenceError(str(error)) from error
    versions = _pinned_tool_versions(agent_perf_executable)
    _require_standard_contract(workload, fixture, versions)

    repository_root = repository_root.resolve()
    environment = dict(os.environ)
    environment.update(workload.environment)
    environment["PYTHONPATH"] = str(repository_root / "experiments" / "physical-architecture")
    state_root = scratch_root / "agent-perf-state"
    environment["AGENT_PERF_STATE_DIR"] = str(state_root)

    with _canonical_run_paths(
        scratch_root=scratch_root,
        fixture_root=fixture_root,
        python_executable=python_executable,
    ):
        records: list[dict[str, object]] = []
        identities: set[str] = set()
        for index in range(1, workload.minimum_unprofiled_runs + 1):
            output = scratch_root / f"unprofiled-{index:02d}"
            command = workload.command(
                python=_CANONICAL_RUN_ROOT / "python",
                fixture_root=_CANONICAL_RUN_ROOT / "fixture",
                output_root=_CANONICAL_RUN_ROOT / f"unprofiled-{index:02d}",
            )
            capture = process_runner(command, cwd=repository_root, environment=environment)
            if capture.exit_code != 0:
                raise AgentPerfEvidenceError(f"unprofiled process {index} failed")
            _, identity = _load_result(output / "result.json", workload)
            identities.add(identity)
            records.append(
                _run_record(
                    sample_id=f"unprofiled-{index:02d}",
                    capture=capture,
                    result_identity=identity,
                )
            )

        profiled_output = scratch_root / "profiled"
        profiled_command = workload.command(
            python=_CANONICAL_RUN_ROOT / "python",
            fixture_root=_CANONICAL_RUN_ROOT / "fixture",
            output_root=_CANONICAL_RUN_ROOT / "profiled",
        )
        command = (
            str(agent_perf_executable.resolve()),
            "run",
            "--root",
            str(repository_root),
            "--runtime",
            "python",
            "--label",
            _AGENT_PERF_LABEL,
            "--include",
            _CANDIDATE_INCLUDE,
            "--",
            *profiled_command,
        )
        profile_capture = process_runner(command, cwd=repository_root, environment=environment)
        if profile_capture.exit_code != 0:
            raise AgentPerfEvidenceError("profile process failed")
        _, profile_identity = _load_result(profiled_output / "result.json", workload)
        identities.add(profile_identity)
        if len(identities) != 1:
            raise AgentPerfEvidenceError("result identities differ across executions")
        profile_run_id, profile = _normalized_profile(
            repository_root=repository_root,
            state_root=state_root,
            capture=profile_capture,
        )

    payload: dict[str, object] = {
        "candidate_id": "A",
        "fixture": {
            "manifest_sha256": workload.fixture_manifest_digest,
            "oracle_sha256": workload.fixture_oracle_digest,
            "profile": workload.fixture_profile,
            "revision": workload.fixture_revision,
            "synthetic_only": True,
        },
        "profiled_run": {
            **_run_record(
                sample_id=profile_run_id,
                capture=profile_capture,
                result_identity=profile_identity,
            ),
            "command_shape": profiled_command,
            "profile": profile,
        },
        "schema": _EVIDENCE_SCHEMA,
        "tool_versions": dict(sorted(versions.items())),
        "unprofiled_runs": records,
        "workload": {
            "digest": workload.digest,
            "id": workload.workload_id,
            "matrix_sha256": workload.workload_matrix_digest,
            "minimum_unprofiled_runs": workload.minimum_unprofiled_runs,
            "profile_is_attribution_only": True,
        },
    }
    canonical = canonical_json_bytes(payload)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical)
    except FileExistsError as error:
        raise AgentPerfEvidenceError(
            f"evidence destination already exists: {destination.name}"
        ) from error
    except OSError as error:
        raise AgentPerfEvidenceError("evidence destination could not be written") from error
    return AgentPerfEvidenceBuild(canonical_bytes=canonical, payload=payload)


__all__ = [
    "AgentPerfEvidenceBuild",
    "AgentPerfEvidenceError",
    "ProcessCapture",
    "canonical_json_bytes",
    "collect_agent_perf_evidence",
]
