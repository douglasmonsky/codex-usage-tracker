from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scripts.check_kernel_scope import CK07R1_RUN_INVOCATION_AUTHORITY_ADDITIONS

_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_PATH = _ROOT / "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json"
_SCHEMA_PATH = (
    _ROOT / "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.schema.json"
)


def _authority() -> dict[str, Any]:
    return json.loads(_AUTHORITY_PATH.read_text(encoding="utf-8"))


def _schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _errors(value: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_schema()).iter_errors(value))


def _set_path(value: dict[str, Any], path: tuple[str | int, ...], replacement: Any) -> None:
    target: Any = value
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = replacement


def test_run_invocation_authority_validates_and_is_strict() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_authority())
    assert schema["additionalProperties"] is False


def test_preserved_authority_path_bytes_are_exact() -> None:
    for record in _authority()["preserved_authorities"].values():
        for path_key, digest_key in (
            ("path", "sha256"),
            ("schema_path", "schema_sha256"),
        ):
            path = _ROOT / record[path_key]
            assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == record[digest_key]


def test_command_cwd_interpreter_environment_and_output_are_exact() -> None:
    launch = _authority()["launch_contract"]
    assert launch["repository_relative_command"] == [
        ".venv/bin/python",
        "scripts/benchmark_ck07r1_lifecycle_scale.py",
        "--profile",
        "all",
        "--samples",
        "5",
        "--output",
        "output/ck07r1/lifecycle-requalification-v1.json",
    ]
    assert launch["required_cwd"] == "repository_root"
    assert launch["interpreter"]["executable"] == ".venv/bin/python"
    assert launch["interpreter"]["system_fallback"] is False
    assert launch["environment"]["required"] == {
        "LC_ALL": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONUNBUFFERED": "1",
        "TZ": "UTC",
    }
    assert launch["output"]["relative_path"] == "output/ck07r1/lifecycle-requalification-v1.json"
    assert launch["output"]["exclusive_paths"] == {
        "output": "output/ck07r1/lifecycle-requalification-v1.json",
        "ledger": "output/ck07r1/lifecycle-requalification-v1.launch-token.json",
        "stdout": "output/ck07r1/lifecycle-requalification-v1.stdout.txt",
        "stderr": "output/ck07r1/lifecycle-requalification-v1.stderr.txt",
    }
    assert "all four exact" in launch["output"]["prelaunch_rule"]
    assert "fail closed" in launch["output"]["overwrite_rule"]


def test_corrected_argv_guard_accepts_exact_candidate_in_real_non_launching_subprocess(
    tmp_path: Path,
) -> None:
    authority = _authority()
    relative_candidate = Path("scripts/benchmark_ck07r1_lifecycle_scale.py")
    candidate_roots = [
        _ROOT,
        _ROOT.parents[1] / authority["selected_candidate"]["retained_worktree"],
    ]
    candidate = next(
        (
            root / relative_candidate
            for root in candidate_roots
            if (root / relative_candidate).is_file()
        ),
        None,
    )
    if candidate is None:
        pytest.skip("the retained candidate is unavailable until the worker reapplies it")
    assert (
        hashlib.sha256(candidate.read_bytes()).hexdigest()
        == authority["selected_candidate"]["artifacts"][1]["sha256"]
    )
    candidate_copy = tmp_path / relative_candidate
    candidate_copy.parent.mkdir(parents=True)
    candidate_copy.write_bytes(candidate.read_bytes())

    frozen_args = [
        "--profile",
        "all",
        "--samples",
        "5",
        "--output",
        "output/ck07r1/lifecycle-requalification-v1.json",
    ]
    exact_paths = [
        _ROOT / "output/ck07r1/lifecycle-requalification-v1.json",
        _ROOT / "output/ck07r1/lifecycle-requalification-v1.launch-token.json",
        _ROOT / "output/ck07r1/lifecycle-requalification-v1.stdout.txt",
        _ROOT / "output/ck07r1/lifecycle-requalification-v1.stderr.txt",
    ]
    assert all(not path.exists() for path in exact_paths)

    wrapper = """
import runpy
import sys

candidate_path = sys.argv[1]
sys.argv = ["scripts/benchmark_ck07r1_lifecycle_scale.py", *sys.argv[2:]]
candidate = runpy.run_path(candidate_path, run_name="ck07r1_candidate")
calls = []

def suppress_launch():
    calls.append("_launch_exact")
    return 0

candidate["main"].__globals__["_launch_exact"] = suppress_launch
result = candidate["main"]()
if result != 0 or calls != ["_launch_exact"]:
    raise SystemExit(91)
print("exact argv accepted; launch boundary suppressed")
"""
    environment = os.environ.copy()
    environment.update(
        {
            "LC_ALL": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONUNBUFFERED": "1",
            "TZ": "UTC",
        }
    )
    environment.pop("PYTHONPATH", None)
    environment.pop("CODEX_HOME", None)
    result = subprocess.run(
        [sys.executable, "-c", wrapper, str(candidate_copy), *frozen_args],
        cwd=_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "exact argv accepted; launch boundary suppressed\n"
    assert result.stderr == ""
    assert all(not path.exists() for path in exact_paths)


def test_argv_correction_preserves_first_failure_and_one_run_gate() -> None:
    authority = _authority()
    correction = authority["argv_correction"]
    assert correction["old_guard"] == "sys.argv[1:] == LAUNCH_COMMAND[1:]"
    assert correction["corrected_guard"] == "(sys.argv[0], *sys.argv[1:]) == LAUNCH_COMMAND[1:]"
    assert correction["corrected_candidate_artifacts"] == {
        "benchmark_sha256": "f108dbb45d7586a15eb370c94fc124268a249f2f6f1ee97e7b8b28a3874b737c",
        "lifecycle_test_sha256": "4c51488988397e0ccaf40266a4f68bb1d6d342e4be1db36dd1cf36ab63aa335a",
    }
    assert correction["old_candidate_artifacts"]["reuse"] == "forbidden"
    assert correction["non_launching_subprocess_test"]["required"] is True

    failure = authority["first_failure"]
    assert failure["classification"] == "pre_child_argv_guard_failure"
    assert failure["attempted_once"] is True
    assert failure["exit_code"] == 2
    assert failure["elapsed_seconds"] == 0.075241709
    assert set(failure["evidence"].values()) == {"absent", "absent_and_unconsumed"}
    assert failure["retry"] == failure["restart"] == failure["replacement"] == "none"
    assert authority["run_token"]["first_successful_launch"].startswith(
        "exactly one first successful child launch"
    )
    assert authority["run_token"]["old_candidate_reuse"] == "forbidden"
    assert authority["change_control"] == {
        "exactly_one_pr": True,
        "hosted_ci_required": True,
        "merge_policy": "squash merge only when all required hosted CI jobs pass",
        "exact_main_verification": "attach verification against the exact merged main contents before acceptance",
        "merged_sha": None,
        "downstream": "blocked_until_authority_merge_and_exact_main_verification",
    }


def test_selected_candidate_is_exact_ck07_cohort_and_runtime_stays_blocked() -> None:
    authority = _authority()
    candidate = authority["selected_candidate"]
    assert authority["schema"] == "codex-usage-tracker.lifecycle-run-invocation-authority.v11"
    assert authority["authority_version"] == 11
    assert authority["authority_base_sha"] == "6c08ecd92a2c5166c1585be426e1ed437309a910"
    assert authority["status"] == "blocked_no_run"
    assert authority["shared_preparation_binding"] == {
        "authority_main_sha256": "7d1831ff5229e8e2a9819f0bd155d116ad97c3c3579bfa0444f791fe81e81feb",
        "r3a_atomic_cohort_sha256": "6689d61fbf6d7948e1958a9d0bc58b4ea326a7f04221914b74c0651e0be1e37c",
        "historical_d192_sha256": "d192c858b48e44b5aa7a7e39ef524e5ec2f08085655fe485639f5e875a727aa1",
        "r3a_requires_complete_cohort": True,
        "direct_ck07_use_of_r3a_preparation": "forbidden",
        "direct_use_of_d192": "forbidden",
        "mixed_state": "fail_closed",
        "runtime_acceptance": "not_claimed",
        "launch_authorized": False,
    }
    assert authority["historical_d192"]["direct_use"] == "forbidden"
    assert candidate["status"] == "exact_ck07_successor_permitted_not_accepted"
    assert candidate["base_sha"] == authority["authority_base_sha"]
    assert candidate["source_successor_sha256"] == (
        "66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea"
    )
    assert candidate["requires_complete_candidate_cohort"] is True
    assert candidate["direct_ck07_use"] == (
        "worker_prequalification_only_after_authority_exact_main"
    )
    assert candidate["launch_authorized"] is False
    assert candidate["artifacts"][0] == {
        "path": "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
        "sha256": "66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea",
        "role": "source",
    }
    assert candidate["binding"] == (
        "only the byte-exact 66c015de/f108dbb4/4c514889 cohort may enter "
        "worker_prequalification after this authority merges and exact-main verifies"
    )
    assert authority["run_token"]["status"] == "unspent_unavailable"
    assert authority["run_token"]["maximum_new_end_to_end_runs"] == 1
    assert authority["change_control"]["merged_sha"] is None


def test_finite_source_runtime_state_machine_is_exact_and_currently_unlaunched() -> None:
    machine = _authority()["lifecycle_state_machine"]
    assert machine["current_state"] == "authority_main"
    assert [state["name"] for state in machine["states"]] == [
        "authority_main",
        "worker_prequalification",
        "post_single_run",
        "final_accepted",
    ]
    assert machine["states"][0] == {
        "name": "authority_main",
        "source_sha256": "7d1831ff5229e8e2a9819f0bd155d116ad97c3c3579bfa0444f791fe81e81feb",
        "source_role": "accepted_current_r1b_predecessor",
        "runtime_acceptance": "not_claimed",
        "receipt_policy": "receipt_absent_and_non_qualifying",
        "evidence_identity_policy": "not_available",
        "merge_policy": "current_authority_state",
    }
    assert machine["states"][1]["source_sha256"] == (
        "66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea"
    )
    assert machine["states"][1]["source_role"] == "selected_ck07_exact_candidate"
    assert machine["states"][1]["runtime_acceptance"] == "not_claimed"
    assert machine["states"][2]["receipt_policy"] == "complete_planner_valid_receipt_required"
    assert machine["states"][2]["evidence_identity_policy"] == (
        "bind_exact_dynamic_receipt_and_evidence_identity"
    )
    assert machine["states"][3]["merge_policy"] == (
        "worker_pr_squash_merge_and_exact_main_verification_required"
    )
    assert [
        transition["from"] + "->" + transition["to"] for transition in machine["transitions"]
    ] == [
        "authority_main->worker_prequalification",
        "worker_prequalification->post_single_run",
        "post_single_run->final_accepted",
    ]
    assert machine["dynamic_receipt_identity"]["required_fields"] == [
        "run_token_id",
        "receipt_schema",
        "workload_transition_digest",
        "publication_digest",
        "ledger_file_sha256",
        "stdout_sha256",
        "stderr_sha256",
        "output_sha256",
        "launch_pid",
        "launch_cwd",
        "launch_argv",
    ]
    assert machine["dynamic_receipt_identity"]["ledger_path"] == (
        "output/ck07r1/lifecycle-requalification-v1.launch-token.json"
    )
    assert machine["dynamic_receipt_identity"]["identity_paths"] == {
        "run_token_id": "ledger.run_token_id",
        "receipt_schema": "ledger.receipt.schema",
        "workload_transition_digest": "ledger.receipt.workload_transition_digest",
        "publication_digest": "ledger.receipt.publication_digest",
        "ledger_file_sha256": (
            "sha256(exact ledger file bytes at "
            "output/ck07r1/lifecycle-requalification-v1.launch-token.json)"
        ),
        "stdout_sha256": "ledger.evidence.stdout_sha256",
        "stderr_sha256": "ledger.evidence.stderr_sha256",
        "output_sha256": "ledger.evidence.output_sha256",
        "launch_pid": "ledger.process.pid",
        "launch_cwd": "ledger.process.cwd",
        "launch_argv": "ledger.process.argv",
    }
    assert machine["dynamic_receipt_identity"]["mismatch"] == "fail_closed"
    assert "authority_main->final_accepted" in machine["forbidden_transitions"]


def test_dynamic_receipt_identity_uses_only_frozen_ledger_paths() -> None:
    identity = _authority()["lifecycle_state_machine"]["dynamic_receipt_identity"]
    ledger = {
        "run_token_id": "synthetic-run-token",
        "receipt": {
            "schema": "synthetic-receipt-schema",
            "workload_transition_digest": "a" * 64,
            "publication_digest": "b" * 64,
        },
        "evidence": {
            "stdout_sha256": "c" * 64,
            "stderr_sha256": "d" * 64,
            "output_sha256": "e" * 64,
        },
        "process": {
            "pid": 123,
            "cwd": "/synthetic/repository",
            "argv": [".venv/bin/python", "scripts/benchmark_ck07r1_lifecycle_scale.py"],
        },
    }
    resolved_fields = {
        "run_token_id": ledger["run_token_id"],
        "receipt_schema": ledger["receipt"]["schema"],
        "workload_transition_digest": ledger["receipt"]["workload_transition_digest"],
        "publication_digest": ledger["receipt"]["publication_digest"],
        "stdout_sha256": ledger["evidence"]["stdout_sha256"],
        "stderr_sha256": ledger["evidence"]["stderr_sha256"],
        "output_sha256": ledger["evidence"]["output_sha256"],
        "launch_pid": ledger["process"]["pid"],
        "launch_cwd": ledger["process"]["cwd"],
        "launch_argv": ledger["process"]["argv"],
    }
    assert resolved_fields == {
        "run_token_id": "synthetic-run-token",
        "receipt_schema": "synthetic-receipt-schema",
        "workload_transition_digest": "a" * 64,
        "publication_digest": "b" * 64,
        "stdout_sha256": "c" * 64,
        "stderr_sha256": "d" * 64,
        "output_sha256": "e" * 64,
        "launch_pid": 123,
        "launch_cwd": "/synthetic/repository",
        "launch_argv": [".venv/bin/python", "scripts/benchmark_ck07r1_lifecycle_scale.py"],
    }
    assert "ledger_file_sha256" not in ledger
    assert identity["source"].startswith("the frozen launch ledger")


def test_fixture_identity_vocabulary_and_static_file_shas_are_distinct_and_proven() -> None:
    identity = _authority()["launch_contract"]["fixture_identity"]
    assert set(identity["vocabulary"]) == {
        "fixture_manifest_digest",
        "fixture_file_sha256",
        "workload_transition_digest",
    }
    assert (
        identity["manifest"]["fixture_manifest_digest"]
        != identity["manifest"]["fixture_file_sha256"]
    )
    assert identity["rejected_dispatch_values"] == [
        {
            "value": "e8c79373697ebe2af5385dbb2899ae49cec61037c4a3b0909f91225128e0bc",
            "length": 62,
            "status": "revoked_never_authoritative",
            "use": "never_used",
            "reason": "malformed dispatch value; the canonical fixture file SHA-256 is 64 hexadecimal characters",
        }
    ]
    for item in identity["fixture_files"]:
        path = _ROOT / item["path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["fixture_file_sha256"]
    dynamic = identity["dynamic_digest"]
    assert dynamic["supplied_before_launch"] is False
    assert dynamic["field"] == "workload_transition_digest"
    assert dynamic["mismatch"] == "fail_closed"


def test_profiles_samples_counts_seed_and_tail_limits_are_frozen() -> None:
    contract = _authority()["launch_contract"]
    assert contract["profiles"]["sample_count"] == 5
    assert contract["profiles"]["warmup_count"] == 0
    assert contract["profiles"]["profiled"] is False
    assert contract["profiles"]["seed"] == 20260728
    assert contract["profiles"]["workloads"] == [
        {
            "name": "standard_30_day",
            "source_profile": "standard",
            "history_preset": "30_days",
            "model_calls": 2740,
            "entities": 685,
            "observations": 1369,
            "seed": 20260728,
            "profile_file_sha256": "ef0da880255a0b13ea6055e0f8d748870c075635aa6f199c9521462c681250f3",
        },
        {
            "name": "production_all_time",
            "source_profile": "production",
            "history_preset": "all_time",
            "model_calls": 1316864,
            "entities": 329216,
            "observations": 658431,
            "seed": 20260728,
            "profile_file_sha256": "2de0b4dc198603da6c1b0905b8d934e2cd5604e4036ef009d0cd07f1cc81f51b",
        },
        {
            "name": "no_change",
            "source_profile": "synthetic_tail",
            "history_preset": "all_time",
            "model_calls": 0,
            "entities": 0,
            "observations": 0,
            "seed": 20260728,
            "profile_file_sha256": None,
        },
        {
            "name": "one_call_tail",
            "source_profile": "synthetic_tail",
            "history_preset": "all_time",
            "model_calls": 0,
            "entities": 1,
            "observations": 1,
            "seed": 20260728,
            "profile_file_sha256": None,
        },
        {
            "name": "one_tool_tail",
            "source_profile": "synthetic_tail",
            "history_preset": "all_time",
            "model_calls": 0,
            "entities": 1,
            "observations": 1,
            "seed": 20260728,
            "profile_file_sha256": None,
        },
    ]
    assert contract["tail_limits"]["values"] == {
        "selected_bytes": 8388608,
        "selected_records": 32,
        "observations": 12000,
        "occurrences": 12000,
        "affected_sessions": 2000,
        "affected_turns": 4000,
        "affected_resources": 4000,
        "affected_allowance_cycles": 512,
        "dirty_keys": 16000,
        "projection_rows": 16000,
        "expected_wal_bytes": 16777216,
        "planning_staleness_us": 5000000,
        "model_call_tail_rows": 32000,
    }


def test_reachable_path_and_plan_identity_are_explicit() -> None:
    path = _authority()["launch_contract"]["reachable_path"]
    assert path["ordered_steps"] == [
        "select_readable_artifact(pointer_path, validate_open=...)",
        "recover_startup(pointer_path, selection=..., store=..., ...)",
        "plan_refresh(changes, intent, limits=TailLimits(), dirty_keys=0, projection_rows=0, expected_wal_bytes=None)",
        "selected_plan_unchanged",
        "PublicationWriter.publish_with_pointer(plan, request, write_set, pointer_path=..., operational_store=..., pointer_request=..., validate_open=...)",
        "publish_small_with_pointer(..., commit_analytical=...)",
        "PublicationWriter.publish(plan, request, write_set)",
    ]
    assert path["unchanged_plan"]["identity"].startswith("the exact object")
    assert len(path["identity_binding"]) == 6
    assert path["failure"].startswith("any path")


def test_corrected_launcher_safety_contract_is_exact() -> None:
    safety = _authority()["launch_contract"]["launcher_safety"]

    assert safety == {
        "overlay_and_cohort_verification": (
            "must_complete_before_ledger_fork_child_release_or_token_consumption"
        ),
        "receipt_binding": (
            "must_equal_exact_overlay_verification_result_and_three_artifact_cohort"
        ),
        "receipt_completion_ordering": (
            "construct_exact_overlay_bound_receipt_then_validate_then_first_durable_"
            "completed_finalization"
        ),
        "receipt_failure_state": (
            "construction_validation_or_finalization_failure_is_failed_after_launch_"
            "never_completed"
        ),
        "child_pre_release_failure": (
            "every_pre_release_child_failure_routes_to_os._exit_71"
        ),
        "child_wait_signal_handling": (
            "SIGINT_SIGTERM_ignored_while_waiting_for_parent_release"
        ),
        "parent_cleanup_pid_guard": (
            "reject_pid_less_than_or_equal_to_zero_before_kill_wait_or_reap"
        ),
        "atomic_ledger_update": (
            "unique_same_directory_mkstemp_close_and_unlink_on_every_failed_or_"
            "interrupted_write_fsync_replace_or_post_replace_path"
        ),
        "atomic_failure_state": (
            "durable_failed_after_launch_token_consumed_no_retry_no_temp_residue"
        ),
        "parent_signal_handling": (
            "temporary_SIGINT_SIGTERM_handlers_installed_before_child_observation_"
            "held_through_bounded_reap_evidence_receipt_and_terminal_ledger_"
            "persistence_then_restored"
        ),
        "wait_interruption_cleanup": (
            "every_wait_exception_or_parent_signal_requires_bounded_SIGTERM_then_"
            "SIGKILL_then_reap_before_terminal_failure"
        ),
        "signal_cleanup_mask": (
            "SIGINT_SIGTERM_ignored_during_bounded_child_cleanup"
        ),
        "terminal_fallback_signal_mask": (
            "SIGINT_SIGTERM_ignored_during_every_terminal_fallback_persistence_"
            "then_prior_temporary_handlers_restored"
        ),
        "evidence_completion_ordering": (
            "required_non_null_stdout_stderr_output_read_hash_parse_validate_before_"
            "first_durable_completed_finalization"
        ),
        "evidence_failure_state": (
            "missing_read_hash_parse_validation_or_finalization_failure_is_failed_"
            "after_launch_never_completed"
        ),
        "interpreter_identity": {
            "executable": "lexical_repository_worktree_.venv/bin/python_required",
            "sys_prefix": "lexical_repository_worktree_.venv_required",
            "base_interpreter": "rejected",
            "symlink_or_resolved_equivalence": "rejected",
            "wrong_worktree_venv": "rejected",
            "prefix_mismatch": "rejected",
        },
        "post_token_or_release_failure_state": "failed_after_launch",
        "termination_sequence": [
            "SIGTERM",
            "wait_up_to_5_seconds",
            "SIGKILL",
        ],
        "final_reap_timeout_seconds": 5,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }


def test_process_exclusion_launch_token_and_evidence_capture_are_required() -> None:
    authority = _authority()
    prelaunch = authority["launch_gates"]["prelaunch"]
    assert any("no matching process" in item for item in prelaunch["required"])
    assert prelaunch["token"] == "not consumed"
    launch = authority["launch_gates"]["successful_process_launch"]
    assert launch["record"] == [
        "pid",
        "parent_pid",
        "launched_at_utc",
        "launched_monotonic_ns",
        "argv",
        "cwd",
        "interpreter",
        "run_token_id",
    ]
    runtime = authority["launch_gates"]["runtime_and_completion"]["record"]
    assert any("RSS" in item for item in runtime)
    assert any("disk" in item for item in runtime)
    assert any("evidence" in item or "SHA-256" in item for item in runtime)
    assert authority["run_token"] == {
        "maximum_new_end_to_end_runs": 1,
        "status": "unspent_unavailable",
        "consumption": "successful_process_launch_only",
        "refund": False,
        "prior_identities_reused": False,
        "concurrent_processes_allowed": False,
        "eligibility": "only after this authority merges and exact-main verifies, the stopped existing worker resumes only the preserved exact 66c015de/f108dbb4/4c514889 candidate cohort, and all gates pass",
        "first_successful_launch": "exactly one first successful child launch may consume the still-unspent token; this is not a retry, restart, or replacement of a launched process",
        "old_candidate_reuse": "forbidden",
    }


def test_no_retry_semantics_and_candidate_blocker_are_explicit() -> None:
    authority = _authority()
    after_launch = authority["failure_matrix"]["after_launch"]
    assert after_launch["no_retry"] is True
    assert after_launch["no_restart"] is True
    assert after_launch["no_replacement"] is True
    assert after_launch["token_remains_consumed"] is True
    assert {
        "interruption",
        "timeout",
        "incomplete receipt",
        "budget miss",
        "postcondition failure",
    } <= set(after_launch["failures"])
    feasibility = authority["feasibility"]
    assert feasibility["candidate_status"] == "exact_successor_bound_no_run_runtime_unqualified"
    assert "planner-valid receipt" in feasibility["exact_blocker"]
    assert feasibility["run_action"].startswith("do not execute")


@pytest.mark.parametrize(
    ("label", "path", "replacement"),
    [
        ("old-argv-guard", ("argv_correction", "old_guard"), "sys.argv == LAUNCH_COMMAND"),
        (
            "corrected-argv-guard",
            ("argv_correction", "corrected_guard"),
            "sys.argv[1:] == LAUNCH_COMMAND[1:]",
        ),
        (
            "first-failure-classification",
            ("first_failure", "classification"),
            "successful_process_launch",
        ),
        ("first-failure-exit", ("first_failure", "exit_code"), 0),
        ("first-failure-token-evidence", ("first_failure", "evidence", "token"), "consumed"),
        (
            "exclusive-output-path",
            ("launch_contract", "output", "exclusive_paths", "ledger"),
            "output/other.json",
        ),
        ("old-candidate-reuse", ("run_token", "old_candidate_reuse"), "allowed"),
        ("merge-sha-invention", ("change_control", "merged_sha"), "0" * 40),
        ("command", ("launch_contract", "repository_relative_command", 1), "wrong.py"),
        ("cwd", ("launch_contract", "required_cwd"), "scripts"),
        (
            "fixture-vocabulary",
            ("launch_contract", "fixture_identity", "vocabulary", "fixture_file_sha256"),
            "manifest",
        ),
        (
            "fixture-digest-binding",
            ("launch_contract", "fixture_identity", "manifest", "fixture_file_sha256"),
            "0" * 64,
        ),
        ("aggregate-timeout", ("launch_contract", "aggregate_timeout", "seconds"), 120),
        (
            "overlay-after-ledger",
            (
                "launch_contract",
                "launcher_safety",
                "overlay_and_cohort_verification",
            ),
            "after_ledger",
        ),
        (
            "receipt-unbound",
            ("launch_contract", "launcher_safety", "receipt_binding"),
            "optional",
        ),
        (
            "receipt-finalized-before-validation",
            ("launch_contract", "launcher_safety", "receipt_completion_ordering"),
            "durable_completed_before_validation",
        ),
        (
            "receipt-construction-false-completed",
            ("launch_contract", "launcher_safety", "receipt_failure_state"),
            "completed",
        ),
        (
            "child-pre-release-return",
            ("launch_contract", "launcher_safety", "child_pre_release_failure"),
            "exception_returns_to_parent_path",
        ),
        (
            "child-wait-signals-actionable",
            ("launch_contract", "launcher_safety", "child_wait_signal_handling"),
            "signals_actionable_while_waiting",
        ),
        (
            "nonpositive-child-pid",
            ("launch_contract", "launcher_safety", "parent_cleanup_pid_guard"),
            "pid_zero_allowed",
        ),
        (
            "fixed-atomic-temp",
            ("launch_contract", "launcher_safety", "atomic_ledger_update"),
            "fixed_temp_without_cleanup",
        ),
        (
            "atomic-failure-retry",
            ("launch_contract", "launcher_safety", "atomic_failure_state"),
            "retry_or_temp_residue_allowed",
        ),
        (
            "parent-signals-not-installed",
            ("launch_contract", "launcher_safety", "parent_signal_handling"),
            "not_installed",
        ),
        (
            "parent-signals-restored-before-finalization",
            ("launch_contract", "launcher_safety", "parent_signal_handling"),
            "restored_after_wait",
        ),
        (
            "wait-error-without-reap",
            ("launch_contract", "launcher_safety", "wait_interruption_cleanup"),
            "persist_without_reap",
        ),
        (
            "cleanup-signals-actionable",
            ("launch_contract", "launcher_safety", "signal_cleanup_mask"),
            "signals_remain_actionable",
        ),
        (
            "fallback-persistence-signals-actionable",
            ("launch_contract", "launcher_safety", "terminal_fallback_signal_mask"),
            "signals_remain_actionable",
        ),
        (
            "nullable-evidence-before-completed",
            ("launch_contract", "launcher_safety", "evidence_completion_ordering"),
            "nullable_hashes_allowed",
        ),
        (
            "evidence-failure-nonterminal",
            ("launch_contract", "launcher_safety", "evidence_failure_state"),
            "launched_consumed",
        ),
        (
            "resolved-interpreter-equivalence",
            (
                "launch_contract",
                "launcher_safety",
                "interpreter_identity",
                "executable",
            ),
            "resolved_equivalent_python_allowed",
        ),
        (
            "prefix-mismatch-allowed",
            (
                "launch_contract",
                "launcher_safety",
                "interpreter_identity",
                "prefix_mismatch",
            ),
            "accepted",
        ),
        (
            "post-token-prelaunch-label",
            (
                "launch_contract",
                "launcher_safety",
                "post_token_or_release_failure_state",
            ),
            "prelaunch_failed",
        ),
        (
            "unbounded-reap",
            (
                "launch_contract",
                "launcher_safety",
                "final_reap_timeout_seconds",
            ),
            0,
        ),
        ("candidate-benchmark", ("selected_candidate", "artifacts", 1, "sha256"), "0" * 64),
        ("candidate-launch-authorization", ("selected_candidate", "launch_authorized"), True),
        ("shared-launch-authorization", ("shared_preparation_binding", "launch_authorized"), True),
        ("candidate-runtime-acceptance", ("selected_candidate", "runtime_acceptance"), "accepted"),
        (
            "rejected-dispatch",
            ("launch_contract", "fixture_identity", "rejected_dispatch_values", 0, "status"),
            "used",
        ),
        ("output-overwrite", ("launch_contract", "output", "overwrite_rule"), "overwrite"),
        (
            "process-exclusion",
            ("launch_gates", "prelaunch", "required", 3),
            "process check omitted",
        ),
        ("run-token-timing", ("run_token", "consumption"), "before launch"),
        ("run-token-status", ("run_token", "status"), "spent"),
        ("no-retry", ("failure_matrix", "after_launch", "no_retry"), False),
        ("tail-limit", ("launch_contract", "tail_limits", "values", "observations"), 12001),
        ("count", ("launch_contract", "profiles", "workloads", 0, "observations"), 1370),
        ("seed", ("launch_contract", "profiles", "seed"), 42),
        (
            "reachable-path",
            ("launch_contract", "reachable_path", "ordered_steps", 2),
            "direct writer",
        ),
        ("generic-drift", ("preserved_history", "source_predecessor_sha256"), "0" * 64),
        ("current-state", ("lifecycle_state_machine", "current_state"), "worker_prequalification"),
        ("successor-drift", ("lifecycle_state_machine", "states", 1, "source_sha256"), "0" * 64),
        ("receipt-bypass", ("lifecycle_state_machine", "states", 2, "receipt_policy"), "optional"),
        (
            "post-run-no-receipt-qualification",
            ("lifecycle_state_machine", "states", 2, "runtime_acceptance"),
            "accepted",
        ),
        (
            "final-no-receipt-acceptance",
            ("lifecycle_state_machine", "states", 3, "receipt_policy"),
            "optional",
        ),
        (
            "final-no-evidence-acceptance",
            ("lifecycle_state_machine", "states", 3, "evidence_identity_policy"),
            "not_available",
        ),
        (
            "final-merge-bypass",
            ("lifecycle_state_machine", "states", 3, "merge_policy"),
            "optional",
        ),
        (
            "transition-bypass",
            ("lifecycle_state_machine", "transitions", 0, "to"),
            "final_accepted",
        ),
        (
            "receipt-path-drift",
            (
                "lifecycle_state_machine",
                "dynamic_receipt_identity",
                "identity_paths",
                "output_sha256",
            ),
            "receipt.output_file_sha256",
        ),
        (
            "receipt-ledger-drift",
            ("lifecycle_state_machine", "dynamic_receipt_identity", "ledger_path"),
            "output/other.json",
        ),
        (
            "fixture-inventory-omission",
            ("launch_contract", "fixture_identity", "fixture_files", 0),
            None,
        ),
        (
            "fixture-inventory-digest",
            ("launch_contract", "fixture_identity", "fixture_files", 1, "fixture_file_sha256"),
            "0" * 64,
        ),
    ],
)
def test_negative_contract_mutations_fail_closed(
    label: str, path: tuple[str | int, ...], replacement: Any
) -> None:
    mutated = copy.deepcopy(_authority())
    if replacement is None:
        del mutated[path[0]][path[1]][path[2]][path[3]]
    else:
        _set_path(mutated, path, replacement)
    assert _errors(mutated), label


def test_dag_ledger_index_and_scope_bind_the_authority_without_new_task() -> None:
    authority = _authority()
    index = (_ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    central = (_ROOT / "docs/roadmap/REMAINING_EXECUTION_PLAN.md").read_text(encoding="utf-8")
    ledger = (_ROOT / "docs/roadmap/TASK_PACKETS.md").read_text(encoding="utf-8")
    packet = (_ROOT / "docs/roadmap/tasks/ck-07r1a0-freeze-lifecycle-path-authority.md").read_text(
        encoding="utf-8"
    )
    ck07r1 = (
        _ROOT / "docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md"
    ).read_text(encoding="utf-8")
    artifact = "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json"
    assert artifact in index
    assert artifact in packet
    assert "run-invocation authority" in ck07r1
    assert "run-invocation authority" in central
    assert "run-invocation authority" in ledger
    assert "CK-07R1" in central and "CK-07R1" in ledger
    assert authority["scope"]["authority_only_files"]
    assert set(authority["scope"]["authority_only_files"]) == {
        "AGENTS.md",
        "docs/INDEX.md",
        "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json",
        "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.schema.json",
        "docs/decisions/evidence/ck07r1a0/lifecycle-source-digest-authority.json",
        "docs/decisions/evidence/ck07r1a0/lifecycle-source-digest-authority.schema.json",
        "docs/roadmap/REMAINING_EXECUTION_PLAN.md",
        "docs/roadmap/TASK_PACKETS.md",
        "docs/roadmap/tasks/ck-07r1a0-freeze-lifecycle-path-authority.md",
        "docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md",
        "scripts/check_kernel_scope.py",
        "tests/kernel/test_documentation_authority.py",
        "tests/kernel/test_lifecycle_run_invocation_authority.py",
    }
    assert "scripts/benchmark_ck07r1_lifecycle_scale.py" in authority["scope"]["forbidden"]
    assert CK07R1_RUN_INVOCATION_AUTHORITY_ADDITIONS == {
        "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json",
        "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.schema.json",
        "tests/kernel/test_lifecycle_run_invocation_authority.py",
    }
