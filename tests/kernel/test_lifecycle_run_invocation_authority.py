from __future__ import annotations

import copy
import hashlib
import json
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
    assert "must not exist" in launch["output"]["prelaunch_rule"]
    assert "fail closed" in launch["output"]["overwrite_rule"]


def test_fixture_identity_vocabulary_and_static_file_shas_are_distinct_and_proven() -> None:
    identity = _authority()["launch_contract"]["fixture_identity"]
    assert set(identity["vocabulary"]) == {
        "fixture_manifest_digest",
        "fixture_file_sha256",
        "workload_transition_digest",
    }
    assert identity["manifest"]["fixture_manifest_digest"] != identity["manifest"]["fixture_file_sha256"]
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
    assert feasibility["candidate_status"] == "cannot_support_one_explicit_launch_without_behavioral_implementation"
    assert "prelaunch process exclusion" in feasibility["exact_blocker"]
    assert feasibility["run_action"].startswith("do not execute")


@pytest.mark.parametrize(
    ("label", "path", "replacement"),
    [
        ("command", ("launch_contract", "repository_relative_command", 1), "wrong.py"),
        ("cwd", ("launch_contract", "required_cwd"), "scripts"),
        ("fixture-vocabulary", ("launch_contract", "fixture_identity", "vocabulary", "fixture_file_sha256"), "manifest"),
        ("fixture-digest-binding", ("launch_contract", "fixture_identity", "manifest", "fixture_file_sha256"), "0" * 64),
        ("output-overwrite", ("launch_contract", "output", "overwrite_rule"), "overwrite"),
        ("process-exclusion", ("launch_gates", "prelaunch", "required", 2), "process check omitted"),
        ("run-token-timing", ("run_token", "consumption"), "before launch"),
        ("no-retry", ("failure_matrix", "after_launch", "no_retry"), False),
        ("tail-limit", ("launch_contract", "tail_limits", "values", "observations"), 12001),
        ("count", ("launch_contract", "profiles", "workloads", 0, "observations"), 1370),
        ("seed", ("launch_contract", "profiles", "seed"), 42),
        ("reachable-path", ("launch_contract", "reachable_path", "ordered_steps", 2), "direct writer"),
        ("generic-drift", ("preserved_history", "source_predecessor_sha256"), "0" * 64),
    ],
)
def test_negative_contract_mutations_fail_closed(
    label: str, path: tuple[str | int, ...], replacement: Any
) -> None:
    mutated = copy.deepcopy(_authority())
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
    assert "scripts/benchmark_ck07r1_lifecycle_scale.py" in authority["scope"]["forbidden"]
    assert CK07R1_RUN_INVOCATION_AUTHORITY_ADDITIONS == {
        "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json",
        "docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.schema.json",
        "tests/kernel/test_lifecycle_run_invocation_authority.py",
    }
