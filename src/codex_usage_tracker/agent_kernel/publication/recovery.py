"""Durable artifact promotion and read-first startup recovery."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from codex_usage_tracker.agent_kernel.storage.operational import (
    ArtifactPointerRecord,
    JobSnapshot,
    JobState,
    LeaseFenceError,
    LeaseName,
    LeaseSnapshot,
    OperationalStatus,
    OperationalStore,
    RecoveryIntent,
    RecoveryIntentState,
    WorkerIdentity,
    WorkerProbe,
)

POINTER_FILENAME = "active-artifact-pointer-v1.json"
POINTER_SCHEMA = "codex-usage-tracker.agent-kernel.artifact-pointer.v1"
FaultHook = Callable[[str], None]
ArtifactValidator = Callable[[Path, "PointerArtifact"], "AnalyticalHead"]
RollbackFinalizer = Callable[[Path, "PointerArtifact"], str]
AnalyticalCommit = Callable[[], "AnalyticalHead"]


class RecoveryError(RuntimeError):
    """Publication recovery could not select or reconcile a valid artifact."""


class PointerValidationError(RecoveryError):
    """The filesystem publication pointer is malformed or inconsistent."""


class PromotionConflictError(RecoveryError):
    """Promotion expectations no longer match the selected publication."""


def _is_lower_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _safe_artifact_name(value: str) -> bool:
    return 1 <= len(value) <= 255 and "/" not in value and "\\" not in value and ".." not in value


@dataclass(frozen=True)
class PointerArtifact:
    artifact_name: str
    artifact_manifest_sha256: str
    file_sha256: str | None
    publication_id: str
    schema_contract_sha256: str

    def __post_init__(self) -> None:
        if not _safe_artifact_name(self.artifact_name):
            raise PointerValidationError("artifact name is not a safe basename")
        for field_name, value in (
            ("artifact manifest", self.artifact_manifest_sha256),
            ("schema contract", self.schema_contract_sha256),
        ):
            if not _is_lower_sha256(value):
                raise PointerValidationError(f"{field_name} digest is not lowercase SHA-256")
        if self.file_sha256 is not None and not _is_lower_sha256(self.file_sha256):
            raise PointerValidationError("file digest is not lowercase SHA-256")
        if not self.publication_id:
            raise PointerValidationError("publication identity cannot be empty")

    def as_json(self) -> dict[str, str | None]:
        return {
            "artifact_name": self.artifact_name,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "file_sha256": self.file_sha256,
            "publication_id": self.publication_id,
            "schema_contract_sha256": self.schema_contract_sha256,
        }


@dataclass(frozen=True)
class PointerDocument:
    active: PointerArtifact
    generation: int
    rollback: PointerArtifact | None
    written_at_us: int
    schema: str = POINTER_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != POINTER_SCHEMA:
            raise PointerValidationError("unsupported artifact-pointer schema")
        if self.generation <= 0:
            raise PointerValidationError("pointer generation must be positive")
        if self.written_at_us < 0:
            raise PointerValidationError("pointer write time cannot be negative")
        if self.rollback is not None and self.rollback.file_sha256 is None:
            raise PointerValidationError("rollback artifact requires a finalized file digest")

    def canonical_bytes(self) -> bytes:
        payload = {
            "active": self.active.as_json(),
            "generation": self.generation,
            "rollback": None if self.rollback is None else self.rollback.as_json(),
            "schema": self.schema,
            "written_at_us": self.written_at_us,
        }
        return (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
        ).encode("utf-8")


@dataclass(frozen=True)
class AnalyticalHead:
    publication_id: str
    parent_publication_id: str | None
    operation_id: str
    artifact_manifest_sha256: str
    schema_contract_sha256: str


@dataclass(frozen=True)
class ReadSelection:
    pointer: PointerDocument
    selected: PointerArtifact
    head: AnalyticalHead
    role: str
    pointer_repair_required: bool


@dataclass(frozen=True)
class PromotionRequest:
    recovery_id: str
    operation_id: str
    expected_pointer_generation: int
    expected_active_publication_id: str | None
    candidate: PointerArtifact
    owner_nonce: str
    worker: WorkerIdentity
    now_us: int
    lease_ttl_us: int


@dataclass(frozen=True)
class PromotionResult:
    pointer: PointerDocument
    head: AnalyticalHead
    fencing_token: int


@dataclass(frozen=True)
class SmallPublicationRequest:
    operation_id: str
    expected_pointer_generation: int
    expected_active_publication_id: str
    expected_artifact_name: str
    owner_nonce: str
    worker: WorkerIdentity
    now_us: int
    lease_ttl_us: int


@dataclass(frozen=True)
class SmallPublicationResult:
    pointer: PointerDocument
    head: AnalyticalHead
    fencing_token: int


@dataclass(frozen=True)
class StartupRecoveryReport:
    selection: ReadSelection
    repaired_pointer: bool
    completed_operations: tuple[str, ...]
    failed_operations: tuple[str, ...]
    reconciled_intents: tuple[str, ...]
    removed_leases: tuple[str, ...]


def _artifact_from_json(value: Any, *, field: str) -> PointerArtifact:
    if not isinstance(value, dict):
        raise PointerValidationError(f"{field} pointer must be an object")
    expected = {
        "artifact_name",
        "artifact_manifest_sha256",
        "file_sha256",
        "publication_id",
        "schema_contract_sha256",
    }
    if set(value) != expected:
        raise PointerValidationError(f"{field} pointer fields differ from the contract")
    if any(item is not None and not isinstance(item, str) for item in value.values()):
        raise PointerValidationError(f"{field} pointer values must be strings or null")
    return PointerArtifact(**value)


def parse_pointer(payload: bytes) -> PointerDocument:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PointerValidationError("artifact pointer is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise PointerValidationError("artifact pointer root must be an object")
    if set(value) != {"active", "generation", "rollback", "schema", "written_at_us"}:
        raise PointerValidationError("artifact pointer fields differ from the contract")
    active = _artifact_from_json(value["active"], field="active")
    rollback_value = value["rollback"]
    rollback = (
        None if rollback_value is None else _artifact_from_json(rollback_value, field="rollback")
    )
    if isinstance(value["generation"], bool) or not isinstance(value["generation"], int):
        raise PointerValidationError("pointer generation must be an integer")
    if isinstance(value["written_at_us"], bool) or not isinstance(value["written_at_us"], int):
        raise PointerValidationError("pointer write time must be an integer")
    if not isinstance(value["schema"], str):
        raise PointerValidationError("pointer schema must be a string")
    document = PointerDocument(
        active=active,
        generation=value["generation"],
        rollback=rollback,
        schema=value["schema"],
        written_at_us=value["written_at_us"],
    )
    if document.canonical_bytes() != payload:
        raise PointerValidationError("artifact pointer is not canonical JSON")
    return document


def _verify_owner_directory(path: Path) -> None:
    if path.is_symlink():
        raise PointerValidationError("pointer directory cannot be a symlink")
    info = path.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise PointerValidationError("pointer directory must be owner-owned with mode 0700")


def read_pointer(path: Path) -> PointerDocument:
    path = Path(path)
    _verify_owner_directory(path.parent)
    if path.is_symlink():
        raise PointerValidationError("artifact pointer cannot be a symlink")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise PointerValidationError("artifact pointer must be an owner-owned regular file")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PointerValidationError("artifact pointer permissions must be 0600")
    return parse_pointer(path.read_bytes())


def _verify_owner_artifact(path: Path) -> None:
    if path.is_symlink():
        raise PointerValidationError(f"artifact cannot be a symlink: {path.name}")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise PointerValidationError(f"artifact must be an owner-owned regular file: {path.name}")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PointerValidationError(f"artifact permissions must be 0600: {path.name}")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file_and_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_descriptor = os.open(path.parent, flags)
    try:
        os.fsync(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _validate_file_digest(owner_directory: Path, artifact: PointerArtifact) -> Path:
    path = owner_directory / artifact.artifact_name
    _verify_owner_artifact(path)
    if artifact.file_sha256 is not None and _file_sha256(path) != artifact.file_sha256:
        raise PointerValidationError(f"artifact file digest differs: {artifact.artifact_name}")
    return path


def write_pointer_durable(
    path: Path,
    pointer: PointerDocument,
    *,
    fault: FaultHook | None = None,
) -> None:
    """Durably replace one canonical pointer in its owner-only directory."""

    path = Path(path)
    directory = path.parent
    _verify_owner_directory(directory)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=directory
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(pointer.canonical_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        if fault is not None:
            fault("before_pointer_replace")
        os.replace(temporary_path, path)
        if fault is not None:
            fault("after_pointer_replace")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(directory, flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        if fault is not None:
            fault("after_directory_fsync")
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _validate_head(artifact: PointerArtifact, head: AnalyticalHead) -> None:
    if artifact.schema_contract_sha256 != head.schema_contract_sha256:
        raise PointerValidationError("artifact schema digest differs from its analytical head")
    if artifact.publication_id == head.publication_id:
        if artifact.artifact_manifest_sha256 != head.artifact_manifest_sha256:
            raise PointerValidationError("artifact manifest differs from its analytical head")
        return
    if head.parent_publication_id != artifact.publication_id:
        raise PointerValidationError("pointer publication does not match a recoverable head")


def select_readable_artifact(
    pointer_path: Path,
    *,
    validate_open: ArtifactValidator,
) -> ReadSelection:
    """Open analytical reads before any sidecar is inspected or repaired."""

    pointer = read_pointer(pointer_path)
    failures: list[str] = []
    for role, artifact in (("active", pointer.active), ("rollback", pointer.rollback)):
        if artifact is None:
            continue
        try:
            artifact_path = pointer_path.parent / artifact.artifact_name
            _verify_owner_artifact(artifact_path)
            file_digest_matches = (
                artifact.file_sha256 is None or _file_sha256(artifact_path) == artifact.file_sha256
            )
            if role == "rollback" and not file_digest_matches:
                raise PointerValidationError("rollback artifact file digest differs")
            head = validate_open(artifact_path, artifact)
            _validate_head(artifact, head)
            repair = role == "active" and artifact.publication_id != head.publication_id
            if not file_digest_matches and not repair:
                raise PointerValidationError("active artifact file digest differs")
            return ReadSelection(pointer, artifact, head, role, repair)
        except Exception as error:
            failures.append(f"{role}:{type(error).__name__}")
    raise RecoveryError(f"no readable artifact pointer pair ({', '.join(failures)})")


def _intent_for_promotion(request: PromotionRequest) -> RecoveryIntent:
    if request.candidate.file_sha256 is None:
        raise PointerValidationError("isolated candidate requires a finalized file digest")
    return RecoveryIntent(
        recovery_id=request.recovery_id,
        operation_id=request.operation_id,
        expected_pointer_generation=request.expected_pointer_generation,
        target_pointer_generation=request.expected_pointer_generation + 1,
        expected_active_publication_id=request.expected_active_publication_id,
        candidate_publication_id=request.candidate.publication_id,
        candidate_artifact_name=request.candidate.artifact_name,
        candidate_artifact_sha256=request.candidate.file_sha256,
        state=RecoveryIntentState.PREPARED,
        created_at_us=request.now_us,
        updated_at_us=request.now_us,
        error_code=None,
    )


def _intent_matches_promotion(intent: RecoveryIntent, request: PromotionRequest) -> bool:
    candidate_file_sha256 = request.candidate.file_sha256
    return (
        candidate_file_sha256 is not None
        and intent.operation_id == request.operation_id
        and intent.expected_pointer_generation == request.expected_pointer_generation
        and intent.target_pointer_generation == request.expected_pointer_generation + 1
        and intent.expected_active_publication_id == request.expected_active_publication_id
        and intent.candidate_publication_id == request.candidate.publication_id
        and intent.candidate_artifact_name == request.candidate.artifact_name
        and intent.candidate_artifact_sha256 == candidate_file_sha256
        and intent.state is RecoveryIntentState.PREPARED
        and intent.error_code is None
    )


def promote_isolated_artifact(
    pointer_path: Path,
    *,
    store: OperationalStore,
    request: PromotionRequest,
    worker_is_alive: WorkerProbe,
    validate_open: ArtifactValidator,
    finalize_rollback: RollbackFinalizer,
    fault: FaultHook | None = None,
) -> PromotionResult:
    """Promote a finalized artifact through a fenced, crash-recoverable intent."""

    if request.candidate.file_sha256 is None:
        raise PointerValidationError("isolated candidate requires a finalized file digest")
    if request.expected_pointer_generation < 0:
        raise PromotionConflictError("expected pointer generation cannot be negative")
    writer_lease = store.acquire_lease(
        LeaseName.ANALYTICAL_WRITER,
        operation_id=request.operation_id,
        owner_nonce=request.owner_nonce,
        worker=request.worker,
        now_us=request.now_us,
        ttl_us=request.lease_ttl_us,
        worker_is_alive=worker_is_alive,
    )
    promotion_lease = None
    try:
        promotion_lease = store.acquire_lease(
            LeaseName.ARTIFACT_PROMOTION,
            operation_id=request.operation_id,
            owner_nonce=request.owner_nonce,
            worker=request.worker,
            now_us=request.now_us,
            ttl_us=request.lease_ttl_us,
            worker_is_alive=worker_is_alive,
        )
        result = _promote_isolated_artifact_locked(
            pointer_path,
            store=store,
            request=request,
            validate_open=validate_open,
            finalize_rollback=finalize_rollback,
            writer_lease=writer_lease,
            promotion_lease=promotion_lease,
            fault=fault,
        )
        return result
    finally:
        if promotion_lease is not None:
            with suppress(LeaseFenceError):
                store.release_lease(promotion_lease)
        with suppress(LeaseFenceError):
            store.release_lease(writer_lease)


def _promote_isolated_artifact_locked(
    pointer_path: Path,
    *,
    store: OperationalStore,
    request: PromotionRequest,
    validate_open: ArtifactValidator,
    finalize_rollback: RollbackFinalizer,
    writer_lease: LeaseSnapshot,
    promotion_lease: LeaseSnapshot,
    fault: FaultHook | None,
) -> PromotionResult:
    candidate_path = _validate_file_digest(pointer_path.parent, request.candidate)
    _fsync_file_and_directory(candidate_path)
    if fault is not None:
        # This is the authoritative preflight: it runs after both fences are
        # held, so a candidate cannot pass a hash/fsync check and change before
        # the pointer write.  Avoiding an earlier identical pass keeps the
        # activation bounded without weakening the isolated build validation.
        fault("after_candidate_preflight")
    initial_promotion = (
        request.expected_pointer_generation == 0 and request.expected_active_publication_id is None
    )
    try:
        current = read_pointer(pointer_path)
    except FileNotFoundError as error:
        if not initial_promotion:
            raise PromotionConflictError(
                "artifact pointer is absent for a non-initial promotion"
            ) from error
        current = None
    if current is not None:
        if current.generation != request.expected_pointer_generation:
            raise PromotionConflictError("pointer generation changed before promotion")
        if current.active.publication_id != request.expected_active_publication_id:
            raise PromotionConflictError("active publication changed before promotion")
    existing_intent = store.recovery_intent(request.recovery_id)
    if existing_intent is None:
        store.create_recovery_intent(_intent_for_promotion(request))
    elif not _intent_matches_promotion(existing_intent, request):
        raise PromotionConflictError("recovery identifier belongs to another promotion")
    rollback = None
    if current is not None:
        prior_path = _validate_file_digest(pointer_path.parent, current.active)
        active_head = validate_open(prior_path, current.active)
        _validate_head(current.active, active_head)
        if active_head.publication_id != current.active.publication_id:
            raise PromotionConflictError("analytical head advanced before artifact promotion")
        rollback = (
            current.active
            if current.active.file_sha256 is not None
            else replace(
                current.active,
                file_sha256=finalize_rollback(prior_path, current.active),
            )
        )
        if rollback.file_sha256 is None or not _is_lower_sha256(rollback.file_sha256):
            raise PointerValidationError("rollback finalizer did not return lowercase SHA-256")
        _fsync_file_and_directory(prior_path)
    promoted = PointerDocument(
        active=request.candidate,
        generation=request.expected_pointer_generation + 1,
        rollback=rollback,
        written_at_us=request.now_us,
    )
    store.validate_lease(writer_lease, now_us=request.now_us)
    store.validate_lease(promotion_lease, now_us=request.now_us)
    if fault is not None:
        fault("before_pointer_write")
    write_pointer_durable(pointer_path, promoted, fault=fault)
    store.transition_recovery_intent(
        request.recovery_id,
        expected=RecoveryIntentState.PREPARED,
        state=RecoveryIntentState.POINTER_WRITTEN,
        now_us=request.now_us,
    )
    if fault is not None:
        fault("after_pointer_write")
    head = validate_open(candidate_path, request.candidate)
    _validate_head(request.candidate, head)
    store.transition_recovery_intent(
        request.recovery_id,
        expected=RecoveryIntentState.POINTER_WRITTEN,
        state=RecoveryIntentState.VERIFIED,
        now_us=request.now_us,
    )
    if fault is not None:
        fault("after_reopen_validate")
    store.record_pointer_pair(
        active=ArtifactPointerRecord(
            promoted.generation,
            "active",
            promoted.active.artifact_name,
            promoted.active.publication_id,
            promoted.active.artifact_manifest_sha256,
            promoted.active.file_sha256,
            promoted.active.schema_contract_sha256,
            request.operation_id,
            request.now_us,
        ),
        rollback=(
            None
            if rollback is None
            else ArtifactPointerRecord(
                promoted.generation,
                "rollback",
                rollback.artifact_name,
                rollback.publication_id,
                rollback.artifact_manifest_sha256,
                rollback.file_sha256,
                rollback.schema_contract_sha256,
                request.operation_id,
                request.now_us,
            )
        ),
    )
    store.transition_recovery_intent(
        request.recovery_id,
        expected=RecoveryIntentState.VERIFIED,
        state=RecoveryIntentState.RECONCILED,
        now_us=request.now_us,
    )
    store.force_terminal(
        request.operation_id,
        state=JobState.COMPLETED,
        stage="promotion_reconciled",
        now_us=request.now_us,
        terminal_publication_id=head.publication_id,
    )
    if fault is not None:
        fault("after_sidecar_reconcile")
    return PromotionResult(promoted, head, promotion_lease.fencing_token)


def publish_small_with_pointer(
    pointer_path: Path,
    *,
    store: OperationalStore,
    request: SmallPublicationRequest,
    worker_is_alive: WorkerProbe,
    validate_open: ArtifactValidator,
    commit_analytical: AnalyticalCommit,
    fault: FaultHook | None = None,
) -> SmallPublicationResult:
    """Fence, commit, and reconcile one proven-small in-place publication."""

    lease = store.acquire_lease(
        LeaseName.ANALYTICAL_WRITER,
        operation_id=request.operation_id,
        owner_nonce=request.owner_nonce,
        worker=request.worker,
        now_us=request.now_us,
        ttl_us=request.lease_ttl_us,
        worker_is_alive=worker_is_alive,
    )
    try:
        current = read_pointer(pointer_path)
        if current.generation != request.expected_pointer_generation:
            raise PromotionConflictError("pointer generation changed before small publication")
        if current.active.publication_id != request.expected_active_publication_id:
            raise PromotionConflictError("active publication changed before small publication")
        if current.active.artifact_name != request.expected_artifact_name:
            raise PromotionConflictError("active artifact changed before small publication")
        artifact_path = _validate_file_digest(pointer_path.parent, current.active)
        current_head = validate_open(artifact_path, current.active)
        _validate_head(current.active, current_head)
        if current_head.publication_id != request.expected_active_publication_id:
            raise PromotionConflictError(
                "analytical head already advanced before small publication"
            )

        head = commit_analytical()
        if fault is not None:
            fault("after_small_analytical_commit")
        if (
            head.operation_id != request.operation_id
            or head.parent_publication_id != request.expected_active_publication_id
            or head.publication_id == request.expected_active_publication_id
        ):
            raise PromotionConflictError("committed head is not the expected direct child")
        store.validate_lease(lease, now_us=request.now_us)
        active = PointerArtifact(
            artifact_name=current.active.artifact_name,
            artifact_manifest_sha256=head.artifact_manifest_sha256,
            file_sha256=None,
            publication_id=head.publication_id,
            schema_contract_sha256=head.schema_contract_sha256,
        )
        advanced = PointerDocument(
            active=active,
            generation=current.generation + 1,
            rollback=current.rollback,
            written_at_us=request.now_us,
        )
        write_pointer_durable(pointer_path, advanced, fault=fault)
        if fault is not None:
            fault("after_small_pointer_write")
        rollback = current.rollback
        store.record_pointer_pair(
            active=ArtifactPointerRecord(
                advanced.generation,
                "active",
                active.artifact_name,
                active.publication_id,
                active.artifact_manifest_sha256,
                None,
                active.schema_contract_sha256,
                request.operation_id,
                request.now_us,
            ),
            rollback=(
                None
                if rollback is None
                else ArtifactPointerRecord(
                    advanced.generation,
                    "rollback",
                    rollback.artifact_name,
                    rollback.publication_id,
                    rollback.artifact_manifest_sha256,
                    rollback.file_sha256,
                    rollback.schema_contract_sha256,
                    request.operation_id,
                    request.now_us,
                )
            ),
        )
        store.force_terminal(
            request.operation_id,
            state=JobState.COMPLETED,
            stage="small_publication_reconciled",
            now_us=request.now_us,
            terminal_publication_id=head.publication_id,
        )
        if fault is not None:
            fault("after_small_sidecar_reconcile")
        return SmallPublicationResult(advanced, head, lease.fencing_token)
    finally:
        with suppress(LeaseFenceError):
            store.release_lease(lease)


def protected_artifact_names(pointer: PointerDocument, status: OperationalStatus) -> frozenset[str]:
    """Protect selected pairs and every active candidate with recovery ownership."""

    if status.truncated:
        raise RecoveryError("refusing cleanup protection from a truncated status snapshot")
    names = {pointer.active.artifact_name}
    if pointer.rollback is not None:
        names.add(pointer.rollback.artifact_name)
    names.update(
        job.candidate_artifact_name
        for job in status.active_jobs
        if job.candidate_artifact_name is not None
    )
    names.update(intent.candidate_artifact_name for intent in status.pending_intents)
    return frozenset(names)


def cleanup_owned_artifacts(
    owner_directory: Path,
    *,
    owned_artifact_names: Iterable[str],
    protected_names: frozenset[str],
    now_us: int,
    minimum_age_us: int,
    fault: FaultHook | None = None,
) -> tuple[str, ...]:
    """Delete only explicit, old, owner-only, unprotected unpublished artifacts."""

    if minimum_age_us < 0:
        raise ValueError("cleanup age cannot be negative")
    _verify_owner_directory(owner_directory)
    removed: list[str] = []
    for name in sorted(set(owned_artifact_names)):
        if not _safe_artifact_name(name) or name in protected_names:
            continue
        path = owner_directory / name
        try:
            _verify_owner_artifact(path)
        except (FileNotFoundError, PointerValidationError):
            continue
        age_us = now_us - path.stat().st_mtime_ns // 1_000
        if age_us < minimum_age_us:
            continue
        if fault is not None:
            fault("before_cleanup_unlink")
        path.unlink()
        removed.append(name)
        if fault is not None:
            fault("after_cleanup_unlink")
    if removed:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_descriptor = os.open(owner_directory, flags)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        if fault is not None:
            fault("after_cleanup_directory_fsync")
    return tuple(removed)


def _reconciled_artifact(selection: ReadSelection) -> PointerArtifact:
    return PointerArtifact(
        artifact_name=selection.selected.artifact_name,
        artifact_manifest_sha256=selection.head.artifact_manifest_sha256,
        file_sha256=None,
        publication_id=selection.head.publication_id,
        schema_contract_sha256=selection.head.schema_contract_sha256,
    )


_TERMINAL_JOB_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.ROLLED_BACK})


def _repair_selected_pointer(
    pointer_path: Path,
    selection: ReadSelection,
    *,
    now_us: int,
    fault: FaultHook | None,
) -> tuple[PointerDocument, bool]:
    if not selection.pointer_repair_required:
        return selection.pointer, False
    repaired = PointerDocument(
        active=_reconciled_artifact(selection),
        generation=selection.pointer.generation + 1,
        rollback=selection.pointer.rollback,
        written_at_us=now_us,
    )
    write_pointer_durable(pointer_path, repaired, fault=fault)
    return repaired, True


def _live_lease_operations(
    status: OperationalStatus,
    *,
    now_us: int,
    worker_is_alive: WorkerProbe,
) -> frozenset[str]:
    return frozenset(
        lease.operation_id
        for lease in status.leases
        if lease.expires_at_us > now_us
        and worker_is_alive(lease.worker.pid, lease.worker.start_token)
    )


def _complete_selected_operation(
    store: OperationalStore,
    selection: ReadSelection,
    *,
    now_us: int,
) -> str | None:
    operation_id = selection.head.operation_id
    job = store.job(operation_id)
    if job is None or job.state in _TERMINAL_JOB_STATES:
        return None
    store.force_terminal(
        operation_id,
        state=JobState.COMPLETED,
        stage="startup_analytical_reconciliation",
        now_us=now_us,
        terminal_publication_id=selection.head.publication_id,
    )
    return operation_id


def _intent_candidate_is_selected(
    intent: RecoveryIntent,
    selection: ReadSelection,
    pointer: PointerDocument,
) -> bool:
    return all(
        (
            selection.role == "active",
            intent.candidate_artifact_name == selection.selected.artifact_name,
            intent.candidate_publication_id == selection.head.publication_id,
            intent.target_pointer_generation == pointer.generation,
        )
    )


def _record_selected_pointer(
    store: OperationalStore,
    *,
    pointer: PointerDocument,
    selection: ReadSelection,
    owner_operation_id: str,
    now_us: int,
) -> None:
    selected_pointer = pointer.active
    rollback_pointer = pointer.rollback
    rollback_record = None
    if rollback_pointer is not None:
        rollback_record = ArtifactPointerRecord(
            pointer.generation,
            "rollback",
            rollback_pointer.artifact_name,
            rollback_pointer.publication_id,
            rollback_pointer.artifact_manifest_sha256,
            rollback_pointer.file_sha256,
            rollback_pointer.schema_contract_sha256,
            owner_operation_id,
            now_us,
        )
    store.record_pointer_pair(
        active=ArtifactPointerRecord(
            pointer.generation,
            "active",
            selected_pointer.artifact_name,
            selection.head.publication_id,
            selection.head.artifact_manifest_sha256,
            selected_pointer.file_sha256,
            selection.head.schema_contract_sha256,
            owner_operation_id,
            now_us,
        ),
        rollback=rollback_record,
    )


def _reconcile_selected_intent(
    store: OperationalStore,
    *,
    pointer: PointerDocument,
    selection: ReadSelection,
    intent: RecoveryIntent,
    now_us: int,
) -> None:
    _record_selected_pointer(
        store,
        pointer=pointer,
        selection=selection,
        owner_operation_id=intent.operation_id,
        now_us=now_us,
    )
    current = intent
    recovery_order = (
        RecoveryIntentState.PREPARED,
        RecoveryIntentState.POINTER_WRITTEN,
        RecoveryIntentState.VERIFIED,
        RecoveryIntentState.RECONCILED,
    )
    for target in recovery_order[recovery_order.index(current.state) + 1 :]:
        current = store.transition_recovery_intent(
            current.recovery_id,
            expected=current.state,
            state=target,
            now_us=now_us,
        )


def _recover_pending_intent(
    store: OperationalStore,
    *,
    pointer: PointerDocument,
    selection: ReadSelection,
    intent: RecoveryIntent,
    live_lease_operations: frozenset[str],
    now_us: int,
) -> tuple[str | None, str | None]:
    if _intent_candidate_is_selected(intent, selection, pointer):
        _reconcile_selected_intent(
            store,
            pointer=pointer,
            selection=selection,
            intent=intent,
            now_us=now_us,
        )
        return intent.recovery_id, None
    if intent.operation_id in live_lease_operations:
        return None, None
    terminal_intent_state = (
        RecoveryIntentState.ROLLED_BACK
        if intent.state in {RecoveryIntentState.PREPARED, RecoveryIntentState.POINTER_WRITTEN}
        else RecoveryIntentState.FAILED
    )
    store.transition_recovery_intent(
        intent.recovery_id,
        expected=intent.state,
        state=terminal_intent_state,
        now_us=now_us,
        error_code="candidate_not_selected",
    )
    job = store.job(intent.operation_id)
    if job is None or job.state in _TERMINAL_JOB_STATES:
        return None, None
    store.force_terminal(
        intent.operation_id,
        state=JobState.ROLLED_BACK,
        stage="startup_pointer_rollback",
        now_us=now_us,
        error_code="candidate_not_selected",
    )
    return None, intent.operation_id


def _remove_stale_lease(
    store: OperationalStore,
    lease: LeaseSnapshot,
    *,
    selected_operation: str,
    now_us: int,
) -> str | None:
    store.remove_stale_lease(lease)
    if lease.operation_id == selected_operation:
        return None
    job = store.job(lease.operation_id)
    if job is None or job.state in _TERMINAL_JOB_STATES:
        return None
    store.force_terminal(
        lease.operation_id,
        state=JobState.FAILED,
        stage="startup_stale_worker",
        now_us=now_us,
        error_code="stale_worker",
    )
    return lease.operation_id


def _recover_dead_job_without_lease(
    store: OperationalStore,
    job: JobSnapshot,
    *,
    live_lease_operations: frozenset[str],
    selected_operation: str,
    now_us: int,
    stale_after_us: int,
    worker_is_alive: WorkerProbe,
) -> str | None:
    if (
        job.operation_id == selected_operation
        or job.operation_id in live_lease_operations
        or job.worker is None
    ):
        return None
    heartbeat_stale = (
        job.heartbeat_at_us is None
        or job.heartbeat_at_us > now_us
        or now_us - job.heartbeat_at_us >= stale_after_us
    )
    worker_dead = not worker_is_alive(job.worker.pid, job.worker.start_token)
    if not heartbeat_stale and not worker_dead:
        return None
    store.force_terminal(
        job.operation_id,
        state=JobState.FAILED,
        stage=f"startup_stale_{job.state.value}",
        now_us=now_us,
        error_code=f"stale_{job.state.value}",
    )
    return job.operation_id


def recover_startup(
    pointer_path: Path,
    *,
    selection: ReadSelection,
    store: OperationalStore,
    now_us: int,
    worker_is_alive: WorkerProbe,
    fault: FaultHook | None = None,
    recovery_page_size: int = 100,
    job_stale_after_us: int = 30_000_000,
) -> StartupRecoveryReport:
    """Repair sidecar state only after ``select_readable_artifact`` opened reads."""

    pointer, repaired_pointer = _repair_selected_pointer(
        pointer_path,
        selection,
        now_us=now_us,
        fault=fault,
    )
    completed: list[str] = []
    failed: list[str] = []
    reconciled: list[str] = []
    removed_leases: list[str] = []
    if not 1 <= recovery_page_size <= 1_000:
        raise ValueError("recovery page size must be between 1 and 1000")
    if job_stale_after_us <= 0:
        raise ValueError("job stale interval must be positive")
    status = store.status_snapshot(limit=1_000)
    live_lease_operations = _live_lease_operations(
        status,
        now_us=now_us,
        worker_is_alive=worker_is_alive,
    )

    selected_operation = selection.head.operation_id
    completed_operation = _complete_selected_operation(store, selection, now_us=now_us)
    if completed_operation is not None:
        _record_selected_pointer(
            store,
            pointer=pointer,
            selection=selection,
            owner_operation_id=completed_operation,
            now_us=now_us,
        )
        completed.append(completed_operation)

    intent_cursor = None
    while True:
        intents, next_intent_cursor = store.pending_intents_page(
            limit=recovery_page_size,
            after=intent_cursor,
        )
        for intent in intents:
            reconciled_intent, failed_operation = _recover_pending_intent(
                store,
                pointer=pointer,
                selection=selection,
                intent=intent,
                live_lease_operations=live_lease_operations,
                now_us=now_us,
            )
            if reconciled_intent is not None:
                reconciled.append(reconciled_intent)
            if failed_operation is not None:
                failed.append(failed_operation)
        if next_intent_cursor is None:
            break
        intent_cursor = next_intent_cursor

    stale = store.stale_leases(now_us=now_us, worker_is_alive=worker_is_alive)
    for lease in stale:
        failed_operation = _remove_stale_lease(
            store,
            lease,
            selected_operation=selected_operation,
            now_us=now_us,
        )
        removed_leases.append(lease.lease_name.value)
        if failed_operation is not None:
            failed.append(failed_operation)

    job_cursor = None
    while True:
        jobs, next_job_cursor = store.active_jobs_page(
            limit=recovery_page_size,
            after=job_cursor,
        )
        for job in jobs:
            failed_operation = _recover_dead_job_without_lease(
                store,
                job,
                live_lease_operations=live_lease_operations,
                selected_operation=selected_operation,
                now_us=now_us,
                stale_after_us=job_stale_after_us,
                worker_is_alive=worker_is_alive,
            )
            if failed_operation is not None:
                failed.append(failed_operation)
        if next_job_cursor is None:
            break
        job_cursor = next_job_cursor

    return StartupRecoveryReport(
        selection=selection,
        repaired_pointer=repaired_pointer,
        completed_operations=tuple(completed),
        failed_operations=tuple(failed),
        reconciled_intents=tuple(reconciled),
        removed_leases=tuple(removed_leases),
    )
