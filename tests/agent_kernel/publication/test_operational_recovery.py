from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass as PlannerOperationClass,
)
from codex_usage_tracker.agent_kernel.publication.recovery import (
    AnalyticalHead,
    PointerArtifact,
    PointerDocument,
    PointerValidationError,
    PromotionConflictError,
    PromotionRequest,
    SmallPublicationRequest,
    cleanup_owned_artifacts,
    parse_pointer,
    promote_isolated_artifact,
    protected_artifact_names,
    publish_small_with_pointer,
    read_pointer,
    recover_startup,
    select_readable_artifact,
    write_pointer_durable,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationResult,
    PublicationWriter,
)
from codex_usage_tracker.agent_kernel.storage.database import initialize_operational
from codex_usage_tracker.agent_kernel.storage.operational import (
    CompatibilityConflictError,
    DirtyReason,
    HostWaitTimeoutError,
    JobProgress,
    JobRequest,
    JobState,
    LeaseConflictError,
    LeaseName,
    OperationalStateError,
    OperationalStore,
    OperationClass,
    RecoveryIntent,
    RecoveryIntentState,
    WorkerIdentity,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


@pytest.fixture
def store(tmp_path: Path) -> Iterator[OperationalStore]:
    connection = initialize_operational(tmp_path / "operations.sqlite3")
    try:
        yield OperationalStore(connection)
    finally:
        connection.close()


def _request(
    operation_id: str = "operation-1",
    *,
    request_sha256: str = SHA_A,
    compatibility_key: str = "refresh:all",
) -> JobRequest:
    return JobRequest(
        operation_id=operation_id,
        request_sha256=request_sha256,
        compatibility_key=compatibility_key,
        parent_publication_id="publication-1",
        operation_class=OperationClass.APPEND_SAFE_SMALL,
    )


def _advance_to_promoting(
    store: OperationalStore, operation_id: str, *, worker: WorkerIdentity | None = None
) -> None:
    store.transition(
        operation_id,
        expected=JobState.PLANNED,
        state=JobState.BUILDING,
        stage="building",
        now_us=2,
        worker=worker,
    )
    store.transition(
        operation_id,
        expected=JobState.BUILDING,
        state=JobState.VALIDATING,
        stage="validating",
        now_us=3,
        worker=worker,
    )
    store.transition(
        operation_id,
        expected=JobState.VALIDATING,
        state=JobState.PROMOTING,
        stage="promoting",
        now_us=4,
        worker=worker,
    )


def _advance_to_writing(
    store: OperationalStore, operation_id: str, *, worker: WorkerIdentity
) -> None:
    store.transition(
        operation_id,
        expected=JobState.PLANNED,
        state=JobState.PARSING,
        stage="parsing",
        now_us=2,
        worker=worker,
    )
    store.transition(
        operation_id,
        expected=JobState.PARSING,
        state=JobState.READY_TO_WRITE,
        stage="ready",
        now_us=3,
        worker=worker,
    )
    store.transition(
        operation_id,
        expected=JobState.READY_TO_WRITE,
        state=JobState.WRITING,
        stage="writing",
        now_us=4,
        worker=worker,
    )


def _artifact(directory: Path, name: str, content: bytes, publication_id: str) -> PointerArtifact:
    path = directory / name
    path.write_bytes(content)
    path.chmod(0o600)
    return PointerArtifact(
        artifact_name=name,
        artifact_manifest_sha256=hashlib.sha256(publication_id.encode()).hexdigest(),
        file_sha256=hashlib.sha256(content).hexdigest(),
        publication_id=publication_id,
        schema_contract_sha256=SHA_C,
    )


def _head(artifact: PointerArtifact, operation_id: str) -> AnalyticalHead:
    return AnalyticalHead(
        publication_id=artifact.publication_id,
        parent_publication_id=None,
        operation_id=operation_id,
        artifact_manifest_sha256=artifact.artifact_manifest_sha256,
        schema_contract_sha256=artifact.schema_contract_sha256,
    )


def _finalize_rollback(path: Path, _artifact_pointer: PointerArtifact) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_compatible_requests_join_one_job_and_conflicting_request_fails(
    store: OperationalStore,
) -> None:
    created = store.start_or_join(_request(), now_us=1)
    worker = WorkerIdentity(101, "worker-start")
    store.transition(
        created.job.operation_id,
        expected=JobState.PLANNED,
        state=JobState.PARSING,
        stage="parsing",
        now_us=2,
        worker=worker,
    )
    joined = store.start_or_join(_request("joining-operation"), now_us=2)

    assert created.joined is False
    assert joined.joined is True
    assert joined.job.operation_id == created.job.operation_id
    assert joined.job.worker == worker
    assert len(store.status_snapshot().active_jobs) == 1

    with pytest.raises(CompatibilityConflictError):
        store.start_or_join(
            _request("conflict", request_sha256=SHA_B),
            now_us=3,
        )


def test_progress_transition_is_monotonic_and_terminal_is_immutable(
    store: OperationalStore,
) -> None:
    store.start_or_join(_request(), now_us=1)
    parsing = store.transition(
        "operation-1",
        expected=JobState.PLANNED,
        state=JobState.PARSING,
        stage="parse",
        now_us=2,
        progress=JobProgress(1, 3, "records"),
    )
    assert parsing.progress == JobProgress(1, 3, "records")

    with pytest.raises(OperationalStateError):
        store.transition(
            "operation-1",
            expected=JobState.PARSING,
            state=JobState.READY_TO_WRITE,
            stage="ready",
            now_us=3,
            progress=JobProgress(0, 3, "records"),
        )

    store.force_terminal(
        "operation-1",
        state=JobState.FAILED,
        stage="failed",
        now_us=4,
        error_code="synthetic_failure",
    )
    with pytest.raises(OperationalStateError):
        store.transition(
            "operation-1",
            expected=JobState.FAILED,
            state=JobState.PARSING,
            stage="retry",
            now_us=5,
        )


def test_host_wait_is_bounded_and_returns_terminal_job(store: OperationalStore) -> None:
    store.start_or_join(_request(), now_us=1)
    ticks = iter((0.0, 0.0, 0.1, 0.2, 0.3))
    with pytest.raises(HostWaitTimeoutError):
        store.wait_for_terminal(
            "operation-1",
            timeout_s=0.2,
            poll_interval_s=0.1,
            monotonic=lambda: next(ticks),
            sleeper=lambda _seconds: None,
        )

    store.force_terminal(
        "operation-1",
        state=JobState.COMPLETED,
        stage="done",
        now_us=2,
        terminal_publication_id="publication-2",
    )
    assert (
        store.wait_for_terminal(
            "operation-1",
            timeout_s=0,
            monotonic=lambda: 1.0,
            sleeper=lambda _seconds: None,
        ).state
        is JobState.COMPLETED
    )


def test_lease_is_pid_start_token_fenced_and_stale_recovery_increments_token(
    store: OperationalStore,
) -> None:
    store.start_or_join(_request(), now_us=1)
    owner = WorkerIdentity(100, "start-a")
    lease = store.acquire_lease(
        LeaseName.ANALYTICAL_WRITER,
        operation_id="operation-1",
        owner_nonce="nonce-a",
        worker=owner,
        now_us=2,
        ttl_us=10,
        worker_is_alive=lambda pid, token: (pid, token) == (100, "start-a"),
    )
    with pytest.raises(LeaseConflictError):
        store.acquire_lease(
            LeaseName.ANALYTICAL_WRITER,
            operation_id="operation-1",
            owner_nonce="nonce-b",
            worker=WorkerIdentity(100, "start-b"),
            now_us=3,
            ttl_us=10,
            worker_is_alive=lambda _pid, _token: True,
        )

    recovered = store.acquire_lease(
        LeaseName.ANALYTICAL_WRITER,
        operation_id="operation-1",
        owner_nonce="nonce-b",
        worker=WorkerIdentity(100, "start-b"),
        now_us=4,
        ttl_us=10,
        worker_is_alive=lambda _pid, _token: False,
    )
    assert recovered.fencing_token == lease.fencing_token + 1
    assert store.job("operation-1").state is JobState.RECOVERY_REQUIRED  # type: ignore[union-attr]


def test_dirty_hints_coalesce_on_composite_key_and_status_is_read_only(
    store: OperationalStore,
) -> None:
    first = store.add_dirty_hint(
        source_id="source-a",
        technical_path_key="sessions/one.jsonl",
        observed_at_us=20,
        reasons=DirtyReason.CREATED,
    )
    merged = store.add_dirty_hint(
        source_id="source-a",
        technical_path_key="sessions/one.jsonl",
        observed_at_us=30,
        reasons=DirtyReason.MODIFIED | DirtyReason.REPLACED,
    )
    other = store.add_dirty_hint(
        source_id="source-b",
        technical_path_key="sessions/one.jsonl",
        observed_at_us=25,
        reasons=DirtyReason.MODIFIED,
    )

    assert first.observation_count == 1
    assert merged.observation_count == 2
    assert merged.reason_mask == int(
        DirtyReason.CREATED | DirtyReason.MODIFIED | DirtyReason.REPLACED
    )
    assert other.source_id == "source-b"
    before = store._connection.total_changes
    status = store.status_snapshot()
    assert store._connection.total_changes == before
    assert len(status.dirty_hints) == 2
    assert status.truncated is False
    assert store.status_snapshot(limit=1).truncated is True


def test_pointer_json_is_canonical_and_durable(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-a.sqlite3", b"active", "publication-1")
    pointer = PointerDocument(active=active, generation=1, rollback=None, written_at_us=10)
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"

    write_pointer_durable(pointer_path, pointer)

    assert read_pointer(pointer_path) == pointer
    assert parse_pointer(pointer.canonical_bytes()) == pointer
    assert pointer_path.stat().st_mode & 0o777 == 0o600
    assert not tuple(tmp_path.glob("*.tmp"))


def test_pointer_read_rejects_non_owner_only_directory(tmp_path: Path) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact.sqlite3", b"artifact", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    tmp_path.chmod(0o755)
    with pytest.raises(PointerValidationError, match="owner-owned with mode 0700"):
        read_pointer(pointer_path)


def test_read_first_selection_falls_back_to_rollback_without_sidecar(
    tmp_path: Path,
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-bad.sqlite3", b"bad", "publication-bad")
    rollback = _artifact(tmp_path, "artifact-good.sqlite3", b"good", "publication-good")
    pointer = PointerDocument(active, 2, rollback, 10)
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, pointer)
    opened: list[str] = []

    def validate(path: Path, artifact: PointerArtifact) -> AnalyticalHead:
        opened.append(path.name)
        if artifact.artifact_name == active.artifact_name:
            raise ValueError("synthetic corrupt artifact")
        return _head(artifact, "operation-good")

    selection = select_readable_artifact(pointer_path, validate_open=validate)

    assert opened == ["artifact-bad.sqlite3", "artifact-good.sqlite3"]
    assert selection.role == "rollback"
    assert selection.head.publication_id == "publication-good"


def test_isolated_promotion_retains_rollback_and_reconciles_sidecar(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    prior = _artifact(tmp_path, "artifact-prior.sqlite3", b"prior", "publication-1")
    candidate = _artifact(tmp_path, "artifact-next.sqlite3", b"next", "publication-2")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(prior, 1, None, 1))
    store.start_or_join(
        JobRequest(
            "operation-2",
            SHA_A,
            "promote:2",
            "publication-1",
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-2")
    fault_points: list[str] = []

    result = promote_isolated_artifact(
        pointer_path,
        store=store,
        request=PromotionRequest(
            recovery_id="recovery-2",
            operation_id="operation-2",
            expected_pointer_generation=1,
            expected_active_publication_id="publication-1",
            candidate=candidate,
            owner_nonce="nonce-2",
            worker=WorkerIdentity(200, "start-2"),
            now_us=10,
            lease_ttl_us=100,
        ),
        worker_is_alive=lambda _pid, _token: True,
        validate_open=lambda _path, artifact: AnalyticalHead(
            artifact.publication_id,
            "publication-1",
            "operation-2",
            artifact.artifact_manifest_sha256,
            artifact.schema_contract_sha256,
        ),
        finalize_rollback=_finalize_rollback,
        fault=fault_points.append,
    )

    assert result.pointer.active == candidate
    assert result.pointer.rollback == prior
    assert read_pointer(pointer_path).generation == 2
    assert store.job("operation-2").state is JobState.COMPLETED  # type: ignore[union-attr]
    assert store.recovery_intent("recovery-2").state is RecoveryIntentState.RECONCILED  # type: ignore[union-attr]
    assert [item.pointer_role for item in store.status_snapshot().pointers] == [
        "active",
        "rollback",
    ]
    assert "after_sidecar_reconcile" in fault_points


@pytest.mark.parametrize(
    "crash_point",
    ("after_small_analytical_commit", "after_small_pointer_write"),
)
def test_small_publication_crash_gaps_reconcile_direct_child(
    tmp_path: Path,
    store: OperationalStore,
    crash_point: str,
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"prior", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    worker = WorkerIdentity(301, "small-start")
    store.start_or_join(_request(), now_us=1)
    _advance_to_writing(store, "operation-1", worker=worker)
    committed_head = AnalyticalHead(
        publication_id="publication-2",
        parent_publication_id="publication-1",
        operation_id="operation-1",
        artifact_manifest_sha256=SHA_B,
        schema_contract_sha256=SHA_C,
    )
    current_head = _head(active, "operation-prior")

    def commit() -> AnalyticalHead:
        nonlocal current_head
        (tmp_path / active.artifact_name).write_bytes(b"committed-child")
        (tmp_path / active.artifact_name).chmod(0o600)
        current_head = committed_head
        return committed_head

    def crash(point: str) -> None:
        if point == crash_point:
            raise RuntimeError("synthetic small-process crash")

    with pytest.raises(RuntimeError, match="small-process crash"):
        publish_small_with_pointer(
            pointer_path,
            store=store,
            request=SmallPublicationRequest(
                "operation-1",
                1,
                "publication-1",
                active.artifact_name,
                "small-nonce",
                worker,
                10,
                100,
            ),
            worker_is_alive=lambda _pid, _token: True,
            validate_open=lambda _path, _artifact_pointer: current_head,
            commit_analytical=commit,
            fault=crash,
        )

    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, _artifact_pointer: current_head,
    )
    assert selection.head == committed_head
    assert selection.pointer_repair_required is (crash_point == "after_small_analytical_commit")

    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=20,
        worker_is_alive=lambda _pid, _token: False,
    )
    repaired = read_pointer(pointer_path)
    assert report.completed_operations == ("operation-1",)
    assert repaired.generation == 2
    assert repaired.active.publication_id == "publication-2"
    assert repaired.active.file_sha256 is None
    assert [item.pointer_role for item in store.status_snapshot().pointers] == ["active"]


def test_small_publication_excludes_isolated_promotion(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"prior", "publication-1")
    candidate = _artifact(tmp_path, "artifact-candidate.sqlite3", b"candidate", "publication-3")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    small_worker = WorkerIdentity(301, "small-start")
    store.start_or_join(_request(), now_us=1)
    _advance_to_writing(store, "operation-1", worker=small_worker)
    store.start_or_join(
        JobRequest(
            "operation-3",
            SHA_B,
            "promote:3",
            "publication-1",
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-3")
    current_head = _head(active, "operation-prior")

    def commit() -> AnalyticalHead:
        with pytest.raises(LeaseConflictError):
            promote_isolated_artifact(
                pointer_path,
                store=store,
                request=PromotionRequest(
                    "recovery-3",
                    "operation-3",
                    1,
                    "publication-1",
                    candidate,
                    "promotion-nonce",
                    WorkerIdentity(303, "promotion-start"),
                    10,
                    100,
                ),
                worker_is_alive=lambda _pid, _token: True,
                validate_open=lambda _path, artifact: _head(artifact, "operation-3"),
                finalize_rollback=_finalize_rollback,
            )
        (tmp_path / active.artifact_name).write_bytes(b"committed-child")
        return AnalyticalHead("publication-2", "publication-1", "operation-1", SHA_B, SHA_C)

    result = publish_small_with_pointer(
        pointer_path,
        store=store,
        request=SmallPublicationRequest(
            "operation-1",
            1,
            "publication-1",
            active.artifact_name,
            "small-nonce",
            small_worker,
            10,
            100,
        ),
        worker_is_alive=lambda _pid, _token: True,
        validate_open=lambda _path, _artifact_pointer: current_head,
        commit_analytical=commit,
    )

    assert result.pointer.active.publication_id == "publication-2"
    assert result.pointer.active.file_sha256 is None
    assert store.recovery_intent("recovery-3") is None


def test_writer_additive_hook_routes_commit_through_pointer_coordinator(
    tmp_path: Path,
    store: OperationalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"prior", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    worker = WorkerIdentity(301, "small-start")
    store.start_or_join(_request(), now_us=1)
    _advance_to_writing(store, "operation-1", worker=worker)
    committed = PublicationResult("publication-2", "operation-1", False, False, 1, 10, 5)

    def fake_publish(
        _self: PublicationWriter,
        _plan: object,
        _request_value: object,
        _write_set: object,
        *,
        fault_injector: object = None,
    ) -> PublicationResult:
        assert fault_injector is None
        return committed

    monkeypatch.setattr(PublicationWriter, "publish", fake_publish)
    connection = sqlite3.connect(":memory:")
    writer = PublicationWriter(connection)
    try:
        result = writer.publish_with_pointer(
            SimpleNamespace(
                operation_class=PlannerOperationClass.APPEND_SAFE_SMALL,
                analytical_write_required=True,
                parent_publication_id="publication-1",
            ),
            SimpleNamespace(
                publication_id="publication-2",
                operation_id="operation-1",
                parent_publication_id="publication-1",
                artifact_manifest_sha256=SHA_B,
            ),
            object(),
            pointer_path=pointer_path,
            operational_store=store,
            pointer_request=SmallPublicationRequest(
                "operation-1",
                1,
                "publication-1",
                active.artifact_name,
                "small-nonce",
                worker,
                10,
                100,
            ),
            worker_is_alive=lambda _pid, _token: True,
            validate_open=lambda _path, artifact: _head(artifact, "parent-operation"),
        )
    finally:
        connection.close()

    assert result == committed
    assert read_pointer(pointer_path).active.publication_id == "publication-2"
    assert store.job("operation-1").state is JobState.COMPLETED  # type: ignore[union-attr]


def test_initial_isolated_promotion_creates_generation_one_without_rollback(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    candidate = _artifact(tmp_path, "artifact-first.sqlite3", b"first", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    store.start_or_join(
        JobRequest(
            "operation-1",
            SHA_A,
            "promote:initial",
            None,
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-1")

    result = promote_isolated_artifact(
        pointer_path,
        store=store,
        request=PromotionRequest(
            "recovery-1",
            "operation-1",
            0,
            None,
            candidate,
            "nonce-1",
            WorkerIdentity(100, "start-1"),
            10,
            100,
        ),
        worker_is_alive=lambda _pid, _token: True,
        validate_open=lambda _path, artifact: _head(artifact, "operation-1"),
        finalize_rollback=lambda _path, _artifact_pointer: pytest.fail(
            "initial promotion must not finalize a rollback"
        ),
    )

    assert result.pointer.generation == 1
    assert result.pointer.active == candidate
    assert result.pointer.rollback is None
    assert read_pointer(pointer_path) == result.pointer
    assert [item.pointer_role for item in store.status_snapshot().pointers] == ["active"]
    assert store.job("operation-1").state is JobState.COMPLETED  # type: ignore[union-attr]
    assert store.recovery_intent("recovery-1").state is RecoveryIntentState.RECONCILED  # type: ignore[union-attr]


def test_initial_promotion_recovers_crash_after_durable_pointer(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    candidate = _artifact(tmp_path, "artifact-first.sqlite3", b"first", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    store.start_or_join(
        JobRequest(
            "operation-1",
            SHA_A,
            "promote:initial",
            None,
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-1", worker=WorkerIdentity(100, "start-1"))

    def crash(point: str) -> None:
        if point == "after_directory_fsync":
            raise RuntimeError("synthetic initial crash")

    with pytest.raises(RuntimeError, match="synthetic initial crash"):
        promote_isolated_artifact(
            pointer_path,
            store=store,
            request=PromotionRequest(
                "recovery-1",
                "operation-1",
                0,
                None,
                candidate,
                "nonce-1",
                WorkerIdentity(100, "start-1"),
                10,
                100,
            ),
            worker_is_alive=lambda _pid, _token: True,
            validate_open=lambda _path, artifact: _head(artifact, "operation-1"),
            finalize_rollback=_finalize_rollback,
            fault=crash,
        )

    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, artifact: _head(artifact, "operation-1"),
    )
    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=20,
        worker_is_alive=lambda _pid, _token: False,
    )

    assert report.completed_operations == ("operation-1",)
    assert report.reconciled_intents == ("recovery-1",)
    assert read_pointer(pointer_path).rollback is None
    assert [item.pointer_role for item in store.status_snapshot().pointers] == ["active"]


def test_initial_promotion_retry_reuses_prepared_intent_before_pointer_replace(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    candidate = _artifact(tmp_path, "artifact-first.sqlite3", b"first", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    store.start_or_join(
        JobRequest(
            "operation-1",
            SHA_A,
            "promote:initial",
            None,
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-1")

    def crash(point: str) -> None:
        if point == "before_pointer_replace":
            raise RuntimeError("synthetic pre-pointer crash")

    first_request = PromotionRequest(
        "recovery-1",
        "operation-1",
        0,
        None,
        candidate,
        "nonce-1",
        WorkerIdentity(100, "start-1"),
        10,
        100,
    )
    with pytest.raises(RuntimeError, match="synthetic pre-pointer crash"):
        promote_isolated_artifact(
            pointer_path,
            store=store,
            request=first_request,
            worker_is_alive=lambda _pid, _token: True,
            validate_open=lambda _path, artifact: _head(artifact, "operation-1"),
            finalize_rollback=_finalize_rollback,
            fault=crash,
        )
    assert not pointer_path.exists()
    assert store.recovery_intent("recovery-1").state is RecoveryIntentState.PREPARED  # type: ignore[union-attr]

    result = promote_isolated_artifact(
        pointer_path,
        store=store,
        request=PromotionRequest(
            "recovery-1",
            "operation-1",
            0,
            None,
            candidate,
            "nonce-1",
            WorkerIdentity(100, "start-1"),
            20,
            100,
        ),
        worker_is_alive=lambda _pid, _token: True,
        validate_open=lambda _path, artifact: _head(artifact, "operation-1"),
        finalize_rollback=_finalize_rollback,
    )

    assert result.pointer.generation == 1
    assert store.recovery_intent("recovery-1").state is RecoveryIntentState.RECONCILED  # type: ignore[union-attr]


def test_absent_pointer_rejects_noninitial_promotion(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    candidate = _artifact(tmp_path, "artifact-next.sqlite3", b"next", "publication-2")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    store.start_or_join(
        JobRequest(
            "operation-2",
            SHA_A,
            "promote:2",
            "publication-1",
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-2")

    with pytest.raises(PromotionConflictError, match="absent"):
        promote_isolated_artifact(
            pointer_path,
            store=store,
            request=PromotionRequest(
                "recovery-2",
                "operation-2",
                1,
                "publication-1",
                candidate,
                "nonce-2",
                WorkerIdentity(200, "start-2"),
                10,
                100,
            ),
            worker_is_alive=lambda _pid, _token: True,
            validate_open=lambda _path, artifact: _head(artifact, "operation-2"),
            finalize_rollback=_finalize_rollback,
        )

    assert store.recovery_intent("recovery-2") is None
    assert store.status_snapshot().leases == ()


@pytest.mark.parametrize(
    "crash_point",
    ("after_directory_fsync", "after_pointer_write", "after_reopen_validate"),
)
def test_startup_repairs_pointer_crash_points_and_opens_reads_first(
    tmp_path: Path, store: OperationalStore, crash_point: str
) -> None:
    tmp_path.chmod(0o700)
    prior = _artifact(tmp_path, "artifact-prior.sqlite3", b"prior", "publication-1")
    candidate = _artifact(tmp_path, "artifact-next.sqlite3", b"next", "publication-2")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(prior, 1, None, 1))
    store.start_or_join(
        JobRequest(
            "operation-2",
            SHA_A,
            "promote:2",
            "publication-1",
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-2", worker=WorkerIdentity(200, "start-2"))

    def crash(point: str) -> None:
        if point == crash_point:
            raise RuntimeError("synthetic crash")

    with pytest.raises(RuntimeError, match="synthetic crash"):
        promote_isolated_artifact(
            pointer_path,
            store=store,
            request=PromotionRequest(
                "recovery-2",
                "operation-2",
                1,
                "publication-1",
                candidate,
                "nonce-2",
                WorkerIdentity(200, "start-2"),
                10,
                100,
            ),
            worker_is_alive=lambda _pid, _token: True,
            validate_open=lambda _path, artifact: _head(artifact, "operation-2"),
            finalize_rollback=_finalize_rollback,
            fault=crash,
        )

    sidecar_changes_before_read = store._connection.total_changes
    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, artifact: AnalyticalHead(
            artifact.publication_id,
            "publication-1",
            "operation-2",
            artifact.artifact_manifest_sha256,
            artifact.schema_contract_sha256,
        ),
    )
    assert store._connection.total_changes == sidecar_changes_before_read

    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=20,
        worker_is_alive=lambda _pid, _token: False,
    )
    if report.repaired_pointer:
        assert read_pointer(pointer_path).active.file_sha256 == candidate.file_sha256
    assert report.completed_operations == ("operation-2",)
    assert report.reconciled_intents == ("recovery-2",)
    assert store.recovery_intent("recovery-2").state is RecoveryIntentState.RECONCILED  # type: ignore[union-attr]


def test_startup_preserves_pending_intent_owned_by_live_lease(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"active", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, artifact: _head(artifact, "selected-operation"),
    )
    worker = WorkerIdentity(200, "start-2")
    store.start_or_join(
        JobRequest(
            "operation-2",
            SHA_A,
            "promote:2",
            "publication-1",
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    _advance_to_promoting(store, "operation-2", worker=worker)
    store.create_recovery_intent(
        RecoveryIntent(
            "recovery-2",
            "operation-2",
            1,
            2,
            "publication-1",
            "publication-2",
            "artifact-candidate.sqlite3",
            SHA_B,
            RecoveryIntentState.PREPARED,
            5,
            5,
            None,
        )
    )
    store.acquire_lease(
        LeaseName.ARTIFACT_PROMOTION,
        operation_id="operation-2",
        owner_nonce="nonce-2",
        worker=worker,
        now_us=10,
        ttl_us=100,
        worker_is_alive=lambda _pid, _token: True,
    )

    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=20,
        worker_is_alive=lambda _pid, _token: True,
    )

    assert report.completed_operations == ()
    assert report.failed_operations == ()
    assert report.reconciled_intents == ()
    assert report.removed_leases == ()
    assert store.job("operation-2").state is JobState.PROMOTING  # type: ignore[union-attr]
    assert store.recovery_intent("recovery-2").state is RecoveryIntentState.PREPARED  # type: ignore[union-attr]
    assert len(store.status_snapshot().leases) == 1


def test_startup_paginates_and_terminalizes_dead_jobs_without_leases(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"active", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    for index in range(101):
        operation_id = f"dead-operation-{index:03d}"
        store.start_or_join(
            JobRequest(
                operation_id,
                SHA_A,
                f"dead:{index:03d}",
                "publication-1",
                OperationClass.APPEND_SAFE_SMALL,
            ),
            now_us=1,
        )
        store.transition(
            operation_id,
            expected=JobState.PLANNED,
            state=JobState.PARSING,
            stage="parsing",
            now_us=2,
            worker=WorkerIdentity(1_000 + index, f"start-{index:03d}"),
        )
    assert store.status_snapshot().truncated is True
    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, artifact: _head(artifact, "active-owner"),
    )

    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=100,
        worker_is_alive=lambda _pid, _token: False,
        recovery_page_size=10,
        job_stale_after_us=10,
    )

    assert len(report.failed_operations) == 101
    assert store.active_jobs_page(limit=10)[0] == ()
    assert all(
        store.job(f"dead-operation-{index:03d}").state is JobState.FAILED  # type: ignore[union-attr]
        for index in range(101)
    )


def test_startup_paginates_more_than_one_hundred_pending_intents(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"active", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    for index in range(101):
        operation_id = f"intent-operation-{index:03d}"
        store.start_or_join(
            JobRequest(
                operation_id,
                SHA_A,
                f"intent:{index:03d}",
                "publication-1",
                OperationClass.APPEND_SAFE_LARGE,
            ),
            now_us=1,
        )
        store.create_recovery_intent(
            RecoveryIntent(
                f"recovery-{index:03d}",
                operation_id,
                1,
                2,
                "publication-1",
                f"publication-candidate-{index:03d}",
                f"artifact-candidate-{index:03d}.sqlite3",
                SHA_B,
                RecoveryIntentState.PREPARED,
                5,
                5,
                None,
            )
        )
    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, artifact: _head(artifact, "active-owner"),
    )

    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=100,
        worker_is_alive=lambda _pid, _token: False,
        recovery_page_size=10,
    )

    assert len(report.failed_operations) == 101
    assert store.pending_intents_page(limit=10)[0] == ()
    assert all(
        store.recovery_intent(f"recovery-{index:03d}").state is RecoveryIntentState.ROLLED_BACK  # type: ignore[union-attr]
        for index in range(101)
    )


def test_startup_preserves_live_recently_heartbeating_job_without_lease(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"active", "publication-1")
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(active, 1, None, 1))
    worker = WorkerIdentity(404, "live-start")
    store.start_or_join(_request(), now_us=1)
    store.transition(
        "operation-1",
        expected=JobState.PLANNED,
        state=JobState.PARSING,
        stage="parsing",
        now_us=2,
        worker=worker,
    )
    store.heartbeat_job("operation-1", worker=worker, now_us=90)
    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, artifact: _head(artifact, "active-owner"),
    )

    report = recover_startup(
        pointer_path,
        selection=selection,
        store=store,
        now_us=100,
        worker_is_alive=lambda pid, token: (pid, token) == (404, "live-start"),
        job_stale_after_us=20,
    )

    assert report.failed_operations == ()
    assert store.job("operation-1").state is JobState.PARSING  # type: ignore[union-attr]


def test_cleanup_never_removes_pointer_or_recovery_protected_artifacts(
    tmp_path: Path, store: OperationalStore
) -> None:
    tmp_path.chmod(0o700)
    active = _artifact(tmp_path, "artifact-active.sqlite3", b"active", "publication-1")
    rollback = _artifact(tmp_path, "artifact-rollback.sqlite3", b"rollback", "publication-0")
    candidate = _artifact(tmp_path, "artifact-candidate.sqlite3", b"candidate", "publication-2")
    old = _artifact(tmp_path, "artifact-old.sqlite3", b"old", "publication-old")
    pointer = PointerDocument(active, 2, rollback, 1)
    store.start_or_join(
        JobRequest(
            "operation-2",
            SHA_A,
            "promote:2",
            "publication-1",
            OperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    store.transition(
        "operation-2",
        expected=JobState.PLANNED,
        state=JobState.BUILDING,
        stage="building",
        now_us=2,
        candidate_artifact_name=candidate.artifact_name,
        candidate_artifact_sha256=candidate.artifact_manifest_sha256,
    )
    protected = protected_artifact_names(pointer, store.status_snapshot())
    for name in (
        active.artifact_name,
        rollback.artifact_name,
        candidate.artifact_name,
        old.artifact_name,
    ):
        os.utime(tmp_path / name, ns=(0, 0))

    removed = cleanup_owned_artifacts(
        tmp_path,
        owned_artifact_names=(
            active.artifact_name,
            rollback.artifact_name,
            candidate.artifact_name,
            old.artifact_name,
            "../outside",
        ),
        protected_names=protected,
        now_us=1_000_000,
        minimum_age_us=1,
    )

    assert removed == (old.artifact_name,)
    assert (tmp_path / active.artifact_name).exists()
    assert (tmp_path / rollback.artifact_name).exists()
    assert (tmp_path / candidate.artifact_name).exists()
