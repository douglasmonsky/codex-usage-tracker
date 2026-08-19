from __future__ import annotations

import copy
import json
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest import ingest
from codex_usage_tracker.agent_kernel.publication.writer import (
    PriorPublicationSnapshot,
    PublicationRequest,
)
from scripts import benchmark_ck07r1_lifecycle_scale as benchmark
from tests.agent_kernel.contracts.reference.lifecycle import fold_lifecycle


def _request(publication_id: str, parent: str | None = None) -> PublicationRequest:
    return PublicationRequest(
        publication_id=publication_id,
        operation_id=publication_id.replace("publication:", "operation:", 1),
        committed_at_us=1_800_000_000_000_000,
        history_preset="all_time",
        artifact_manifest_sha256="0" * 64,
        parent_publication_id=parent,
    )


def test_lifecycle_preparation_groups_transitions_and_matches_reference_truth() -> None:
    observations = benchmark._scale_observations(
        "standard",
        {"model_calls": 8, "history_days": 30, "ratios_basis_points": {"tool_invocations": 10_000}},
        None,
    )
    changes = benchmark._changes(observations)
    preparer = benchmark.preparation._WriteSetPreparer(
        changes,
        _request("publication:scale"),
        configured_producer_key="synthetic-ck07r1",
        prior=PriorPublicationSnapshot(),
        inventory_started_at_us=1_800_000_000_000_000,
        inventory_completed_at_us=1_800_000_000_000_000,
    )

    preparer.prepare()

    grouped = {}
    for transition in preparer.transitions:
        grouped.setdefault(transition.entity_logical_id, []).append(
            {
                "basis": transition.state_basis,
                "coordinate": {
                    "source_order": ["synthetic-lifecycle", transition.source_order],
                    "event_at_us": transition.transition_at_us,
                },
                "event_at_us": transition.transition_at_us,
                "event_kind_order": transition.event_kind_order,
                "logical_id": transition.entity_logical_id,
                "state": transition.lifecycle_state,
                "source_order": ["synthetic-lifecycle", transition.source_order],
            }
        )

    assert len(preparer.folds) == len(grouped)
    for logical_id, transitions in grouped.items():
        reference = fold_lifecycle(transitions)
        actual = preparer.folds[logical_id]
        assert actual.lifecycle_state == reference["state"]
        assert actual.state_basis == reference["state_basis"]
        assert actual.transition_version == reference["transition_count"]
        assert actual.start_at_us == reference["start_coordinate"]["event_at_us"]
        assert actual.terminal_at_us == (
            None
            if reference["terminal_coordinate"] is None
            else reference["terminal_coordinate"]["event_at_us"]
        )
        assert actual.observed_duration_us == reference["observed_duration_us"]
        assert actual.transition_count == reference["transition_count"]


def test_lifecycle_preparation_appends_prior_transition_without_rewriting_identity() -> None:
    observations = benchmark._scale_observations(
        "standard",
        {"model_calls": 2, "history_days": 30, "ratios_basis_points": {"tool_invocations": 10_000}},
        None,
    )
    first = observations[0]
    terminal = observations[1]
    first_request = _request("publication:first")
    initial = benchmark.preparation._WriteSetPreparer(
        benchmark._changes((first,)),
        first_request,
        configured_producer_key="synthetic-ck07r1",
        prior=PriorPublicationSnapshot(),
        inventory_started_at_us=first_request.committed_at_us,
        inventory_completed_at_us=first_request.committed_at_us,
    )
    initial.prepare()
    prior = replace(
        PriorPublicationSnapshot(),
        lifecycle={first.logical_id: tuple(initial.transitions)},
    )
    second_request = _request("publication:second", "publication:first")
    successor = benchmark.preparation._WriteSetPreparer(
        benchmark._changes((terminal,)),
        second_request,
        configured_producer_key="synthetic-ck07r1",
        prior=prior,
        inventory_started_at_us=second_request.committed_at_us,
        inventory_completed_at_us=second_request.committed_at_us,
    )
    successor.prepare()

    assert successor.transitions[0].transition_version == 2
    assert successor.transitions[0].transition_id != initial.transitions[0].transition_id
    assert successor.folds[first.logical_id].lifecycle_state == "succeeded"
    assert successor.folds[first.logical_id].transition_count == 2


def test_budget_checks_fail_closed_on_first_budget_miss() -> None:
    measurements = {
        "standard_30_day": {"lifecycle_preparation": {"max_ms": 5_001}},
        "production_all_time": {"lifecycle_preparation": {"max_ms": 120_000}},
        "no_change": {"max_ms": 100},
        "one_call_tail": {"max_ms": 500},
        "one_tool_tail": {"max_ms": 500},
    }

    checks, first_failure = benchmark._budget_checks(measurements)

    assert checks == {
        "standard_30_day": False,
        "production_all_time": True,
        "no_change": True,
        "one_call_tail": True,
        "one_tool_tail": True,
    }
    assert first_failure == {
        "gate": "standard_30_day",
        "observed_max_ms": 5_001,
        "budget_ms": 5_000,
    }


def test_reachable_path_binds_plan_recovery_pointer_and_chain() -> None:
    root = Path(__file__).resolve().parents[3]
    base = ingest(
        root / "tests" / "agent_kernel" / "fixtures" / "tiny-v1",
        manifest=root / "tests" / "agent_kernel" / "fixtures" / "tiny-v1" / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    scale = benchmark._scale_observations(
        "standard",
        {"model_calls": 4, "history_days": 30, "ratios_basis_points": {"tool_invocations": 10_000}},
        None,
    )

    receipt = benchmark._publication_receipt("standard", scale, base)

    assert receipt["planner_operation_class"] == "append_safe_small"
    assert receipt["postconditions"]["identity_bindings"] is True
    assert receipt["postconditions"]["independent_oracle"].endswith("fold_lifecycle")
    assert receipt["publication_chain"]["direct_child_chain"] is True
    assert receipt["recovery_report"]["failed_operations"] == ()
    assert receipt["recovery_probe"]["first_recovery_reconciled"] == (
        "recovery:ck07r1:standard:prepared-crash",
    )
    assert receipt["recovery_probe"]["retry_reconciled"] == ()
    assert receipt["postconditions"]["source_occurrence_delta"] == receipt["postconditions"]["inserted_occurrences"]
    assert receipt["postconditions"]["source_occurrence_ids_unique"] is True
    assert receipt["postconditions"]["identity_bindings"] is True
    assert receipt["planner_tail_limits"] == benchmark.FROZEN_TAIL_LIMITS
    assert all(
        chunk["plan_digest_before_writer"] == chunk["plan_digest_at_writer"]
        and chunk["identity_bindings"]["selection_head"]
        == chunk["identity_bindings"]["refresh_intent_parent"]
        == chunk["identity_bindings"]["plan_parent"]
        == chunk["identity_bindings"]["small_request_expected_active"]
        == chunk["identity_bindings"]["pre_commit_pointer_active"]
        == chunk["identity_bindings"]["committed_head_parent"]
        and chunk["identity_bindings"]["post_commit_pointer_active"] == chunk["publication_id"]
        for chunk in receipt["publication_chain"]["chunks"]
    )


def _planner_intent() -> benchmark.RefreshIntent:
    return benchmark.RefreshIntent(
        parent_publication_id="publication:parent",
        parent_observed_at_us=1_800_000_000_000_000,
        planned_at_us=1_800_000_000_000_001,
        history_preset="30_days",
        current_history_preset="30_days",
    )


def test_standard_profile_1369_records_routes_large_with_exact_reason() -> None:
    observations = benchmark._scale_observations(
        "standard", benchmark._profile("standard"), 30
    )
    assert len(observations) == 1_369
    plan = benchmark.plan_refresh(
        benchmark._changes(observations),
        _planner_intent(),
        limits=benchmark._tail_limits(),
    )

    assert plan.operation_class is benchmark.OperationClass.APPEND_SAFE_LARGE
    assert plan.estimate.selected_records == 1_369
    assert plan.estimate.expected_wal_bytes == 11_214_848
    assert plan.reasons == ("limit_exceeded:selected_records",)


def test_production_first_chunk_is_large_for_selected_records_and_wal() -> None:
    observations = benchmark._scale_observations(
        "production", benchmark._profile("production"), None
    )[: benchmark.PUBLICATION_CHUNK_OBSERVATIONS]
    plan = benchmark.plan_refresh(
        benchmark._changes(observations),
        _planner_intent(),
        limits=benchmark._tail_limits(),
    )

    assert plan.operation_class is benchmark.OperationClass.APPEND_SAFE_LARGE
    assert "limit_exceeded:selected_records" in plan.reasons
    assert "limit_exceeded:expected_wal_bytes" in plan.reasons
    assert plan.estimate.selected_records > benchmark.FROZEN_TAIL_LIMITS["selected_records"]
    assert plan.estimate.expected_wal_bytes > benchmark.FROZEN_TAIL_LIMITS["expected_wal_bytes"]


@pytest.mark.parametrize(
    ("record_count", "operation_class", "reasons"),
    [
        (32, benchmark.OperationClass.APPEND_SAFE_SMALL, ("all_small_tail_bounds_proven",)),
        (33, benchmark.OperationClass.APPEND_SAFE_LARGE, ("limit_exceeded:selected_records",)),
    ],
)
def test_selected_record_boundary_preserves_planner_class_and_reason(
    record_count: int,
    operation_class: benchmark.OperationClass,
    reasons: tuple[str, ...],
) -> None:
    observations = benchmark._scale_observations(
        "standard",
        {"model_calls": 32, "history_days": 30, "ratios_basis_points": {"tool_invocations": 10_000}},
        None,
    )[:record_count]
    plan = benchmark.plan_refresh(
        benchmark._changes(observations),
        _planner_intent(),
        limits=benchmark._tail_limits(),
    )

    assert plan.operation_class is operation_class
    assert plan.reasons == reasons
    assert benchmark._validate_selected_plan(plan, _planner_intent(), benchmark._tail_limits()) == (
        () if record_count == 32 else ("selected_records",)
    )


def test_mixed_receipt_reports_large_promotion_then_small_pointer_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[3]
    base = ingest(
        root / "tests" / "agent_kernel" / "fixtures" / "tiny-v1",
        manifest=root / "tests" / "agent_kernel" / "fixtures" / "tiny-v1" / "manifest.json",
        workers=1,
        batch_size=32,
    ).changes
    scale = benchmark._scale_observations(
        "standard",
        {"model_calls": 40, "history_days": 30, "ratios_basis_points": {"tool_invocations": 10_000}},
        None,
    )[:65]
    monkeypatch.setattr(benchmark, "PUBLICATION_CHUNK_OBSERVATIONS", 33)

    receipt = benchmark._publication_receipt("standard", scale, base)
    chunks = receipt["publication_chain"]["chunks"]

    assert receipt["planner_operation_classes"] == [
        "append_safe_large",
        "append_safe_small",
    ]
    assert receipt["writer_paths"] == [
        "large_isolated_artifact_build_validate_promote",
        "small_pointer_coordinated",
    ]
    assert chunks[0]["large_artifact"]["file_sha256"]
    assert chunks[0]["large_artifact"]["rollback_artifact_name"]
    assert chunks[0]["identity_bindings"]["promotion_request_expected_active"] == (
        chunks[0]["identity_bindings"]["writer_request_expected_active"]
    )
    assert chunks[1]["identity_bindings"]["small_request_expected_active"] == (
        chunks[1]["identity_bindings"]["writer_request_expected_active"]
    )
    assert receipt["postconditions"]["identity_bindings"] is True
    assert receipt["publication_chain"]["direct_child_chain"] is True


def test_plan_mutations_and_missing_large_evidence_fail_closed(
    tmp_path: Path,
) -> None:
    observations = benchmark._scale_observations(
        "standard", benchmark._profile("standard"), 30
    )
    intent = _planner_intent()
    limits = benchmark._tail_limits()
    plan = benchmark.plan_refresh(benchmark._changes(observations), intent, limits=limits)

    with pytest.raises(AssertionError, match="APPEND_SAFE_SMALL"):
        benchmark._validate_selected_plan(
            replace(plan, operation_class=benchmark.OperationClass.APPEND_SAFE_SMALL),
            intent,
            limits,
        )
    with pytest.raises(ValueError, match="non-authoritative TailLimits"):
        benchmark._validate_selected_plan(plan, intent, replace(limits, selected_records=99))

    writer = benchmark._RecordingWriter(None, plan, [])
    with pytest.raises(AssertionError, match="different plan object"):
        writer.publish(replace(plan, reasons=("substituted",)), _request("publication:drift"), object())

    candidate_path = tmp_path / "candidate.sqlite3"
    candidate_path.write_bytes(b"synthetic-candidate")
    candidate = type(
        "Candidate",
        (),
        {
            "path": candidate_path,
            "publication_id": "publication:missing-evidence",
            "artifact_manifest_sha256": "0" * 64,
            "file_sha256": None,
        },
    )()
    with pytest.raises(AssertionError, match="evidence is missing"):
        benchmark._validate_large_artifact_evidence(
            candidate,
            _request("publication:missing-evidence"),
        )


def test_launch_output_preflight_is_exclusive_and_non_overwriting(tmp_path: Path) -> None:
    (tmp_path / "output" / "ck07r1").mkdir(parents=True)

    paths = benchmark._preflight_launch_paths(tmp_path)

    assert paths["output"].relative_to(tmp_path) == benchmark.RUN_OUTPUT_RELATIVE
    assert all(
        "lifecycle-requalification-v2" in str(path)
        for path in (
            benchmark.RUN_OUTPUT_RELATIVE,
            benchmark.RUN_LEDGER_RELATIVE,
            benchmark.RUN_STDOUT_RELATIVE,
            benchmark.RUN_STDERR_RELATIVE,
        )
    )
    assert "lifecycle-requalification-v1" in str(benchmark.PRESERVED_V1_LEDGER_RELATIVE)
    benchmark._exclusive_write(paths["ledger"], b'{"token":true}\n')
    with pytest.raises(FileExistsError):
        benchmark._exclusive_write(paths["ledger"], b'{"token":false}\n')
    assert paths["ledger"].read_bytes() == b'{"token":true}\n'

    paths["output"].write_bytes(b"existing\n")
    with pytest.raises(FileExistsError, match="refusing overwrite"):
        benchmark._preflight_launch_paths(tmp_path)


def test_atomic_json_update_uses_unique_same_directory_temps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ledger.json"
    replacements: list[tuple[Path, Path]] = []
    real_replace = benchmark.os.replace

    def replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(benchmark.os, "replace", replace)

    benchmark._atomic_json_update(path, {"state": "first"})
    benchmark._atomic_json_update(path, {"state": "second"})

    assert len(replacements) == 2
    temporary_paths = [source for source, _destination in replacements]
    assert len(set(temporary_paths)) == 2
    assert all(source.parent == path.parent for source in temporary_paths)
    assert all(source.name.startswith(f".{path.name}.") for source in temporary_paths)
    assert all(source.name.endswith(".tmp") for source in temporary_paths)
    assert path.read_text(encoding="utf-8") == '{"state":"second"}\n'
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


@pytest.mark.parametrize(
    ("failure_kind", "expected_exception"),
    [
        ("write", OSError),
        ("file_fsync", OSError),
        ("replace", OSError),
        ("directory_fsync", OSError),
        ("interrupt", KeyboardInterrupt),
    ],
)
def test_atomic_json_update_cleans_temps_on_failure(
    failure_kind: str,
    expected_exception: type[BaseException],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "ledger.json"
    real_fsync = benchmark.os.fsync
    fsync_calls = 0

    if failure_kind in {"write", "interrupt"}:
        def fail_write(_fd: int, _data: bytes) -> int:
            if failure_kind == "interrupt":
                raise KeyboardInterrupt
            raise OSError("synthetic atomic write failure")

        monkeypatch.setattr(benchmark.os, "write", fail_write)
    elif failure_kind == "file_fsync":
        monkeypatch.setattr(
            benchmark.os,
            "fsync",
            lambda _fd: (_ for _ in ()).throw(OSError("synthetic file fsync failure")),
        )
    elif failure_kind == "replace":
        monkeypatch.setattr(
            benchmark.os,
            "replace",
            lambda _source, _destination: (_ for _ in ()).throw(
                OSError("synthetic replace failure")
            ),
        )
    else:
        def fail_directory_fsync(fd: int) -> None:
            nonlocal fsync_calls
            fsync_calls += 1
            if fsync_calls == 2:
                raise OSError("synthetic directory fsync failure")
            real_fsync(fd)

        monkeypatch.setattr(benchmark.os, "fsync", fail_directory_fsync)

    with pytest.raises(expected_exception):
        benchmark._atomic_json_update(path, {"state": failure_kind})

    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_atomic_json_update_cleans_consumed_temp_after_replace_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ledger.json"
    real_replace = benchmark.os.replace

    def replace_then_interrupt(source: Path, destination: Path) -> None:
        real_replace(source, destination)
        raise InterruptedError("synthetic interruption after replace")

    monkeypatch.setattr(benchmark.os, "replace", replace_then_interrupt)

    with pytest.raises(InterruptedError):
        benchmark._atomic_json_update(path, {"state": "replaced"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "replaced"}
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_matching_process_check_requires_exact_owner_argv_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = benchmark.LAUNCH_COMMAND
    candidate_argv = [
        "/opt/homebrew/.../Resources/Python",
        *expected[1:],
    ]
    candidate_command = benchmark.shlex.join(candidate_argv)
    candidate_signature = benchmark._platform_process_signature(candidate_command)
    parent_argv = [str(tmp_path / ".venv" / "bin" / "python"), *expected[1:]]
    parent_command = benchmark.shlex.join(parent_argv)
    parent_signature = benchmark._platform_process_signature(parent_command)
    monkeypatch.setattr(
        benchmark,
        "_process_snapshot",
        lambda: [
            {
                "pid": 123,
                "parent_pid": 1,
                "user": "synthetic-owner",
                "argv": candidate_argv,
                "command": candidate_command,
                "platform_signature": candidate_signature,
            }
        ],
    )
    monkeypatch.setattr(benchmark, "_process_cwd", lambda _pid: tmp_path.resolve())
    verified_parent_snapshot = {
        "pid": 999,
        "parent_pid": 1,
        "user": "synthetic-owner",
        "argv": parent_argv,
        "command": parent_command,
        "platform_signature": parent_signature,
        "cwd": str(tmp_path.resolve()),
    }

    matches = benchmark._matching_processes(
        expected,
        tmp_path,
        owner="synthetic-owner",
        exclude_pids=(),
        verified_parent_snapshot=verified_parent_snapshot,
    )
    assert matches[0]["pid"] == 123
    assert matches[0]["platform_signature"] == candidate_signature
    assert candidate_signature != parent_signature
    assert benchmark._matching_processes(
        expected,
        tmp_path,
        owner="synthetic-owner",
        exclude_pids=(123,),
        verified_parent_snapshot=verified_parent_snapshot,
    ) == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong-owner", "owner"),
        ("wrong-argv", "argv"),
        ("missing-command", "command snapshot"),
        ("wrong-pid", "missing or ambiguous"),
        ("ambiguous", "missing or ambiguous"),
        ("unreadable-cwd", "cwd"),
    ],
)
def test_verified_parent_snapshot_rejects_identity_drift(
    mutation: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = benchmark.LAUNCH_COMMAND
    platform_argv = [
        "/opt/homebrew/.../Resources/Python",
        *expected[1:],
    ]
    platform_command = benchmark.shlex.join(platform_argv)
    process: dict[str, Any] = {
        "pid": 123,
        "parent_pid": 1,
        "user": "synthetic-owner",
        "argv": platform_argv,
        "command": platform_command,
        "platform_signature": benchmark._platform_process_signature(platform_command),
    }
    expected_owner = "synthetic-owner"
    if mutation == "wrong-owner":
        process["user"] = "other-owner"
    elif mutation == "wrong-argv":
        process["argv"] = [*platform_argv, "--drift"]
        process["command"] = benchmark.shlex.join(process["argv"])
        process["platform_signature"] = benchmark._platform_process_signature(
            process["command"]
        )
    elif mutation == "missing-command":
        process.pop("command")
    elif mutation == "wrong-pid":
        process["pid"] = 456
    elif mutation == "unreadable-cwd":
        monkeypatch.setattr(benchmark, "_process_cwd", lambda _pid: None)
    processes = [process, process.copy()] if mutation == "ambiguous" else [process]
    monkeypatch.setattr(benchmark, "_process_snapshot", lambda: processes)
    if mutation != "unreadable-cwd":
        monkeypatch.setattr(benchmark, "_process_cwd", lambda _pid: tmp_path.resolve())

    with pytest.raises(RuntimeError, match=message):
        benchmark._capture_verified_parent_process_snapshot(
            123, expected, tmp_path, expected_owner
        )


def test_non_consuming_dummy_process_snapshot_proof(tmp_path: Path) -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(2)"],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 2.0
        observed: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            observed = next(
                (item for item in benchmark._process_snapshot() if item["pid"] == process.pid),
                None,
            )
            if observed is not None:
                break
            time.sleep(0.02)
        if observed is None:
            pytest.fail("dummy process did not appear in the platform snapshot")
        assert observed["platform_signature"] == benchmark._platform_process_signature(
            observed["command"]
        )
        verified = benchmark._capture_verified_parent_process_snapshot(
            process.pid,
            tuple(observed["argv"]),
            tmp_path,
            observed["user"],
        )
        assert verified["pid"] == process.pid
        assert verified["cwd"] == str(tmp_path.resolve())
    finally:
        process.terminate()
        process.wait(timeout=2)


def _contract_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    executable: Path,
    prefix: Path,
    base_prefix: Path,
) -> Path:
    root = tmp_path / "worktree"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text("[build-system]\n", encoding="utf-8")
    monkeypatch.setattr(benchmark, "ROOT", root)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "base_prefix", str(base_prefix))
    monkeypatch.setattr(sys, "argv", list(benchmark.LAUNCH_COMMAND[1:]))
    monkeypatch.setattr(
        benchmark,
        "_preflight_launch_paths",
        lambda _root: {
            "output": root / "output.json",
            "ledger": root / "ledger.json",
            "stdout": root / "stdout.txt",
            "stderr": root / "stderr.txt",
        },
    )
    platform_argv = [
        "/opt/homebrew/.../Resources/Python",
        *benchmark.LAUNCH_COMMAND[1:],
    ]
    platform_command = benchmark.shlex.join(platform_argv)
    monkeypatch.setattr(
        benchmark,
        "_capture_verified_parent_process_snapshot",
        lambda *_args, **_kwargs: {
            "pid": benchmark.os.getpid(),
            "parent_pid": 1,
            "user": benchmark.getpass.getuser(),
            "argv": platform_argv,
            "command": platform_command,
            "platform_signature": benchmark._platform_process_signature(platform_command),
            "cwd": str(root.resolve()),
        },
    )
    monkeypatch.setattr(benchmark, "_matching_processes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(benchmark, "_fixture_identity", lambda: {"synthetic": True})
    monkeypatch.setattr(benchmark, "_disk_available_bytes", lambda _root: 1)
    for name, value in benchmark.LAUNCH_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    for name in benchmark.FORBIDDEN_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    return root


def test_launch_contract_accepts_only_lexical_worktree_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "worktree"
    executable = root / ".venv" / "bin" / "python"
    _contract_fixture(
        tmp_path,
        monkeypatch,
        executable=executable,
        prefix=root / ".venv",
        base_prefix=tmp_path / "base",
    )

    launch = benchmark._verify_launch_contract(root)

    assert launch["interpreter"] == str(executable)
    assert launch["venv_prefix"] == str(root / ".venv")


def test_launch_contract_rejects_duplicate_platform_signature_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "worktree"
    executable = root / ".venv" / "bin" / "python"
    _contract_fixture(
        tmp_path,
        monkeypatch,
        executable=executable,
        prefix=root / ".venv",
        base_prefix=tmp_path / "base",
    )
    monkeypatch.setattr(
        benchmark,
        "_matching_processes",
        lambda *_args, **_kwargs: [
            {"pid": 456, "platform_signature": "same"},
            {"pid": 789, "platform_signature": "same"},
        ],
    )

    with pytest.raises(RuntimeError, match="matching launch process already exists"):
        benchmark._verify_launch_contract(root)


def test_launch_contract_rejects_ambiguous_alternate_argv0_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "worktree"
    executable = root / ".venv" / "bin" / "python"
    real_matching_processes = benchmark._matching_processes
    _contract_fixture(
        tmp_path,
        monkeypatch,
        executable=executable,
        prefix=root / ".venv",
        base_prefix=tmp_path / "base",
    )
    monkeypatch.setattr(benchmark, "_matching_processes", real_matching_processes)
    argv0s = (
        "/opt/homebrew/.../Resources/Python",
        str(executable),
    )
    processes = []
    for pid, argv0 in zip((456, 789), argv0s, strict=True):
        argv = [argv0, *benchmark.LAUNCH_COMMAND[1:]]
        command = benchmark.shlex.join(argv)
        processes.append(
            {
                "pid": pid,
                "parent_pid": 1,
                "user": benchmark.getpass.getuser(),
                "argv": argv,
                "command": command,
                "platform_signature": benchmark._platform_process_signature(command),
            }
        )
    monkeypatch.setattr(benchmark, "_process_snapshot", lambda: processes)
    monkeypatch.setattr(benchmark, "_process_cwd", lambda _pid: root.resolve())

    with pytest.raises(RuntimeError, match="matching launch process already exists"):
        benchmark._verify_launch_contract(root)


@pytest.mark.parametrize(
    ("case", "executable_kind", "prefix_kind", "base_kind", "message"),
    [
        ("base-interpreter", "base", "expected", "base", "lexical"),
        ("resolved-equivalent-symlink", "symlink", "expected", "base", "lexical"),
        ("wrong-worktree", "other-worktree", "other", "base", "lexical"),
        ("prefix-mismatch", "expected", "other", "base", "sys.prefix"),
        ("base-prefix-equality", "expected", "expected", "expected", "running inside"),
    ],
)
def test_launch_contract_rejects_interpreter_identity_tricks(
    case: str,
    executable_kind: str,
    prefix_kind: str,
    base_kind: str,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "worktree"
    expected = root / ".venv" / "bin" / "python"
    other_root = tmp_path / "other-worktree"
    (other_root / ".venv" / "bin").mkdir(parents=True)
    other_executable = other_root / ".venv" / "bin" / "python"
    other_executable.write_text("", encoding="utf-8")
    base = tmp_path / "base-python"
    base.write_text("", encoding="utf-8")
    if executable_kind == "symlink":
        symlink = tmp_path / "base-python-symlink"
        symlink.symlink_to(expected)
        executable = symlink
    elif executable_kind == "other-worktree":
        executable = other_executable
    elif executable_kind == "base":
        executable = base
    else:
        executable = expected
    prefix = {
        "expected": root / ".venv",
        "other": other_root / ".venv",
    }[prefix_kind]
    base_prefix = {
        "expected": root / ".venv",
        "base": base,
    }[base_kind]
    _contract_fixture(
        tmp_path,
        monkeypatch,
        executable=executable,
        prefix=prefix,
        base_prefix=base_prefix,
    )

    with pytest.raises(RuntimeError, match=message):
        benchmark._verify_launch_contract(root)


def _overlay_test_authority(state: str = "worker_prequalification") -> dict[str, Any]:
    return {
        "schema": benchmark.SHARED_OVERLAY_SCHEMA,
        "authority_version": 1,
        "authority_base_sha": "cf44f4fdd3f54ad53263b5e744203be468fbe5ca",
        "status": "permitted_not_accepted",
        "states": {
            "successor": {
                "status": "permitted_not_accepted",
                "runtime_acceptance": "not_claimed",
                "launch_authorized": False,
                "artifacts": [
                    {
                        "path": "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
                        "sha256": "a" * 64,
                        "presence": "required",
                    },
                    {
                        "path": "scripts/benchmark_ck07r1_lifecycle_scale.py",
                        "sha256": "b" * 64,
                        "presence": "required",
                    },
                    {
                        "path": "tests/agent_kernel/publication/test_lifecycle_scale.py",
                        "sha256": "c" * 64,
                        "presence": "required",
                    },
                ],
            }
        },
        "non_consuming_invariants": {
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
        },
    }


def _overlay_test_root(tmp_path: Path) -> None:
    for relative in (
        benchmark.SHARED_OVERLAY_AUTHORITY_RELATIVE,
        benchmark.SHARED_OVERLAY_SCHEMA_RELATIVE,
        benchmark.SHARED_OVERLAY_VERIFIER_RELATIVE,
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


def _recovery_test_root(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    for relative in (
        benchmark.PRESERVED_V1_LEDGER_RELATIVE,
        Path("src/codex_usage_tracker/agent_kernel/publication/preparation.py"),
        Path("scripts/benchmark_ck07r1_lifecycle_scale.py"),
        Path("tests/agent_kernel/publication/test_lifecycle_scale.py"),
        *benchmark.HISTORICAL_SHARED_OVERLAY_RELATIVES,
    ):
        source = benchmark.ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    for relative in (
        benchmark.PRELAUNCH_RECOVERY_AUTHORITY_RELATIVE,
        benchmark.PRELAUNCH_RECOVERY_SCHEMA_RELATIVE,
    ):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    authority = {
        "schema": benchmark.PRELAUNCH_RECOVERY_SCHEMA,
        "authority_version": 1,
        "status": "permitted_not_accepted",
        "decision": {
            "launch_authorized_in_authority_task": False,
            "implementation_acceptance": "not_claimed",
            "runtime_acceptance": "not_claimed",
        },
        "recovery_transition": {
            "old_shared_overlay": "immutable_historical_predecessor_evidence",
            "live_corrected_cohort_authority": "this_versioned_recovery_authority_only",
            "launched_process_retry": False,
            "restart": False,
            "replacement": False,
            "refund": False,
        },
        "immutable_authorities": [
            {
                "path": str(relative),
                "sha256": benchmark._sha256(tmp_path / relative),
            }
            for relative in benchmark.HISTORICAL_SHARED_OVERLAY_RELATIVES
        ],
        "preserved_v1_ledger": benchmark._preserved_v1_ledger_identity(tmp_path),
        "candidate_cohort": benchmark._candidate_cohort(tmp_path),
        "v2_paths": {
            "output": str(benchmark.RUN_OUTPUT_RELATIVE),
            "ledger": str(benchmark.RUN_LEDGER_RELATIVE),
            "stdout": str(benchmark.RUN_STDOUT_RELATIVE),
            "stderr": str(benchmark.RUN_STDERR_RELATIVE),
        },
        "run_token": {
            "id": benchmark.RUN_TOKEN_ID,
            "maximum_new_end_to_end_runs": 1,
            "status": benchmark.RUN_TOKEN_STATUS,
            "token_consumed": False,
            "refund": False,
            "retry": "none",
            "restart": "none",
            "replacement": "none",
            "successful_launches_observed": 0,
            "new_recovery_invocations_permitted": 1,
        },
    }
    return tmp_path, authority


class _RecoveryVerifier:
    authority: dict[str, Any]

    @classmethod
    def verify_prelaunch_recovery(cls, _root: Path) -> tuple[dict[str, Any], str]:
        return cls.authority, "prelaunch_recovery_verified"


def test_prelaunch_recovery_verification_binds_v1_witness_cohort_and_v2_paths(
    tmp_path: Path,
) -> None:
    root, authority = _recovery_test_root(tmp_path)
    _RecoveryVerifier.authority = authority

    result = benchmark._verify_prelaunch_recovery(root, verifier=_RecoveryVerifier)

    assert result["state"] == "prelaunch_recovery_verified"
    assert result["preserved_v1_ledger"]["sha256"] == (
        benchmark.PRESERVED_V1_LEDGER_SHA256
    )
    assert result["preserved_v1_ledger"]["token_consumed"] is False
    assert result["preserved_v1_ledger"]["matching_processes"] == []
    assert result["candidate_cohort"] == authority["candidate_cohort"]
    assert result["v2_paths"] == authority["v2_paths"]
    assert result["historical_shared_overlay"] == authority["immutable_authorities"]


@pytest.mark.parametrize(
    "binding",
    ["preserved_v1_ledger", "candidate_cohort", "v2_paths", "immutable_authorities"],
)
def test_prelaunch_recovery_rejects_binding_drift(
    binding: str, tmp_path: Path
) -> None:
    root, authority = _recovery_test_root(tmp_path)
    authority = copy.deepcopy(authority)
    if binding == "preserved_v1_ledger":
        authority[binding]["token_consumed"] = True
    elif binding == "candidate_cohort":
        authority[binding][1]["sha256"] = "0" * 64
    elif binding == "v2_paths":
        authority[binding]["ledger"] = "output/ck07r1/other.launch-token.json"
    else:
        authority[binding][0]["sha256"] = "0" * 64
    _RecoveryVerifier.authority = authority

    with pytest.raises(RuntimeError, match="binding drifted"):
        benchmark._verify_prelaunch_recovery(root, verifier=_RecoveryVerifier)


def test_prelaunch_recovery_requires_merged_authority_and_verifier(tmp_path: Path) -> None:
    class UnusedVerifier:
        @staticmethod
        def verify_prelaunch_recovery(_root: Path) -> tuple[dict[str, Any], str]:
            pytest.fail("verifier must not run without authority/schema files")

    with pytest.raises(RuntimeError, match="authority/schema"):
        benchmark._verify_prelaunch_recovery(tmp_path, verifier=UnusedVerifier())


def test_overlay_verification_rejects_unauthorized_live_state(tmp_path: Path) -> None:
    _overlay_test_root(tmp_path)

    class UnauthorizedVerifier:
        @staticmethod
        def verify_shared_successor_overlay(_root: Path) -> tuple[dict[str, Any], str]:
            return _overlay_test_authority(), "authority_main"

    with pytest.raises(RuntimeError, match="worker_prequalification"):
        benchmark._verify_overlay_cohort(tmp_path, verifier=UnauthorizedVerifier())


def test_overlay_verification_rejects_mixed_cohort(tmp_path: Path) -> None:
    _overlay_test_root(tmp_path)

    class MixedVerifier:
        @staticmethod
        def verify_shared_successor_overlay(_root: Path) -> tuple[dict[str, Any], str]:
            raise ValueError("mixed, partial, historical, or unbound CK-07R1 cohort")

    with pytest.raises(RuntimeError, match="mixed, partial"):
        benchmark._verify_overlay_cohort(tmp_path, verifier=MixedVerifier())


def test_old_overlay_cannot_authorize_corrected_cohort_without_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = {
        name: tmp_path / f"{name}.json"
        for name in ("output", "ledger", "stdout", "stderr")
    }
    monkeypatch.setattr(
        benchmark,
        "_verify_launch_contract",
        lambda: {"paths": paths},
    )
    monkeypatch.setattr(
        benchmark,
        "_verify_overlay_cohort",
        lambda: {"schema": benchmark.SHARED_OVERLAY_SCHEMA, "state": "worker_prequalification"},
    )
    monkeypatch.setattr(
        benchmark,
        "_verify_prelaunch_recovery",
        lambda: (_ for _ in ()).throw(ValueError("recovery authority rejected corrected cohort")),
    )
    exclusive_writes: list[Path] = []
    monkeypatch.setattr(
        benchmark,
        "_exclusive_write",
        lambda path, _data: exclusive_writes.append(path),
    )
    monkeypatch.setattr(
        benchmark.os,
        "fork",
        lambda: pytest.fail("fork must not occur before recovery verification"),
    )

    with pytest.raises(ValueError, match="recovery authority rejected"):
        benchmark._launch_exact()

    assert exclusive_writes == []
    assert all(not path.exists() for path in paths.values())


def test_prelaunch_recovery_verification_precedes_ledger_fork_and_token_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = {
        name: tmp_path / f"{name}.json"
        for name in ("output", "ledger", "stdout", "stderr")
    }
    monkeypatch.setattr(
        benchmark,
        "_verify_launch_contract",
        lambda: {"paths": paths},
    )
    monkeypatch.setattr(
        benchmark,
        "_verify_overlay_cohort",
        lambda: pytest.fail("old overlay must not be a live corrected-cohort gate"),
    )
    monkeypatch.setattr(
        benchmark,
        "_verify_prelaunch_recovery",
        lambda: (_ for _ in ()).throw(ValueError("recovery witness rejected")),
    )
    exclusive_writes: list[Path] = []
    monkeypatch.setattr(
        benchmark,
        "_exclusive_write",
        lambda path, _data: exclusive_writes.append(path),
    )
    monkeypatch.setattr(
        benchmark.os,
        "fork",
        lambda: pytest.fail("fork must not occur before recovery verification"),
    )

    with pytest.raises(ValueError, match="recovery witness rejected"):
        benchmark._launch_exact()

    assert exclusive_writes == []
    assert all(not path.exists() for path in paths.values())


def _fake_launch_contract(tmp_path: Path) -> dict[str, Any]:
    return {
        "argv": list(benchmark.LAUNCH_COMMAND),
        "cwd": str(tmp_path.resolve()),
        "owner": "synthetic-owner",
        "interpreter": "synthetic-python",
        "venv_prefix": str(tmp_path / ".venv"),
        "base_prefix": "synthetic-base-python",
        "environment": dict(benchmark.LAUNCH_ENVIRONMENT),
        "output_path": str(benchmark.RUN_OUTPUT_RELATIVE),
        "fixture_identity": {},
        "disk_available_bytes_before_launch": 1,
        "matching_processes": [],
        "paths": {
            "output": tmp_path / "output.json",
            "ledger": tmp_path / "ledger.json",
            "stdout": tmp_path / "stdout.txt",
            "stderr": tmp_path / "stderr.txt",
        },
    }


def _patch_fake_process_boundary(
    launch: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform_argv = [
        "/opt/homebrew/.../Resources/Python",
        *benchmark.LAUNCH_COMMAND[1:],
    ]
    platform_command = benchmark.shlex.join(platform_argv)
    snapshot = {
        "pid": benchmark.os.getpid(),
        "parent_pid": 1,
        "user": "synthetic-owner",
        "argv": platform_argv,
        "command": platform_command,
        "platform_signature": benchmark._platform_process_signature(platform_command),
        "cwd": str(tmp_path.resolve()),
    }
    launch["verified_parent_process_snapshot"] = snapshot
    monkeypatch.setattr(
        benchmark,
        "_capture_verified_parent_process_snapshot",
        lambda *_args, **_kwargs: snapshot,
    )
    monkeypatch.setattr(benchmark, "_matching_processes", lambda *_args, **_kwargs: [])


@pytest.mark.parametrize("failure_point", ["token_persistence", "child_release"])
def test_post_launch_exceptions_are_never_classified_prelaunch_failed(
    failure_point: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = _fake_launch_contract(tmp_path)
    _patch_fake_process_boundary(launch, tmp_path, monkeypatch)
    paths = launch["paths"]
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(benchmark, "_verify_launch_contract", lambda: launch)
    monkeypatch.setattr(benchmark, "_verify_prelaunch_recovery", lambda: {"verification": "passed"})
    monkeypatch.setattr(benchmark.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(benchmark.os, "fork", lambda: 123)
    monkeypatch.setattr(benchmark.os, "close", lambda _fd: None)
    monkeypatch.setattr(benchmark, "_reap_child", lambda _pid: None)
    monkeypatch.setattr(
        benchmark,
        "_observe_child_start",
        lambda _pid, _launch, parent_pid: {
            "pid": 123,
            "parent_pid": parent_pid,
            "user": "synthetic-owner",
            "argv": list(benchmark.LAUNCH_COMMAND),
            "cwd": str(tmp_path.resolve()),
        },
    )
    real_update = benchmark._ledger_update
    update_calls = 0

    def update(path: Path, value: dict[str, Any]) -> None:
        nonlocal update_calls
        update_calls += 1
        if failure_point == "token_persistence" and update_calls == 1:
            raise OSError("synthetic token persistence failure")
        real_update(path, value)

    monkeypatch.setattr(benchmark, "_ledger_update", update)
    if failure_point == "child_release":
        real_write = benchmark.os.write

        def fail_child_release(fd: int, data: bytes) -> int:
            if fd == 11:
                raise OSError("synthetic child release failure")
            return real_write(fd, data)

        monkeypatch.setattr(
            benchmark.os,
            "write",
            fail_child_release,
        )

    with pytest.raises(OSError):
        benchmark._launch_exact()

    persisted = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    assert persisted["state"] == "failed_after_launch"
    assert persisted["token_consumed"] is True
    assert persisted["failure"]["stage"] == "post_launch_handshake"
    assert persisted["state"] != "prelaunch_failed"


def test_initial_token_persistence_failure_is_terminal_and_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = _fake_launch_contract(tmp_path)
    _patch_fake_process_boundary(launch, tmp_path, monkeypatch)
    paths = launch["paths"]
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(benchmark, "_verify_launch_contract", lambda: launch)
    monkeypatch.setattr(benchmark, "_verify_prelaunch_recovery", lambda: {"verification": "passed"})
    monkeypatch.setattr(benchmark.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(benchmark.os, "fork", lambda: 123)
    monkeypatch.setattr(benchmark.os, "close", lambda _fd: None)
    monkeypatch.setattr(benchmark, "_reap_child", lambda _pid: None)
    monkeypatch.setattr(
        benchmark,
        "_observe_child_start",
        lambda _pid, _launch, parent_pid: {
            "pid": 123,
            "parent_pid": parent_pid,
            "user": "synthetic-owner",
            "argv": list(benchmark.LAUNCH_COMMAND),
            "cwd": str(tmp_path.resolve()),
        },
    )
    real_replace = benchmark.os.replace
    replace_calls = 0

    def fail_initial_replace(source: Path, destination: Path) -> None:
        nonlocal replace_calls
        replace_calls += 1
        if replace_calls == 1:
            raise OSError("synthetic initial token persistence failure")
        real_replace(source, destination)

    monkeypatch.setattr(benchmark.os, "replace", fail_initial_replace)

    with pytest.raises(OSError, match="synthetic initial token persistence failure"):
        benchmark._launch_exact()

    persisted = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    assert persisted["state"] == "failed_after_launch"
    assert persisted["token_consumed"] is True
    assert persisted["retry_allowed"] is False
    assert persisted["restart_allowed"] is False
    assert persisted["replacement_allowed"] is False
    assert replace_calls == 2
    assert list(paths["ledger"].parent.glob(f".{paths['ledger'].name}.*.tmp")) == []


@pytest.mark.parametrize("failure_kind", ["keyboard_interrupt", "sigint", "sigterm", "wait_error"])
def test_wait_interruptions_are_reaped_before_terminal_failure(
    failure_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = _fake_launch_contract(tmp_path)
    _patch_fake_process_boundary(launch, tmp_path, monkeypatch)
    paths = launch["paths"]
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(benchmark, "_verify_launch_contract", lambda: launch)
    monkeypatch.setattr(benchmark, "_verify_prelaunch_recovery", lambda: {"verification": "passed"})
    monkeypatch.setattr(benchmark.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(benchmark.os, "fork", lambda: 123)
    monkeypatch.setattr(benchmark.os, "close", lambda _fd: None)
    real_write = benchmark.os.write
    monkeypatch.setattr(
        benchmark.os,
        "write",
        lambda fd, data: len(data) if fd == 11 else real_write(fd, data),
    )
    monkeypatch.setattr(
        benchmark,
        "_observe_child_start",
        lambda _pid, _launch, parent_pid: {
            "pid": 123,
            "parent_pid": parent_pid,
            "user": "synthetic-owner",
            "argv": list(benchmark.LAUNCH_COMMAND),
            "cwd": str(tmp_path.resolve()),
        },
    )
    cleanup: list[int] = []
    monkeypatch.setattr(benchmark, "_reap_child", lambda pid: cleanup.append(pid))
    sequence: list[str] = []
    real_update = benchmark._ledger_update

    def update(path: Path, value: dict[str, Any]) -> None:
        sequence.append(value["state"])
        real_update(path, value)

    monkeypatch.setattr(benchmark, "_ledger_update", update)

    def wait_failure(_pid: int) -> tuple[int, int, object, bool]:
        if failure_kind == "keyboard_interrupt":
            raise KeyboardInterrupt
        if failure_kind == "sigint":
            benchmark._parent_signal_handler(signal.SIGINT, None)
        if failure_kind == "sigterm":
            benchmark._parent_signal_handler(signal.SIGTERM, None)
        raise OSError("synthetic wait failure")

    monkeypatch.setattr(benchmark, "_wait_for_child", wait_failure)

    expected_exception = {
        "keyboard_interrupt": KeyboardInterrupt,
        "sigint": KeyboardInterrupt,
        "sigterm": benchmark._ParentChildSignal,
        "wait_error": OSError,
    }[failure_kind]
    with pytest.raises(expected_exception):
        benchmark._launch_exact()

    persisted = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    assert cleanup == [123]
    assert sequence[-1] == "failed_after_launch"
    assert sequence.index("launched_consumed") < sequence.index("failed_after_launch")
    assert persisted["state"] == "failed_after_launch"
    assert persisted["token_consumed"] is True
    assert persisted["retry_allowed"] is False
    assert persisted["restart_allowed"] is False
    assert persisted["replacement_allowed"] is False


@pytest.mark.parametrize(
    "failure",
    [
        KeyboardInterrupt(),
        benchmark._ParentChildSignal(signal.SIGINT),
        benchmark._ParentChildSignal(signal.SIGTERM),
        OSError("synthetic release read failure"),
    ],
    ids=("keyboard-interrupt", "sigint", "sigterm", "read-error"),
)
def test_child_entry_pre_release_failures_exit_71_without_real_child(
    failure: BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ChildExit(BaseException):
        pass

    exits: list[int] = []

    def fail_wait(_read_fd: int, _write_fd: int) -> bool:
        raise failure

    def fake_exit(code: int) -> None:
        exits.append(code)
        raise ChildExit

    monkeypatch.setattr(benchmark, "_child_wait_for_release", fail_wait)
    monkeypatch.setattr(benchmark.os, "_exit", fake_exit)

    with pytest.raises(ChildExit):
        benchmark._child_entry({}, {}, 10, 11)

    assert exits == [71]


@pytest.mark.parametrize(
    "read_failure",
    [
        KeyboardInterrupt(),
        benchmark._ParentChildSignal(signal.SIGINT),
        benchmark._ParentChildSignal(signal.SIGTERM),
        OSError("synthetic release read failure"),
    ],
    ids=("keyboard-interrupt", "sigint", "sigterm", "read-error"),
)
def test_child_release_ignores_signals_and_contains_read_failures(
    read_failure: BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed: list[tuple[int, object]] = []
    closed: list[int] = []

    monkeypatch.setattr(benchmark.signal, "getsignal", lambda _number: "previous")
    monkeypatch.setattr(
        benchmark.signal,
        "signal",
        lambda number, handler: installed.append((number, handler)),
    )
    monkeypatch.setattr(benchmark.os, "close", lambda fd: closed.append(fd))

    def fail_read(_fd: int, _size: int) -> bytes:
        raise read_failure

    monkeypatch.setattr(benchmark.os, "read", fail_read)

    assert benchmark._child_wait_for_release(10, 11) is False
    assert (signal.SIGINT, signal.SIG_IGN) in installed
    assert (signal.SIGTERM, signal.SIG_IGN) in installed
    assert closed == [11, 10]


@pytest.mark.parametrize("pid", [0, -1])
def test_parent_reap_rejects_nonpositive_pid_without_process_group_signal(
    pid: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(
        benchmark.os,
        "kill",
        lambda child_pid, _signal: calls.append(("kill", child_pid)),
    )
    monkeypatch.setattr(
        benchmark.os,
        "wait4",
        lambda child_pid, _options: calls.append(("wait4", child_pid)),
    )

    operations = (
        lambda: benchmark._bounded_reap(pid, 0.0),
        lambda: benchmark._terminate_and_reap_child(pid),
        lambda: benchmark._wait_for_child(pid),
        lambda: benchmark._reap_child(pid),
    )
    for operation in operations:
        with pytest.raises(ValueError, match="child pid must be positive"):
            operation()

    assert calls == []


def _completion_fixture(
    tmp_path: Path,
    *,
    payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], Path, dict[str, Path]]:
    paths = {
        "output": tmp_path / "output.json",
        "ledger": tmp_path / "ledger.json",
        "stdout": tmp_path / "stdout.txt",
        "stderr": tmp_path / "stderr.txt",
    }
    paths["output"].write_text(
        json.dumps(
            payload
            or {
                "schema": benchmark.SCHEMA,
                "workload_transition_digest": "a" * 64,
                "publication_digest": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    paths["stdout"].write_text("", encoding="utf-8")
    paths["stderr"].write_text("", encoding="utf-8")
    ledger = {
        "token_consumed": True,
        "token_status": "consumed",
        "state": "launched_consumed",
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
        "process_states": [{"state": "launched_consumed"}],
    }
    benchmark._exclusive_write(paths["ledger"], json.dumps(ledger).encode() + b"\n")
    launch = {
        "fixture_identity": {"synthetic": True},
        "prelaunch_recovery": {
            "schema": benchmark.PRELAUNCH_RECOVERY_SCHEMA,
            "state": "prelaunch_recovery_verified",
        },
    }
    return launch, paths["ledger"], paths


def _finalize_child_result(
    launch: dict[str, Any],
    ledger_path: Path,
    paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    monkeypatch.setattr(benchmark, "_rss_from_usage", lambda _usage: 1)
    monkeypatch.setattr(benchmark, "_disk_available_bytes", lambda _root: 1)
    return benchmark._finalize_child_result(
        {
            "token_consumed": True,
            "token_status": "consumed",
            "state": "launched_consumed",
            "retry_allowed": False,
            "restart_allowed": False,
            "replacement_allowed": False,
            "process_states": [{"state": "launched_consumed"}],
        },
        ledger_path,
        paths,
        launch,
        exit_code=0,
        status=0,
        usage=object(),
        timed_out=False,
        completed_at_utc="2026-08-11T00:00:00Z",
        launched_monotonic_ns=0,
    )


def test_receipt_validation_precedes_durable_completed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch, ledger_path, paths = _completion_fixture(tmp_path)
    events: list[str] = []

    def validate(
        _payload: dict[str, Any],
        _fixture: dict[str, Any],
        _prelaunch_recovery: dict[str, Any],
        **_kwargs: object,
    ) -> None:
        events.append("validate")
        assert json.loads(ledger_path.read_text(encoding="utf-8"))["state"] == (
            "launched_consumed"
        )

    real_update = benchmark._ledger_update

    def update(path: Path, value: dict[str, Any]) -> None:
        events.append(value["state"])
        real_update(path, value)

    monkeypatch.setattr(benchmark, "_validate_receipt", validate)
    monkeypatch.setattr(benchmark, "_ledger_update", update)

    assert _finalize_child_result(launch, ledger_path, paths, monkeypatch) == 0
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert events == ["validate", "completed"]
    assert persisted["state"] == "completed"
    assert persisted["receipt"]["schema"] == benchmark.SCHEMA


@pytest.mark.parametrize("failure_seam", ["validation", "receipt_construction", "finalization"])
def test_receipt_ordering_failures_never_durably_complete(
    failure_seam: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "schema": benchmark.SCHEMA,
        "workload_transition_digest": "a" * 64,
    }
    if failure_seam != "receipt_construction":
        payload["publication_digest"] = "b" * 64
    launch, ledger_path, paths = _completion_fixture(tmp_path, payload=payload)
    real_update = benchmark._ledger_update
    completed_attempts = 0

    def validate(
        _payload: dict[str, Any],
        _fixture: dict[str, Any],
        _prelaunch_recovery: dict[str, Any],
        **_kwargs: object,
    ) -> None:
        if failure_seam == "validation":
            raise ValueError("synthetic receipt validation interruption")

    def update(path: Path, value: dict[str, Any]) -> None:
        nonlocal completed_attempts
        if failure_seam == "finalization" and value["state"] == "completed":
            completed_attempts += 1
            if completed_attempts == 1:
                real_update(path, value)
                raise InterruptedError("synthetic final ledger interruption")
        real_update(path, value)

    monkeypatch.setattr(benchmark, "_validate_receipt", validate)
    monkeypatch.setattr(benchmark, "_ledger_update", update)

    assert _finalize_child_result(launch, ledger_path, paths, monkeypatch) == 70
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "failed_after_launch"
    assert persisted["state"] != "completed"
    assert persisted["process_states"][-1]["state"] == "failed_after_launch"
    if failure_seam == "finalization":
        assert completed_attempts == 1


@pytest.mark.parametrize("signal_phase", ["evidence", "completed_persistence"])
def test_sigterm_after_bounded_reap_is_terminal_and_handlers_restore_last(
    signal_phase: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch = _fake_launch_contract(tmp_path)
    _patch_fake_process_boundary(launch, tmp_path, monkeypatch)
    paths = launch["paths"]
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    paths["output"].write_text(
        json.dumps(
            {
                "schema": benchmark.SCHEMA,
                "workload_transition_digest": "a" * 64,
                "publication_digest": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    paths["stdout"].write_text("", encoding="utf-8")
    paths["stderr"].write_text("", encoding="utf-8")

    monkeypatch.setattr(benchmark, "_verify_launch_contract", lambda: launch)
    monkeypatch.setattr(benchmark, "_verify_prelaunch_recovery", lambda: {"verification": "passed"})
    monkeypatch.setattr(benchmark.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(benchmark.os, "fork", lambda: 123)
    real_close = benchmark.os.close

    def close(fd: int) -> None:
        if fd in {10, 11}:
            return
        real_close(fd)

    monkeypatch.setattr(benchmark.os, "close", close)
    real_write = benchmark.os.write
    monkeypatch.setattr(
        benchmark.os,
        "write",
        lambda fd, data: len(data) if fd == 11 else real_write(fd, data),
    )
    monkeypatch.setattr(
        benchmark,
        "_observe_child_start",
        lambda _pid, _launch, parent_pid: {
            "pid": 123,
            "parent_pid": parent_pid,
            "user": "synthetic-owner",
            "argv": list(benchmark.LAUNCH_COMMAND),
            "cwd": str(tmp_path.resolve()),
        },
    )
    events: list[str] = []

    def wait_for_child(_pid: int) -> tuple[int, int, object, bool]:
        events.append("bounded_reap_complete")
        return 123, 0, object(), False

    monkeypatch.setattr(benchmark, "_wait_for_child", wait_for_child)
    monkeypatch.setattr(benchmark, "_rss_from_usage", lambda _usage: 1)
    monkeypatch.setattr(benchmark, "_disk_available_bytes", lambda _root: 1)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def raise_sigterm_while_active() -> None:
        events.append("sigterm_requested")
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is benchmark._parent_signal_handler
        handler(signal.SIGTERM, None)

    evidence = {
        "stdout_path": str(benchmark.RUN_STDOUT_RELATIVE),
        "stdout_sha256": "a" * 64,
        "stderr_path": str(benchmark.RUN_STDERR_RELATIVE),
        "stderr_sha256": "b" * 64,
        "output_path": str(benchmark.RUN_OUTPUT_RELATIVE),
        "output_sha256": "c" * 64,
    }
    if signal_phase == "evidence":
        def fail_during_evidence(_paths: dict[str, Path]) -> dict[str, str]:
            raise_sigterm_while_active()

        monkeypatch.setattr(benchmark, "_build_evidence", fail_during_evidence)
    else:
        monkeypatch.setattr(benchmark, "_build_evidence", lambda _paths: evidence)
        monkeypatch.setattr(benchmark, "_validate_receipt", lambda *_args, **_kwargs: None)
        real_update = benchmark._ledger_update

        def update(path: Path, value: dict[str, Any]) -> None:
            if value["state"] == "completed":
                raise_sigterm_while_active()
            real_update(path, value)

        monkeypatch.setattr(benchmark, "_ledger_update", update)

    result = benchmark._launch_exact()

    assert result == 70
    assert events == ["bounded_reap_complete", "sigterm_requested"]
    assert signal.getsignal(signal.SIGTERM) == previous_sigterm
    persisted = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    assert persisted["state"] == "failed_after_launch"
    assert persisted["token_consumed"] is True
    assert persisted["retry_allowed"] is False
    assert persisted["restart_allowed"] is False
    assert persisted["replacement_allowed"] is False
    assert list(paths["ledger"].parent.glob(f".{paths['ledger'].name}.*.tmp")) == []


def test_sigterm_during_fallback_persistence_is_blocked_after_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = _fake_launch_contract(tmp_path)
    _patch_fake_process_boundary(launch, tmp_path, monkeypatch)
    paths = launch["paths"]
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(benchmark, "_verify_launch_contract", lambda: launch)
    monkeypatch.setattr(benchmark, "_verify_prelaunch_recovery", lambda: {"verification": "passed"})
    monkeypatch.setattr(benchmark.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(benchmark.os, "fork", lambda: 123)
    real_close = benchmark.os.close

    def close(fd: int) -> None:
        if fd in {10, 11}:
            return
        real_close(fd)

    monkeypatch.setattr(benchmark.os, "close", close)
    real_write = benchmark.os.write
    monkeypatch.setattr(
        benchmark.os,
        "write",
        lambda fd, data: len(data) if fd == 11 else real_write(fd, data),
    )
    monkeypatch.setattr(
        benchmark,
        "_observe_child_start",
        lambda _pid, _launch, parent_pid: {
            "pid": 123,
            "parent_pid": parent_pid,
            "user": "synthetic-owner",
            "argv": list(benchmark.LAUNCH_COMMAND),
            "cwd": str(tmp_path.resolve()),
        },
    )
    events: list[str] = []

    def wait_for_child(_pid: int) -> tuple[int, int, object, bool]:
        events.append("bounded_reap_complete")
        return 123, 0, object(), False

    monkeypatch.setattr(benchmark, "_wait_for_child", wait_for_child)

    def fail_evidence(_paths: dict[str, Path]) -> dict[str, str]:
        raise ValueError("synthetic evidence failure before fallback")

    monkeypatch.setattr(benchmark, "_build_evidence", fail_evidence)
    real_update = benchmark._ledger_update

    def update(path: Path, value: dict[str, Any]) -> None:
        if value["state"] == "failed_after_launch":
            events.append("fallback_persistence")
            assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN
            assert signal.getsignal(signal.SIGTERM) is signal.SIG_IGN
            signal.raise_signal(signal.SIGTERM)
        real_update(path, value)

    monkeypatch.setattr(benchmark, "_ledger_update", update)
    previous_sigint = signal.getsignal(signal.SIGINT)
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    assert benchmark._launch_exact() == 70
    assert events == ["bounded_reap_complete", "fallback_persistence"]
    assert signal.getsignal(signal.SIGINT) == previous_sigint
    assert signal.getsignal(signal.SIGTERM) == previous_sigterm
    persisted = json.loads(paths["ledger"].read_text(encoding="utf-8"))
    assert persisted["state"] == "failed_after_launch"
    assert persisted["token_consumed"] is True
    assert persisted["retry_allowed"] is False
    assert persisted["restart_allowed"] is False
    assert persisted["replacement_allowed"] is False
    assert list(paths["ledger"].parent.glob(f".{paths['ledger'].name}.*.tmp")) == []


@pytest.mark.parametrize(
    "evidence_seam",
    [
        "missing_stdout",
        "missing_stderr",
        "missing_output",
        "hash_read",
        "output_read",
        "nullable_evidence",
        "mismatched_evidence",
    ],
)
def test_evidence_failures_are_terminal_failed_after_launch(
    evidence_seam: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch, ledger_path, paths = _completion_fixture(tmp_path)
    if evidence_seam.startswith("missing_"):
        paths[evidence_seam.removeprefix("missing_")].unlink()
    elif evidence_seam == "hash_read":
        def fail_hash(_path: Path) -> str:
            raise OSError("synthetic evidence hash read failure")

        monkeypatch.setattr(benchmark, "_sha256", fail_hash)
    elif evidence_seam == "output_read":
        real_read_text = Path.read_text

        def fail_output_read(path: Path, *args: object, **kwargs: object) -> str:
            if path == paths["output"]:
                raise OSError("synthetic output read failure")
            return real_read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", fail_output_read)
    else:
        evidence = {
            "stdout_path": str(benchmark.RUN_STDOUT_RELATIVE),
            "stdout_sha256": None if evidence_seam == "nullable_evidence" else "a" * 64,
            "stderr_path": str(benchmark.RUN_STDERR_RELATIVE),
            "stderr_sha256": "b" * 64,
            "output_path": (
                "output/ck07r1/wrong.json"
                if evidence_seam == "mismatched_evidence"
                else str(benchmark.RUN_OUTPUT_RELATIVE)
            ),
            "output_sha256": "c" * 64,
        }
        monkeypatch.setattr(benchmark, "_build_evidence", lambda _paths: evidence)

    assert _finalize_child_result(launch, ledger_path, paths, monkeypatch) == 70
    persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert persisted["state"] == "failed_after_launch"
    assert persisted["state"] != "completed"


def test_timeout_kills_term_resistant_child_with_bounded_reap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    waits = [
        (0, 0, object()),
        (0, 0, object()),
        (123, signal.SIGKILL, object()),
    ]
    monotonic_values = iter((0.0, 1.0, 1.0, 6.0, 6.0, 12.0, 12.0))
    signals: list[signal.Signals] = []
    monkeypatch.setattr(benchmark, "AGGREGATE_TIMEOUT_CANDIDATE_SECONDS", 0.0)
    monkeypatch.setattr(benchmark.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(benchmark.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(benchmark.os, "wait4", lambda _pid, _options: waits.pop(0))
    monkeypatch.setattr(benchmark.os, "kill", lambda _pid, sig: signals.append(sig))

    waited_pid, status, _usage, timed_out = benchmark._wait_for_child(123)

    assert waited_pid == 123
    assert status == signal.SIGKILL
    assert timed_out is True
    assert signals == [signal.SIGTERM, signal.SIGKILL]


def test_receipt_binds_exact_prelaunch_recovery_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = {"manifest": "synthetic"}
    recovery = {
        "schema": benchmark.PRELAUNCH_RECOVERY_SCHEMA,
        "state": "prelaunch_recovery_verified",
    }
    receipt = {
        "schema": benchmark.SCHEMA,
        "fixture_identity": fixture,
        "prelaunch_recovery": recovery,
        "first_failure": None,
        "linear_work_counters": {
            "budget_checks": {name: True for name in benchmark.FROZEN_BUDGETS_MS},
            **{
                name: {
                    "publication_receipt": {
                        "postconditions": {"identity_bindings": True},
                        "planner_tail_limits": benchmark.FROZEN_TAIL_LIMITS,
                    }
                }
                for name in ("standard_30_day", "production_all_time")
            },
        },
    }
    monkeypatch.setattr(benchmark, "_validate_workload_transition_digest", lambda _payload: None)

    evidence = {
        "stdout_path": str(benchmark.RUN_STDOUT_RELATIVE),
        "stdout_sha256": "a" * 64,
        "stderr_path": str(benchmark.RUN_STDERR_RELATIVE),
        "stderr_sha256": "b" * 64,
        "output_path": str(benchmark.RUN_OUTPUT_RELATIVE),
        "output_sha256": "c" * 64,
    }
    benchmark._validate_receipt(receipt, fixture, recovery, evidence=evidence)
    with pytest.raises(ValueError, match="prelaunch recovery binding"):
        benchmark._validate_receipt(
            receipt,
            fixture,
            {**recovery, "state": "rejected"},
            evidence=evidence,
        )
    with pytest.raises(ValueError, match="evidence digest"):
        benchmark._validate_receipt(
            receipt,
            fixture,
            recovery,
            evidence={**evidence, "stderr_sha256": None},
        )


def test_all_profile_exact_script_and_flags_reach_launcher_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(benchmark, "_launch_exact", lambda: calls.append(1) or 0)
    monkeypatch.setattr(sys, "argv", list(benchmark.LAUNCH_COMMAND[1:]))

    assert benchmark.main() == 0
    assert calls == [1]


@pytest.mark.parametrize(
    "argv",
    [
        [
            benchmark.LAUNCH_COMMAND[1],
            "--profile",
            "all",
            "--samples",
            "5",
        ],
        [*benchmark.LAUNCH_COMMAND[1:], "--samples", "5"],
        [
            benchmark.LAUNCH_COMMAND[1],
            "--samples",
            "5",
            "--profile",
            "all",
            "--output",
            "output/ck07r1/lifecycle-requalification-v2.json",
        ],
        [
            "scripts/benchmark_ck07r1_lifecycle_scale_drift.py",
            *benchmark.LAUNCH_COMMAND[2:],
        ],
    ],
    ids=("missing", "extra", "reordered", "script-path-drift"),
)
def test_all_profile_argv_mutations_exit_two_without_launch(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(benchmark, "_launch_exact", lambda: calls.append(1) or 0)
    monkeypatch.setattr(sys, "argv", argv)

    assert benchmark.main() == 2
    assert calls == []


@pytest.mark.parametrize("profile", ["standard", "production"])
def test_non_all_local_modes_remain_unchanged(
    profile: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, int]] = []

    def local_run(*, profile_name: str, samples: int) -> dict[str, object]:
        calls.append((profile_name, samples))
        return {"first_failure": None}

    monkeypatch.setattr(benchmark, "run", local_run)
    monkeypatch.setattr(
        benchmark,
        "_launch_exact",
        lambda: pytest.fail("non-all mode must not launch the all-profile runner"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [benchmark.LAUNCH_COMMAND[1], "--profile", profile, "--samples", "1"],
    )

    assert benchmark.main() == 0
    assert calls == [(profile, 1)]


def test_child_start_handshake_waits_for_exact_process_before_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = benchmark.LAUNCH_COMMAND
    platform_argv = [
        "/opt/homebrew/.../Resources/Python",
        *expected[1:],
    ]
    platform_command = benchmark.shlex.join(platform_argv)
    platform_signature = benchmark._platform_process_signature(platform_command)
    launch = {
        "cwd": str(tmp_path.resolve()),
        "owner": "synthetic-owner",
        "verified_parent_process_snapshot": {
            "pid": 123,
            "parent_pid": 1,
            "user": "synthetic-owner",
            "argv": platform_argv,
            "command": platform_command,
            "platform_signature": platform_signature,
            "cwd": str(tmp_path.resolve()),
        },
    }
    snapshots = [
        [],
        [
            {
                "pid": 456,
                "parent_pid": 123,
                "user": "synthetic-owner",
                "argv": platform_argv,
                "command": platform_command,
                "platform_signature": platform_signature,
                "cwd": str(tmp_path.resolve()),
            }
        ],
    ]
    observed_calls: list[int] = []

    def observe(*_args: object, **_kwargs: object) -> list[dict[str, object]]:
        observed_calls.append(1)
        return snapshots[min(len(observed_calls) - 1, len(snapshots) - 1)]

    monkeypatch.setattr(benchmark, "_matching_processes", observe)
    result = benchmark._observe_child_start(456, launch, 123)

    assert result["pid"] == 456
    assert len(observed_calls) == 2


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong-pid",
        "wrong-ppid",
        "wrong-owner",
        "wrong-cwd",
        "missing-cwd",
        "wrong-argv",
        "wrong-signature",
        "alternate-argv0",
    ],
)
def test_child_start_handshake_rejects_snapshot_drift(
    mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = benchmark.LAUNCH_COMMAND
    platform_argv = [
        "/opt/homebrew/.../Resources/Python",
        *expected[1:],
    ]
    platform_command = benchmark.shlex.join(platform_argv)
    platform_signature = benchmark._platform_process_signature(platform_command)
    launch = {
        "cwd": str(tmp_path.resolve()),
        "owner": "synthetic-owner",
        "verified_parent_process_snapshot": {
            "pid": 123,
            "parent_pid": 1,
            "user": "synthetic-owner",
            "argv": platform_argv,
            "command": platform_command,
            "platform_signature": platform_signature,
            "cwd": str(tmp_path.resolve()),
        },
    }
    child: dict[str, Any] = {
        "pid": 456,
        "parent_pid": 123,
        "user": "synthetic-owner",
        "argv": platform_argv,
        "command": platform_command,
        "platform_signature": platform_signature,
        "cwd": str(tmp_path.resolve()),
    }
    if mutation == "wrong-pid":
        child["pid"] = 789
    elif mutation == "wrong-ppid":
        child["parent_pid"] = 999
    elif mutation == "wrong-owner":
        child["user"] = "other-owner"
    elif mutation == "wrong-cwd":
        child["cwd"] = str(tmp_path / "other")
    elif mutation == "missing-cwd":
        child.pop("cwd")
    elif mutation == "wrong-argv":
        child["argv"] = [*platform_argv, "--drift"]
    elif mutation == "wrong-signature":
        child["platform_signature"] = "0" * 64
    elif mutation == "alternate-argv0":
        child["argv"] = [str(tmp_path / ".venv" / "bin" / "python"), *expected[1:]]
        child["command"] = benchmark.shlex.join(child["argv"])
        child["platform_signature"] = benchmark._platform_process_signature(
            child["command"]
        )
    monkeypatch.setattr(benchmark, "_matching_processes", lambda *_args, **_kwargs: [child])
    clock = iter((0.0, 100.0))
    monkeypatch.setattr(benchmark.time, "monotonic", lambda: next(clock))

    with pytest.raises(RuntimeError, match="child-start handshake"):
        benchmark._observe_child_start(456, launch, 123)


def test_child_start_handshake_rejects_duplicate_or_ambiguous_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = benchmark.LAUNCH_COMMAND
    platform_argv = ["/opt/homebrew/.../Resources/Python", *expected[1:]]
    platform_command = benchmark.shlex.join(platform_argv)
    signature = benchmark._platform_process_signature(platform_command)
    launch = {
        "cwd": str(tmp_path.resolve()),
        "owner": "synthetic-owner",
        "verified_parent_process_snapshot": {
            "pid": 123,
            "parent_pid": 1,
            "user": "synthetic-owner",
            "argv": platform_argv,
            "command": platform_command,
            "platform_signature": signature,
            "cwd": str(tmp_path.resolve()),
        },
    }
    child = {
        "pid": 456,
        "parent_pid": 123,
        "user": "synthetic-owner",
        "argv": platform_argv,
        "command": platform_command,
        "platform_signature": signature,
        "cwd": str(tmp_path.resolve()),
    }
    duplicate = {**child, "pid": 789}
    monkeypatch.setattr(
        benchmark, "_matching_processes", lambda *_args, **_kwargs: [child, duplicate]
    )
    monkeypatch.setattr(benchmark.time, "monotonic", lambda: 0.0)

    with pytest.raises(RuntimeError, match="unexpected matching process"):
        benchmark._observe_child_start(456, launch, 123)


def test_terminal_receipt_failure_is_durable_and_no_retry(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    ledger = {
        "token_consumed": True,
        "token_status": "consumed",
        "state": "launched_consumed",
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
        "process_states": [{"state": "launched_consumed"}],
    }
    benchmark._exclusive_write(ledger_path, b"{}\n")

    benchmark._persist_terminal_failure(
        ledger,
        ledger_path,
        state="failed_after_launch",
        stage="receipt_parse_validation",
        exc=ValueError("invalid receipt"),
    )

    persisted = json.loads(ledger_path.read_text())
    assert persisted["state"] == "failed_after_launch"
    assert persisted["token_consumed"] is True
    assert persisted["failure"] == {
        "stage": "receipt_parse_validation",
        "exception_type": "ValueError",
        "message": "invalid receipt",
    }
    assert persisted["process_states"][-1]["stage"] == "receipt_parse_validation"
    assert persisted["retry_allowed"] is False
    assert persisted["restart_allowed"] is False
    assert persisted["replacement_allowed"] is False


def _digest_payload() -> dict[str, Any]:
    descriptors = []
    counters: dict[str, Any] = {}
    for name, source_profile, entities, observations in (
        ("standard_30_day", "standard", 1, 1),
        ("production_all_time", "production", 1, 1),
    ):
        vector = ("a" if source_profile == "standard" else "b") * 64
        descriptor = {
            "source_profile": source_profile,
            "history_preset": "30_days" if source_profile == "standard" else "all_time",
            "model_calls": 1,
            "entities": entities,
            "observations": observations,
            "seed": benchmark.FIXTURE_SEED,
            "profile_file_sha256": benchmark.PROFILE_DIGESTS[source_profile],
            "ordered_transition_vector_sha256": vector,
        }
        descriptors.append(descriptor)
        counters[name] = {
            "workload_descriptor": descriptor,
            "lifecycle_preparation": {"transition_digest": vector},
        }
    for name, entities, observations, vector in (
        ("no_change", 0, 0, "c" * 64),
        ("one_call_tail", 1, 1, "d" * 64),
        ("one_tool_tail", 1, 1, "e" * 64),
    ):
        descriptors.append(
            {
                "source_profile": "synthetic_tail",
                "history_preset": "all_time",
                "model_calls": 0,
                "entities": entities,
                "observations": observations,
                "seed": benchmark.FIXTURE_SEED,
                "profile_file_sha256": None,
                "ordered_transition_vector_sha256": vector,
            }
        )
        counters[name] = {"transition_digest": vector}
    return {
        "workload_descriptors": descriptors,
        "workload_transition_digest": benchmark._workload_transition_digest(descriptors),
        "linear_work_counters": counters,
    }


def test_workload_transition_digest_is_recomputed_from_vectors() -> None:
    payload = _digest_payload()
    benchmark._validate_workload_transition_digest(payload)

    mutated = copy.deepcopy(payload)
    mutated["workload_descriptors"][0]["ordered_transition_vector_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="transition vector binding drifted"):
        benchmark._validate_workload_transition_digest(mutated)


def test_aggregate_timeout_candidate_is_derived_and_non_authoritative() -> None:
    assert benchmark.AGGREGATE_TIMEOUT_CANDIDATE_SECONDS == 720.0
    assert benchmark.AGGREGATE_TIMEOUT_CANDIDATE_SECONDS == (
        benchmark.PRODUCTION_SAMPLE_COUNT
        * benchmark.FROZEN_BUDGETS_MS["production_all_time"]
        / 1_000
        + benchmark.PUBLICATION_RECOVERY_OVERHEAD_CANDIDATE_SECONDS
    )
    assert "requires a later authority freeze" in benchmark.AGGREGATE_TIMEOUT_CANDIDATE_RULE


def test_workload_transition_digest_is_dynamic_and_order_sensitive() -> None:
    descriptor = {
        "source_profile": "synthetic",
        "history_preset": "all_time",
        "model_calls": 1,
        "entities": 1,
        "observations": 1,
        "seed": benchmark.FIXTURE_SEED,
        "profile_file_sha256": None,
        "ordered_transition_vector_sha256": "a" * 64,
    }
    reversed_descriptor = {**descriptor, "ordered_transition_vector_sha256": "b" * 64}

    assert benchmark._workload_transition_digest((descriptor,)) != benchmark._workload_transition_digest(
        (reversed_descriptor,)
    )
