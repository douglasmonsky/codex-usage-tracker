"""Typed operational-sidecar state for publication coordination.

The sidecar coordinates work; it is deliberately not an accounting authority.
All mutations in this module are bounded point updates against database-v1.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum, IntFlag

WorkerProbe = Callable[[int, str], bool]


class OperationalStateError(RuntimeError):
    """An operational transition would violate the publication protocol."""


class CompatibilityConflictError(OperationalStateError):
    """A compatibility slot is occupied by a different request."""


class LeaseConflictError(OperationalStateError):
    """A live, differently owned lease prevents acquisition."""


class LeaseFenceError(OperationalStateError):
    """A lease mutation was attempted with stale ownership evidence."""


class HostWaitTimeoutError(OperationalStateError):
    """A bounded host wait expired before an operation terminalized."""


class OperationClass(str, Enum):
    NO_CHANGE = "no_change"
    APPEND_SAFE_SMALL = "append_safe_small"
    APPEND_SAFE_LARGE = "append_safe_large"
    VALUATION_ONLY = "valuation_only"
    SOURCE_REPLACE = "source_replace"
    RECANONICALIZE = "recanonicalize"
    SCHEMA_UPGRADE = "schema_upgrade"
    PROJECTION_UPGRADE = "projection_upgrade"
    HISTORY_EXPAND = "history_expand"


class JobState(str, Enum):
    PLANNED = "planned"
    PARSING = "parsing"
    READY_TO_WRITE = "ready_to_write"
    WRITING = "writing"
    BUILDING = "building"
    CATCHING_UP = "catching_up"
    VALIDATING = "validating"
    PROMOTING = "promoting"
    RECONCILING = "reconciling"
    RECOVERY_REQUIRED = "recovery_required"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RecoveryIntentState(str, Enum):
    PREPARED = "prepared"
    POINTER_WRITTEN = "pointer_written"
    VERIFIED = "verified"
    RECONCILED = "reconciled"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class LeaseName(str, Enum):
    ANALYTICAL_WRITER = "analytical_writer"
    ARTIFACT_PROMOTION = "artifact_promotion"


class DirtyReason(IntFlag):
    CREATED = 1
    MODIFIED = 2
    REMOVED = 4
    REPLACED = 8
    RECONCILIATION = 16


ACTIVE_JOB_STATES = frozenset(
    {
        JobState.PLANNED,
        JobState.PARSING,
        JobState.READY_TO_WRITE,
        JobState.WRITING,
        JobState.BUILDING,
        JobState.CATCHING_UP,
        JobState.VALIDATING,
        JobState.PROMOTING,
        JobState.RECONCILING,
        JobState.RECOVERY_REQUIRED,
    }
)
TERMINAL_JOB_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.ROLLED_BACK})

_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.PLANNED: frozenset(
        {JobState.PARSING, JobState.BUILDING, JobState.COMPLETED, JobState.FAILED}
    ),
    JobState.PARSING: frozenset({JobState.READY_TO_WRITE, JobState.BUILDING, JobState.FAILED}),
    JobState.READY_TO_WRITE: frozenset({JobState.WRITING, JobState.BUILDING, JobState.FAILED}),
    JobState.WRITING: frozenset(
        {JobState.RECONCILING, JobState.RECOVERY_REQUIRED, JobState.FAILED}
    ),
    JobState.BUILDING: frozenset({JobState.CATCHING_UP, JobState.VALIDATING, JobState.FAILED}),
    JobState.CATCHING_UP: frozenset({JobState.VALIDATING, JobState.FAILED}),
    JobState.VALIDATING: frozenset({JobState.PROMOTING, JobState.FAILED}),
    JobState.PROMOTING: frozenset(
        {JobState.RECONCILING, JobState.RECOVERY_REQUIRED, JobState.ROLLED_BACK}
    ),
    JobState.RECONCILING: frozenset(
        {JobState.COMPLETED, JobState.RECOVERY_REQUIRED, JobState.FAILED}
    ),
    JobState.RECOVERY_REQUIRED: frozenset(
        {
            JobState.PARSING,
            JobState.BUILDING,
            JobState.PROMOTING,
            JobState.RECONCILING,
            JobState.COMPLETED,
            JobState.FAILED,
            JobState.ROLLED_BACK,
        }
    ),
    JobState.COMPLETED: frozenset(),
    JobState.FAILED: frozenset(),
    JobState.ROLLED_BACK: frozenset(),
}

_INTENT_TRANSITIONS: dict[RecoveryIntentState, frozenset[RecoveryIntentState]] = {
    RecoveryIntentState.PREPARED: frozenset(
        {
            RecoveryIntentState.POINTER_WRITTEN,
            RecoveryIntentState.ROLLED_BACK,
            RecoveryIntentState.FAILED,
        }
    ),
    RecoveryIntentState.POINTER_WRITTEN: frozenset(
        {
            RecoveryIntentState.VERIFIED,
            RecoveryIntentState.ROLLED_BACK,
            RecoveryIntentState.FAILED,
        }
    ),
    RecoveryIntentState.VERIFIED: frozenset(
        {RecoveryIntentState.RECONCILED, RecoveryIntentState.FAILED}
    ),
    RecoveryIntentState.RECONCILED: frozenset(),
    RecoveryIntentState.ROLLED_BACK: frozenset(),
    RecoveryIntentState.FAILED: frozenset(),
}


@dataclass(frozen=True)
class WorkerIdentity:
    pid: int
    start_token: str

    def __post_init__(self) -> None:
        if self.pid <= 0 or not self.start_token:
            raise ValueError("worker identity requires a positive PID and start token")


@dataclass(frozen=True)
class JobRequest:
    operation_id: str
    request_sha256: str
    compatibility_key: str
    parent_publication_id: str | None
    operation_class: OperationClass


@dataclass(frozen=True)
class JobProgress:
    numerator: int
    denominator: int
    basis: str

    def __post_init__(self) -> None:
        if self.numerator < 0 or self.denominator < 0:
            raise ValueError("progress values cannot be negative")
        if self.numerator > self.denominator:
            raise ValueError("progress numerator cannot exceed denominator")
        if not self.basis:
            raise ValueError("progress basis cannot be empty")


@dataclass(frozen=True)
class JobSnapshot:
    operation_id: str
    request_sha256: str
    compatibility_key: str
    parent_publication_id: str | None
    operation_class: OperationClass
    state: JobState
    stage: str
    created_at_us: int
    updated_at_us: int
    progress: JobProgress | None
    worker: WorkerIdentity | None
    heartbeat_at_us: int | None
    candidate_artifact_name: str | None
    candidate_artifact_sha256: str | None
    terminal_publication_id: str | None
    error_code: str | None
    error_detail: str | None


@dataclass(frozen=True)
class StartJobResult:
    job: JobSnapshot
    joined: bool


@dataclass(frozen=True)
class LeaseSnapshot:
    lease_name: LeaseName
    operation_id: str
    owner_nonce: str
    fencing_token: int
    worker: WorkerIdentity
    acquired_at_us: int
    heartbeat_at_us: int
    expires_at_us: int


@dataclass(frozen=True)
class ArtifactPointerRecord:
    pointer_generation: int
    pointer_role: str
    artifact_name: str
    publication_id: str
    artifact_manifest_sha256: str
    file_sha256: str | None
    schema_contract_sha256: str
    owner_operation_id: str
    activated_at_us: int


@dataclass(frozen=True)
class RecoveryIntent:
    recovery_id: str
    operation_id: str
    expected_pointer_generation: int
    target_pointer_generation: int
    expected_active_publication_id: str | None
    candidate_publication_id: str
    candidate_artifact_name: str
    candidate_artifact_sha256: str
    state: RecoveryIntentState
    created_at_us: int
    updated_at_us: int
    error_code: str | None


@dataclass(frozen=True)
class DirtyHint:
    source_id: str
    technical_path_key: str
    first_observed_at_us: int
    last_observed_at_us: int
    observation_count: int
    reason_mask: int


@dataclass(frozen=True)
class OperationalStatus:
    active_jobs: tuple[JobSnapshot, ...]
    leases: tuple[LeaseSnapshot, ...]
    pending_intents: tuple[RecoveryIntent, ...]
    pointers: tuple[ArtifactPointerRecord, ...]
    dirty_hints: tuple[DirtyHint, ...]
    truncated: bool


def _job_from_row(row: sqlite3.Row) -> JobSnapshot:
    progress = None
    values = (row["progress_numerator"], row["progress_denominator"], row["progress_basis"])
    if any(value is not None for value in values):
        if any(value is None for value in values):
            raise OperationalStateError("stored job has incoherent progress")
        progress = JobProgress(int(values[0]), int(values[1]), str(values[2]))
    worker = None
    if row["worker_pid"] is not None:
        worker = WorkerIdentity(int(row["worker_pid"]), str(row["worker_start_token"]))
    return JobSnapshot(
        operation_id=str(row["operation_id"]),
        request_sha256=str(row["request_sha256"]),
        compatibility_key=str(row["compatibility_key"]),
        parent_publication_id=row["parent_publication_id"],
        operation_class=OperationClass(row["operation_class"]),
        state=JobState(row["state"]),
        stage=str(row["stage"]),
        created_at_us=int(row["created_at_us"]),
        updated_at_us=int(row["updated_at_us"]),
        progress=progress,
        worker=worker,
        heartbeat_at_us=row["heartbeat_at_us"],
        candidate_artifact_name=row["candidate_artifact_name"],
        candidate_artifact_sha256=row["candidate_artifact_sha256"],
        terminal_publication_id=row["terminal_publication_id"],
        error_code=row["error_code"],
        error_detail=row["error_detail"],
    )


def _lease_from_row(row: sqlite3.Row) -> LeaseSnapshot:
    return LeaseSnapshot(
        lease_name=LeaseName(row["lease_name"]),
        operation_id=str(row["operation_id"]),
        owner_nonce=str(row["owner_nonce"]),
        fencing_token=int(row["fencing_token"]),
        worker=WorkerIdentity(int(row["worker_pid"]), str(row["worker_start_token"])),
        acquired_at_us=int(row["acquired_at_us"]),
        heartbeat_at_us=int(row["heartbeat_at_us"]),
        expires_at_us=int(row["expires_at_us"]),
    )


def _intent_from_row(row: sqlite3.Row) -> RecoveryIntent:
    return RecoveryIntent(
        recovery_id=str(row["recovery_id"]),
        operation_id=str(row["operation_id"]),
        expected_pointer_generation=int(row["expected_pointer_generation"]),
        target_pointer_generation=int(row["target_pointer_generation"]),
        expected_active_publication_id=row["expected_active_publication_id"],
        candidate_publication_id=str(row["candidate_publication_id"]),
        candidate_artifact_name=str(row["candidate_artifact_name"]),
        candidate_artifact_sha256=str(row["candidate_artifact_sha256"]),
        state=RecoveryIntentState(row["state"]),
        created_at_us=int(row["created_at_us"]),
        updated_at_us=int(row["updated_at_us"]),
        error_code=row["error_code"],
    )


def _pointer_from_row(row: sqlite3.Row) -> ArtifactPointerRecord:
    return ArtifactPointerRecord(
        pointer_generation=int(row["pointer_generation"]),
        pointer_role=str(row["pointer_role"]),
        artifact_name=str(row["artifact_name"]),
        publication_id=str(row["publication_id"]),
        artifact_manifest_sha256=str(row["artifact_manifest_sha256"]),
        file_sha256=row["file_sha256"],
        schema_contract_sha256=str(row["schema_contract_sha256"]),
        owner_operation_id=str(row["owner_operation_id"]),
        activated_at_us=int(row["activated_at_us"]),
    )


def _pointer_reconciliation_identity(pointer: ArtifactPointerRecord) -> tuple[object, ...]:
    return (
        pointer.pointer_generation,
        pointer.pointer_role,
        pointer.artifact_name,
        pointer.publication_id,
        pointer.artifact_manifest_sha256,
        pointer.file_sha256,
        pointer.schema_contract_sha256,
        pointer.owner_operation_id,
    )


def _expected_job_states(
    expected: JobState | frozenset[JobState],
) -> frozenset[JobState]:
    return frozenset({expected}) if isinstance(expected, JobState) else expected


def _validate_transition_request(stage: str, error_detail: str | None) -> None:
    if not stage:
        raise ValueError("stage cannot be empty")
    if error_detail is not None and len(error_detail) > 1024:
        raise ValueError("error detail exceeds the bounded structural limit")


def _validate_state_transition(
    current: JobSnapshot,
    *,
    expected_states: frozenset[JobState],
    state: JobState,
    now_us: int,
) -> None:
    if current.state not in expected_states:
        raise OperationalStateError(
            f"expected {sorted(item.value for item in expected_states)}, "
            f"found {current.state.value}"
        )
    if state not in _TRANSITIONS[current.state]:
        raise OperationalStateError(
            f"invalid job transition: {current.state.value} -> {state.value}"
        )
    if now_us < current.updated_at_us:
        raise OperationalStateError("job update time cannot move backwards")


def _validate_progress_transition(current: JobSnapshot, progress: JobProgress | None) -> None:
    if progress is None or current.progress is None or progress.basis != current.progress.basis:
        return
    if progress.denominator != current.progress.denominator:
        raise OperationalStateError("progress denominator changed for one basis")
    if progress.numerator < current.progress.numerator:
        raise OperationalStateError("progress numerator moved backwards")


def _validate_terminal_transition(
    state: JobState,
    *,
    terminal_publication_id: str | None,
    error_code: str | None,
) -> None:
    if state is JobState.COMPLETED and not terminal_publication_id:
        raise OperationalStateError("completed jobs require a terminal publication")
    if state in {JobState.FAILED, JobState.ROLLED_BACK} and not error_code:
        raise OperationalStateError("failed or rolled-back jobs require an error code")


def _progress_columns(
    progress: JobProgress | None,
) -> tuple[int | None, int | None, str | None]:
    if progress is None:
        return None, None, None
    return progress.numerator, progress.denominator, progress.basis


def _worker_columns(
    worker: WorkerIdentity | None, now_us: int
) -> tuple[int | None, str | None, int | None]:
    if worker is None:
        return None, None, None
    return worker.pid, worker.start_token, now_us


class OperationalStore:
    """Bounded state-machine operations over one validated sidecar connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @contextmanager
    def _immediate(self) -> Iterator[None]:
        if self._connection.in_transaction:
            raise OperationalStateError("operational mutation cannot nest a transaction")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def job(self, operation_id: str) -> JobSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM operation_jobs WHERE operation_id = ?", (operation_id,)
        ).fetchone()
        return None if row is None else _job_from_row(row)

    def start_or_join(self, request: JobRequest, *, now_us: int) -> StartJobResult:
        if not request.operation_id or not request.compatibility_key:
            raise ValueError("operation and compatibility identifiers cannot be empty")
        with self._immediate():
            active = self._connection.execute(
                "SELECT * FROM operation_jobs WHERE compatibility_key = ? "
                "AND state IN ('planned','parsing','ready_to_write','writing','building',"
                "'catching_up','validating','promoting','reconciling','recovery_required')",
                (request.compatibility_key,),
            ).fetchone()
            if active is not None:
                job = _job_from_row(active)
                if (
                    job.request_sha256 != request.request_sha256
                    or job.operation_class != request.operation_class
                    or job.parent_publication_id != request.parent_publication_id
                ):
                    raise CompatibilityConflictError(
                        f"compatibility key is occupied by operation {job.operation_id}"
                    )
                return StartJobResult(job, joined=True)
            self._connection.execute(
                "INSERT INTO operation_jobs("
                "operation_id, request_sha256, compatibility_key, parent_publication_id, "
                "operation_class, state, stage, created_at_us, updated_at_us"
                ") VALUES (?, ?, ?, ?, ?, 'planned', 'planned', ?, ?)",
                (
                    request.operation_id,
                    request.request_sha256,
                    request.compatibility_key,
                    request.parent_publication_id,
                    request.operation_class.value,
                    now_us,
                    now_us,
                ),
            )
            created = self.job(request.operation_id)
            assert created is not None
            return StartJobResult(created, joined=False)

    def transition(
        self,
        operation_id: str,
        *,
        expected: JobState | frozenset[JobState],
        state: JobState,
        stage: str,
        now_us: int,
        progress: JobProgress | None = None,
        worker: WorkerIdentity | None = None,
        candidate_artifact_name: str | None = None,
        candidate_artifact_sha256: str | None = None,
        terminal_publication_id: str | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> JobSnapshot:
        expected_states = _expected_job_states(expected)
        _validate_transition_request(stage, error_detail)
        with self._immediate():
            current = self.job(operation_id)
            if current is None:
                raise OperationalStateError(f"unknown operation: {operation_id}")
            _validate_state_transition(
                current,
                expected_states=expected_states,
                state=state,
                now_us=now_us,
            )
            _validate_progress_transition(current, progress)
            _validate_terminal_transition(
                state,
                terminal_publication_id=terminal_publication_id,
                error_code=error_code,
            )
            progress_numerator, progress_denominator, progress_basis = _progress_columns(progress)
            worker_pid, worker_start_token, heartbeat_at_us = _worker_columns(worker, now_us)
            self._connection.execute(
                "UPDATE operation_jobs SET state = ?, stage = ?, updated_at_us = ?, "
                "progress_numerator = ?, progress_denominator = ?, progress_basis = ?, "
                "worker_pid = ?, worker_start_token = ?, heartbeat_at_us = ?, "
                "candidate_artifact_name = COALESCE(?, candidate_artifact_name), "
                "candidate_artifact_sha256 = COALESCE(?, candidate_artifact_sha256), "
                "terminal_publication_id = ?, error_code = ?, error_detail = ? "
                "WHERE operation_id = ?",
                (
                    state.value,
                    stage,
                    now_us,
                    progress_numerator,
                    progress_denominator,
                    progress_basis,
                    worker_pid,
                    worker_start_token,
                    heartbeat_at_us,
                    candidate_artifact_name,
                    candidate_artifact_sha256,
                    terminal_publication_id,
                    error_code,
                    error_detail,
                    operation_id,
                ),
            )
            updated = self.job(operation_id)
            assert updated is not None
            return updated

    def force_terminal(
        self,
        operation_id: str,
        *,
        state: JobState,
        stage: str,
        now_us: int,
        terminal_publication_id: str | None = None,
        error_code: str | None = None,
    ) -> JobSnapshot:
        if state not in TERMINAL_JOB_STATES:
            raise ValueError("force_terminal accepts terminal states only")
        current = self.job(operation_id)
        if current is None:
            raise OperationalStateError(f"unknown operation: {operation_id}")
        if current.state in TERMINAL_JOB_STATES:
            return current
        if now_us < current.updated_at_us:
            raise OperationalStateError("job terminal time cannot move backwards")
        if state is JobState.COMPLETED and not terminal_publication_id:
            raise OperationalStateError("completed jobs require a terminal publication")
        if state in {JobState.FAILED, JobState.ROLLED_BACK} and not error_code:
            raise OperationalStateError("failed or rolled-back jobs require an error code")
        with self._immediate():
            self._connection.execute(
                "UPDATE operation_jobs SET state = ?, stage = ?, updated_at_us = ?, "
                "worker_pid = NULL, worker_start_token = NULL, heartbeat_at_us = NULL, "
                "terminal_publication_id = ?, error_code = ? "
                "WHERE operation_id = ? AND state NOT IN ('completed','failed','rolled_back')",
                (
                    state.value,
                    stage,
                    now_us,
                    terminal_publication_id,
                    error_code,
                    operation_id,
                ),
            )
            updated = self.job(operation_id)
            assert updated is not None
            return updated

    def _next_fencing_token(self, lease_name: LeaseName) -> int:
        key = f"lease_fencing_token:{lease_name.value}"
        row = self._connection.execute(
            "SELECT value FROM operational_metadata WHERE key = ?", (key,)
        ).fetchone()
        token = 1 if row is None else int(row["value"]) + 1
        self._connection.execute(
            "INSERT INTO operational_metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(token)),
        )
        return token

    def acquire_lease(
        self,
        lease_name: LeaseName,
        *,
        operation_id: str,
        owner_nonce: str,
        worker: WorkerIdentity,
        now_us: int,
        ttl_us: int,
        worker_is_alive: WorkerProbe,
    ) -> LeaseSnapshot:
        if not owner_nonce or ttl_us <= 0:
            raise ValueError("lease owner nonce and positive TTL are required")
        with self._immediate():
            row = self._connection.execute(
                "SELECT * FROM writer_leases WHERE lease_name = ?", (lease_name.value,)
            ).fetchone()
            if row is not None:
                current = _lease_from_row(row)
                same_owner = (
                    current.operation_id == operation_id
                    and current.owner_nonce == owner_nonce
                    and current.worker == worker
                )
                stale = current.expires_at_us <= now_us or not worker_is_alive(
                    current.worker.pid, current.worker.start_token
                )
                if same_owner and not stale:
                    self._connection.execute(
                        "UPDATE writer_leases SET heartbeat_at_us = ?, expires_at_us = ? "
                        "WHERE lease_name = ?",
                        (now_us, now_us + ttl_us, lease_name.value),
                    )
                    renewed = self._connection.execute(
                        "SELECT * FROM writer_leases WHERE lease_name = ?", (lease_name.value,)
                    ).fetchone()
                    assert renewed is not None
                    return _lease_from_row(renewed)
                if not stale:
                    raise LeaseConflictError(
                        f"{lease_name.value} held by operation {current.operation_id}"
                    )
                self._connection.execute(
                    "UPDATE operation_jobs SET state = 'recovery_required', "
                    "stage = 'stale_lease_recovered', updated_at_us = ?, "
                    "worker_pid = NULL, worker_start_token = NULL, heartbeat_at_us = NULL, "
                    "error_code = 'stale_lease' "
                    "WHERE operation_id = ? AND state NOT IN ('completed','failed','rolled_back')",
                    (now_us, current.operation_id),
                )
                self._connection.execute(
                    "DELETE FROM writer_leases WHERE lease_name = ?", (lease_name.value,)
                )
            fencing_token = self._next_fencing_token(lease_name)
            self._connection.execute(
                "INSERT INTO writer_leases("
                "lease_name, operation_id, owner_nonce, fencing_token, worker_pid, "
                "worker_start_token, acquired_at_us, heartbeat_at_us, expires_at_us"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lease_name.value,
                    operation_id,
                    owner_nonce,
                    fencing_token,
                    worker.pid,
                    worker.start_token,
                    now_us,
                    now_us,
                    now_us + ttl_us,
                ),
            )
            acquired = self._connection.execute(
                "SELECT * FROM writer_leases WHERE lease_name = ?", (lease_name.value,)
            ).fetchone()
            assert acquired is not None
            return _lease_from_row(acquired)

    def release_lease(self, lease: LeaseSnapshot) -> None:
        with self._immediate():
            cursor = self._connection.execute(
                "DELETE FROM writer_leases WHERE lease_name = ? AND operation_id = ? "
                "AND owner_nonce = ? AND fencing_token = ? AND worker_pid = ? "
                "AND worker_start_token = ?",
                (
                    lease.lease_name.value,
                    lease.operation_id,
                    lease.owner_nonce,
                    lease.fencing_token,
                    lease.worker.pid,
                    lease.worker.start_token,
                ),
            )
            if cursor.rowcount != 1:
                raise LeaseFenceError("lease release rejected by fencing evidence")

    def validate_lease(self, lease: LeaseSnapshot, *, now_us: int) -> None:
        row = self._connection.execute(
            "SELECT * FROM writer_leases WHERE lease_name = ?", (lease.lease_name.value,)
        ).fetchone()
        if row is None:
            raise LeaseFenceError("lease no longer exists")
        current = _lease_from_row(row)
        if (
            current.operation_id != lease.operation_id
            or current.owner_nonce != lease.owner_nonce
            or current.fencing_token != lease.fencing_token
            or current.worker != lease.worker
            or current.expires_at_us <= now_us
        ):
            raise LeaseFenceError("lease validation rejected stale fencing evidence")

    def heartbeat_job(
        self,
        operation_id: str,
        *,
        worker: WorkerIdentity,
        now_us: int,
    ) -> JobSnapshot:
        """Refresh active ownership without changing stage or progress."""

        with self._immediate():
            current = self.job(operation_id)
            if current is None:
                raise OperationalStateError(f"unknown operation: {operation_id}")
            if current.state not in ACTIVE_JOB_STATES or current.worker != worker:
                raise OperationalStateError("job heartbeat rejected stale ownership evidence")
            if current.heartbeat_at_us is not None and now_us < current.heartbeat_at_us:
                raise OperationalStateError("job heartbeat cannot move backwards")
            self._connection.execute(
                "UPDATE operation_jobs SET heartbeat_at_us = ? WHERE operation_id = ?",
                (now_us, operation_id),
            )
            updated = self.job(operation_id)
            assert updated is not None
            return updated

    def add_dirty_hint(
        self,
        *,
        source_id: str,
        technical_path_key: str,
        observed_at_us: int,
        reasons: DirtyReason,
    ) -> DirtyHint:
        if not source_id or not technical_path_key or int(reasons) <= 0:
            raise ValueError("dirty hint requires composite identity and reasons")
        with self._connection:
            self._connection.execute(
                "INSERT INTO source_dirty_hints("
                "source_id, technical_path_key, first_observed_at_us, last_observed_at_us, "
                "observation_count, reason_mask"
                ") VALUES (?, ?, ?, ?, 1, ?) "
                "ON CONFLICT(source_id, technical_path_key) DO UPDATE SET "
                "first_observed_at_us = min(first_observed_at_us, excluded.first_observed_at_us), "
                "last_observed_at_us = max(last_observed_at_us, excluded.last_observed_at_us), "
                "observation_count = observation_count + 1, "
                "reason_mask = reason_mask | excluded.reason_mask",
                (
                    source_id,
                    technical_path_key,
                    observed_at_us,
                    observed_at_us,
                    int(reasons),
                ),
            )
        row = self._connection.execute(
            "SELECT * FROM source_dirty_hints WHERE source_id = ? AND technical_path_key = ?",
            (source_id, technical_path_key),
        ).fetchone()
        assert row is not None
        return DirtyHint(*tuple(row))

    def create_recovery_intent(self, intent: RecoveryIntent) -> None:
        if intent.state is not RecoveryIntentState.PREPARED:
            raise ValueError("new recovery intents must be prepared")
        with self._connection:
            self._connection.execute(
                "INSERT INTO recovery_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    intent.recovery_id,
                    intent.operation_id,
                    intent.expected_pointer_generation,
                    intent.target_pointer_generation,
                    intent.expected_active_publication_id,
                    intent.candidate_publication_id,
                    intent.candidate_artifact_name,
                    intent.candidate_artifact_sha256,
                    intent.state.value,
                    intent.created_at_us,
                    intent.updated_at_us,
                    intent.error_code,
                ),
            )

    def recovery_intent(self, recovery_id: str) -> RecoveryIntent | None:
        row = self._connection.execute(
            "SELECT * FROM recovery_intents WHERE recovery_id = ?", (recovery_id,)
        ).fetchone()
        return None if row is None else _intent_from_row(row)

    def transition_recovery_intent(
        self,
        recovery_id: str,
        *,
        expected: RecoveryIntentState,
        state: RecoveryIntentState,
        now_us: int,
        error_code: str | None = None,
    ) -> RecoveryIntent:
        if state not in _INTENT_TRANSITIONS[expected]:
            raise OperationalStateError(
                f"invalid recovery transition: {expected.value} -> {state.value}"
            )
        with self._immediate():
            row = self._connection.execute(
                "SELECT * FROM recovery_intents WHERE recovery_id = ?", (recovery_id,)
            ).fetchone()
            if row is None:
                raise OperationalStateError(f"unknown recovery intent: {recovery_id}")
            current = _intent_from_row(row)
            if current.state is not expected:
                raise OperationalStateError(
                    f"expected recovery {expected.value}, found {current.state.value}"
                )
            if now_us < current.updated_at_us:
                raise OperationalStateError("recovery update time cannot move backwards")
            self._connection.execute(
                "UPDATE recovery_intents SET state = ?, updated_at_us = ?, error_code = ? "
                "WHERE recovery_id = ?",
                (state.value, now_us, error_code, recovery_id),
            )
            updated = self._connection.execute(
                "SELECT * FROM recovery_intents WHERE recovery_id = ?", (recovery_id,)
            ).fetchone()
            assert updated is not None
            return _intent_from_row(updated)

    def record_pointer_pair(
        self,
        *,
        active: ArtifactPointerRecord,
        rollback: ArtifactPointerRecord | None,
    ) -> None:
        if active.pointer_role != "active":
            raise ValueError("active record must have the active role")
        if rollback is not None and (
            rollback.pointer_role != "rollback"
            or rollback.pointer_generation != active.pointer_generation
        ):
            raise ValueError("rollback must share the active pointer generation")
        records = (active,) if rollback is None else (active, rollback)
        with self._immediate():
            existing = tuple(
                _pointer_from_row(row)
                for row in self._connection.execute(
                    "SELECT * FROM artifact_pointers WHERE pointer_generation = ? "
                    "ORDER BY pointer_role",
                    (active.pointer_generation,),
                )
            )
            if existing:
                if {_pointer_reconciliation_identity(item) for item in existing} == {
                    _pointer_reconciliation_identity(item) for item in records
                }:
                    return
                raise OperationalStateError("pointer generation already has different records")
            self._connection.executemany(
                "INSERT INTO artifact_pointers VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        item.pointer_generation,
                        item.pointer_role,
                        item.artifact_name,
                        item.publication_id,
                        item.artifact_manifest_sha256,
                        item.file_sha256,
                        item.schema_contract_sha256,
                        item.owner_operation_id,
                        item.activated_at_us,
                    )
                    for item in records
                ],
            )

    def status_snapshot(self, *, limit: int = 100) -> OperationalStatus:
        """Return a read-only bounded coordination snapshot without side effects."""

        if not 1 <= limit <= 1_000:
            raise ValueError("status limit must be between 1 and 1000")
        active_values = tuple(item.value for item in ACTIVE_JOB_STATES)
        placeholders = ",".join("?" for _ in active_values)
        jobs_all = tuple(
            _job_from_row(row)
            for row in self._connection.execute(
                f"SELECT * FROM operation_jobs WHERE state IN ({placeholders}) "
                "ORDER BY updated_at_us, operation_id LIMIT ?",
                (*active_values, limit + 1),
            )
        )
        leases_all = tuple(
            _lease_from_row(row)
            for row in self._connection.execute(
                "SELECT * FROM writer_leases ORDER BY lease_name LIMIT ?", (limit + 1,)
            )
        )
        intents_all = tuple(
            _intent_from_row(row)
            for row in self._connection.execute(
                "SELECT * FROM recovery_intents "
                "WHERE state NOT IN ('reconciled','rolled_back','failed') "
                "ORDER BY updated_at_us, recovery_id LIMIT ?",
                (limit + 1,),
            )
        )
        pointers_all = tuple(
            _pointer_from_row(row)
            for row in self._connection.execute(
                "SELECT * FROM artifact_pointers "
                "ORDER BY pointer_generation DESC, pointer_role LIMIT ?",
                (limit + 1,),
            )
        )
        hints_all = tuple(
            DirtyHint(*tuple(row))
            for row in self._connection.execute(
                "SELECT * FROM source_dirty_hints "
                "ORDER BY last_observed_at_us, source_id, technical_path_key LIMIT ?",
                (limit + 1,),
            )
        )
        groups = (jobs_all, leases_all, intents_all, pointers_all, hints_all)
        truncated = any(len(group) > limit for group in groups)
        return OperationalStatus(
            jobs_all[:limit],
            leases_all[:limit],
            intents_all[:limit],
            pointers_all[:limit],
            hints_all[:limit],
            truncated,
        )

    def active_jobs_page(
        self,
        *,
        limit: int = 100,
        after: tuple[int, str] | None = None,
    ) -> tuple[tuple[JobSnapshot, ...], tuple[int, str] | None]:
        """Page active jobs in stable update/id order for bounded recovery."""

        if not 1 <= limit <= 1_000:
            raise ValueError("recovery page limit must be between 1 and 1000")
        active_values = tuple(item.value for item in ACTIVE_JOB_STATES)
        placeholders = ",".join("?" for _ in active_values)
        cursor_clause = ""
        parameters: tuple[object, ...] = active_values
        if after is not None:
            cursor_clause = "AND (updated_at_us > ? OR (updated_at_us = ? AND operation_id > ?)) "
            parameters = (*parameters, after[0], after[0], after[1])
        rows = tuple(
            _job_from_row(row)
            for row in self._connection.execute(
                f"SELECT * FROM operation_jobs WHERE state IN ({placeholders}) "
                f"{cursor_clause}ORDER BY updated_at_us, operation_id LIMIT ?",
                (*parameters, limit + 1),
            )
        )
        page = rows[:limit]
        next_cursor = (
            (page[-1].updated_at_us, page[-1].operation_id) if len(rows) > limit and page else None
        )
        return page, next_cursor

    def pending_intents_page(
        self,
        *,
        limit: int = 100,
        after: tuple[int, str] | None = None,
    ) -> tuple[tuple[RecoveryIntent, ...], tuple[int, str] | None]:
        """Page unresolved recovery intents without an unbounded status read."""

        if not 1 <= limit <= 1_000:
            raise ValueError("recovery page limit must be between 1 and 1000")
        cursor_clause = ""
        parameters: tuple[object, ...] = ()
        if after is not None:
            cursor_clause = "AND (updated_at_us > ? OR (updated_at_us = ? AND recovery_id > ?)) "
            parameters = (after[0], after[0], after[1])
        rows = tuple(
            _intent_from_row(row)
            for row in self._connection.execute(
                "SELECT * FROM recovery_intents "
                "WHERE state NOT IN ('reconciled','rolled_back','failed') "
                f"{cursor_clause}ORDER BY updated_at_us, recovery_id LIMIT ?",
                (*parameters, limit + 1),
            )
        )
        page = rows[:limit]
        next_cursor = (
            (page[-1].updated_at_us, page[-1].recovery_id) if len(rows) > limit and page else None
        )
        return page, next_cursor

    def wait_for_terminal(
        self,
        operation_id: str,
        *,
        timeout_s: float,
        poll_interval_s: float = 0.05,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> JobSnapshot:
        """Wait inside the host boundary; this is not a model polling API."""

        if timeout_s < 0 or not 0 < poll_interval_s <= 0.25:
            raise ValueError("host wait requires a nonnegative timeout and interval <= 0.25s")
        deadline = monotonic() + timeout_s
        while True:
            job = self.job(operation_id)
            if job is None:
                raise OperationalStateError(f"unknown operation: {operation_id}")
            if job.state in TERMINAL_JOB_STATES:
                return job
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise HostWaitTimeoutError(f"operation did not terminalize: {operation_id}")
            sleeper(min(poll_interval_s, remaining))

    def stale_leases(
        self, *, now_us: int, worker_is_alive: WorkerProbe
    ) -> tuple[LeaseSnapshot, ...]:
        leases = tuple(
            _lease_from_row(row)
            for row in self._connection.execute("SELECT * FROM writer_leases ORDER BY lease_name")
        )
        return tuple(
            lease
            for lease in leases
            if lease.expires_at_us <= now_us
            or not worker_is_alive(lease.worker.pid, lease.worker.start_token)
        )

    def remove_stale_lease(self, lease: LeaseSnapshot) -> None:
        self.release_lease(lease)
