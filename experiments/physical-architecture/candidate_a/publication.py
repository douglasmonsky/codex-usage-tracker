from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import shared

from .ingest import BuildArtifact, build_artifact, file_sha256
from .schema import database, validate_database

_ACTIVE_ARTIFACT = "publication.sqlite"
_ROLLBACK_ARTIFACT = "rollback.sqlite"
_STAGING_ARTIFACT = "candidate.sqlite"
_ACTIVE_POINTER = "active-publication.json"
_ROLLBACK_POINTER = "rollback-publication.json"
_SIDECAR = "publication-state.json"
_LEASE = "publication-lease.json"
_CLEANUP_PENDING = "old-artifact-cleanup.pending"
_FAULT_OBSERVATION = "fault-observation.json"
_RECOVERY_TERMINAL = "recovery-terminal-state.json"
_SUBSEQUENT_PUBLICATION = "subsequent-publication.json"
_RECOVERY_LOCK = ".publication-recovery.lock"
_WORKER_CRASH_EXIT = 86
_WORKER_FAULT_EXIT = 87


@dataclass(frozen=True)
class _ArtifactInspection:
    name: str
    exists: bool
    valid: bool
    publication_id: str | None = None
    artifact_sha256: str | None = None
    error_type: str | None = None

    def as_record(self) -> dict[str, object]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "error_type": self.error_type,
            "exists": self.exists,
            "name": self.name,
            "publication_id": self.publication_id,
            "valid": self.valid,
        }


@dataclass(frozen=True)
class RecoveryResult:
    active_publication_id: str
    prior_publication_queryable: bool
    rollback_available: bool
    candidate_publication_committed: bool
    sidecar_terminal_state: str
    abandoned_artifact_disposition: str
    recovery_action: str
    evidence_path: Path


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _atomic_write_json(path: Path, value: Mapping[str, object]) -> None:
    _atomic_write_bytes(path, shared.canonical_json_bytes(value))


def _read_json_record(path: Path) -> tuple[dict[str, Any] | None, str]:
    if not path.is_file():
        return None, "missing"
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, f"invalid:{type(error).__name__}"
    if not isinstance(value, dict):
        return None, "invalid:shape"
    return {str(key): item for key, item in value.items()}, "valid"


def _canonical_record_sha256(path: Path) -> str:
    record, status = _read_json_record(path)
    if record is None or status != "valid":
        raise RuntimeError(f"candidate A evidence record is not readable: {path.name}")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"candidate A evidence record cannot be read: {path.name}") from error
    if payload != shared.canonical_json_bytes(record):
        raise RuntimeError(f"candidate A evidence record is not canonical: {path.name}")
    return shared.canonical_sha256(record)


def _copy_artifact_atomic(source: Path, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.tmp")
    shutil.copyfile(source, temporary)
    os.chmod(temporary, 0o600)
    os.replace(temporary, destination)


def _remove_sqlite_artifact(path: Path) -> None:
    for candidate in (
        path,
        path.with_name(f"{path.name}-journal"),
        path.with_name(f"{path.name}-shm"),
        path.with_name(f"{path.name}-wal"),
    ):
        candidate.unlink(missing_ok=True)


def _publication_id(path: Path, *, prepublication: bool = False) -> str:
    with database(path, read_only=True) as connection:
        validate_database(
            connection,
            mode="prepublication" if prepublication else "exhaustive",
        )
        row = connection.execute(
            """
            SELECT publication_id FROM publications
            WHERE status='committed'
            ORDER BY committed_at_us DESC, publication_id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise ValueError("candidate A publication has no committed identity")
        return str(row["publication_id"])


def _inspect_artifact(path: Path) -> _ArtifactInspection:
    if not path.is_file():
        return _ArtifactInspection(name=path.name, exists=False, valid=False)
    try:
        publication_id = _publication_id(path, prepublication=True)
        with database(path, read_only=True) as connection:
            connection.execute("SELECT count(*) FROM model_calls_visible").fetchone()
        digest = file_sha256(path)
    except (OSError, sqlite3.Error, ValueError) as error:
        return _ArtifactInspection(
            name=path.name,
            exists=True,
            valid=False,
            error_type=type(error).__name__,
        )
    return _ArtifactInspection(
        name=path.name,
        exists=True,
        valid=True,
        publication_id=publication_id,
        artifact_sha256=digest,
    )


def _pointer_record(artifact: _ArtifactInspection) -> dict[str, object]:
    if not artifact.valid or artifact.publication_id is None:
        raise ValueError("candidate A cannot point at an invalid artifact")
    return {
        "artifact_path": artifact.name,
        "artifact_sha256": artifact.artifact_sha256,
        "publication_id": artifact.publication_id,
        "schema": "candidate-a-publication-pointer.v1",
    }


def _pointer_matches(
    pointer: Mapping[str, Any] | None,
    artifact: _ArtifactInspection,
) -> bool:
    return bool(
        pointer is not None
        and artifact.valid
        and pointer.get("schema") == "candidate-a-publication-pointer.v1"
        and pointer.get("artifact_path") == artifact.name
        and pointer.get("publication_id") == artifact.publication_id
        and pointer.get("artifact_sha256") == artifact.artifact_sha256
    )


def _write_pointer(path: Path, artifact: _ArtifactInspection) -> None:
    _atomic_write_json(path, _pointer_record(artifact))


def _operation_record(
    *,
    operation_id: str,
    parent_publication_id: str | None,
    state: str,
    stage: str,
) -> dict[str, object]:
    return {
        "operation_id": operation_id,
        "parent_publication_id": parent_publication_id,
        "schema": "candidate-a-publication-operation.v1",
        "stage": stage,
        "state": state,
    }


def publish_artifact(
    fixture: shared.FixtureBundle,
    run_root: Path,
    *,
    history_selection: str = "all_time",
    parent_publication_id: str | None = None,
    hook: Callable[[str], None] | None = None,
    defer_secondary_indexes: bool = True,
    parser_workers: int = 1,
) -> BuildArtifact:
    run_root.mkdir(parents=True, exist_ok=True)
    staging = run_root / _STAGING_ARTIFACT
    publication = run_root / _ACTIVE_ARTIFACT
    rollback = run_root / _ROLLBACK_ARTIFACT
    sidecar = run_root / _SIDECAR
    lease = run_root / _LEASE
    if staging.exists():
        raise FileExistsError(staging)

    active_before = _inspect_artifact(publication)
    if active_before.exists and not active_before.valid:
        raise ValueError("candidate A active publication is invalid")
    if (
        active_before.valid
        and parent_publication_id is not None
        and active_before.publication_id != parent_publication_id
    ):
        raise ValueError("candidate A parent publication is no longer active")
    operation_id = shared.canonical_sha256(
        {
            "candidate": "A",
            "fixture": fixture.manifest_digest,
            "history_selection": history_selection,
            "parent_publication_id": parent_publication_id,
        }
    )
    operation = _operation_record(
        operation_id=operation_id,
        parent_publication_id=parent_publication_id,
        state="running",
        stage="planned",
    )
    _atomic_write_json(sidecar, operation)
    _atomic_write_json(
        lease,
        {
            "operation_id": operation_id,
            "pid": os.getpid(),
            "schema": "candidate-a-publication-lease.v1",
            "start_token": f"{os.getpid()}:{time.monotonic_ns()}",
        },
    )

    def notify(boundary: str) -> None:
        _atomic_write_json(
            sidecar,
            _operation_record(
                operation_id=operation_id,
                parent_publication_id=parent_publication_id,
                state="running",
                stage=boundary,
            ),
        )
        if hook is not None:
            hook(boundary)

    notify("before_staging")
    artifact = build_artifact(
        fixture,
        staging,
        history_selection=history_selection,
        parent_publication_id=parent_publication_id,
        hook=notify,
        defer_secondary_indexes=defer_secondary_indexes,
        parser_workers=parser_workers,
    )
    notify("after_validation_before_promotion")

    if active_before.valid:
        _copy_artifact_atomic(publication, rollback)
        rollback_state = _inspect_artifact(rollback)
        _write_pointer(run_root / _ROLLBACK_POINTER, rollback_state)
    notify("during_promotion")
    os.replace(staging, publication)
    active_after = _inspect_artifact(publication)
    if not active_after.valid or active_after.publication_id != artifact.publication_id:
        raise ValueError("candidate A promoted artifact failed identity validation")
    _write_pointer(run_root / _ACTIVE_POINTER, active_after)
    notify("after_promotion_before_sidecar_reconciliation")

    terminal = {
        **_operation_record(
            operation_id=operation_id,
            parent_publication_id=parent_publication_id,
            state="succeeded",
            stage="completed",
        ),
        "active": _pointer_record(active_after),
        "rollback": (_pointer_record(_inspect_artifact(rollback)) if rollback.is_file() else None),
    }
    _atomic_write_json(sidecar, terminal)
    lease.unlink(missing_ok=True)

    cleanup_pending = run_root / _CLEANUP_PENDING
    _atomic_write_json(
        cleanup_pending,
        {
            "protected_artifacts": [_ACTIVE_ARTIFACT, _ROLLBACK_ARTIFACT],
            "schema": "candidate-a-cleanup-intent.v1",
            "state": "pending",
        },
    )
    if hook is not None:
        hook("during_old_artifact_cleanup")
    cleanup_pending.unlink(missing_ok=True)
    return BuildArtifact(
        path=publication,
        publication_id=artifact.publication_id,
        observed_through_us=artifact.observed_through_us,
        stats=artifact.stats,
    )


def _stage_from_records(
    sidecar: Mapping[str, Any] | None,
    fault_record: Mapping[str, Any] | None,
) -> str | None:
    stage = sidecar.get("stage") if sidecar is not None else None
    if isinstance(stage, str) and stage in shared.CRASH_BOUNDARIES:
        return stage
    fault_stage = fault_record.get("stage") if fault_record is not None else None
    if isinstance(fault_stage, str) and fault_stage in shared.CRASH_BOUNDARIES:
        return fault_stage
    return None


def _classify_disposition(
    *,
    stage: str | None,
    staging: _ArtifactInspection,
    cleanup_pending: bool,
    active_changed: bool,
    sidecar_status: str,
    recovery_action: str,
) -> str:
    if cleanup_pending:
        return "defer_cleanup"
    if recovery_action in {
        "reconstructed_missing_active_pointer",
        "rolled_back_to_valid_pair",
    }:
        return "reconcile_pointer_or_rollback"
    if stage == "after_promotion_before_sidecar_reconciliation" and active_changed:
        return "reconcile_sidecar"
    if stage == "during_promotion":
        return "reconcile_pointer_or_rollback"
    if stage == "after_validation_before_promotion" and staging.valid:
        return "retain_valid_candidate"
    if staging.exists:
        return "abandon_staging" if stage == "during_parse" else "abandon_candidate"
    if sidecar_status.startswith("invalid") and active_changed:
        return "reconcile_sidecar"
    return "none"


def _lease_observation(run_root: Path) -> dict[str, object]:
    lease, lease_status = _read_json_record(run_root / _LEASE)
    live_process, _ = _read_json_record(run_root / "live-process.json")
    lease_pid = int(lease["pid"]) if lease is not None and type(lease.get("pid")) is int else None
    pid_alive = False
    token_matches = False
    if lease_pid is not None and lease is not None:
        try:
            os.kill(lease_pid, 0)
        except (OSError, OverflowError):
            pid_alive = False
        else:
            pid_alive = True
        token_matches = bool(
            live_process is not None
            and live_process.get("pid") == lease.get("pid")
            and live_process.get("start_token") == lease.get("start_token")
        )
    return {
        "exists": lease_status != "missing",
        "pid": lease_pid,
        "pid_alive": pid_alive,
        "status": lease_status,
        "token_matches": token_matches,
    }


def recover_publication_state(
    run_root: Path,
    *,
    prior_publication_id: str,
    recovery_id: str = "startup",
    timeout_seconds: float = 10.0,
) -> RecoveryResult:
    run_root.mkdir(parents=True, exist_ok=True)
    lock_path = run_root / _RECOVERY_LOCK
    deadline = time.monotonic() + timeout_seconds
    with lock_path.open("a+b") as recovery_lock:
        while True:
            try:
                fcntl.flock(recovery_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("candidate A startup recovery lock timed out") from None
                time.sleep(0.005)
        try:
            return _recover_publication_state_locked(
                run_root,
                prior_publication_id=prior_publication_id,
                recovery_id=recovery_id,
            )
        finally:
            fcntl.flock(recovery_lock.fileno(), fcntl.LOCK_UN)


def _recover_publication_state_locked(
    run_root: Path,
    *,
    prior_publication_id: str,
    recovery_id: str,
) -> RecoveryResult:
    active_path = run_root / _ACTIVE_ARTIFACT
    rollback_path = run_root / _ROLLBACK_ARTIFACT
    staging_path = run_root / _STAGING_ARTIFACT
    active_before = _inspect_artifact(active_path)
    rollback_before = _inspect_artifact(rollback_path)
    staging_before = _inspect_artifact(staging_path)
    active_pointer, active_pointer_status = _read_json_record(run_root / _ACTIVE_POINTER)
    rollback_pointer, rollback_pointer_status = _read_json_record(run_root / _ROLLBACK_POINTER)
    sidecar, sidecar_status = _read_json_record(run_root / _SIDECAR)
    fault_record, fault_status = _read_json_record(run_root / _FAULT_OBSERVATION)
    stage = _stage_from_records(sidecar, fault_record)
    active_pair_valid = _pointer_matches(active_pointer, active_before)
    rollback_pair_valid = _pointer_matches(rollback_pointer, rollback_before)
    recovery_action = "kept_active_pair"

    if not active_pair_valid:
        if rollback_pair_valid:
            _copy_artifact_atomic(rollback_path, active_path)
            restored_active = _inspect_artifact(active_path)
            _write_pointer(run_root / _ACTIVE_POINTER, restored_active)
            recovery_action = "rolled_back_to_valid_pair"
        elif active_before.valid and active_pointer_status == "missing":
            _write_pointer(run_root / _ACTIVE_POINTER, active_before)
            recovery_action = "reconstructed_missing_active_pointer"
        else:
            raise RuntimeError("candidate A recovery found no valid active or rollback pair")

    active_recovered = _inspect_artifact(active_path)
    if not active_recovered.valid or active_recovered.publication_id is None:
        raise RuntimeError("candidate A recovery did not select a queryable active artifact")
    active_changed = active_recovered.publication_id != prior_publication_id
    cleanup_pending = (run_root / _CLEANUP_PENDING).is_file()
    if stage is None and cleanup_pending:
        stage = "during_old_artifact_cleanup"
    disposition = _classify_disposition(
        stage=stage,
        staging=staging_before,
        cleanup_pending=cleanup_pending,
        active_changed=active_changed,
        sidecar_status=sidecar_status,
        recovery_action=recovery_action,
    )

    retained_path: Path | None = None
    if staging_before.exists:
        if disposition == "retain_valid_candidate" and staging_before.valid:
            retained_path = run_root / "retained-candidate.sqlite"
            _remove_sqlite_artifact(retained_path)
            os.replace(staging_path, retained_path)
        else:
            _remove_sqlite_artifact(staging_path)
    lease_observation = _lease_observation(run_root)
    (run_root / _LEASE).unlink(missing_ok=True)

    rollback_after = _inspect_artifact(rollback_path)
    prior_candidates = (active_recovered, rollback_after)
    prior_publication_queryable = any(
        artifact.valid and artifact.publication_id == prior_publication_id
        for artifact in prior_candidates
    )
    rollback_available = bool(
        rollback_after.valid and rollback_after.publication_id == prior_publication_id
    )
    terminal_state = "succeeded" if active_changed else "failed"
    terminal_sidecar = {
        **_operation_record(
            operation_id=(
                str(sidecar.get("operation_id"))
                if sidecar is not None and sidecar.get("operation_id") is not None
                else f"recovered:{recovery_id}"
            ),
            parent_publication_id=prior_publication_id,
            state=terminal_state,
            stage="recovered",
        ),
        "active": _pointer_record(active_recovered),
        "recovery_action": recovery_action,
        "rollback": (_pointer_record(rollback_after) if rollback_after.valid else None),
    }
    _atomic_write_json(run_root / _SIDECAR, terminal_sidecar)
    observed_sidecar, observed_sidecar_status = _read_json_record(run_root / _SIDECAR)
    if observed_sidecar is None or observed_sidecar_status != "valid":
        raise RuntimeError("candidate A recovered sidecar is not readable")
    observed_terminal_state = str(observed_sidecar.get("state"))
    evidence_path = run_root / f"recovery-observation-{recovery_id}.json"
    evidence = {
        "active_after": active_recovered.as_record(),
        "active_before": active_before.as_record(),
        "active_pointer_status": active_pointer_status,
        "candidate_publication_committed": active_changed,
        "cleanup_pending": cleanup_pending,
        "disposition": disposition,
        "fault_record_status": fault_status,
        "lease": lease_observation,
        "prior_publication_id": prior_publication_id,
        "prior_publication_queryable": prior_publication_queryable,
        "recovery_action": recovery_action,
        "recovery_id": recovery_id,
        "rollback_after": rollback_after.as_record(),
        "rollback_available": rollback_available,
        "rollback_before": rollback_before.as_record(),
        "rollback_pointer_status": rollback_pointer_status,
        "schema": "candidate-a-recovery-observation.v1",
        "sidecar_status_before": sidecar_status,
        "sidecar_terminal_state": observed_terminal_state,
        "stage": stage,
        "staging_before": staging_before.as_record(),
        "retained_candidate": retained_path.name if retained_path is not None else None,
    }
    _atomic_write_json(evidence_path, evidence)
    _atomic_write_json(run_root / _RECOVERY_TERMINAL, evidence)
    return RecoveryResult(
        active_publication_id=active_recovered.publication_id,
        prior_publication_queryable=prior_publication_queryable,
        rollback_available=rollback_available,
        candidate_publication_committed=active_changed,
        sidecar_terminal_state=observed_terminal_state,
        abandoned_artifact_disposition=disposition,
        recovery_action=recovery_action,
        evidence_path=evidence_path,
    )


def _validate_execution_evidence(
    crash_case: shared.CrashCase,
    evidence: Mapping[str, Any],
    *,
    case_root: Path,
    expected_worker_pid: int,
) -> None:
    process = evidence.get("process")
    recovery = evidence.get("recovery_evidence")
    if not isinstance(process, Mapping) or not isinstance(recovery, Mapping):
        raise RuntimeError("candidate A execution evidence is incomplete")

    worker_pid = process.get("worker_pid")
    if type(worker_pid) is not int or worker_pid <= 0:
        raise RuntimeError("candidate A worker PID is missing")
    if worker_pid != expected_worker_pid:
        raise RuntimeError("candidate A worker PID differs from the launched process")

    expected_return_code = (
        _WORKER_CRASH_EXIT if crash_case.boundary is not None else _WORKER_FAULT_EXIT
    )
    if (
        process.get("expected_return_code") != expected_return_code
        or process.get("actual_return_code") != expected_return_code
    ):
        raise RuntimeError("candidate A worker return code does not match the requested case")

    terminal, terminal_status = _read_json_record(case_root / _RECOVERY_TERMINAL)
    if terminal is None or terminal_status != "valid":
        raise RuntimeError("candidate A recovery terminal evidence is missing")
    expected_stage = crash_case.boundary or _fault_boundary(crash_case.fault)
    if (
        process.get("requested_boundary") != crash_case.boundary
        or process.get("observed_stage") != expected_stage
        or recovery.get("observed_stage") != expected_stage
        or terminal.get("stage") != expected_stage
    ):
        raise RuntimeError("candidate A persisted observed stage differs from the requested case")

    lease = terminal.get("lease")
    if not isinstance(lease, Mapping):
        raise RuntimeError("candidate A persisted lease evidence is missing")
    lease_pid = lease.get("pid")
    expected_agreement = lease_pid == expected_worker_pid if type(lease_pid) is int else None
    if (
        process.get("lease_status") != lease.get("status")
        or process.get("pid_lease_agreement") is not expected_agreement
    ):
        raise RuntimeError("candidate A PID and lease evidence do not agree")
    if process.get("worker_alive_after_exit") is not False:
        raise RuntimeError("candidate A retained a nonterminal worker")

    expected_kind = "exit_code" if crash_case.boundary is not None else "injected_fault"
    lease_liveness_agrees = bool(
        (
            crash_case.boundary == "during_old_artifact_cleanup"
            and lease.get("status") == "missing"
            and lease_pid is None
        )
        or (
            crash_case.boundary is not None
            and crash_case.boundary != "during_old_artifact_cleanup"
            and lease.get("status") == "valid"
            and expected_agreement is True
            and lease.get("pid_alive") is False
        )
    )
    termination_observed = bool(
        crash_case.boundary is not None
        and process.get("actual_return_code") == process.get("expected_return_code")
        and process.get("requested_boundary") == process.get("observed_stage")
        and process.get("worker_alive_after_exit") is False
        and lease_liveness_agrees
    )
    if (
        process.get("status") != "observed"
        or process.get("termination_kind") != expected_kind
        or process.get("termination_observed") is not termination_observed
    ):
        raise RuntimeError("candidate A termination evidence is inconsistent")

    if recovery.get("recovery_action") != terminal.get("recovery_action"):
        raise RuntimeError("candidate A recovery action differs from terminal evidence")
    if recovery.get("recovery_terminal_sha256") != _canonical_record_sha256(
        case_root / _RECOVERY_TERMINAL
    ):
        raise RuntimeError("candidate A recovery terminal digest is not exact")
    if recovery.get("subsequent_publication_sha256") != _canonical_record_sha256(
        case_root / _SUBSEQUENT_PUBLICATION
    ):
        raise RuntimeError("candidate A subsequent publication digest is not exact")


def _execution_evidence(
    crash_case: shared.CrashCase,
    *,
    case_root: Path,
    worker_pid: int,
    actual_return_code: int,
    expected_return_code: int,
    worker_alive_after_exit: bool,
) -> dict[str, dict[str, object]]:
    terminal, terminal_status = _read_json_record(case_root / _RECOVERY_TERMINAL)
    if terminal is None or terminal_status != "valid":
        raise RuntimeError("candidate A recovery terminal evidence is missing")
    lease = terminal.get("lease")
    if not isinstance(lease, Mapping):
        raise RuntimeError("candidate A persisted lease evidence is missing")
    lease_pid = lease.get("pid")
    pid_lease_agreement = lease_pid == worker_pid if type(lease_pid) is int else None
    observed_stage = terminal.get("stage")
    requested_boundary = crash_case.boundary
    lease_liveness_agrees = bool(
        (
            requested_boundary == "during_old_artifact_cleanup"
            and lease.get("status") == "missing"
            and lease_pid is None
        )
        or (
            requested_boundary is not None
            and requested_boundary != "during_old_artifact_cleanup"
            and lease.get("status") == "valid"
            and pid_lease_agreement is True
            and lease.get("pid_alive") is False
        )
    )
    process = {
        "actual_return_code": actual_return_code,
        "expected_return_code": expected_return_code,
        "lease_status": str(lease.get("status")),
        "observed_stage": observed_stage,
        "pid_lease_agreement": pid_lease_agreement,
        "requested_boundary": requested_boundary,
        "status": "observed",
        "termination_kind": ("exit_code" if requested_boundary is not None else "injected_fault"),
        "termination_observed": bool(
            requested_boundary is not None
            and actual_return_code == expected_return_code
            and requested_boundary == observed_stage
            and not worker_alive_after_exit
            and lease_liveness_agrees
        ),
        "worker_alive_after_exit": worker_alive_after_exit,
        "worker_pid": worker_pid,
    }
    recovery_evidence = {
        "observed_stage": observed_stage,
        "recovery_action": str(terminal.get("recovery_action")),
        "recovery_terminal_sha256": _canonical_record_sha256(case_root / _RECOVERY_TERMINAL),
        "subsequent_publication_sha256": _canonical_record_sha256(
            case_root / _SUBSEQUENT_PUBLICATION
        ),
    }
    evidence = {
        "process": process,
        "recovery_evidence": recovery_evidence,
    }
    _validate_execution_evidence(
        crash_case,
        evidence,
        case_root=case_root,
        expected_worker_pid=worker_pid,
    )
    return evidence


class CandidateACrashDriver:
    candidate_id = "A"
    _execution_evidence: dict[str, dict[str, object]] | None = None

    def __init__(
        self,
        fixture: shared.FixtureBundle,
        run_root: Path,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.fixture = fixture
        self.run_root = run_root
        self.timeout_seconds = timeout_seconds

    def run_crash_case(self, crash_case: shared.CrashCase) -> shared.CrashObservation:
        self._execution_evidence = None
        case_root = self.run_root / crash_case.case_id.replace(".", "-")
        case_root.mkdir(parents=True, exist_ok=False)
        prior = publish_artifact(self.fixture, case_root)
        _copy_artifact_atomic(prior.path, case_root / "prior.sqlite")
        _copy_artifact_atomic(prior.path, case_root / _ROLLBACK_ARTIFACT)
        _write_pointer(
            case_root / _ROLLBACK_POINTER,
            _inspect_artifact(case_root / _ROLLBACK_ARTIFACT),
        )
        driver_start_token = shared.canonical_sha256(
            {"case_id": crash_case.case_id, "pid": os.getpid()}
        )
        _atomic_write_json(
            case_root / "live-process.json",
            {
                "pid": os.getpid(),
                "schema": "candidate-a-live-process.v1",
                "start_token": driver_start_token,
            },
        )
        command = [
            sys.executable,
            "-m",
            "candidate_a.crash_worker",
            "--fixture",
            str(self.fixture.root),
            "--run-root",
            str(case_root),
            "--parent-publication-id",
            prior.publication_id,
            "--driver-pid",
            str(os.getpid()),
            "--driver-start-token",
            driver_start_token,
            "--timeout",
            str(self.timeout_seconds),
        ]
        if crash_case.boundary is not None:
            command.extend(("--stop-at", crash_case.boundary))
            expected_returncode = _WORKER_CRASH_EXIT
        else:
            command.extend(("--fault", str(crash_case.fault)))
            expected_returncode = _WORKER_FAULT_EXIT
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
        process = subprocess.Popen(
            command,
            cwd=case_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.communicate(timeout=self.timeout_seconds)
            raise TimeoutError("candidate A crash worker timed out") from error
        worker_alive_after_exit = process.poll() is None
        if process.returncode != expected_returncode:
            raise RuntimeError(
                "candidate A crash worker exited "
                f"{process.returncode}, expected {expected_returncode}"
            )
        if crash_case.fault is not None:
            fault_record, fault_status = _read_json_record(case_root / _FAULT_OBSERVATION)
            if (
                fault_status != "valid"
                or fault_record is None
                or fault_record.get("fault") != crash_case.fault
            ):
                raise RuntimeError("candidate A fault worker did not record its mechanism")

        if crash_case.fault == "simultaneous_startup_recovery":
            recovery = self._run_simultaneous_recovery(case_root, prior.publication_id)
        else:
            recovery = recover_publication_state(
                case_root,
                prior_publication_id=prior.publication_id,
                recovery_id="driver",
                timeout_seconds=self.timeout_seconds,
            )
        terminal_record, terminal_status = _read_json_record(case_root / _RECOVERY_TERMINAL)
        if terminal_status != "valid" or terminal_record is None:
            raise RuntimeError("candidate A recovery did not leave terminal evidence")
        prior_queryable = bool(terminal_record["prior_publication_queryable"])
        rollback_available = bool(terminal_record["rollback_available"])
        committed = bool(terminal_record["candidate_publication_committed"])
        terminal_state = str(terminal_record["sidecar_terminal_state"])
        disposition = str(terminal_record["disposition"])

        subsequent = publish_artifact(
            self.fixture,
            case_root,
            parent_publication_id=recovery.active_publication_id,
        )
        active_after = _inspect_artifact(case_root / _ACTIVE_ARTIFACT)
        active_pointer, _ = _read_json_record(case_root / _ACTIVE_POINTER)
        sidecar_after, sidecar_status = _read_json_record(case_root / _SIDECAR)
        subsequent_succeeds = bool(
            active_after.valid
            and active_after.publication_id == subsequent.publication_id
            and _pointer_matches(active_pointer, active_after)
            and sidecar_status == "valid"
            and sidecar_after is not None
            and sidecar_after.get("state") == "succeeded"
        )
        _atomic_write_json(
            case_root / _SUBSEQUENT_PUBLICATION,
            {
                "active": active_after.as_record(),
                "parent_publication_id": recovery.active_publication_id,
                "schema": "candidate-a-subsequent-publication.v1",
                "succeeded": subsequent_succeeds,
            },
        )
        self._execution_evidence = _execution_evidence(
            crash_case,
            case_root=case_root,
            worker_pid=process.pid,
            actual_return_code=process.returncode,
            expected_return_code=expected_returncode,
            worker_alive_after_exit=worker_alive_after_exit,
        )
        if crash_case.fault is not None:
            return shared.CrashObservation(
                boundary=None,
                fault=crash_case.fault,
                prior_publication_queryable=prior_queryable,
                rollback_available=rollback_available,
                candidate_publication_committed=committed,
                sidecar_terminal_state=terminal_state,
                abandoned_artifact_disposition=disposition,
                subsequent_operation_succeeds=subsequent_succeeds,
            )
        return shared.CrashObservation(
            boundary=crash_case.boundary,
            prior_publication_queryable=prior_queryable,
            rollback_available=rollback_available,
            candidate_publication_committed=committed,
            sidecar_terminal_state=terminal_state,
            abandoned_artifact_disposition=disposition,
            subsequent_operation_succeeds=subsequent_succeeds,
        )

    @property
    def execution_evidence(self) -> dict[str, dict[str, object]]:
        if self._execution_evidence is None:
            raise RuntimeError("candidate A crash execution evidence is not available")
        return self._execution_evidence

    def _run_simultaneous_recovery(
        self,
        case_root: Path,
        prior_publication_id: str,
    ) -> RecoveryResult:
        start = case_root / "simultaneous-recovery.start"
        processes: list[subprocess.Popen[bytes]] = []
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
        try:
            for ordinal in range(2):
                ready = case_root / f"simultaneous-recovery-{ordinal}.ready"
                result = case_root / f"simultaneous-recovery-{ordinal}.json"
                command = (
                    sys.executable,
                    "-m",
                    "candidate_a.crash_worker",
                    "--recover-run-root",
                    str(case_root),
                    "--recover-prior-publication-id",
                    prior_publication_id,
                    "--recover-id",
                    f"startup-{ordinal}",
                    "--recover-ready",
                    str(ready),
                    "--recover-start",
                    str(start),
                    "--recover-result",
                    str(result),
                    "--timeout",
                    str(self.timeout_seconds),
                )
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=case_root,
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                )
            deadline = time.monotonic() + self.timeout_seconds
            ready_paths = tuple(
                case_root / f"simultaneous-recovery-{ordinal}.ready" for ordinal in range(2)
            )
            while not all(path.is_file() for path in ready_paths):
                if any(process.poll() is not None for process in processes):
                    raise RuntimeError("candidate A recovery worker exited before its barrier")
                if time.monotonic() >= deadline:
                    raise TimeoutError("candidate A simultaneous recovery barrier timed out")
                time.sleep(0.005)
            _atomic_write_json(
                start,
                {"schema": "candidate-a-recovery-barrier.v1", "state": "released"},
            )
            for process in processes:
                process.wait(timeout=max(0.1, deadline - time.monotonic()))
                if process.returncode != 0:
                    raise RuntimeError("candidate A simultaneous recovery worker failed")
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=self.timeout_seconds)
        terminal, terminal_status = _read_json_record(case_root / _RECOVERY_TERMINAL)
        if terminal is None or terminal_status != "valid":
            raise RuntimeError("candidate A simultaneous recovery has no terminal result")
        return RecoveryResult(
            active_publication_id=str(terminal["active_after"]["publication_id"]),
            prior_publication_queryable=bool(terminal["prior_publication_queryable"]),
            rollback_available=bool(terminal["rollback_available"]),
            candidate_publication_committed=bool(terminal["candidate_publication_committed"]),
            sidecar_terminal_state=str(terminal["sidecar_terminal_state"]),
            abandoned_artifact_disposition=str(terminal["disposition"]),
            recovery_action=str(terminal["recovery_action"]),
            evidence_path=case_root / _RECOVERY_TERMINAL,
        )


def _fault_boundary(fault: str | None) -> str:
    if fault in {
        "disk_full_before_transaction",
        "invalid_rate_card",
        "stale_writer_lease",
        "stale_lease_pid_reuse",
    }:
        return "before_staging"
    if fault in {"malformed_source", "disappearing_source"}:
        return "during_parse"
    if fault == "disk_full_during_transaction":
        return "during_fact_writes"
    if fault == "disk_full":
        return "during_projection_update"
    if fault in {
        "corrupt_staging_artifact",
        "analytical_candidate_corruption",
        "schema_projection_incompatibility",
    }:
        return "after_validation_before_promotion"
    if fault == "busy_reader":
        return "during_promotion"
    if fault in {
        "sidecar_corruption",
        "pointer_mismatch",
        "read_process_open_during_promotion",
        "simultaneous_startup_recovery",
    }:
        return "after_promotion_before_sidecar_reconciliation"
    raise ValueError(f"unknown candidate A crash fault: {fault}")
