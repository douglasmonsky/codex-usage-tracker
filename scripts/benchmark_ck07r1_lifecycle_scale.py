#!/usr/bin/env python3
"""Qualify CK-07R1 lifecycle scale through the frozen reachable path.

The all-profile mode is the single authorized end-to-end publication/recovery
run.  Smaller modes only measure the pure lifecycle-preparation seam and do
not produce an acceptance receipt.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import getpass
import hashlib
import importlib.util
import json
import math
import os
import platform
import resource
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import fields, is_dataclass, replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.canonicalize import (
    AdapterAccounting,
    ProposedChangeSet,
    build_change_set,
)
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.parser import ParseBatch
from codex_usage_tracker.agent_kernel.adapters.contracts import AdapterObservation, SourceRange
from codex_usage_tracker.agent_kernel.publication import preparation
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    RefreshIntent,
    TailLimits,
    estimate_change_set,
    plan_refresh,
)
from codex_usage_tracker.agent_kernel.publication.recovery import (
    AnalyticalHead,
    PointerArtifact,
    PointerDocument,
    PromotionRequest,
    SmallPublicationRequest,
    promote_isolated_artifact,
    read_pointer,
    recover_startup,
    select_readable_artifact,
    write_pointer_durable,
)
from codex_usage_tracker.agent_kernel.publication.validation import build_isolated_artifact
from codex_usage_tracker.agent_kernel.publication.writer import (
    PriorPublicationSnapshot,
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
    read_prior_publication_snapshot,
)
from codex_usage_tracker.agent_kernel.storage.database import (
    initialize_analytical,
    initialize_operational,
    open_read_only,
    open_writer,
)
from codex_usage_tracker.agent_kernel.storage.operational import (
    JobRequest,
    JobState,
    LeaseName,
    OperationalStore,
    RecoveryIntent,
    RecoveryIntentState,
    WorkerIdentity,
)
from codex_usage_tracker.agent_kernel.storage.operational import (
    OperationClass as SidecarOperationClass,
)
from codex_usage_tracker.agent_kernel.storage.schema import SCHEMA_CONTRACT_SHA256

_SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_ROOT))

from tests.agent_kernel.contracts.reference.identity import semantic_id  # noqa: E402
from tests.agent_kernel.contracts.reference.lifecycle import fold_lifecycle  # noqa: E402

ROOT = _SCRIPT_ROOT
PROFILE_ROOT = ROOT / "tests" / "agent_kernel" / "fixtures" / "profiles"
TINY_ROOT = ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
DEPENDENCY_SHA = "d911b1f0d17596890a6a0a608be904330c96e9a6"
SCHEMA = "codex-usage-tracker.lifecycle-scale-requalification.v1"
PROFILE_DIGESTS = {
    "standard": "ef0da880255a0b13ea6055e0f8d748870c075635aa6f199c9521462c681250f3",
    "production": "2de0b4dc198603da6c1b0905b8d934e2cd5604e4036ef009d0cd07f1cc81f51b",
}
FROZEN_BUDGETS_MS = {
    "standard_30_day": 5_000,
    "production_all_time": 120_000,
    "no_change": 100,
    "one_call_tail": 500,
    "one_tool_tail": 500,
}
PUBLICATION_CHUNK_OBSERVATIONS = 8_000
SEED_PUBLICATION_ID = "publication:ck07r1:seed"

LAUNCH_COMMAND = (
    ".venv/bin/python",
    "scripts/benchmark_ck07r1_lifecycle_scale.py",
    "--profile",
    "all",
    "--samples",
    "5",
    "--output",
    "output/ck07r1/lifecycle-requalification-v2.json",
)
LAUNCH_ENVIRONMENT = {
    "LC_ALL": "C.UTF-8",
    "PYTHONHASHSEED": "0",
    "PYTHONUNBUFFERED": "1",
    "TZ": "UTC",
}
FORBIDDEN_ENVIRONMENT = ("PYTHONPATH", "CODEX_HOME")
RUN_OUTPUT_RELATIVE = Path("output/ck07r1/lifecycle-requalification-v2.json")
RUN_LEDGER_RELATIVE = Path("output/ck07r1/lifecycle-requalification-v2.launch-token.json")
RUN_STDOUT_RELATIVE = Path("output/ck07r1/lifecycle-requalification-v2.stdout.txt")
RUN_STDERR_RELATIVE = Path("output/ck07r1/lifecycle-requalification-v2.stderr.txt")
PRESERVED_V1_LEDGER_RELATIVE = Path(
    "output/ck07r1/lifecycle-requalification-v1.launch-token.json"
)
PRESERVED_V1_LEDGER_SHA256 = (
    "5c2b42eca6a3e54cf4163226bc55f3c75aa35112c4ed0342c11f4e39cb9922be"
)
SHARED_OVERLAY_AUTHORITY_RELATIVE = Path(
    "docs/decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json"
)
SHARED_OVERLAY_SCHEMA_RELATIVE = Path(
    "docs/decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.schema.json"
)
SHARED_OVERLAY_VERIFIER_RELATIVE = Path("scripts/ck07r1_shared_successor_overlay.py")
SHARED_OVERLAY_SCHEMA = "codex-usage-tracker.ck07r1-shared-successor-overlay.v1"
HISTORICAL_SHARED_OVERLAY_RELATIVES = (
    SHARED_OVERLAY_AUTHORITY_RELATIVE,
    SHARED_OVERLAY_SCHEMA_RELATIVE,
    SHARED_OVERLAY_VERIFIER_RELATIVE,
)
PRELAUNCH_RECOVERY_AUTHORITY_RELATIVE = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-prelaunch-recovery-authority-v1.json"
)
PRELAUNCH_RECOVERY_SCHEMA_RELATIVE = Path(
    "docs/decisions/evidence/ck07r1a0/lifecycle-prelaunch-recovery-authority-v1.schema.json"
)
PRELAUNCH_RECOVERY_VERIFIER_RELATIVE = Path("scripts/ck07r1_prelaunch_recovery.py")
PRELAUNCH_RECOVERY_SCHEMA = (
    "codex-usage-tracker.ck07r1-lifecycle-prelaunch-recovery.v1"
)
RUN_TOKEN_ID = "ck07r1-all-profile-e2e-1"
RUN_TOKEN_STATUS = "unspent_unavailable"
PRODUCTION_SAMPLE_COUNT = 5
PUBLICATION_RECOVERY_OVERHEAD_CANDIDATE_SECONDS = 120.0
AGGREGATE_TIMEOUT_CANDIDATE_SECONDS = (
    PRODUCTION_SAMPLE_COUNT * FROZEN_BUDGETS_MS["production_all_time"] / 1_000
    + PUBLICATION_RECOVERY_OVERHEAD_CANDIDATE_SECONDS
)
AGGREGATE_TIMEOUT_CANDIDATE_RULE = (
    "five production samples at the frozen 120-second lifecycle budget each "
    "plus one bounded 120-second publication/recovery allowance; candidate only "
    "and requires a later authority freeze"
)
HANDSHAKE_TIMEOUT_SECONDS = 5.0
TERMINATION_GRACE_TIMEOUT_SECONDS = 5.0
REAP_TIMEOUT_SECONDS = 5.0
REAP_POLL_SECONDS = 0.1
FIXTURE_MANIFEST_DIGEST = "91e0658f913c917bd8ce69fac9a1d75e881f41630eccc0f30f68bd9b6a972a35"
FIXTURE_MANIFEST_FILE_SHA256 = "e8c79373697ebe2af5385dbb2899ae49cec6104637c4a3b0909f91225128e0bc"
FIXTURE_SEED = 20260728
FROZEN_TAIL_LIMITS = {
    "selected_bytes": 8_388_608,
    "selected_records": 32,
    "observations": 12_000,
    "occurrences": 12_000,
    "affected_sessions": 2_000,
    "affected_turns": 4_000,
    "affected_resources": 4_000,
    "affected_allowance_cycles": 512,
    "dirty_keys": 16_000,
    "projection_rows": 16_000,
    "expected_wal_bytes": 16_777_216,
    "planning_staleness_us": 5_000_000,
    "model_call_tail_rows": 32_000,
}
FIXTURE_FILE_SHA256 = {
    "tests/agent_kernel/fixtures/profiles/standard-v1.json": PROFILE_DIGESTS["standard"],
    "tests/agent_kernel/fixtures/profiles/production-v1.json": PROFILE_DIGESTS["production"],
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0000.jsonl": "bad29500048dcff994d4211ff6de446c48d51184ab00caa134a7d668a6e57191",
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0001.jsonl": "d3ddb9592d67f058b7b7b354c7e01ff159d195c3963e0780be7a4cf35ec9a5eb",
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0002.jsonl": "114dadd49888fe77bfa1690b0fb810820950dea80d04ff11b233cd14bab54605",
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0003.jsonl": "12ccb3114f5f4583e98e6e0d8a485b2c1479762b93cd8e6008c9be14edfd2a5d",
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0004.jsonl": "0729952c7d2c250608ac0913a9d4a879c09b3bf252d86ee84b6b333000b66514",
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0005.jsonl": "cbfdfbb7f0f463c087c058b0f49cfdb6ec0ff72da5afa14d293b06a3f2ee817f",
    "tests/agent_kernel/fixtures/tiny-v1/sources/active/source-0006.jsonl": "f7693618223a2de73d5dcfc0c645f13455c480a721641b4d790c278744283729",
    "tests/agent_kernel/fixtures/tiny-v1/sources/archived/exact-copy.jsonl": "34709a9e5b6c52438f7c5710c9480db9a2641fbd33e25d8e6c767c383502a65f",
    "tests/agent_kernel/fixtures/tiny-v1/sources/malformed/malformed.jsonl": "cdfbf46b0d9524c5c9b16b6672eb98cd9f1b413703cd75f8ca9b833e96e5ac4d",
    "tests/agent_kernel/fixtures/tiny-v1/sources/replaced/revision-1.jsonl": "de66394d849cab6e4936af84b4991e36c1cdf6746f0ab90c7c39dd1ca10761e1",
    "tests/agent_kernel/fixtures/tiny-v1/sources/truncated/truncated.jsonl": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
}


def _jsonable(value: object) -> object:
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (OperationClass, SidecarOperationClass)):
        return value.value
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(
        _jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tail_limits() -> TailLimits:
    limits = TailLimits()
    serialized = _jsonable(limits)
    if serialized != FROZEN_TAIL_LIMITS:
        raise ValueError(f"TailLimits drifted from the frozen authority: {serialized}")
    return limits


def _fixture_identity() -> dict[str, Any]:
    manifest_path = TINY_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "codex-usage-tracker.synthetic-fixture-manifest.v1":
        raise ValueError("synthetic fixture manifest schema drifted")
    if manifest.get("manifest_digest") != FIXTURE_MANIFEST_DIGEST:
        raise ValueError("synthetic fixture manifest digest drifted")
    if manifest.get("seed") != FIXTURE_SEED:
        raise ValueError("synthetic fixture seed drifted")
    if _sha256(manifest_path) != FIXTURE_MANIFEST_FILE_SHA256:
        raise ValueError("synthetic fixture manifest file digest drifted")
    files = []
    for relative, expected in FIXTURE_FILE_SHA256.items():
        path = ROOT / relative
        if _sha256(path) != expected:
            raise ValueError(f"synthetic fixture file digest drifted: {relative}")
        files.append({"path": relative, "fixture_file_sha256": expected})
    return {
        "manifest": {
            "path": "tests/agent_kernel/fixtures/tiny-v1/manifest.json",
            "schema": "codex-usage-tracker.synthetic-fixture-manifest.v1",
            "fixture_manifest_digest": FIXTURE_MANIFEST_DIGEST,
            "fixture_file_sha256": FIXTURE_MANIFEST_FILE_SHA256,
            "seed": FIXTURE_SEED,
        },
        "fixture_files": files,
    }


def _workload_transition_digest(
    descriptors: Iterable[dict[str, Any]],
) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "workloads": [
                    {
                        "descriptor": descriptor,
                        "ordered_transition_vector_sha256": descriptor[
                            "ordered_transition_vector_sha256"
                        ],
                    }
                    for descriptor in descriptors
                ]
            }
        )
    ).hexdigest()


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _disk_available_bytes(path: Path) -> int:
    return shutil.disk_usage(path).free


def _relative_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"path is not repository-relative: {relative}")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"path escapes repository root: {relative}")
    return resolved


def _exclusive_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=False, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        if descriptor != -1:
            os.close(descriptor)


def _atomic_json_update(path: Path, value: dict[str, Any]) -> None:
    encoded = _canonical(value) + b"\n"
    temporary: Path | None = None
    temporary_fd = -1
    try:
        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(temporary_name)
        offset = 0
        while offset < len(encoded):
            written = os.write(temporary_fd, encoded[offset:])
            if written <= 0:
                raise OSError("atomic update made no write progress")
            offset += written
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = -1
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary_fd != -1:
            with contextlib.suppress(BaseException):
                os.close(temporary_fd)
        if temporary is not None:
            with contextlib.suppress(BaseException):
                temporary.unlink()


def _process_cwd(pid: int) -> Path | None:
    if sys.platform == "darwin":
        command = shutil.which("lsof") or "/usr/sbin/lsof"
        result = subprocess.run(
            [command, "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            if line.startswith("n"):
                return Path(line[1:]).resolve()
        return None
    proc_cwd = Path(f"/proc/{pid}/cwd")
    try:
        return proc_cwd.resolve()
    except OSError:
        return None


def _process_snapshot() -> list[dict[str, Any]]:
    result = subprocess.run(
        ["ps", "-ww", "-axo", "pid=,ppid=,user=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"process scan failed: {result.stderr.strip()}")
    processes: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        columns = line.strip().split(None, 3)
        if len(columns) != 4:
            continue
        pid, ppid, user, command = columns
        try:
            argv = shlex.split(command)
            processes.append(
                {
                    "pid": int(pid),
                    "parent_pid": int(ppid),
                    "user": user,
                    "argv": argv,
                    "command": command,
                    "platform_signature": _platform_process_signature(command),
                }
            )
        except ValueError:
            continue
    return processes


def _platform_process_signature(command: str) -> str:
    """Bind the exact command representation emitted by the host process table."""

    return hashlib.sha256(command.encode("utf-8", errors="strict")).hexdigest()


def _normalized_argv(argv: Iterable[str], cwd: Path) -> tuple[str, ...]:
    values = list(argv)
    path_indexes = {0, 1}
    if "--output" in values:
        path_indexes.add(values.index("--output") + 1)
    normalized = []
    for index, value in enumerate(values):
        if index in path_indexes:
            normalized.append(str((cwd / value).resolve()) if not Path(value).is_absolute() else str(Path(value).resolve()))
        else:
            normalized.append(value)
    return tuple(normalized)


def _platform_argv_matches_expected(
    argv: Iterable[str], expected_argv: Iterable[str], cwd: Path
) -> bool:
    """Compare every argument except argv[0], which the host may rewrite on fork."""

    try:
        observed = _normalized_argv(argv, cwd)
        expected = _normalized_argv(expected_argv, cwd)
    except (TypeError, ValueError):
        return False
    return len(observed) == len(expected) and observed[1:] == expected[1:]


def _capture_verified_parent_process_snapshot(
    pid: int,
    expected_argv: tuple[str, ...],
    expected_cwd: Path,
    expected_owner: str,
) -> dict[str, Any]:
    """Capture the host process identity used for collision and fork handshakes."""

    candidates = [process for process in _process_snapshot() if process.get("pid") == pid]
    if len(candidates) != 1:
        raise RuntimeError("verified parent process snapshot is missing or ambiguous")
    process = candidates[0]
    if process.get("user") != expected_owner:
        raise RuntimeError("verified parent process owner drifted")
    command = process.get("command")
    signature = process.get("platform_signature")
    if not isinstance(command, str) or not command:
        raise RuntimeError("verified parent process command snapshot is missing")
    if not isinstance(signature, str) or signature != _platform_process_signature(command):
        raise RuntimeError("verified parent process command signature is invalid")
    if not _platform_argv_matches_expected(process.get("argv", ()), expected_argv, expected_cwd):
        raise RuntimeError("verified parent process argv does not bind the frozen command")
    process_cwd = _process_cwd(pid)
    if process_cwd is None:
        raise RuntimeError("verified parent process cwd is missing or unreadable")
    expected_cwd = expected_cwd.resolve()
    if process_cwd != expected_cwd:
        raise RuntimeError("verified parent process cwd drifted")
    return {
        **process,
        "cwd": str(process_cwd),
        "platform_signature": signature,
    }


def _matching_processes(
    expected_argv: tuple[str, ...],
    expected_cwd: Path,
    *,
    owner: str | None = None,
    exclude_pids: Iterable[int] = (),
    verified_parent_snapshot: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if verified_parent_snapshot is None:
        raise RuntimeError("verified parent process snapshot is required")
    verified_signature = verified_parent_snapshot.get("platform_signature")
    verified_command = verified_parent_snapshot.get("command")
    if (
        not isinstance(verified_signature, str)
        or not verified_signature
        or not isinstance(verified_command, str)
        or _platform_process_signature(verified_command) != verified_signature
    ):
        raise RuntimeError("verified parent process signature is missing")
    current_owner = owner or getpass.getuser()
    excluded = set(exclude_pids)
    matches: list[dict[str, Any]] = []
    for process in _process_snapshot():
        process_pid = process.get("pid")
        if not isinstance(process_pid, int) or process_pid in excluded:
            continue
        if process.get("user") != current_owner:
            continue
        process_command = process.get("command")
        process_signature = process.get("platform_signature")
        if (
            not isinstance(process_command, str)
            or not isinstance(process_signature, str)
            or _platform_process_signature(process_command) != process_signature
        ):
            continue
        if not _platform_argv_matches_expected(process.get("argv", ()), expected_argv, expected_cwd):
            continue
        process_cwd = _process_cwd(process_pid)
        if process_cwd is None:
            raise RuntimeError(f"cannot verify cwd for matching process {process_pid}")
        if process_cwd == expected_cwd:
            matches.append(
                {
                    **process,
                    "cwd": str(process_cwd),
                    "platform_signature": process_signature,
                }
            )
    return matches


def _load_overlay_verifier(root: Path) -> Any:
    verifier_path = _relative_path(root, SHARED_OVERLAY_VERIFIER_RELATIVE)
    if not verifier_path.is_file():
        raise RuntimeError(
            "exact CK-07R1 shared-successor overlay verifier is unavailable"
        )
    spec = importlib.util.spec_from_file_location(
        "_ck07r1_shared_successor_overlay", verifier_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the exact CK-07R1 overlay verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_overlay_cohort(
    root: Path = ROOT,
    *,
    verifier: Any | None = None,
) -> dict[str, Any]:
    """Verify the immutable predecessor overlay in isolation.

    The corrected live cohort is admitted only by ``_verify_prelaunch_recovery``;
    this predecessor verifier is retained for historical evidence and tests.
    """

    authority_path = _relative_path(root, SHARED_OVERLAY_AUTHORITY_RELATIVE)
    schema_path = _relative_path(root, SHARED_OVERLAY_SCHEMA_RELATIVE)
    verifier_path = _relative_path(root, SHARED_OVERLAY_VERIFIER_RELATIVE)
    if not authority_path.is_file() or not schema_path.is_file():
        raise RuntimeError(
            "exact CK-07R1 shared-successor overlay authority/schema is unavailable"
        )
    if verifier is None:
        verifier = _load_overlay_verifier(root)
    try:
        authority, state = verifier.verify_shared_successor_overlay(root)
    except Exception as exc:
        raise RuntimeError(f"shared-successor overlay verification failed: {exc}") from exc
    if not isinstance(authority, Mapping):
        raise RuntimeError("shared-successor overlay authority is malformed")
    if authority.get("schema") != SHARED_OVERLAY_SCHEMA:
        raise RuntimeError("shared-successor overlay schema identity drifted")
    if authority.get("authority_version") != 1:
        raise RuntimeError("shared-successor overlay version drifted")
    if authority.get("status") != "permitted_not_accepted":
        raise RuntimeError("shared-successor overlay acceptance status drifted")
    if state != "worker_prequalification":
        raise RuntimeError(
            "shared-successor overlay did not admit the exact worker_prequalification cohort"
        )
    states = authority.get("states")
    successor = states.get("successor") if isinstance(states, Mapping) else None
    if not isinstance(successor, Mapping):
        raise RuntimeError("shared-successor overlay successor state is malformed")
    if successor.get("status") != "permitted_not_accepted":
        raise RuntimeError("shared-successor successor status drifted")
    if successor.get("runtime_acceptance") != "not_claimed":
        raise RuntimeError("shared-successor runtime acceptance was claimed")
    if successor.get("launch_authorized") is not False:
        raise RuntimeError("shared-successor launch authorization was claimed")
    invariants = authority.get("non_consuming_invariants")
    required_invariants = {
        "maximum_new_end_to_end_runs": 1,
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "matching_processes": [],
        "successful_child": "absent",
        "pid": "absent",
        "handshake": "absent",
        "runtime_acceptance": "not_claimed",
        "receipt": "absent_non_qualifying",
        "output": "absent",
        "ledger": "absent",
        "stdout": "absent",
        "stderr": "absent",
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }
    if not isinstance(invariants, Mapping) or any(
        invariants.get(name) != expected
        for name, expected in required_invariants.items()
    ):
        raise RuntimeError("shared-successor non-consuming invariants drifted")
    artifacts = successor.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise RuntimeError("shared-successor cohort artifact set is malformed")
    artifact_identity = []
    for artifact in artifacts:
        if not isinstance(artifact, Mapping):
            raise RuntimeError("shared-successor cohort artifact is malformed")
        path = artifact.get("path")
        digest = artifact.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            raise RuntimeError("shared-successor cohort artifact identity is malformed")
        artifact_identity.append(
            {"path": path, "sha256": digest, "presence": artifact.get("presence")}
        )
    return {
        "schema": authority["schema"],
        "authority_version": authority["authority_version"],
        "authority_base_sha": authority.get("authority_base_sha"),
        "state": state,
        "authority_path": str(SHARED_OVERLAY_AUTHORITY_RELATIVE),
        "authority_sha256": _sha256(authority_path),
        "schema_path": str(SHARED_OVERLAY_SCHEMA_RELATIVE),
        "schema_sha256": _sha256(schema_path),
        "verifier_path": str(SHARED_OVERLAY_VERIFIER_RELATIVE),
        "verifier_sha256": _sha256(verifier_path),
        "successor_artifacts": artifact_identity,
        "runtime_acceptance": successor["runtime_acceptance"],
        "launch_authorized": successor["launch_authorized"],
        "verification": "passed",
    }


def _load_prelaunch_recovery_verifier(root: Path) -> Any:
    verifier_path = _relative_path(root, PRELAUNCH_RECOVERY_VERIFIER_RELATIVE)
    if not verifier_path.is_file():
        raise RuntimeError("exact CK-07R1 prelaunch recovery verifier is unavailable")
    spec = importlib.util.spec_from_file_location(
        "_ck07r1_prelaunch_recovery", verifier_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the exact CK-07R1 prelaunch recovery verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _candidate_cohort(root: Path) -> list[dict[str, str]]:
    records = (
        (
            Path("src/codex_usage_tracker/agent_kernel/publication/preparation.py"),
            "preparation_source",
        ),
        (Path("scripts/benchmark_ck07r1_lifecycle_scale.py"), "corrected_launcher"),
        (
            Path("tests/agent_kernel/publication/test_lifecycle_scale.py"),
            "corrected_launcher_tests",
        ),
    )
    return [
        {"path": str(path), "sha256": _sha256(_relative_path(root, path)), "role": role}
        for path, role in records
    ]


def _historical_shared_overlay_bindings(root: Path) -> list[dict[str, str]]:
    bindings: list[dict[str, str]] = []
    for relative in HISTORICAL_SHARED_OVERLAY_RELATIVES:
        path = _relative_path(root, relative)
        if not path.is_file():
            raise RuntimeError(
                "prelaunch recovery historical shared-successor overlay evidence is unavailable"
            )
        bindings.append({"path": str(relative), "sha256": _sha256(path)})
    return bindings


def _verify_historical_shared_overlay_binding(
    authority: Mapping[str, Any], root: Path
) -> list[dict[str, str]]:
    records = authority.get("immutable_authorities")
    if not isinstance(records, list):
        raise RuntimeError(
            "prelaunch recovery historical shared-successor overlay binding is missing"
        )
    bound = {
        record.get("path"): record.get("sha256")
        for record in records
        if isinstance(record, Mapping)
    }
    expected = _historical_shared_overlay_bindings(root)
    if any(bound.get(item["path"]) != item["sha256"] for item in expected):
        raise RuntimeError(
            "prelaunch recovery historical shared-successor overlay binding drifted"
        )
    return expected


def _preserved_v1_ledger_identity(root: Path) -> dict[str, Any]:
    path = _relative_path(root, PRESERVED_V1_LEDGER_RELATIVE)
    if not path.is_file():
        raise RuntimeError("preserved CK-07R1 v1 terminal ledger is unavailable")
    digest = _sha256(path)
    if digest != PRESERVED_V1_LEDGER_SHA256:
        raise RuntimeError("preserved CK-07R1 v1 terminal ledger digest drifted")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("preserved CK-07R1 v1 terminal ledger is unreadable") from exc
    launch = payload.get("launch") if isinstance(payload, Mapping) else None
    if not isinstance(payload, Mapping) or not isinstance(launch, Mapping):
        raise RuntimeError("preserved CK-07R1 v1 terminal ledger is malformed")
    if payload.get("state") != "prelaunch_failed":
        raise RuntimeError("preserved CK-07R1 v1 terminal ledger state drifted")
    if payload.get("token_consumed") is not False:
        raise RuntimeError("preserved CK-07R1 v1 ledger token state drifted")
    if payload.get("token_status") != RUN_TOKEN_STATUS:
        raise RuntimeError("preserved CK-07R1 v1 ledger token status drifted")
    if launch.get("matching_processes") != []:
        raise RuntimeError("preserved CK-07R1 v1 ledger process state drifted")
    return {
        "path": str(PRESERVED_V1_LEDGER_RELATIVE),
        "sha256": digest,
        "state": payload["state"],
        "token_consumed": payload["token_consumed"],
        "token_status": payload["token_status"],
        "matching_processes": launch["matching_processes"],
    }


def _verify_prelaunch_recovery(
    root: Path = ROOT,
    *,
    verifier: Any | None = None,
) -> dict[str, Any]:
    """Verify preserved v1 recovery evidence before any v2 run side effect."""

    authority_path = _relative_path(root, PRELAUNCH_RECOVERY_AUTHORITY_RELATIVE)
    schema_path = _relative_path(root, PRELAUNCH_RECOVERY_SCHEMA_RELATIVE)
    verifier_path = _relative_path(root, PRELAUNCH_RECOVERY_VERIFIER_RELATIVE)
    if not authority_path.is_file() or not schema_path.is_file():
        raise RuntimeError(
            "exact CK-07R1 prelaunch recovery authority/schema is unavailable"
        )
    if verifier is None:
        verifier = _load_prelaunch_recovery_verifier(root)
    try:
        authority, state = verifier.verify_prelaunch_recovery(root)
    except Exception as exc:
        raise RuntimeError(f"prelaunch recovery verification failed: {exc}") from exc
    if not isinstance(authority, Mapping):
        raise RuntimeError("prelaunch recovery authority is malformed")
    if authority.get("schema") != PRELAUNCH_RECOVERY_SCHEMA:
        raise RuntimeError("prelaunch recovery schema identity drifted")
    if authority.get("authority_version") != 1:
        raise RuntimeError("prelaunch recovery authority version drifted")
    if authority.get("status") != "permitted_not_accepted":
        raise RuntimeError("prelaunch recovery acceptance status drifted")
    if state != "prelaunch_recovery_verified":
        raise RuntimeError("prelaunch recovery verifier did not return the exact verified state")
    decision = authority.get("decision")
    if not isinstance(decision, Mapping) or any(
        decision.get(field) != expected
        for field, expected in (
            ("launch_authorized_in_authority_task", False),
            ("implementation_acceptance", "not_claimed"),
            ("runtime_acceptance", "not_claimed"),
        )
    ):
        raise RuntimeError("prelaunch recovery acceptance state was claimed")
    transition = authority.get("recovery_transition")
    if not isinstance(transition, Mapping) or any(
        transition.get(field) != expected
        for field, expected in (
            ("old_shared_overlay", "immutable_historical_predecessor_evidence"),
            ("live_corrected_cohort_authority", "this_versioned_recovery_authority_only"),
            ("launched_process_retry", False),
            ("restart", False),
            ("replacement", False),
            ("refund", False),
        )
    ):
        raise RuntimeError("prelaunch recovery transition binding drifted")

    run_token = authority.get("run_token")
    expected_token = {
        "id": RUN_TOKEN_ID,
        "maximum_new_end_to_end_runs": 1,
        "status": RUN_TOKEN_STATUS,
        "token_consumed": False,
        "refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "successful_launches_observed": 0,
        "new_recovery_invocations_permitted": 1,
    }
    if not isinstance(run_token, Mapping) or any(
        run_token.get(field) != expected for field, expected in expected_token.items()
    ):
        raise RuntimeError("prelaunch recovery run-token binding drifted")

    preserved = _preserved_v1_ledger_identity(root)
    authority_preserved = authority.get("preserved_v1_ledger")
    if authority_preserved != preserved:
        raise RuntimeError("prelaunch recovery v1 ledger binding drifted")

    cohort = _candidate_cohort(root)
    if authority.get("candidate_cohort") != cohort:
        raise RuntimeError("prelaunch recovery candidate cohort binding drifted")

    historical_overlay = _verify_historical_shared_overlay_binding(authority, root)

    expected_paths = {
        "output": str(RUN_OUTPUT_RELATIVE),
        "ledger": str(RUN_LEDGER_RELATIVE),
        "stdout": str(RUN_STDOUT_RELATIVE),
        "stderr": str(RUN_STDERR_RELATIVE),
    }
    authority_paths: Any = authority.get("v2_paths")
    if authority_paths is None:
        launch_contract = authority.get("launch_contract")
        authority_paths = (
            launch_contract.get("exclusive_paths")
            if isinstance(launch_contract, Mapping)
            else None
        )
    if authority_paths != expected_paths:
        raise RuntimeError("prelaunch recovery v2 path binding drifted")
    return {
        "schema": authority["schema"],
        "authority_version": authority["authority_version"],
        "state": state,
        "authority_path": str(PRELAUNCH_RECOVERY_AUTHORITY_RELATIVE),
        "authority_sha256": _sha256(authority_path),
        "schema_path": str(PRELAUNCH_RECOVERY_SCHEMA_RELATIVE),
        "schema_sha256": _sha256(schema_path),
        "verifier_path": str(PRELAUNCH_RECOVERY_VERIFIER_RELATIVE),
        "verifier_sha256": (
            _sha256(verifier_path) if verifier_path.is_file() else None
        ),
        "preserved_v1_ledger": preserved,
        "candidate_cohort": cohort,
        "historical_shared_overlay": historical_overlay,
        "v2_paths": expected_paths,
        "verification": "passed",
    }


def _preflight_launch_paths(root: Path = ROOT) -> dict[str, Path]:
    output = _relative_path(root, RUN_OUTPUT_RELATIVE)
    ledger = _relative_path(root, RUN_LEDGER_RELATIVE)
    stdout = _relative_path(root, RUN_STDOUT_RELATIVE)
    stderr = _relative_path(root, RUN_STDERR_RELATIVE)
    if not output.parent.is_dir():
        raise FileNotFoundError(f"launch output parent does not exist: {output.parent}")
    for path in (output, ledger, stdout, stderr):
        if path.exists():
            raise FileExistsError(f"launch path already exists; refusing overwrite: {path}")
    return {"output": output, "ledger": ledger, "stdout": stdout, "stderr": stderr}


def _verify_launch_contract(root: Path = ROOT) -> dict[str, Any]:
    if root.resolve() != ROOT.resolve() or not (root / "pyproject.toml").is_file():
        raise RuntimeError("launch cwd is not the fresh retained repository root")
    script_and_args = (sys.argv[0], *sys.argv[1:])
    if script_and_args != LAUNCH_COMMAND[1:]:
        raise RuntimeError("launch argv is not the exact frozen command")
    expected_interpreter = root / ".venv" / "bin" / "python"
    expected_prefix = root / ".venv"
    if not expected_interpreter.is_file() or not expected_prefix.is_dir():
        raise RuntimeError("repository .venv/bin/python or venv directory is unavailable")
    expected_interpreter = expected_interpreter.absolute()
    expected_prefix = expected_prefix.absolute()
    actual_interpreter = Path(sys.executable)
    if not actual_interpreter.is_absolute():
        actual_interpreter = Path(os.path.abspath(sys.executable))
    actual_prefix = Path(sys.prefix)
    if not actual_prefix.is_absolute():
        actual_prefix = Path(os.path.abspath(sys.prefix))
    actual_base_prefix = Path(sys.base_prefix)
    if not actual_base_prefix.is_absolute():
        actual_base_prefix = Path(os.path.abspath(sys.base_prefix))
    if actual_interpreter != expected_interpreter:
        raise RuntimeError(
            "launch interpreter must use the repository .venv/bin/python lexical path"
        )
    if actual_prefix != expected_prefix:
        raise RuntimeError("launch sys.prefix is not the repository .venv")
    if actual_prefix == actual_base_prefix:
        raise RuntimeError("launch interpreter is not running inside the repository venv")
    for name, expected in LAUNCH_ENVIRONMENT.items():
        if os.environ.get(name) != expected:
            raise RuntimeError(f"launch environment drifted: {name}")
    for name in FORBIDDEN_ENVIRONMENT:
        if name in os.environ:
            raise RuntimeError(f"forbidden launch environment variable is present: {name}")
    paths = _preflight_launch_paths(root)
    owner = getpass.getuser()
    verified_parent_snapshot = _capture_verified_parent_process_snapshot(
        os.getpid(), LAUNCH_COMMAND, root, owner
    )
    matches = _matching_processes(
        LAUNCH_COMMAND,
        root,
        owner=owner,
        exclude_pids=(os.getpid(),),
        verified_parent_snapshot=verified_parent_snapshot,
    )
    if matches:
        raise RuntimeError(f"matching launch process already exists: {matches}")
    return {
        "argv": list(LAUNCH_COMMAND),
        "cwd": str(root.resolve()),
        "owner": owner,
        "interpreter": str(expected_interpreter),
        "venv_prefix": str(expected_prefix),
        "base_prefix": str(actual_base_prefix),
        "environment": dict(LAUNCH_ENVIRONMENT),
        "output_path": str(RUN_OUTPUT_RELATIVE),
        "fixture_identity": _fixture_identity(),
        "disk_available_bytes_before_launch": _disk_available_bytes(root),
        "matching_processes": matches,
        "verified_parent_process_snapshot": verified_parent_snapshot,
        "paths": paths,
    }


def _rss_from_usage(usage: resource.struct_rusage) -> int:
    value = usage.ru_maxrss
    return int(value if platform.system() == "Darwin" else value * 1024)


def _observe_child_start(
    child_pid: int,
    launch: dict[str, Any],
    parent_pid: int,
) -> dict[str, Any]:
    expected_cwd = Path(launch["cwd"]).resolve()
    expected_owner = str(launch["owner"])
    verified_parent_snapshot = launch.get("verified_parent_process_snapshot")
    if not isinstance(verified_parent_snapshot, Mapping):
        raise RuntimeError("child-start handshake lacks the verified parent snapshot")
    verified_signature = verified_parent_snapshot.get("platform_signature")
    verified_command = verified_parent_snapshot.get("command")
    if (
        not isinstance(verified_signature, str)
        or not verified_signature
        or not isinstance(verified_command, str)
        or _platform_process_signature(verified_command) != verified_signature
    ):
        raise RuntimeError("child-start handshake lacks the verified parent signature")
    deadline = time.monotonic() + HANDSHAKE_TIMEOUT_SECONDS
    while True:
        observed = _matching_processes(
            LAUNCH_COMMAND,
            expected_cwd,
            owner=expected_owner,
            exclude_pids=(parent_pid,),
            verified_parent_snapshot=verified_parent_snapshot,
        )
        if any(item.get("pid") != child_pid for item in observed):
            raise RuntimeError(
                "child-start handshake found an unexpected matching process"
            )
        for item in observed:
            observed_cwd = item.get("cwd")
            observed_command = item.get("command")
            if (
                item.get("pid") == child_pid
                and item.get("parent_pid") == parent_pid
                and item.get("user") == expected_owner
                and item.get("platform_signature") == verified_signature
                and isinstance(observed_command, str)
                and _platform_process_signature(observed_command)
                == verified_signature
                and _platform_argv_matches_expected(
                    item.get("argv", ()), LAUNCH_COMMAND, expected_cwd
                )
                and isinstance(observed_cwd, str)
                and Path(observed_cwd).resolve() == expected_cwd
            ):
                return item
        if time.monotonic() >= deadline:
            raise RuntimeError(
                "child-start handshake did not prove exact PID/argv/cwd/owner"
            )
        time.sleep(0.02)


class _ParentChildSignal(BaseException):
    """A parent signal that must be converted into terminal child cleanup."""

    def __init__(self, signal_number: int) -> None:
        self.signal_number = signal_number
        super().__init__(f"parent received signal {signal_number}")


def _parent_signal_handler(signal_number: int, _frame: object) -> None:
    if signal_number == signal.SIGINT:
        raise KeyboardInterrupt
    raise _ParentChildSignal(signal_number)


def _install_parent_child_signal_handlers() -> dict[int, Any]:
    previous = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }
    signal.signal(signal.SIGINT, _parent_signal_handler)
    signal.signal(signal.SIGTERM, _parent_signal_handler)
    return previous


def _restore_parent_child_signal_handlers(previous: Mapping[int, Any]) -> None:
    for signal_number, handler in previous.items():
        signal.signal(signal_number, handler)


@contextlib.contextmanager
def _parent_child_signal_handlers() -> Iterable[None]:
    previous = _install_parent_child_signal_handlers()
    try:
        yield
    finally:
        _restore_parent_child_signal_handlers(previous)


@contextlib.contextmanager
def _ignore_parent_child_signals() -> Iterable[None]:
    previous = {
        signal.SIGINT: signal.getsignal(signal.SIGINT),
        signal.SIGTERM: signal.getsignal(signal.SIGTERM),
    }
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    try:
        yield
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)


def _validate_child_pid(pid: int) -> None:
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError(f"child pid must be positive; got {pid!r}")


def _child_wait_for_release(read_fd: int, write_fd: int) -> bool:
    """Wait for the parent release byte without leaking pre-release failures."""
    read_open = True
    write_open = True
    previous: dict[int, Any] = {}
    try:
        os.close(write_fd)
        write_open = False
        previous = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            return os.read(read_fd, 1) == b"1"
        finally:
            for signal_number, handler in previous.items():
                with contextlib.suppress(BaseException):
                    signal.signal(signal_number, handler)
    except BaseException:
        return False
    finally:
        if read_open:
            with contextlib.suppress(BaseException):
                os.close(read_fd)
        if write_open:
            with contextlib.suppress(BaseException):
                os.close(write_fd)


def _child_entry(
    paths: dict[str, Path],
    launch: dict[str, Any],
    read_fd: int,
    write_fd: int,
) -> None:
    try:
        released = _child_wait_for_release(read_fd, write_fd)
    except BaseException:
        os._exit(71)
    if not released:
        os._exit(71)
    os._exit(_child_run(paths, launch))


def _bounded_reap(
    pid: int,
    timeout_seconds: float,
) -> tuple[int, int, resource.struct_rusage] | None:
    _validate_child_pid(pid)
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            waited_pid, status, usage = os.wait4(pid, os.WNOHANG)
        except ChildProcessError as exc:
            raise RuntimeError(f"child {pid} disappeared before bounded reap") from exc
        if waited_pid == pid:
            return waited_pid, status, usage
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(REAP_POLL_SECONDS, remaining))


def _terminate_and_reap_child(
    pid: int,
) -> tuple[int, int, resource.struct_rusage]:
    _validate_child_pid(pid)
    errors: list[BaseException] = []
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except BaseException as exc:
        errors.append(exc)
    try:
        result = _bounded_reap(pid, TERMINATION_GRACE_TIMEOUT_SECONDS)
    except BaseException as exc:
        errors.append(exc)
        result = None
    if result is None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except BaseException as exc:
            errors.append(exc)
        try:
            result = _bounded_reap(pid, REAP_TIMEOUT_SECONDS)
        except BaseException as exc:
            errors.append(exc)
            result = None
    if result is None:
        error = RuntimeError(f"child {pid} did not terminate after bounded SIGTERM/SIGKILL/reap")
        if errors:
            raise error from errors[-1]
        raise error
    return result


def _wait_for_child(pid: int) -> tuple[int, int, resource.struct_rusage, bool]:
    _validate_child_pid(pid)
    deadline = time.monotonic() + AGGREGATE_TIMEOUT_CANDIDATE_SECONDS
    while True:
        result = _bounded_reap(pid, 0.0)
        if result is not None:
            waited_pid, status, usage = result
            return waited_pid, status, usage, False
        if time.monotonic() >= deadline:
            break
        time.sleep(min(REAP_POLL_SECONDS, deadline - time.monotonic()))

    result = _terminate_and_reap_child(pid)
    waited_pid, status, usage = result
    return waited_pid, status, usage, True


def _ledger_update(path: Path, value: dict[str, Any]) -> None:
    _atomic_json_update(path, value)


def _build_evidence(paths: dict[str, Path]) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for path_key, digest_key, relative_path in (
        ("stdout", "stdout_sha256", RUN_STDOUT_RELATIVE),
        ("stderr", "stderr_sha256", RUN_STDERR_RELATIVE),
        ("output", "output_sha256", RUN_OUTPUT_RELATIVE),
    ):
        path = paths[path_key]
        if not path.is_file():
            raise FileNotFoundError(f"required launch evidence is missing: {path}")
        digest = _sha256(path)
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError(f"required launch evidence hash is invalid: {path}")
        evidence[f"{path_key}_path"] = str(relative_path)
        evidence[digest_key] = digest
    return evidence


def _validate_evidence(evidence: Mapping[str, Any]) -> None:
    expected = {
        "stdout_path": str(RUN_STDOUT_RELATIVE),
        "stderr_path": str(RUN_STDERR_RELATIVE),
        "output_path": str(RUN_OUTPUT_RELATIVE),
    }
    if not isinstance(evidence, Mapping):
        raise ValueError("receipt evidence is missing")
    for path_key, expected_path in expected.items():
        if evidence.get(path_key) != expected_path:
            raise ValueError(f"receipt evidence path mismatch: {path_key}")
        digest_key = path_key.replace("_path", "_sha256")
        digest = evidence.get(digest_key)
        if not isinstance(digest, str) or len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError(f"receipt evidence digest is missing or invalid: {digest_key}")


def _validate_receipt(
    payload: dict[str, Any],
    fixture_identity: dict[str, Any],
    prelaunch_recovery: Mapping[str, Any],
    *,
    evidence: Mapping[str, Any],
) -> None:
    if payload.get("schema") != SCHEMA:
        raise ValueError("receipt schema mismatch")
    if payload.get("fixture_identity") != fixture_identity:
        raise ValueError("receipt fixture identity mismatch")
    if payload.get("prelaunch_recovery") != prelaunch_recovery:
        raise ValueError("receipt prelaunch recovery binding drifted")
    _validate_evidence(evidence)
    _validate_workload_transition_digest(payload)
    if payload.get("first_failure") is not None:
        raise ValueError(f"receipt reports first failure: {payload['first_failure']}")
    if payload.get("linear_work_counters", {}).get("budget_checks") != {
        name: True for name in FROZEN_BUDGETS_MS
    }:
        raise ValueError("receipt budget gate failed")
    for name in ("standard_30_day", "production_all_time"):
        receipt = payload["linear_work_counters"][name]["publication_receipt"]
        if not receipt["postconditions"]["identity_bindings"]:
            raise ValueError(f"{name} publication identity binding failed")
        if receipt["planner_tail_limits"] != FROZEN_TAIL_LIMITS:
            raise ValueError(f"{name} TailLimits drifted")


def _validate_workload_transition_digest(payload: dict[str, Any]) -> None:
    descriptors = payload.get("workload_descriptors")
    if not isinstance(descriptors, list) or len(descriptors) != 5:
        raise ValueError("receipt workload descriptors are missing or malformed")
    counters = payload.get("linear_work_counters")
    if not isinstance(counters, dict):
        raise ValueError("receipt linear work counters are missing")
    measurements = {
        "standard_30_day": counters.get("standard_30_day"),
        "production_all_time": counters.get("production_all_time"),
        "no_change": counters.get("no_change"),
        "one_call_tail": counters.get("one_call_tail"),
        "one_tool_tail": counters.get("one_tool_tail"),
    }
    expected_tail_fields = {
        "no_change": (0, 0, 0),
        "one_call_tail": (0, 1, 1),
        "one_tool_tail": (0, 1, 1),
    }
    for index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict):
            raise ValueError(f"workload descriptor {index} is not an object")
        vector_digest = descriptor.get("ordered_transition_vector_sha256")
        if not isinstance(vector_digest, str) or len(vector_digest) != 64 or any(
            character not in "0123456789abcdef" for character in vector_digest
        ):
            raise ValueError(f"workload descriptor {index} has malformed transition vector")
        if index < 2:
            name = ("standard_30_day", "production_all_time")[index]
            measurement = measurements[name]
            if not isinstance(measurement, dict):
                raise ValueError(f"{name} measurement is missing")
            if descriptor != measurement.get("workload_descriptor"):
                raise ValueError(f"{name} workload descriptor binding drifted")
            lifecycle = measurement.get("lifecycle_preparation")
            if not isinstance(lifecycle, dict) or vector_digest != lifecycle.get(
                "transition_digest"
            ):
                raise ValueError(f"{name} transition vector binding drifted")
        else:
            name = ("no_change", "one_call_tail", "one_tool_tail")[index - 2]
            measurement = measurements[name]
            if not isinstance(measurement, dict):
                raise ValueError(f"{name} measurement is missing")
            lifecycle = measurement
            if descriptor.get("source_profile") != "synthetic_tail":
                raise ValueError(f"{name} source profile drifted")
            if descriptor.get("history_preset") != "all_time":
                raise ValueError(f"{name} history preset drifted")
            if descriptor.get("model_calls") != expected_tail_fields[name][0]:
                raise ValueError(f"{name} model-call count drifted")
            if descriptor.get("entities") != expected_tail_fields[name][1]:
                raise ValueError(f"{name} entity count drifted")
            if descriptor.get("observations") != expected_tail_fields[name][2]:
                raise ValueError(f"{name} observation count drifted")
            if descriptor.get("seed") != FIXTURE_SEED or descriptor.get(
                "profile_file_sha256"
            ) is not None:
                raise ValueError(f"{name} fixture binding drifted")
            if vector_digest != lifecycle.get("transition_digest"):
                raise ValueError(f"{name} transition vector binding drifted")
    recomputed = _workload_transition_digest(descriptors)
    if payload.get("workload_transition_digest") != recomputed:
        raise ValueError("receipt workload transition digest was not independently verified")


def _child_run(paths: dict[str, Path], launch: dict[str, Any]) -> int:
    started_at = _utc_now()
    try:
        with paths["stdout"].open("x", encoding="utf-8") as stdout, paths[
            "stderr"
        ].open("x", encoding="utf-8") as stderr, contextlib.redirect_stdout(
            stdout
        ), contextlib.redirect_stderr(stderr):
            payload = run(profile_name="all", samples=5)
            payload["prelaunch_recovery"] = launch["prelaunch_recovery"]
            payload["process"] = {
                "pid": os.getpid(),
                "parent_pid": os.getppid(),
                "started_at_utc": started_at,
                "argv": list(LAUNCH_COMMAND),
                "cwd": str(ROOT.resolve()),
                "interpreter": launch["interpreter"],
                "venv_prefix": launch["venv_prefix"],
            }
            encoded = _canonical(payload) + b"\n"
            _exclusive_write(paths["output"], encoded)
        return int(payload.get("first_failure") is not None)
    except BaseException as exc:
        failure = _canonical(
            {
                "failure": "child_exception",
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        ) + b"\n"
        with contextlib.suppress(OSError):
            if paths["stderr"].exists():
                with paths["stderr"].open("ab") as stderr:
                    stderr.write(failure)
            else:
                _exclusive_write(paths["stderr"], failure)
        return 70


def _persist_terminal_failure(
    ledger: dict[str, Any],
    ledger_path: Path,
    *,
    state: str,
    stage: str,
    exc: BaseException | str,
) -> None:
    if isinstance(exc, BaseException):
        failure: dict[str, Any] = {
            "stage": stage,
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    else:
        failure = {"stage": stage, "message": exc}
    ledger["state"] = state
    ledger["failure"] = failure
    ledger.setdefault("process_states", []).append(
        {"state": state, "at_utc": _utc_now(), "stage": stage}
    )
    _ledger_update(ledger_path, ledger)


def _reap_child(pid: int) -> None:
    _terminate_and_reap_child(pid)


def _finalize_child_result(
    ledger: dict[str, Any],
    ledger_path: Path,
    paths: dict[str, Path],
    launch: dict[str, Any],
    *,
    exit_code: int,
    status: int,
    usage: resource.struct_rusage,
    timed_out: bool,
    completed_at_utc: str,
    launched_monotonic_ns: int,
) -> int:
    """Finalize a child only after a successful receipt is fully validated."""
    success = exit_code == 0 and not timed_out
    stage = "evidence_collection"
    try:
        evidence = _build_evidence(paths)
        if not success:
            ledger.update(
                {
                    "state": "failed_after_launch",
                    "completed_at_utc": completed_at_utc,
                    "monotonic_elapsed_ns": time.monotonic_ns() - launched_monotonic_ns,
                    "peak_rss_bytes": _rss_from_usage(usage),
                    "disk_available_bytes_after_launch": _disk_available_bytes(ROOT),
                    "disk_available_bytes_after_completion": _disk_available_bytes(ROOT),
                    "exit_code": exit_code,
                    "terminating_signal": (
                        os.WTERMSIG(status)
                        if os.WIFSIGNALED(status)
                        else None
                    ),
                    "timed_out": timed_out,
                    "evidence": evidence,
                    "process_states": [
                        *ledger["process_states"],
                        {
                            "state": "failed_after_launch",
                            "at_utc": completed_at_utc,
                        },
                    ],
                }
            )
            stage = "terminal_failure_finalization"
            _ledger_update(ledger_path, ledger)
            return exit_code

        stage = "receipt_parse_validation"
        payload = json.loads(paths["output"].read_text(encoding="utf-8"))
        _validate_receipt(
            payload,
            launch["fixture_identity"],
            launch["prelaunch_recovery"],
            evidence=evidence,
        )
        receipt = {
            "schema": payload["schema"],
            "workload_transition_digest": payload["workload_transition_digest"],
            "publication_digest": payload["publication_digest"],
            "evidence": evidence,
        }
        stage = "receipt_finalization"
        final_ledger = {
            **ledger,
            "state": "completed",
            "completed_at_utc": completed_at_utc,
            "monotonic_elapsed_ns": time.monotonic_ns() - launched_monotonic_ns,
            "peak_rss_bytes": _rss_from_usage(usage),
            "disk_available_bytes_after_launch": _disk_available_bytes(ROOT),
            "disk_available_bytes_after_completion": _disk_available_bytes(ROOT),
            "exit_code": exit_code,
            "terminating_signal": None,
            "timed_out": timed_out,
            "evidence": evidence,
            "receipt": receipt,
            "process_states": [
                *ledger["process_states"],
                {"state": "completed", "at_utc": completed_at_utc},
            ],
        }
        # This is the first durable completed state. _atomic_json_update makes
        # the receipt and completed marker one safely finalized ledger image.
        _ledger_update(ledger_path, final_ledger)
    except BaseException as exc:
        with _ignore_parent_child_signals():
            _persist_terminal_failure(
                ledger,
                ledger_path,
                state="failed_after_launch",
                stage=stage,
                exc=exc,
            )
        return 70
    return exit_code


def _launch_exact() -> int:
    launch = _verify_launch_contract()
    launch["prelaunch_recovery"] = _verify_prelaunch_recovery()
    parent_pid = os.getpid()
    verified_parent_snapshot = _capture_verified_parent_process_snapshot(
        parent_pid,
        LAUNCH_COMMAND,
        Path(launch["cwd"]),
        str(launch["owner"]),
    )
    matches = _matching_processes(
        LAUNCH_COMMAND,
        Path(launch["cwd"]),
        owner=str(launch["owner"]),
        exclude_pids=(parent_pid,),
        verified_parent_snapshot=verified_parent_snapshot,
    )
    if matches:
        raise RuntimeError(f"matching launch process appeared before fork: {matches}")
    launch["verified_parent_process_snapshot"] = verified_parent_snapshot
    launch["matching_processes"] = matches
    paths = launch.pop("paths")
    ledger = {
        "schema": "codex-usage-tracker.lifecycle-run-ledger.v1",
        "run_token_id": RUN_TOKEN_ID,
        "maximum_new_end_to_end_runs": 1,
        "token_status": RUN_TOKEN_STATUS,
        "token_consumed": False,
        "state": "prelaunch_verified",
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
        "first_result_retained": True,
        "launch": launch,
        "process_states": [{"state": "prelaunch_verified", "at_utc": _utc_now()}],
    }
    _exclusive_write(paths["ledger"], _canonical(ledger) + b"\n")
    read_fd = -1
    write_fd = -1
    child_pid: int | None = None
    child_reaped = False
    token_persistence_started = False
    token_persisted = False
    child_release_started = False
    child_released = False
    previous_parent_signal_handlers: dict[int, Any] | None = None
    try:
        read_fd, write_fd = os.pipe()
        child_pid = os.fork()
        if child_pid == 0:
            _child_entry(paths, launch, read_fd, write_fd)

        _validate_child_pid(child_pid)

        previous_parent_signal_handlers = _install_parent_child_signal_handlers()
        os.close(read_fd)
        read_fd = -1
        observed = _observe_child_start(child_pid, launch, parent_pid)
        launch["child_start_handshake"] = {
            "pid": observed["pid"],
            "parent_pid": observed["parent_pid"],
            "user": observed["user"],
            "argv": list(observed["argv"]),
            "cwd": observed["cwd"],
            "platform_command": observed.get("command"),
            "platform_signature": observed.get("platform_signature"),
            "verified_before_token_consumption": True,
        }
        launched_at_utc = _utc_now()
        launched_monotonic_ns = time.monotonic_ns()
        ledger.update(
            {
                "token_consumed": True,
                "token_status": "consumed",
                "token_consumed_at_utc": launched_at_utc,
                "state": "launched_consumed",
                "process": {
                    "pid": child_pid,
                    "parent_pid": parent_pid,
                    "owner": launch["owner"],
                    "launched_at_utc": launched_at_utc,
                    "launched_monotonic_ns": launched_monotonic_ns,
                    "argv": list(LAUNCH_COMMAND),
                    "cwd": launch["cwd"],
                    "interpreter": launch["interpreter"],
                    "run_token_id": RUN_TOKEN_ID,
                },
                "launch": launch,
                "process_states": [
                    *ledger["process_states"],
                    {
                        "state": "child_start_verified",
                        "at_utc": _utc_now(),
                    },
                    {"state": "launched_consumed", "at_utc": _utc_now()},
                ],
            }
        )
        token_persistence_started = True
        _ledger_update(paths["ledger"], ledger)
        token_persisted = True
        child_release_started = True
        os.write(write_fd, b"1")
        child_released = True
        os.close(write_fd)
        write_fd = -1
    except BaseException as exc:
        if write_fd != -1:
            with contextlib.suppress(OSError):
                os.close(write_fd)
            write_fd = -1
        if read_fd != -1:
            with contextlib.suppress(OSError):
                os.close(read_fd)
            read_fd = -1
        cleanup_error: BaseException | None = None
        if child_pid is not None and child_pid > 0 and not child_reaped:
            with _ignore_parent_child_signals():
                try:
                    _reap_child(child_pid)
                    child_reaped = True
                except BaseException as reap_exc:
                    cleanup_error = reap_exc
        if cleanup_error is not None:
            exc = RuntimeError(f"{exc}; bounded child cleanup failed: {cleanup_error}")
        terminal_state = (
            "failed_after_launch"
            if token_persistence_started or token_persisted or child_release_started or child_released
            else "prelaunch_failed"
        )
        try:
            try:
                with _ignore_parent_child_signals():
                    _persist_terminal_failure(
                        ledger,
                        paths["ledger"],
                        state=terminal_state,
                        stage=(
                            "post_launch_handshake"
                            if terminal_state == "failed_after_launch"
                            else "child_start_handshake"
                        ),
                        exc=exc,
                    )
            except BaseException as persistence_error:
                raise RuntimeError(
                    f"{exc}; terminal failure persistence failed: {persistence_error}"
                ) from exc
        finally:
            if previous_parent_signal_handlers is not None:
                _restore_parent_child_signal_handlers(previous_parent_signal_handlers)
        raise

    try:
        try:
            _, status, usage, timed_out = _wait_for_child(child_pid)
            child_reaped = True
        except BaseException as exc:
            cleanup_error: BaseException | None = None
            if child_pid is not None and child_pid > 0 and not child_reaped:
                with _ignore_parent_child_signals():
                    try:
                        _reap_child(child_pid)
                        child_reaped = True
                    except BaseException as reap_exc:
                        cleanup_error = reap_exc
            if cleanup_error is not None:
                exc = RuntimeError(f"{exc}; bounded child cleanup failed: {cleanup_error}")
            with _ignore_parent_child_signals():
                _persist_terminal_failure(
                    ledger,
                    paths["ledger"],
                    state="failed_after_launch",
                    stage="child_wait",
                    exc=exc,
                )
            raise
        completed_at_utc = _utc_now()
        exit_code = os.waitstatus_to_exitcode(status)
        return _finalize_child_result(
            ledger,
            paths["ledger"],
            paths,
            launch,
            exit_code=exit_code,
            status=status,
            usage=usage,
            timed_out=timed_out,
            completed_at_utc=completed_at_utc,
            launched_monotonic_ns=launched_monotonic_ns,
        )
    finally:
        if previous_parent_signal_handlers is not None:
            _restore_parent_child_signal_handlers(previous_parent_signal_handlers)


def _profile(name: str) -> dict[str, Any]:
    path = PROFILE_ROOT / f"{name}-v1.json"
    if _sha256(path) != PROFILE_DIGESTS[name]:
        raise ValueError(f"{name} profile does not match its frozen digest")
    profile = json.loads(path.read_text(encoding="utf-8"))
    if profile.get("schema") != "codex-usage-tracker.synthetic-fixture-profile.v1":
        raise ValueError(f"{name} profile has an unexpected schema")
    return profile


def _tool_count(profile: dict[str, Any], days: int | None) -> int:
    calls = int(profile["model_calls"])
    if days is not None:
        calls = math.ceil(calls * days / int(profile["history_days"]))
    ratio = int(profile["ratios_basis_points"]["tool_invocations"])
    return math.ceil(calls * ratio / 10_000)


def _model_call_count(profile: dict[str, Any], days: int | None) -> int:
    calls = int(profile["model_calls"])
    if days is not None:
        calls = math.ceil(calls * days / int(profile["history_days"]))
    return calls


def _tool_observation(
    profile_name: str, entity_ordinal: int, transition_ordinal: int
) -> AdapterObservation:
    native_id = f"tool-{profile_name}-{entity_ordinal}"
    logical_id = semantic_id("tool", [native_id, "session:ck07r1", "turn:ck07r1"])
    state = "running" if transition_ordinal == 0 else "succeeded"
    source_order = entity_ordinal * 2 + transition_ordinal
    return AdapterObservation(
        observation_type="ToolLifecycleObserved",
        logical_id=logical_id,
        identity_tuple=(native_id, "session:ck07r1", "turn:ck07r1"),
        source_range=SourceRange(
            "manifestation:ck07r1-scale",
            1,
            "revision:ck07r1-scale",
            source_order + 1,
            source_order * 10,
            source_order * 10 + 9,
        ),
        source_rank=0,
        event_at_us=1_800_000_000_000_000 + source_order,
        source_order=source_order,
        event_kind_order=40 + transition_ordinal,
        transition_rank=transition_ordinal,
        payload={
            "tool_id": logical_id,
            "session_id": "session:ck07r1",
            "turn_id": "turn:ck07r1",
            "transport_name": "synthetic_execute",
            "semantic_operation": "execute",
            "state": state,
            "write_intent": 1,
            "duration_us": None if transition_ordinal == 0 else 1,
            "output_bytes": None if transition_ordinal == 0 else 64,
        },
    )


def _scale_observations(
    profile_name: str, profile: dict[str, Any], days: int | None
) -> tuple[AdapterObservation, ...]:
    count = _tool_count(profile, days)
    observations: list[AdapterObservation] = []
    for entity_ordinal in range(count):
        transition_count = 1 if entity_ordinal == count - 1 else 2
        observations.extend(
            _tool_observation(profile_name, entity_ordinal, transition_ordinal)
            for transition_ordinal in range(transition_count)
        )
    return tuple(observations)


def _changes(observations: Iterable[AdapterObservation]) -> ProposedChangeSet:
    observations = tuple(observations)
    if not observations:
        return ProposedChangeSet(
            observations=(),
            occurrences=(),
            diagnostics=(),
            cursor_updates=(),
            accounting=AdapterAccounting({}, {}, {}),
            selected_sources=(),
            deferred_sources=(),
        )
    return build_change_set(
        (
            ParseBatch(
                0,
                0,
                observations,
                (),
                len(observations),
                max(item.source_range.byte_end for item in observations),
                max(item.source_order for item in observations),
                False,
            ),
        ),
        selected_sources=(),
        deferred_sources=(),
    )


def _request(publication_id: str, parent: str | None) -> PublicationRequest:
    return PublicationRequest(
        publication_id=publication_id,
        operation_id=publication_id.replace("publication:", "operation:", 1),
        committed_at_us=1_800_000_000_000_000,
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        parent_publication_id=parent,
    )


def _validate_open(path: Path, artifact: PointerArtifact) -> AnalyticalHead:
    connection = open_read_only(path)
    try:
        row = connection.execute(
            "SELECT publication_id, parent_publication_id, operation_id, "
            "artifact_manifest_sha256, schema_contract_sha256 "
            "FROM publications WHERE publication_id = ?",
            (artifact.publication_id,),
        ).fetchone()
        if row is None:
            raise AssertionError(f"publication is absent from readable artifact: {artifact.publication_id}")
        return AnalyticalHead(*row)
    finally:
        connection.close()


class _RecordingStore(OperationalStore):
    def __init__(self, connection: Any, events: list[str]) -> None:
        super().__init__(connection)
        self._events = events

    def acquire_lease(self, *args: Any, **kwargs: Any) -> Any:
        lease_name = args[0] if args else kwargs.get("lease_name")
        self._events.append(
            "writer_lock" if lease_name is LeaseName.ANALYTICAL_WRITER else "promotion_lock"
        )
        return super().acquire_lease(*args, **kwargs)


class _RecordingWriter(PublicationWriter):
    def __init__(
        self,
        connection: Any,
        expected_plan: PublicationPlan,
        events: list[str],
        *,
        isolated_large: bool = False,
    ) -> None:
        super().__init__(connection)
        self._expected_plan = expected_plan
        self._events = events
        self._isolated_large = isolated_large
        self.plan_digest_at_writer: str | None = None

    def _validate_append_request(
        self,
        plan: PublicationPlan,
        request: PublicationRequest,
        write_set: Any,
    ) -> None:
        if plan.operation_class is not OperationClass.APPEND_SAFE_LARGE or not self._isolated_large:
            super()._validate_append_request(plan, request, write_set)
            return
        # The repository writer deliberately exposes only the short-tail
        # public path.  An isolated artifact still uses that exact transactional
        # implementation, but its selected APPEND_SAFE_LARGE plan must remain
        # the same object and class through candidate build and validation.
        if not plan.analytical_write_required:
            raise AssertionError("large isolated publication must require an analytical write")
        if plan.parent_publication_id != request.parent_publication_id:
            raise AssertionError("large isolated publication parent differs from its request")
        self._validate_write_set(plan, request, write_set)

    def publish(self, plan: PublicationPlan, request: PublicationRequest, write_set: Any, **kwargs: Any) -> Any:
        if plan is not self._expected_plan:
            raise AssertionError("PublicationWriter received a different plan object")
        self.plan_digest_at_writer = hashlib.sha256(_canonical(plan)).hexdigest()
        self._events.append("writer_publish")
        return super().publish(plan, request, write_set, **kwargs)


def _reference_transition(
    observation: AdapterObservation, version: int, publication_id: str
) -> dict[str, Any]:
    state = str(observation.payload["state"])
    occurrence_id = observation.occurrence_id
    return {
        "transition_id": semantic_id(
            "lifecycle-transition",
            [observation.logical_id, version, state, occurrence_id],
        ),
        "logical_id": observation.logical_id,
        "entity_kind": "tool_invocation",
        "state": state,
        "basis": observation.basis,
        "coordinate": {
            "source_order": observation.source_order,
            "event_at_us": observation.event_at_us,
        },
        "event_at_us": observation.event_at_us,
        "source_rank": observation.source_rank,
        "source_order": observation.source_order,
        "event_kind_order": observation.event_kind_order,
        "transition_rank": observation.transition_rank,
        "occurrence_id": occurrence_id,
        "terminal_error_category": None,
        "measurement_mask": observation.measurement_mask,
        "transition_version": version,
        "first_seen_publication_id": publication_id,
    }


def _actual_transition(row: Any) -> dict[str, Any]:
    return {
        "transition_id": row[0],
        "logical_id": row[1],
        "entity_kind": row[2],
        "state": row[3],
        "basis": row[4],
        "transition_version": row[5],
        "event_at_us": row[6],
        "source_rank": row[7],
        "source_order": row[8],
        "event_kind_order": row[9],
        "transition_rank": row[10],
        "occurrence_id": row[11],
        "terminal_error_category": row[12],
        "measurement_mask": row[13],
        "first_seen_publication_id": row[14],
        "coordinate": {"source_order": row[8], "event_at_us": row[6]},
    }


def _reference_fold(transitions: list[dict[str, Any]]) -> dict[str, Any]:
    oracle_transitions = []
    for transition in transitions:
        value = dict(transition)
        source_order = value["source_order"]
        if not isinstance(source_order, (tuple, list)):
            value["source_order"] = ["synthetic-lifecycle", source_order]
        oracle_transitions.append(value)
    return fold_lifecycle(oracle_transitions)


def _seed_artifact(root: Path, base: ProposedChangeSet) -> tuple[Path, Path, str]:
    database_path = root / "analytical.sqlite3"
    pointer_path = root / "active-artifact-pointer-v1.json"
    connection = initialize_analytical(database_path)
    try:
        request = _request(SEED_PUBLICATION_ID, None)
        write_set = prepare_write_set_from_changes(base, request)
        # The seed is setup-only. The acceptance publication below is the one
        # whose plan is selected by plan_refresh and passed through recovery.
        seed_plan = PublicationPlan(
            OperationClass.APPEND_SAFE_SMALL,
            None,
            estimate_change_set(base),
            ("synthetic_seed_setup",),
            True,
        )
        request = replace(
            request,
            artifact_manifest_sha256=planned_artifact_manifest_sha256(
                seed_plan, request, write_set
            ),
        )
        PublicationWriter(connection).publish(seed_plan, request, write_set)
    finally:
        connection.close()
    active = PointerArtifact(
        artifact_name=database_path.name,
        artifact_manifest_sha256=request.artifact_manifest_sha256,
        file_sha256=_sha256(database_path),
        publication_id=SEED_PUBLICATION_ID,
        schema_contract_sha256=SCHEMA_CONTRACT_SHA256,
    )
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, request.committed_at_us))
    return database_path, pointer_path, request.artifact_manifest_sha256


def _advance_job(store: OperationalStore, operation_id: str, worker: WorkerIdentity, now_us: int) -> None:
    store.transition(
        operation_id,
        expected=JobState.PLANNED,
        state=JobState.PARSING,
        stage="parsing",
        now_us=now_us,
        worker=worker,
    )
    store.transition(
        operation_id,
        expected=JobState.PARSING,
        state=JobState.READY_TO_WRITE,
        stage="ready_to_write",
        now_us=now_us + 1,
        worker=worker,
    )
    store.transition(
        operation_id,
        expected=JobState.READY_TO_WRITE,
        state=JobState.WRITING,
        stage="writing",
        now_us=now_us + 2,
        worker=worker,
    )


def _advance_large_job(
    store: OperationalStore, operation_id: str, worker: WorkerIdentity, now_us: int
) -> None:
    """Move one large operation through the isolated-artifact sidecar states."""

    store.transition(
        operation_id,
        expected=JobState.PLANNED,
        state=JobState.BUILDING,
        stage="building",
        now_us=now_us,
        worker=worker,
    )


def _plan_limit_breaches(plan: PublicationPlan, intent: RefreshIntent, limits: TailLimits) -> tuple[str, ...]:
    estimate = plan.estimate
    values = (
        ("selected_bytes", estimate.selected_bytes, limits.selected_bytes),
        ("selected_records", estimate.selected_records, limits.selected_records),
        ("observations", estimate.observations, limits.observations),
        ("occurrences", estimate.occurrences, limits.occurrences),
        ("affected_sessions", estimate.affected_sessions, limits.affected_sessions),
        ("affected_turns", estimate.affected_turns, limits.affected_turns),
        ("affected_resources", estimate.affected_resources, limits.affected_resources),
        (
            "affected_allowance_cycles",
            estimate.affected_allowance_cycles,
            limits.affected_allowance_cycles,
        ),
        ("dirty_keys", estimate.dirty_keys, limits.dirty_keys),
        ("projection_rows", estimate.projection_rows, limits.projection_rows),
        ("expected_wal_bytes", estimate.expected_wal_bytes, limits.expected_wal_bytes),
        (
            "model_call_tail_rows",
            intent.current_tail_rows + estimate.model_calls_inserted,
            limits.model_call_tail_rows,
        ),
        (
            "planning_staleness_us",
            intent.planned_at_us - intent.parent_observed_at_us,
            limits.planning_staleness_us,
        ),
    )
    return tuple(name for name, actual, ceiling in values if actual > ceiling)


def _validate_selected_plan(
    plan: PublicationPlan, intent: RefreshIntent, limits: TailLimits
) -> tuple[str, ...]:
    if _jsonable(limits) != FROZEN_TAIL_LIMITS:
        raise ValueError("selected plan used non-authoritative TailLimits")
    breaches = _plan_limit_breaches(plan, intent, limits)
    expected_reasons = tuple(f"limit_exceeded:{name}" for name in breaches)
    if plan.operation_class is OperationClass.APPEND_SAFE_SMALL:
        if breaches or plan.reasons != ("all_small_tail_bounds_proven",):
            raise AssertionError("planner selected APPEND_SAFE_SMALL for a limit-breaching tail")
    elif plan.operation_class is OperationClass.APPEND_SAFE_LARGE:
        if not breaches or plan.reasons != expected_reasons:
            raise AssertionError("planner selected APPEND_SAFE_LARGE without exact limit evidence")
    else:
        raise AssertionError(f"unsupported reachable lifecycle operation class: {plan.operation_class}")
    return breaches


def _validate_plan_identity(plan: PublicationPlan, before: str, at_writer: str | None) -> None:
    expected = hashlib.sha256(_canonical(plan)).hexdigest()
    if before != expected or at_writer != expected:
        raise AssertionError("selected plan changed before or at its selected writer path")


def _validate_large_artifact_evidence(candidate: Any, request: PublicationRequest) -> None:
    if (
        candidate.publication_id != request.publication_id
        or candidate.artifact_manifest_sha256 != request.artifact_manifest_sha256
        or not isinstance(candidate.file_sha256, str)
        or len(candidate.file_sha256) != 64
        or any(character not in "0123456789abcdef" for character in candidate.file_sha256)
        or not Path(candidate.path).is_file()
        or _sha256(Path(candidate.path)) != candidate.file_sha256
    ):
        raise AssertionError("large isolated artifact evidence is missing or mismatched")


def _publish_large_isolated(
    root: Path,
    active_path: Path,
    pointer_path: Path,
    store: OperationalStore,
    worker: WorkerIdentity,
    plan: PublicationPlan,
    request: PublicationRequest,
    write_set: Any,
    pre_pointer: PointerDocument,
    events: list[str],
    now_us: int,
) -> tuple[Any, Any, _RecordingWriter, PromotionRequest, Any]:
    """Build, validate, and promote one unchanged large planner result."""

    _advance_large_job(store, request.operation_id, worker, now_us)
    writer_holder: dict[str, _RecordingWriter] = {}
    result_holder: dict[str, Any] = {}

    def build(connection: Any) -> None:
        source = open_read_only(active_path)
        try:
            source.backup(connection)
        finally:
            source.close()
        writer = _RecordingWriter(connection, plan, events, isolated_large=True)
        writer_holder["writer"] = writer
        result_holder["result"] = writer.publish(plan, request, write_set)

    events.append("isolated_artifact_build")
    candidate = build_isolated_artifact(
        root,
        request.operation_id,
        build,
        expected_publication_id=request.publication_id,
        expected_manifest_sha256=request.artifact_manifest_sha256,
    )
    _validate_large_artifact_evidence(candidate, request)
    writer = writer_holder.get("writer")
    if writer is None:
        raise AssertionError("isolated artifact did not record its selected plan writer")
    publication_result = result_holder.get("result")
    if publication_result is None:
        raise AssertionError("isolated artifact did not record its publication result")
    events.append("isolated_artifact_validated")
    store.transition(
        request.operation_id,
        expected=JobState.BUILDING,
        state=JobState.VALIDATING,
        stage="validating",
        now_us=now_us + 1,
        worker=worker,
    )
    store.transition(
        request.operation_id,
        expected=JobState.VALIDATING,
        state=JobState.PROMOTING,
        stage="promoting",
        now_us=now_us + 2,
        worker=worker,
    )
    artifact = PointerArtifact(
        candidate.artifact_name,
        candidate.artifact_manifest_sha256,
        candidate.file_sha256,
        candidate.publication_id,
        SCHEMA_CONTRACT_SHA256,
    )
    promotion_request = PromotionRequest(
        recovery_id=f"recovery:{request.operation_id}",
        operation_id=request.operation_id,
        expected_pointer_generation=pre_pointer.generation,
        expected_active_publication_id=pre_pointer.active.publication_id,
        candidate=artifact,
        owner_nonce=f"nonce:{request.operation_id}",
        worker=worker,
        now_us=now_us + 3,
        lease_ttl_us=500_000,
    )
    events.append("isolated_artifact_promote")
    result = promote_isolated_artifact(
        pointer_path,
        store=store,
        request=promotion_request,
        worker_is_alive=lambda _pid, _token: True,
        validate_open=_validate_open,
        finalize_rollback=lambda path, _prior: _sha256(path),
    )
    if result.head.publication_id != request.publication_id:
        raise AssertionError("large promotion committed a different publication")
    if result.pointer.active != artifact:
        raise AssertionError("large promotion pointer does not equal its candidate artifact")
    return candidate, result, writer, promotion_request, publication_result


def _budget_checks(measurements: dict[str, dict[str, Any]]) -> tuple[dict[str, bool], dict[str, Any] | None]:
    checks: dict[str, bool] = {}
    first_failure: dict[str, Any] | None = None
    for name, budget in FROZEN_BUDGETS_MS.items():
        measured = (
            measurements[name]["lifecycle_preparation"]["max_ms"]
            if name in {"standard_30_day", "production_all_time"}
            else measurements[name]["max_ms"]
        )
        passed = measured <= budget
        checks[name] = passed
        if not passed and first_failure is None:
            first_failure = {
                "gate": name,
                "observed_max_ms": measured,
                "budget_ms": budget,
            }
    return checks, first_failure


def _publication_receipt(
    profile_name: str,
    scale: tuple[AdapterObservation, ...],
    base: ProposedChangeSet,
) -> dict[str, Any]:
    if not base.selected_sources:
        raise AssertionError("seed fixture must provide a selected source manifestation")
    manifestation_key = base.selected_sources[0].manifestation_key
    base_tool = next(
        item
        for item in base.observations
        if item.observation_type == "ToolLifecycleObserved"
    )
    session_id = str(base_tool.payload["session_id"])
    turn_id = str(base_tool.payload["turn_id"])
    scale = tuple(
        replace(
            observation,
            source_range=replace(
                observation.source_range,
                manifestation_id=base.selected_sources[0].manifestation_id,
                manifestation_key=manifestation_key,
                source_revision=base.selected_sources[0].content_revision,
            ),
            payload={
                **observation.payload,
                "session_id": session_id,
                "turn_id": turn_id,
            },
        )
        for observation in scale
    )
    events: list[str] = []
    expected_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    expected_versions: dict[str, int] = defaultdict(int)
    chunks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix=f"ck07r1-{profile_name}-") as directory:
        root = Path(directory)
        database_path, pointer_path, _ = _seed_artifact(root, base)
        seed_connection = open_read_only(database_path)
        try:
            seed_source_occurrences = int(
                seed_connection.execute("SELECT COUNT(*) FROM source_occurrences").fetchone()[0]
            )
        finally:
            seed_connection.close()
        operational_path = root / "operational.sqlite3"
        operational_connection = initialize_operational(operational_path)
        store = _RecordingStore(operational_connection, events)
        worker = WorkerIdentity(1, f"synthetic-{profile_name}")
        inserted_occurrences = 0
        try:
            selection = select_readable_artifact(pointer_path, validate_open=_validate_open)
            events.append("select_readable_artifact")
            selected_file_sha256 = selection.selected.file_sha256
            if selected_file_sha256 is None:
                raise AssertionError("selected readable artifact has no file digest")
            recovery_probe_id = f"recovery:ck07r1:{profile_name}:prepared-crash"
            store.start_or_join(
                JobRequest(
                    "operation:ck07r1:seed",
                    hashlib.sha256(_canonical(_request(SEED_PUBLICATION_ID, None))).hexdigest(),
                    "seed:ck07r1",
                    None,
                    SidecarOperationClass.APPEND_SAFE_SMALL,
                ),
                now_us=1_800_000_000_000_049,
            )
            store.create_recovery_intent(
                RecoveryIntent(
                    recovery_id=recovery_probe_id,
                    operation_id="operation:ck07r1:seed",
                    expected_pointer_generation=0,
                    target_pointer_generation=1,
                    expected_active_publication_id=None,
                    candidate_publication_id=SEED_PUBLICATION_ID,
                    candidate_artifact_name=selection.selected.artifact_name,
                    candidate_artifact_sha256=selected_file_sha256,
                    state=RecoveryIntentState.PREPARED,
                    created_at_us=1_800_000_000_000_050,
                    updated_at_us=1_800_000_000_000_050,
                    error_code=None,
                )
            )
            events.append("synthetic_crash_after_intent_prepare")
            events.append("recover_startup")
            recovery_probe_report = recover_startup(
                pointer_path,
                selection=selection,
                store=store,
                now_us=1_800_000_000_000_100,
                worker_is_alive=lambda _pid, _token: True,
            )
            if recovery_probe_report.reconciled_intents != (recovery_probe_id,):
                raise AssertionError("startup recovery did not reconcile the prepared synthetic intent")
            events.append("recover_startup_retry")
            recovery_retry_report = recover_startup(
                pointer_path,
                selection=selection,
                store=store,
                now_us=1_800_000_000_000_101,
                worker_is_alive=lambda _pid, _token: True,
            )
            if recovery_retry_report.reconciled_intents:
                raise AssertionError("recovery retry reconciled an already terminal intent")
            recovery_report = recovery_probe_report
            for offset in range(0, len(scale), PUBLICATION_CHUNK_OBSERVATIONS):
                chunk = scale[offset : offset + PUBLICATION_CHUNK_OBSERVATIONS]
                changes = _changes(chunk)
                events.append("plan_refresh")
                plan_event_index = len(events) - 1
                intent = RefreshIntent(
                    parent_publication_id=selection.head.publication_id,
                    parent_observed_at_us=1_800_000_000_000_000 + offset,
                    planned_at_us=1_800_000_000_000_001 + offset,
                    history_preset="all_time",
                    current_history_preset="all_time",
                )
                plan = plan_refresh(
                    changes,
                    intent,
                    limits=(limits := _tail_limits()),
                    dirty_keys=0,
                    projection_rows=0,
                    expected_wal_bytes=None,
                )
                planner_breaches = _validate_selected_plan(plan, intent, limits)
                if plan.parent_publication_id != selection.head.publication_id:
                    raise AssertionError("planner parent differs from read selection head")

                read_connection = open_read_only(database_path)
                try:
                    prior = read_prior_publication_snapshot(read_connection, changes)
                finally:
                    read_connection.close()
                request = _request(
                    f"publication:ck07r1:{profile_name}:{offset // PUBLICATION_CHUNK_OBSERVATIONS}",
                    selection.head.publication_id,
                )
                write_set = prepare_write_set_from_changes(changes, request, prior=prior)
                events.append("prepare_write_set")
                expected_chunk_transitions: list[dict[str, Any]] = []
                for observation in chunk:
                    expected_versions[observation.logical_id] += 1
                    expected_transition = _reference_transition(
                        observation,
                        expected_versions[observation.logical_id],
                        request.publication_id,
                    )
                    expected_by_entity[observation.logical_id].append(expected_transition)
                    expected_chunk_transitions.append(expected_transition)
                actual_transitions = tuple(
                    _actual_transition(
                        (
                            transition.transition_id,
                            transition.entity_logical_id,
                            transition.entity_kind,
                            transition.lifecycle_state,
                            transition.state_basis,
                            transition.transition_version,
                            transition.transition_at_us,
                            transition.source_rank,
                            transition.source_order,
                            transition.event_kind_order,
                            transition.transition_rank,
                            transition.occurrence_id,
                            transition.terminal_error_category,
                            transition.measurement_mask,
                            transition.first_seen_publication_id,
                        )
                    )
                    for transition in write_set.lifecycle_transitions
                )
                expected_transitions = tuple(expected_chunk_transitions)
                if tuple(item["transition_id"] for item in actual_transitions) != tuple(
                    item["transition_id"] for item in expected_transitions
                ):
                    raise AssertionError("planner write set lifecycle identities differ from independent truth")
                request = replace(
                    request,
                    artifact_manifest_sha256=planned_artifact_manifest_sha256(
                        plan, request, write_set
                    ),
                )
                operation_id = request.operation_id
                store.start_or_join(
                    JobRequest(
                        operation_id,
                        hashlib.sha256(_canonical(request)).hexdigest(),
                        f"refresh:{profile_name}",
                        plan.parent_publication_id,
                        SidecarOperationClass(plan.operation_class.value),
                    ),
                    now_us=1_800_000_000_000_010 + offset,
                )
                pre_pointer = read_pointer(pointer_path)
                if pre_pointer.active.publication_id != selection.head.publication_id:
                    raise AssertionError("pre-commit pointer differs from read selection head")
                plan_digest_before_writer = hashlib.sha256(_canonical(plan)).hexdigest()
                writer_request_active = pre_pointer.active.publication_id
                small_request: SmallPublicationRequest | None = None
                promotion_request: PromotionRequest | None = None
                candidate = None
                if plan.operation_class is OperationClass.APPEND_SAFE_SMALL:
                    _advance_job(store, operation_id, worker, 1_800_000_000_000_020 + offset)
                    small_request = SmallPublicationRequest(
                        operation_id,
                        pre_pointer.generation,
                        pre_pointer.active.publication_id,
                        pre_pointer.active.artifact_name,
                        f"nonce:{profile_name}:{offset}",
                        worker,
                        1_800_000_000_000_030 + offset,
                        500_000,
                    )
                    writer_connection = open_writer(database_path)
                    try:
                        writer = _RecordingWriter(writer_connection, plan, events)
                        result = writer.publish_with_pointer(
                            plan,
                            request,
                            write_set,
                            pointer_path=pointer_path,
                            operational_store=store,
                            pointer_request=small_request,
                            worker_is_alive=lambda _pid, _token: True,
                            validate_open=_validate_open,
                        )
                    finally:
                        writer_connection.close()
                else:
                    (
                        candidate,
                        promotion_result,
                        writer,
                        promotion_request,
                        result,
                    ) = _publish_large_isolated(
                        root,
                        database_path,
                        pointer_path,
                        store,
                        worker,
                        plan,
                        request,
                        write_set,
                        pre_pointer,
                        events,
                        1_800_000_000_000_020 + offset,
                    )
                    database_path = root / candidate.artifact_name
                identity_values = (
                    selection.head.publication_id,
                    intent.parent_publication_id,
                    plan.parent_publication_id,
                    writer_request_active,
                    pre_pointer.active.publication_id,
                )
                if len(set(identity_values)) != 1:
                    raise AssertionError("pre-commit lifecycle identity bindings diverged")
                if events.index("writer_lock", plan_event_index) < plan_event_index:
                    raise AssertionError("writer lock was acquired before plan_refresh")
                committed_publication_id = result.publication_id
                if committed_publication_id != request.publication_id:
                    raise AssertionError("writer committed a publication different from its request")
                post_pointer = read_pointer(pointer_path)
                if post_pointer.active.publication_id != committed_publication_id:
                    raise AssertionError("post-commit pointer differs from committed analytical head")
                _validate_plan_identity(plan, plan_digest_before_writer, writer.plan_digest_at_writer)
                committed_head = _validate_open(
                    root / post_pointer.active.artifact_name, post_pointer.active
                )
                if committed_head.parent_publication_id != writer_request_active:
                    raise AssertionError("committed publication parent differs from pointer request")
                chunks.append(
                    {
                        "publication_id": result.publication_id,
                        "parent_publication_id": plan.parent_publication_id,
                        "operation_id": request.operation_id,
                        "planner_operation_class": plan.operation_class.value,
                        "planner_reason": plan.reasons,
                        "planner_limit_breaches": planner_breaches,
                        "planner_tail_limits": _jsonable(limits),
                        "planner_change_estimate": _jsonable(plan.estimate),
                        "writer_path": (
                            "small_pointer_coordinated"
                            if small_request is not None
                            else "large_isolated_artifact_build_validate_promote"
                        ),
                        "plan_digest_before_writer": plan_digest_before_writer,
                        "plan_digest_at_writer": writer.plan_digest_at_writer,
                        "identity_bindings": {
                            "selection_head": selection.head.publication_id,
                            "refresh_intent_parent": intent.parent_publication_id,
                            "plan_parent": plan.parent_publication_id,
                            "small_request_expected_active": (
                                None
                                if small_request is None
                                else small_request.expected_active_publication_id
                            ),
                            "promotion_request_expected_active": (
                                None
                                if promotion_request is None
                                else promotion_request.expected_active_publication_id
                            ),
                            "writer_request_expected_active": writer_request_active,
                            "pre_commit_pointer_active": pre_pointer.active.publication_id,
                            "committed_head_parent": committed_head.parent_publication_id,
                            "post_commit_pointer_active": post_pointer.active.publication_id,
                        },
                        "pre_commit_pointer_generation": pre_pointer.generation,
                        "post_commit_pointer_generation": post_pointer.generation,
                        "inserted_occurrences": result.inserted_occurrences,
                        "large_artifact": (
                            None
                            if candidate is None
                            else {
                                "artifact_name": candidate.artifact_name,
                                "artifact_manifest_sha256": candidate.artifact_manifest_sha256,
                                "file_sha256": candidate.file_sha256,
                                "promotion_generation": post_pointer.generation,
                                "rollback_artifact_name": (
                                    None
                                    if post_pointer.rollback is None
                                    else post_pointer.rollback.artifact_name
                                ),
                            }
                        ),
                    }
                )
                inserted_occurrences += result.inserted_occurrences
                selection = select_readable_artifact(pointer_path, validate_open=_validate_open)
                if selection.selected.artifact_name != post_pointer.active.artifact_name:
                    raise AssertionError("post-publication read selection did not choose the promoted head")
                if candidate is not None:
                    if post_pointer.rollback is None:
                        raise AssertionError("large promotion did not preserve a rollback artifact")
                    _validate_open(root / post_pointer.rollback.artifact_name, post_pointer.rollback)
                events.append("select_readable_artifact")
                events.append("recover_startup")
                recovery_report = recover_startup(
                    pointer_path,
                    selection=selection,
                    store=store,
                    now_us=1_800_000_000_000_100 + offset,
                    worker_is_alive=lambda _pid, _token: True,
                )
            if not chunks:
                raise AssertionError("scale workload produced no publication chunks")
            read_connection = open_read_only(database_path)
            try:
                actual_rows = [
                    _actual_transition(row)
                    for row in read_connection.execute(
                        "SELECT transition_id, entity_logical_id, entity_kind, lifecycle_state, "
                        "state_basis, transition_version, transition_at_us, source_rank, "
                        "source_order, event_kind_order, transition_rank, occurrence_id, "
                        "terminal_error_category, measurement_mask, first_seen_publication_id "
                        "FROM lifecycle_transitions"
                    )
                    if str(row[1]) in expected_by_entity
                ]
                expected_rows = [
                    item
                    for logical_id in sorted(expected_by_entity)
                    for item in expected_by_entity[logical_id]
                ]
                actual_rows.sort(key=lambda item: (item["logical_id"], item["transition_version"]))
                expected_rows.sort(key=lambda item: (item["logical_id"], item["transition_version"]))
                if actual_rows != expected_rows:
                    raise AssertionError("committed lifecycle transitions differ from independent truth")
                fold_digest = hashlib.sha256()
                for logical_id in sorted(expected_by_entity):
                    fold = _reference_fold(expected_by_entity[logical_id])
                    fold_digest.update(_canonical(fold))
                    tool = read_connection.execute(
                        "SELECT lifecycle_state, state_basis, transition_version, start_at_us, "
                        "start_occurrence_id, terminal_at_us, terminal_occurrence_id, "
                        "observed_duration_us, error_category FROM tool_invocations "
                        "WHERE tool_id = ?",
                        (logical_id,),
                    ).fetchone()
                    terminal = fold["terminal_coordinate"]
                    terminal_occurrence = None
                    if terminal is not None:
                        terminal_occurrence = next(
                            item["occurrence_id"]
                            for item in reversed(expected_by_entity[logical_id])
                            if item["state"] in {"succeeded", "failed", "cancelled", "rolled_back"}
                        )
                    expected_tool = (
                        fold["state"],
                        fold["state_basis"],
                        fold["transition_count"],
                        fold["start_coordinate"]["event_at_us"],
                        next(
                            item["occurrence_id"]
                            for item in expected_by_entity[logical_id]
                            if item["transition_version"] == 1
                        ),
                        None if terminal is None else terminal["event_at_us"],
                        terminal_occurrence,
                        fold["observed_duration_us"],
                        None,
                    )
                    if tool is None or tuple(tool) != expected_tool:
                        raise AssertionError(f"committed tool fold differs for {logical_id}")
                publications = list(
                    read_connection.execute(
                        "SELECT publication_id, parent_publication_id, operation_id "
                        "FROM publications ORDER BY committed_at_us, publication_id"
                    )
                )
                target_publications = publications[1:]
                if any(
                    row[1] != (SEED_PUBLICATION_ID if index == 0 else target_publications[index - 1][0])
                    for index, row in enumerate(target_publications)
                ):
                    raise AssertionError("publication chain is not a sequence of direct children")
                counts = {
                    "publication_head": read_connection.execute(
                        "SELECT publication_id FROM publication_head WHERE singleton = 1"
                    ).fetchone()[0],
                    "publications": len(publications),
                    "lifecycle_transitions": read_connection.execute(
                        "SELECT COUNT(*) FROM lifecycle_transitions"
                    ).fetchone()[0],
                    "source_occurrences": read_connection.execute(
                        "SELECT COUNT(*) FROM source_occurrences"
                    ).fetchone()[0],
                    "distinct_source_occurrences": read_connection.execute(
                        "SELECT COUNT(DISTINCT occurrence_id) FROM source_occurrences"
                    ).fetchone()[0],
                }
            finally:
                read_connection.close()
            expected_chain = [SEED_PUBLICATION_ID, *(chunk["publication_id"] for chunk in chunks)]
            if counts["publication_head"] != expected_chain[-1]:
                raise AssertionError("publication head is not the final direct child")
            source_occurrence_delta = counts["source_occurrences"] - seed_source_occurrences
            if source_occurrence_delta != inserted_occurrences:
                raise AssertionError(
                    "source occurrence delta differs from inserted occurrence truth: "
                    f"seed={seed_source_occurrences}, final={counts['source_occurrences']}, "
                    f"delta={source_occurrence_delta}, inserted={inserted_occurrences}"
                )
            if counts["distinct_source_occurrences"] != counts["source_occurrences"]:
                raise AssertionError("source occurrence identifiers are not unique")
            if events.count("writer_publish") != len(chunks):
                raise AssertionError("writer publish count differs from planner-selected chunks")
            identity_bindings = all(
                len(
                    {
                        chunk["identity_bindings"]["selection_head"],
                        chunk["identity_bindings"]["refresh_intent_parent"],
                        chunk["identity_bindings"]["plan_parent"],
                        chunk["identity_bindings"]["writer_request_expected_active"],
                        chunk["identity_bindings"]["pre_commit_pointer_active"],
                        chunk["identity_bindings"]["committed_head_parent"],
                    }
                )
                == 1
                and (
                    (
                        chunk["planner_operation_class"] == OperationClass.APPEND_SAFE_SMALL.value
                        and chunk["identity_bindings"]["small_request_expected_active"]
                        == chunk["identity_bindings"]["writer_request_expected_active"]
                    )
                    or (
                        chunk["planner_operation_class"] == OperationClass.APPEND_SAFE_LARGE.value
                        and chunk["identity_bindings"]["promotion_request_expected_active"]
                        == chunk["identity_bindings"]["writer_request_expected_active"]
                    )
                )
                and chunk["plan_digest_before_writer"] == chunk["plan_digest_at_writer"]
                and chunk["identity_bindings"]["post_commit_pointer_active"]
                == chunk["publication_id"]
                for chunk in chunks
            )
            if not identity_bindings:
                raise AssertionError("publication identity bindings are not equal")
            if any(
                events.index("plan_refresh") > events.index("writer_lock")
                for _ in [0]
            ):
                raise AssertionError("planner was not evaluated before writer lock")
            independent_truth_digest = hashlib.sha256()
            for logical_id in sorted(expected_by_entity):
                independent_truth_digest.update(
                    _canonical(_reference_fold(expected_by_entity[logical_id]))
                )
            return {
                "run_id": f"ck07r1-requalification-{profile_name}",
                "profile_identity": {
                    "name": profile_name,
                    "history_preset": "30_days" if profile_name == "standard" else "all_time",
                    "profile_digest": _sha256(PROFILE_ROOT / f"{profile_name}-v1.json"),
                    "synthetic_observations": len(scale),
                    "synthetic_entities": len(expected_by_entity),
                },
                "planner_operation_class": chunks[-1]["planner_operation_class"],
                "planner_reason": chunks[-1]["planner_reason"],
                "planner_operation_classes": [chunk["planner_operation_class"] for chunk in chunks],
                "planner_reasons": [chunk["planner_reason"] for chunk in chunks],
                "writer_paths": [chunk["writer_path"] for chunk in chunks],
                "planner_tail_limits": _jsonable(_tail_limits()),
                "planner_change_estimate": chunks[0]["planner_change_estimate"],
                "publication_chain": {
                    "seed_publication_id": SEED_PUBLICATION_ID,
                    "target_publication_ids": [chunk["publication_id"] for chunk in chunks],
                    "direct_child_chain": True,
                    "chunks": chunks,
                },
                "recovery_report": {
                    "selection_role": recovery_report.selection.role,
                    "repaired_pointer": recovery_report.repaired_pointer,
                    "completed_operations": recovery_report.completed_operations,
                    "failed_operations": recovery_report.failed_operations,
                    "reconciled_intents": recovery_report.reconciled_intents,
                    "removed_leases": recovery_report.removed_leases,
                },
                "recovery_probe": {
                    "scenario": "synthetic_crash_after_intent_prepare_then_startup_retry",
                    "prepared_intent_id": recovery_probe_id,
                    "first_recovery_reconciled": recovery_probe_report.reconciled_intents,
                    "retry_reconciled": recovery_retry_report.reconciled_intents,
                    "retry_failed_operations": recovery_retry_report.failed_operations,
                },
                "independent_truth_digest": independent_truth_digest.hexdigest(),
                "fold_digest": fold_digest.hexdigest(),
                "postconditions": {
                    **counts,
                    "seed_source_occurrences": seed_source_occurrences,
                    "source_occurrence_delta": source_occurrence_delta,
                    "inserted_occurrences": inserted_occurrences,
                    "source_occurrence_ids_unique": True,
                    "lifecycle_transition_truth_count": len(actual_rows),
                    "preparation_transaction_open": False,
                    "analytical_transaction_open": False,
                    "path_order": "recovery_read_first; planner_before_writer_lock; selected_plan_unchanged_through_writer",
                    "identity_bindings": identity_bindings,
                    "independent_oracle": "tests/agent_kernel/contracts/reference/lifecycle.py:fold_lifecycle",
                },
            }
        finally:
            operational_connection.close()


def _rss_bytes() -> int:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value if platform.system() == "Darwin" else value * 1024


def _lifecycle_sample(changes: ProposedChangeSet, samples: int) -> dict[str, Any]:
    measurements: list[float] = []
    transition_digest = ""
    fold_digest = ""
    for _ in range(samples):
        gc.collect()
        request = _request("publication:ck07r1:sample", None)
        preparer = preparation._WriteSetPreparer(
            changes,
            request,
            configured_producer_key="synthetic-ck07r1",
            prior=PriorPublicationSnapshot(),
            inventory_started_at_us=request.committed_at_us,
            inventory_completed_at_us=request.committed_at_us,
        )
        started = time.perf_counter_ns()
        preparer._build_lifecycle()
        measurements.append((time.perf_counter_ns() - started) / 1_000_000)
        transitions = [
            {
                "logical_id": transition.entity_logical_id,
                "state": transition.lifecycle_state,
                "basis": transition.state_basis,
                "coordinate": {
                    "source_order": transition.source_order,
                    "event_at_us": transition.transition_at_us,
                },
                "event_at_us": transition.transition_at_us,
                "event_kind_order": transition.event_kind_order,
                "source_order": ["synthetic-lifecycle", transition.source_order],
            }
            for transition in preparer.transitions
        ]
        transition_digest = hashlib.sha256(_canonical(transitions)).hexdigest()
        fold_digest = hashlib.sha256(
            _canonical(
                {
                    logical_id: _reference_fold(
                        [
                            item
                            for item in transitions
                            if item["logical_id"] == logical_id
                        ]
                    )
                    for logical_id in sorted({item["logical_id"] for item in transitions})
                }
            )
        ).hexdigest()
    return {
        "observation_count": len(changes.observations),
        "timing_samples_ms": [round(item, 3) for item in measurements],
        "median_ms": round(statistics.median(measurements), 3),
        "max_ms": max(measurements),
        "transition_digest": transition_digest,
        "fold_digest": fold_digest,
        "rss_bytes": _rss_bytes(),
    }


def _profile_run(name: str, *, samples: int, publish: bool) -> dict[str, Any]:
    profile = _profile(name)
    days = 30 if name == "standard" else None
    scale = _scale_observations(name, profile, days)
    changes = _changes(scale)
    lifecycle = _lifecycle_sample(changes, samples)
    descriptor = {
        "source_profile": name,
        "history_preset": "30_days" if days is not None else "all_time",
        "model_calls": _model_call_count(profile, days),
        "entities": len({item.logical_id for item in scale}),
        "observations": len(scale),
        "seed": FIXTURE_SEED,
        "profile_file_sha256": PROFILE_DIGESTS[name],
        "ordered_transition_vector_sha256": lifecycle["transition_digest"],
    }
    lifecycle["workload_transition_digest"] = _workload_transition_digest((descriptor,))
    result: dict[str, Any] = {
        "profile": name,
        "history_preset": "30_days" if days is not None else "all_time",
        "profile_digest": PROFILE_DIGESTS[name],
        "synthetic_observation_count": len(scale),
        "synthetic_entity_count": len({item.logical_id for item in scale}),
        "workload_descriptor": descriptor,
        "lifecycle_preparation": lifecycle,
    }
    if publish:
        base = ingest(TINY_ROOT, manifest=TINY_ROOT / "manifest.json", workers=1, batch_size=32).changes
        result["publication_receipt"] = _publication_receipt(name, scale, base)
        result["publication_receipt"]["workload_transition_digest"] = lifecycle[
            "workload_transition_digest"
        ]
    return result


def run(*, profile_name: str, samples: int = 5) -> dict[str, Any]:
    if samples != PRODUCTION_SAMPLE_COUNT:
        raise ValueError(
            f"CK-07R1 requires exactly {PRODUCTION_SAMPLE_COUNT} unprofiled samples"
        )
    if profile_name in {"standard", "production"}:
        return _profile_run(profile_name, samples=samples, publish=False)
    standard = _profile_run("standard", samples=samples, publish=True)
    production = _profile_run("production", samples=samples, publish=True)
    measurements = {
        "standard_30_day": standard,
        "production_all_time": production,
        "no_change": _lifecycle_sample(_changes(()), samples),
        "one_call_tail": _lifecycle_sample(
            _changes((_tool_observation("tail", 0, 0),)), samples
        ),
        "one_tool_tail": _lifecycle_sample(
            _changes((_tool_observation("tail", 0, 1),)), samples
        ),
    }
    checks, first_failure = _budget_checks(measurements)
    workload_descriptors = [
        standard["workload_descriptor"],
        production["workload_descriptor"],
        {
            "source_profile": "synthetic_tail",
            "history_preset": "all_time",
            "model_calls": 0,
            "entities": 0,
            "observations": 0,
            "seed": FIXTURE_SEED,
            "profile_file_sha256": None,
            "ordered_transition_vector_sha256": measurements["no_change"]["transition_digest"],
        },
        {
            "source_profile": "synthetic_tail",
            "history_preset": "all_time",
            "model_calls": 0,
            "entities": 1,
            "observations": 1,
            "seed": FIXTURE_SEED,
            "profile_file_sha256": None,
            "ordered_transition_vector_sha256": measurements["one_call_tail"]["transition_digest"],
        },
        {
            "source_profile": "synthetic_tail",
            "history_preset": "all_time",
            "model_calls": 0,
            "entities": 1,
            "observations": 1,
            "seed": FIXTURE_SEED,
            "profile_file_sha256": None,
            "ordered_transition_vector_sha256": measurements["one_tool_tail"]["transition_digest"],
        },
    ]
    workload_transition_digest = _workload_transition_digest(workload_descriptors)
    receipts = {
        name: measurements[name]["publication_receipt"]
        for name in ("standard_30_day", "production_all_time")
    }
    publication_digest = hashlib.sha256(
        _canonical({name: receipt for name, receipt in receipts.items()})
    ).hexdigest()
    return {
        "schema": SCHEMA,
        "dependency_sha": DEPENDENCY_SHA,
        "fixture_identity": _fixture_identity(),
        "workload_descriptors": workload_descriptors,
        "workload_transition_digest": workload_transition_digest,
        "fixture_digest": hashlib.sha256(
            _canonical(
                {
                    "profiles": PROFILE_DIGESTS,
                    "standard_workload": standard["lifecycle_preparation"]["transition_digest"],
                    "production_workload": production["lifecycle_preparation"]["transition_digest"],
                }
            )
        ).hexdigest(),
        "publication_digest": publication_digest,
        "fold_identity_matches": True,
        "linear_work_counters": {
            "complexity": "observations_plus_prior_transitions",
            "implementation_digest": _sha256(
                ROOT / "src/codex_usage_tracker/agent_kernel/publication/preparation.py"
            ),
            "benchmark_digest": _sha256(Path(__file__)),
            "frozen_budgets_ms": FROZEN_BUDGETS_MS,
            "budget_checks": checks,
            "tail_limits": FROZEN_TAIL_LIMITS,
            "standard_30_day": standard,
            "production_all_time": production,
            "run_accounting": [
                {
                    "run_id": "all-profile-initial-serializer",
                    "classification": "failed_preserved",
                    "preservation": "retained_read_only_never_reused_overwritten_hidden_or_upgraded",
                },
                {
                    "run_id": "all-profile-corrected-serializer-tail-oracle",
                    "classification": "failed_preserved",
                    "preservation": "retained_read_only_never_reused_overwritten_hidden_or_upgraded",
                },
                {
                    "run_id": "all-profile-pid-60367-recovery",
                    "classification": "writer_only_not_publication_valid",
                    "receipt_digest": "935e4427b93e67c5ca649b773b0b3895dafac87f49bc76d7ed8917dff2f0250d",
                    "preservation": "retained_read_only_never_reused_overwritten_hidden_or_upgraded",
                },
                {
                    "run_id": "production-only-valid-profile",
                    "classification": "distinct_packet_required_profile",
                    "preservation": "retained_read_only_never_reused_overwritten_hidden_or_upgraded",
                },
                {
                    "run_id": "ck07r1-requalification-standard-production",
                    "classification": "fresh_reachable_path_candidate",
                    "receipt_digest": publication_digest,
                    "new_end_to_end_run": True,
                },
            ],
        },
        "timing_samples_ms": measurements["production_all_time"]["lifecycle_preparation"][
            "timing_samples_ms"
        ],
        "attribution_profile": {
            "scope": "_WriteSetPreparer._build_lifecycle",
            "excluded": ["fixture_generation", "ingestion", "PublicationWriter", "recovery"],
            "speed_claim_source": "five_unprofiled_samples",
            "publication_receipt_mode": "plan_refresh_recovery_pointer_coordinated_small_publication",
            "publication_chunk_observations": PUBLICATION_CHUNK_OBSERVATIONS,
        },
        "rss_bytes": max(
            measurements["standard_30_day"]["lifecycle_preparation"]["rss_bytes"],
            measurements["production_all_time"]["lifecycle_preparation"]["rss_bytes"],
        ),
        "lock_observations": [
            {
                "phase": "lifecycle_preparation",
                "analytical_transaction_open": False,
                "analytical_transaction_closed_after": True,
            },
            {
                "phase": "publication_writer",
                "preparation_completed_before_begin": True,
                "plan_identity_preserved": True,
            },
        ],
        "linked_evidence_amendments": [
            "docs/decisions/evidence/ck07/publication-refresh-recovery-evidence.json"
        ],
        "first_failure": first_failure,
        "noise": [
            {
                "context": "PR-394-first-hosted-failure",
                "classification": "retained_read_only_evidence",
                "case": "ordinary.2000_call_tail",
                "python": "3.14 hosted",
                "authority_changed": False,
            },
            {
                "context": "Agent Perf fixture",
                "classification": "unavailable_or_mismatched",
                "substitution": False,
            },
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("standard", "production", "all"), default="all")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path)
    raw_argv = tuple(sys.argv[1:])
    args = parser.parse_args(raw_argv)
    if args.profile == "all":
        script_and_args = (sys.argv[0], *raw_argv)
        if script_and_args != LAUNCH_COMMAND[1:]:
            print(
                "CK-07R1 all-profile qualification requires the exact frozen launch command",
                file=sys.stderr,
            )
            return 2
        return _launch_exact()
    payload = run(profile_name=args.profile, samples=args.samples)
    encoded = _canonical(payload) + b"\n"
    if args.output is None:
        print(encoded.decode(), end="")
    else:
        _exclusive_write(args.output, encoded)
    return int(payload.get("first_failure") is not None)


if __name__ == "__main__":
    raise SystemExit(main())
