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
_SCHEMA_PATH = _ROOT / "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.schema.json"


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
        (root / relative_candidate for root in candidate_roots if (root / relative_candidate).is_file()),
        None,
    )
    if candidate is None:
        pytest.skip("the retained candidate is unavailable until the worker reapplies it")
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == authority["selected_candidate"]["artifacts"][1]["sha256"]
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
        "benchmark_sha256": "f173837d71e393e53e13f0253f3f1ede4045befb5dab2cbf81d6fe147be4b47a",
        "lifecycle_test_sha256": "b6468b609dd7e47462d4e0c958f33d37d876959c90fb17ae02d64c3d18c22eed",
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


def test_selected_candidate_is_r3a_shared_preparation_only_and_ck07_stays_blocked() -> None:
    authority = _authority()
    candidate = authority["selected_candidate"]
    assert authority["schema"] == "codex-usage-tracker.lifecycle-run-invocation-authority.v4"
    assert authority["authority_version"] == 4
    assert authority["authority_base_sha"] == "ee4a064bf8850bceb362fbe73e40a57fe4af55d6"
    assert authority["status"] == "blocked_no_run"
    assert authority["shared_preparation_binding"] == {
        "authority_main_sha256": "408d18e44c87da234d220c29298ebac1780e9426e2dce767b0bfc3ae65e8a872",
        "r3a_atomic_cohort_sha256": "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174",
        "historical_d192_sha256": "d192c858b48e44b5aa7a7e39ef524e5ec2f08085655fe485639f5e875a727aa1",
        "r3a_requires_complete_cohort": True,
        "direct_ck07_use_of_r3a_preparation": "forbidden",
        "direct_use_of_d192": "forbidden",
        "mixed_state": "fail_closed",
        "runtime_acceptance": "not_claimed",
        "launch_authorized": False,
    }
    assert authority["historical_d192"]["direct_use"] == "forbidden"
    assert candidate["status"] == "r3a_shared_preparation_not_ck07_candidate"
    assert candidate["base_sha"] == authority["authority_base_sha"]
    assert candidate["source_successor_sha256"] == (
        "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174"
    )
    assert candidate["requires_complete_r3a_cohort"] is True
    assert candidate["direct_ck07_use"] == "forbidden"
    assert candidate["launch_authorized"] is False
    assert candidate["artifacts"][0] == {
        "path": "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
        "sha256": "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174",
        "role": "r3a_shared_preparation_not_ck07_source",
    }
    assert candidate["binding"] == (
        "r3a_preparation_is_not_a_ck07_candidate; complete_cohort_required_before_ck07_reapplication"
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
        "source_sha256": "408d18e44c87da234d220c29298ebac1780e9426e2dce767b0bfc3ae65e8a872",
        "source_role": "live_predecessor",
        "runtime_acceptance": "not_claimed",
        "receipt_policy": "receipt_absent_and_non_qualifying",
        "evidence_identity_policy": "not_available",
        "merge_policy": "current_authority_state",
    }
    assert machine["states"][1]["source_sha256"] == (
        "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174"
    )
    assert machine["states"][1]["source_role"] == "selected_r3a_atomic_cohort_preparation"
    assert machine["states"][1]["runtime_acceptance"] == "not_claimed"
    assert machine["states"][2]["receipt_policy"] == "complete_planner_valid_receipt_required"
    assert machine["states"][2]["evidence_identity_policy"] == (
        "bind_exact_dynamic_receipt_and_evidence_identity"
    )
    assert machine["states"][3]["merge_policy"] == (
        "worker_pr_squash_merge_and_exact_main_verification_required"
    )
    assert [transition["from"] + "->" + transition["to"] for transition in machine["transitions"]] == [
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
    assert identity["manifest"]["fixture_manifest_digest"] != identity["manifest"]["fixture_file_sha256"]
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
        "eligibility": "only after this authority merges and exact-main verifies, the stopped existing worker deliberately reapplies only the corrected exact candidate, and all gates pass",
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
    assert {"interruption", "timeout", "incomplete receipt", "budget miss", "postcondition failure"} <= set(
        after_launch["failures"]
    )
    feasibility = authority["feasibility"]
    assert feasibility["candidate_status"] == "corrected_no_run_runtime_unqualified"
    assert "planner-valid receipt" in feasibility["exact_blocker"]
    assert feasibility["run_action"].startswith("do not execute")


@pytest.mark.parametrize(
    ("label", "path", "replacement"),
    [
        ("old-argv-guard", ("argv_correction", "old_guard"), "sys.argv == LAUNCH_COMMAND"),
        ("corrected-argv-guard", ("argv_correction", "corrected_guard"), "sys.argv[1:] == LAUNCH_COMMAND[1:]"),
        ("first-failure-classification", ("first_failure", "classification"), "successful_process_launch"),
        ("first-failure-exit", ("first_failure", "exit_code"), 0),
        ("first-failure-token-evidence", ("first_failure", "evidence", "token"), "consumed"),
        ("exclusive-output-path", ("launch_contract", "output", "exclusive_paths", "ledger"), "output/other.json"),
        ("old-candidate-reuse", ("run_token", "old_candidate_reuse"), "allowed"),
        ("merge-sha-invention", ("change_control", "merged_sha"), "0" * 40),
        ("command", ("launch_contract", "repository_relative_command", 1), "wrong.py"),
        ("cwd", ("launch_contract", "required_cwd"), "scripts"),
        ("fixture-vocabulary", ("launch_contract", "fixture_identity", "vocabulary", "fixture_file_sha256"), "manifest"),
        ("fixture-digest-binding", ("launch_contract", "fixture_identity", "manifest", "fixture_file_sha256"), "0" * 64),
        ("aggregate-timeout", ("launch_contract", "aggregate_timeout", "seconds"), 120),
        ("candidate-benchmark", ("selected_candidate", "artifacts", 1, "sha256"), "0" * 64),
        ("rejected-dispatch", ("launch_contract", "fixture_identity", "rejected_dispatch_values", 0, "status"), "used"),
        ("output-overwrite", ("launch_contract", "output", "overwrite_rule"), "overwrite"),
        ("process-exclusion", ("launch_gates", "prelaunch", "required", 3), "process check omitted"),
        ("run-token-timing", ("run_token", "consumption"), "before launch"),
        ("no-retry", ("failure_matrix", "after_launch", "no_retry"), False),
        ("tail-limit", ("launch_contract", "tail_limits", "values", "observations"), 12001),
        ("count", ("launch_contract", "profiles", "workloads", 0, "observations"), 1370),
        ("seed", ("launch_contract", "profiles", "seed"), 42),
        ("reachable-path", ("launch_contract", "reachable_path", "ordered_steps", 2), "direct writer"),
        ("generic-drift", ("preserved_history", "source_predecessor_sha256"), "0" * 64),
        ("current-state", ("lifecycle_state_machine", "current_state"), "worker_prequalification"),
        ("successor-drift", ("lifecycle_state_machine", "states", 1, "source_sha256"), "0" * 64),
        ("receipt-bypass", ("lifecycle_state_machine", "states", 2, "receipt_policy"), "optional"),
        ("post-run-no-receipt-qualification", ("lifecycle_state_machine", "states", 2, "runtime_acceptance"), "accepted"),
        ("final-no-receipt-acceptance", ("lifecycle_state_machine", "states", 3, "receipt_policy"), "optional"),
        ("final-no-evidence-acceptance", ("lifecycle_state_machine", "states", 3, "evidence_identity_policy"), "not_available"),
        ("final-merge-bypass", ("lifecycle_state_machine", "states", 3, "merge_policy"), "optional"),
        ("transition-bypass", ("lifecycle_state_machine", "transitions", 0, "to"), "final_accepted"),
        ("receipt-path-drift", ("lifecycle_state_machine", "dynamic_receipt_identity", "identity_paths", "output_sha256"), "receipt.output_file_sha256"),
        ("receipt-ledger-drift", ("lifecycle_state_machine", "dynamic_receipt_identity", "ledger_path"), "output/other.json"),
        ("fixture-inventory-omission", ("launch_contract", "fixture_identity", "fixture_files", 0), None),
        ("fixture-inventory-digest", ("launch_contract", "fixture_identity", "fixture_files", 1, "fixture_file_sha256"), "0" * 64),
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
    packet = (_ROOT / "docs/roadmap/tasks/ck-07r1a0-freeze-lifecycle-path-authority.md").read_text(encoding="utf-8")
    ck07r1 = (_ROOT / "docs/roadmap/tasks/ck-07r1-correct-lifecycle-preparation-scale.md").read_text(encoding="utf-8")
    artifact = "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json"
    assert artifact in index
    assert artifact in packet
    assert "run-invocation authority" in ck07r1
    assert "run-invocation authority" in central
    assert "run-invocation authority" in ledger
    assert "CK-07R1" in central and "CK-07R1" in ledger
    assert authority["scope"]["authority_only_files"]
    assert set(authority["scope"]["authority_only_files"]) == {
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
