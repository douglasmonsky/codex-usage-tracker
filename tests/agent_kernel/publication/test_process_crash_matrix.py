from __future__ import annotations

import hashlib
import multiprocessing
import os
from dataclasses import replace
from pathlib import Path

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.publication.planner import (
    OperationClass,
    PublicationPlan,
    estimate_change_set,
)
from codex_usage_tracker.agent_kernel.publication.recovery import (
    AnalyticalHead,
    PointerArtifact,
    PointerDocument,
    PromotionRequest,
    SmallPublicationRequest,
    cleanup_owned_artifacts,
    promote_isolated_artifact,
    protected_artifact_names,
    publish_small_with_pointer,
    read_pointer,
    recover_startup,
    select_readable_artifact,
    write_pointer_durable,
)
from codex_usage_tracker.agent_kernel.publication.writer import (
    PublicationRequest,
    PublicationWriter,
    planned_artifact_manifest_sha256,
    prepare_write_set_from_changes,
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
    OperationalStore,
    RecoveryIntentState,
    WorkerIdentity,
)
from codex_usage_tracker.agent_kernel.storage.operational import (
    OperationClass as SidecarOperationClass,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "tiny-v1"
FAULT_STAGES = (
    "after_begin",
    "after_recheck",
    "after_publication",
    "after_occurrences",
    "after_facts",
    "after_metadata",
    "after_head",
    "before_commit",
)


def _prepared(operation_id: str):
    changes = ingest(
        FIXTURE,
        manifest=FIXTURE / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    plan = PublicationPlan(
        OperationClass.APPEND_SAFE_SMALL,
        None,
        estimate_change_set(changes),
        ("synthetic_crash_matrix",),
        True,
    )
    request = PublicationRequest(
        publication_id=f"publication:{operation_id}",
        operation_id=operation_id,
        committed_at_us=1_800_000_000_000_000,
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        indexed_from_us=1_700_000_000_000_000,
        indexed_through_us=1_800_000_000_000_000,
        guaranteed_complete_from_us=1_700_000_000_000_000,
    )
    write_set = prepare_write_set_from_changes(changes, request)
    digest = planned_artifact_manifest_sha256(plan, request, write_set)
    return plan, replace(request, artifact_manifest_sha256=digest), write_set


def _crash_writer(database: str, stage: str) -> None:
    plan, request, write_set = _prepared(f"crash:{stage}")
    connection = open_writer(Path(database))

    def crash(current: str) -> None:
        if current == stage:
            os._exit(73)

    PublicationWriter(connection).publish(
        plan,
        request,
        write_set,
        fault_injector=crash,
    )
    os._exit(0)


def _crash_small_pointer_protocol(
    pointer_path_text: str,
    operational_path_text: str,
    crash_point: str,
) -> None:
    pointer_path = Path(pointer_path_text)
    operational = open_writer(Path(operational_path_text), kind="operational")
    store = OperationalStore(operational)
    prior = read_pointer(pointer_path).active
    child = AnalyticalHead(
        "publication-child",
        "publication-parent",
        "small-operation",
        "b" * 64,
        prior.schema_contract_sha256,
    )

    def commit() -> AnalyticalHead:
        artifact_path = pointer_path.parent / prior.artifact_name
        artifact_path.write_bytes(b"committed-child")
        artifact_path.chmod(0o600)
        return child

    def crash(stage: str) -> None:
        if stage == crash_point:
            os._exit(74)

    publish_small_with_pointer(
        pointer_path,
        store=store,
        request=SmallPublicationRequest(
            "small-operation",
            1,
            "publication-parent",
            prior.artifact_name,
            "small-owner",
            WorkerIdentity(os.getpid(), "spawn-start-token"),
            10,
            1_000_000,
        ),
        worker_is_alive=lambda _pid, _token: True,
        validate_open=lambda _path, _pointer: AnalyticalHead(
            "publication-parent",
            None,
            "parent-operation",
            prior.artifact_manifest_sha256,
            prior.schema_contract_sha256,
        ),
        commit_analytical=commit,
        fault=crash,
    )
    os._exit(0)


def _crash_isolated_promotion(
    pointer_path_text: str,
    operational_path_text: str,
    candidate_name: str,
    crash_point: str,
) -> None:
    pointer_path = Path(pointer_path_text)
    operational = open_writer(Path(operational_path_text), kind="operational")
    store = OperationalStore(operational)
    prior = read_pointer(pointer_path).active
    candidate_path = pointer_path.parent / candidate_name
    candidate = PointerArtifact(
        candidate_name,
        "b" * 64,
        hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "publication-candidate",
        prior.schema_contract_sha256,
    )

    def validate(_path: Path, artifact: PointerArtifact) -> AnalyticalHead:
        if artifact.artifact_name == candidate_name:
            return AnalyticalHead(
                "publication-candidate",
                "publication-prior",
                "promotion-operation",
                candidate.artifact_manifest_sha256,
                candidate.schema_contract_sha256,
            )
        return AnalyticalHead(
            "publication-prior",
            None,
            "prior-operation",
            prior.artifact_manifest_sha256,
            prior.schema_contract_sha256,
        )

    def crash(stage: str) -> None:
        if stage == crash_point:
            os._exit(76)

    promote_isolated_artifact(
        pointer_path,
        store=store,
        request=PromotionRequest(
            "promotion-recovery",
            "promotion-operation",
            1,
            "publication-prior",
            candidate,
            "promotion-owner",
            WorkerIdentity(os.getpid(), "promotion-start-token"),
            10,
            1_000_000,
        ),
        worker_is_alive=lambda _pid, _token: True,
        validate_open=validate,
        finalize_rollback=lambda path, _pointer: hashlib.sha256(path.read_bytes()).hexdigest(),
        fault=crash,
    )
    os._exit(0)


def _crash_protected_cleanup(
    owner_directory_text: str,
    protected_names: tuple[str, ...],
    old_name: str,
    crash_point: str,
) -> None:
    def crash(stage: str) -> None:
        if stage == crash_point:
            os._exit(77)

    cleanup_owned_artifacts(
        Path(owner_directory_text),
        owned_artifact_names=(*protected_names, old_name),
        protected_names=frozenset(protected_names),
        now_us=1_000_000,
        minimum_age_us=1,
        fault=crash,
    )
    os._exit(0)


@pytest.mark.parametrize("stage", FAULT_STAGES)
def test_abrupt_writer_exit_preserves_prior_truth_and_allows_retry(
    tmp_path: Path,
    stage: str,
) -> None:
    database = tmp_path / "analytical.sqlite3"
    initialize_analytical(database).close()
    process = multiprocessing.get_context("spawn").Process(
        target=_crash_writer,
        args=(str(database), stage),
    )
    process.start()
    process.join(timeout=20)
    assert not process.is_alive()
    assert process.exitcode == 73

    reader = open_read_only(database)
    try:
        assert reader.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 0
        assert reader.execute("SELECT COUNT(*) FROM publication_head").fetchone()[0] == 0
        assert reader.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        reader.close()

    plan, request, write_set = _prepared(f"retry:{stage}")
    writer = open_writer(database)
    try:
        result = PublicationWriter(writer).publish(plan, request, write_set)
        assert result.publication_id == request.publication_id
        assert writer.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        writer.close()


@pytest.mark.parametrize(
    "crash_point",
    ("after_small_analytical_commit", "after_small_pointer_write"),
)
def test_abrupt_small_publication_gaps_reconcile_from_analytical_child(
    tmp_path: Path,
    crash_point: str,
) -> None:
    tmp_path.chmod(0o700)
    artifact_path = tmp_path / "artifact-active.sqlite3"
    artifact_path.write_bytes(b"prior")
    artifact_path.chmod(0o600)
    prior = PointerArtifact(
        artifact_path.name,
        "a" * 64,
        hashlib.sha256(b"prior").hexdigest(),
        "publication-parent",
        "c" * 64,
    )
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(prior, 1, None, 1))
    operational_path = tmp_path / "operations.sqlite3"
    operational = initialize_operational(operational_path)
    store = OperationalStore(operational)
    store.start_or_join(
        JobRequest(
            "small-operation",
            "d" * 64,
            "small:operation",
            "publication-parent",
            SidecarOperationClass.APPEND_SAFE_SMALL,
        ),
        now_us=1,
    )
    worker = WorkerIdentity(999_999, "dead-parent-token")
    store.transition(
        "small-operation",
        expected=JobState.PLANNED,
        state=JobState.PARSING,
        stage="parsing",
        now_us=2,
        worker=worker,
    )
    store.transition(
        "small-operation",
        expected=JobState.PARSING,
        state=JobState.READY_TO_WRITE,
        stage="ready",
        now_us=3,
        worker=worker,
    )
    store.transition(
        "small-operation",
        expected=JobState.READY_TO_WRITE,
        state=JobState.WRITING,
        stage="writing",
        now_us=4,
        worker=worker,
    )
    operational.close()

    process = multiprocessing.get_context("spawn").Process(
        target=_crash_small_pointer_protocol,
        args=(str(pointer_path), str(operational_path), crash_point),
    )
    process.start()
    process.join(timeout=20)
    assert not process.is_alive()
    assert process.exitcode == 74

    child = AnalyticalHead(
        "publication-child",
        "publication-parent",
        "small-operation",
        "b" * 64,
        "c" * 64,
    )
    selection = select_readable_artifact(
        pointer_path,
        validate_open=lambda _path, _pointer: child,
    )
    recovery_connection = open_writer(operational_path, kind="operational")
    recovery_store = OperationalStore(recovery_connection)
    try:
        report = recover_startup(
            pointer_path,
            selection=selection,
            store=recovery_store,
            now_us=20,
            worker_is_alive=lambda _pid, _token: False,
            job_stale_after_us=1,
        )
        assert report.completed_operations == ("small-operation",)
        repaired = read_pointer(pointer_path)
        assert repaired.generation == 2
        assert repaired.active.publication_id == "publication-child"
        assert repaired.active.file_sha256 is None
    finally:
        recovery_connection.close()


@pytest.mark.parametrize(
    "crash_point",
    (
        "before_pointer_replace",
        "after_pointer_replace",
        "after_directory_fsync",
        "after_reopen_validate",
        "after_sidecar_reconcile",
    ),
)
def test_abrupt_isolated_promotion_restart_is_deterministic(
    tmp_path: Path,
    crash_point: str,
) -> None:
    tmp_path.chmod(0o700)
    prior_path = tmp_path / "artifact-prior.sqlite3"
    prior_path.write_bytes(b"prior")
    prior_path.chmod(0o600)
    candidate_path = tmp_path / "artifact-candidate.sqlite3"
    candidate_path.write_bytes(b"candidate")
    candidate_path.chmod(0o600)
    prior = PointerArtifact(
        prior_path.name,
        "a" * 64,
        hashlib.sha256(b"prior").hexdigest(),
        "publication-prior",
        "c" * 64,
    )
    candidate = PointerArtifact(
        candidate_path.name,
        "b" * 64,
        hashlib.sha256(b"candidate").hexdigest(),
        "publication-candidate",
        "c" * 64,
    )
    pointer_path = tmp_path / "active-artifact-pointer-v1.json"
    write_pointer_durable(pointer_path, PointerDocument(prior, 1, None, 1))
    operational_path = tmp_path / "operations.sqlite3"
    operational = initialize_operational(operational_path)
    store = OperationalStore(operational)
    store.start_or_join(
        JobRequest(
            "promotion-operation",
            "d" * 64,
            "promotion:operation",
            "publication-prior",
            SidecarOperationClass.APPEND_SAFE_LARGE,
        ),
        now_us=1,
    )
    store.transition(
        "promotion-operation",
        expected=JobState.PLANNED,
        state=JobState.BUILDING,
        stage="building",
        now_us=2,
        worker=WorkerIdentity(999_998, "dead-promotion-token"),
    )
    store.transition(
        "promotion-operation",
        expected=JobState.BUILDING,
        state=JobState.VALIDATING,
        stage="validating",
        now_us=3,
        worker=WorkerIdentity(999_998, "dead-promotion-token"),
    )
    store.transition(
        "promotion-operation",
        expected=JobState.VALIDATING,
        state=JobState.PROMOTING,
        stage="promoting",
        now_us=4,
        worker=WorkerIdentity(999_998, "dead-promotion-token"),
    )
    operational.close()

    process = multiprocessing.get_context("spawn").Process(
        target=_crash_isolated_promotion,
        args=(
            str(pointer_path),
            str(operational_path),
            candidate.artifact_name,
            crash_point,
        ),
    )
    process.start()
    process.join(timeout=20)
    assert not process.is_alive()
    assert process.exitcode == 76

    def validate(_path: Path, artifact: PointerArtifact) -> AnalyticalHead:
        if artifact.artifact_name == candidate.artifact_name:
            return AnalyticalHead(
                candidate.publication_id,
                prior.publication_id,
                "promotion-operation",
                candidate.artifact_manifest_sha256,
                candidate.schema_contract_sha256,
            )
        return AnalyticalHead(
            prior.publication_id,
            None,
            "prior-operation",
            prior.artifact_manifest_sha256,
            prior.schema_contract_sha256,
        )

    recovery_connection = open_writer(operational_path, kind="operational")
    recovery_store = OperationalStore(recovery_connection)
    try:
        selection = select_readable_artifact(pointer_path, validate_open=validate)
        report = recover_startup(
            pointer_path,
            selection=selection,
            store=recovery_store,
            now_us=20,
            worker_is_alive=lambda _pid, _token: False,
            job_stale_after_us=1,
        )
        selected_pointer = read_pointer(pointer_path)
        if crash_point == "before_pointer_replace":
            assert selected_pointer.active == prior
            assert (
                recovery_store.recovery_intent("promotion-recovery").state
                is RecoveryIntentState.ROLLED_BACK
            )
        else:
            assert selected_pointer.active == candidate
            assert selected_pointer.rollback == prior
            assert (
                recovery_store.recovery_intent("promotion-recovery").state
                is RecoveryIntentState.RECONCILED
            )
        protected = protected_artifact_names(
            selected_pointer,
            recovery_store.status_snapshot(),
        )
        assert selected_pointer.active.artifact_name in protected
        if selected_pointer.rollback is not None:
            assert selected_pointer.rollback.artifact_name in protected
        stable_bytes = selected_pointer.canonical_bytes()
        retry_selection = select_readable_artifact(pointer_path, validate_open=validate)
        retry = recover_startup(
            pointer_path,
            selection=retry_selection,
            store=recovery_store,
            now_us=30,
            worker_is_alive=lambda _pid, _token: False,
            job_stale_after_us=1,
        )
        assert read_pointer(pointer_path).canonical_bytes() == stable_bytes
        assert retry.completed_operations == ()
        assert retry.reconciled_intents == ()
        assert retry.failed_operations == ()
        assert report.removed_leases
    finally:
        recovery_connection.close()


@pytest.mark.parametrize(
    "crash_point",
    ("before_cleanup_unlink", "after_cleanup_unlink"),
)
def test_abrupt_cleanup_protects_pointer_pair_and_retries_deterministically(
    tmp_path: Path,
    crash_point: str,
) -> None:
    tmp_path.chmod(0o700)
    active_path = tmp_path / "artifact-active.sqlite3"
    rollback_path = tmp_path / "artifact-rollback.sqlite3"
    old_path = tmp_path / "artifact-old.sqlite3"
    for path, payload in (
        (active_path, b"active"),
        (rollback_path, b"rollback"),
        (old_path, b"old"),
    ):
        path.write_bytes(payload)
        path.chmod(0o600)
        os.utime(path, ns=(0, 0))
    protected = (active_path.name, rollback_path.name)

    process = multiprocessing.get_context("spawn").Process(
        target=_crash_protected_cleanup,
        args=(str(tmp_path), protected, old_path.name, crash_point),
    )
    process.start()
    process.join(timeout=20)
    assert not process.is_alive()
    assert process.exitcode == 77
    assert active_path.exists()
    assert rollback_path.exists()

    removed = cleanup_owned_artifacts(
        tmp_path,
        owned_artifact_names=(*protected, old_path.name),
        protected_names=frozenset(protected),
        now_us=1_000_000,
        minimum_age_us=1,
    )
    assert removed == ((old_path.name,) if crash_point == "before_cleanup_unlink" else ())
    assert active_path.exists()
    assert rollback_path.exists()
