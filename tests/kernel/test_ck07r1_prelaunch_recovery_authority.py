from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import scripts.ck07r1_prelaunch_recovery as recovery
from scripts.ck07r1_prelaunch_recovery import (
    AUTHORITY_PATH,
    MINIMUM_CAPACITY_BYTES,
    SCHEMA_PATH,
    PrelaunchRecoveryError,
    evaluate_recovery_prelaunch,
    load_authority,
    verify_bound_authority_bytes,
    verify_candidate_cohort,
    verify_exact_authority_delta,
    verify_exact_candidate_delta,
    verify_frozen_candidate_root,
    verify_minimum_capacity,
    verify_new_paths_absent,
    verify_preserved_failure_ledger,
)

ROOT = Path(__file__).resolve().parents[2]


def _authority() -> dict[str, Any]:
    return load_authority(ROOT)


def _ledger(authority: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker.lifecycle-run-ledger.v1",
        "run_token_id": authority["run_token"]["id"],
        "maximum_new_end_to_end_runs": 1,
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "state": "prelaunch_failed",
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
        "first_result_retained": True,
        "launch": {"synthetic": True, "matching_processes": []},
        "failure": {
            "stage": "child_start_handshake",
            "exception_type": "RuntimeError",
            "message": ("child-start handshake did not prove exact PID/argv/cwd/owner"),
        },
        "process_states": [
            {"state": "prelaunch_verified", "at_utc": "2026-08-19T17:16:44Z"},
            {
                "state": "prelaunch_failed",
                "at_utc": "2026-08-19T17:16:49Z",
                "stage": "child_start_handshake",
            },
        ],
    }


def _write_synthetic_candidate(authority: dict[str, Any], root: Path) -> dict[str, Any]:
    for index, record in enumerate(authority["candidate_cohort"]):
        path = root / record["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic candidate {index}\n".encode())
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    ledger = _ledger(authority)
    ledger_path = root / authority["preserved_failure_lineage"]["ledger_path"]
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(
        json.dumps(ledger, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    authority["preserved_v1_ledger"]["sha256"] = hashlib.sha256(
        ledger_path.read_bytes()
    ).hexdigest()
    authority["preserved_v1_ledger"]["matching_processes"] = []
    return ledger


def _valid_observation(authority: dict[str, Any]) -> dict[str, Any]:
    contract = authority["launch_contract"]
    cwd = contract["cwd"]
    required = contract["environment"]["required"]
    return {
        "worker_thread_id": authority["worker"]["thread_id"],
        "cwd": cwd,
        "argv": contract["argv"],
        "environment": required,
        "environment_present": required,
        "interpreter": cwd + "/.venv/bin/python",
        "venv_prefix": cwd + "/.venv",
        "authority_integrity": "passed",
        "candidate_cohort": "passed",
        "candidate_delta": "passed",
        "preserved_ledger": "passed",
        "new_paths_present": [],
        "matching_processes": [],
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "prior_invocation_state": "prelaunch_failed",
        "prior_successful_child": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "synthetic_fixture": True,
        "live_or_real_data": False,
        "disk_available_bytes": MINIMUM_CAPACITY_BYTES,
    }


def test_recovery_authority_schema_is_strict_and_exact() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    assert authority["schema"].endswith(".v1")
    assert authority["authority_base_sha"] == ("213b5d280dac58d11d71511c21aac58f61227fd3")
    assert authority["status"] == "permitted_not_accepted"
    assert authority["decision"]["launch_authorized_in_authority_task"] is False
    assert authority["decision"]["new_invocation_is_launched_process_retry"] is False


def test_recovery_authority_preserves_every_predecessor_byte() -> None:
    verify_bound_authority_bytes(_authority(), ROOT)


def test_recovery_authority_binds_exact_candidate_and_terminal_ledger(
    tmp_path: Path,
) -> None:
    authority = deepcopy(_authority())
    _write_synthetic_candidate(authority, tmp_path)
    verify_candidate_cohort(authority, tmp_path)
    ledger = verify_preserved_failure_ledger(authority, tmp_path)
    verify_new_paths_absent(authority, tmp_path)
    assert ledger["state"] == "prelaunch_failed"
    assert ledger["token_consumed"] is False
    assert "process" not in ledger
    assert "receipt" not in ledger


def test_recovery_rejects_any_terminal_ledger_rewrite(tmp_path: Path) -> None:
    authority = deepcopy(_authority())
    _write_synthetic_candidate(authority, tmp_path)
    path = tmp_path / authority["preserved_failure_lineage"]["ledger_path"]
    ledger = json.loads(path.read_text(encoding="utf-8"))
    ledger["token_consumed"] = True
    path.write_text(json.dumps(ledger), encoding="utf-8")
    with pytest.raises(PrelaunchRecoveryError, match="terminal v1 ledger bytes changed"):
        verify_preserved_failure_ledger(authority, tmp_path)


def test_recovery_rejects_other_candidate_digest(tmp_path: Path) -> None:
    authority = deepcopy(_authority())
    _write_synthetic_candidate(authority, tmp_path)
    path = tmp_path / authority["candidate_cohort"][1]["path"]
    path.write_bytes(b"other candidate\n")
    with pytest.raises(PrelaunchRecoveryError, match="candidate identity mismatch"):
        verify_candidate_cohort(authority, tmp_path)


def test_recovery_candidate_delta_is_exact_and_includes_old_ledger() -> None:
    authority = _authority()
    expected = set(authority["scope"]["combined_preflight_candidate_scope"])
    verify_exact_candidate_delta(authority, ROOT, observed=expected)
    assert authority["preserved_v1_ledger"]["path"] in expected
    for changed in (
        expected - {authority["preserved_v1_ledger"]["path"]},
        expected | {"output/ck07r1/lifecycle-requalification-v2.json"},
    ):
        with pytest.raises(PrelaunchRecoveryError, match="candidate Git delta"):
            verify_exact_candidate_delta(authority, ROOT, observed=changed)


def test_recovery_authority_delta_is_exact() -> None:
    authority = _authority()
    expected = set(authority["scope"]["authority_write_scope"])
    verify_exact_authority_delta(authority, ROOT, observed=expected)
    for changed in (
        expected - {next(iter(expected))},
        expected | {"scripts/benchmark_ck07r1_lifecycle_scale.py"},
    ):
        with pytest.raises(PrelaunchRecoveryError, match="authority Git delta"):
            verify_exact_authority_delta(authority, ROOT, observed=changed)


def test_committed_authority_allows_only_exact_combined_worktree_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _authority()
    expected_authority = set(authority["scope"]["authority_write_scope"])
    expected_candidate = set(
        authority["scope"]["combined_preflight_candidate_scope"]
    )
    head = "a" * 40
    base = authority["authority_base_sha"]

    def fake_git(root: Path, *args: str) -> str:
        assert root == ROOT
        if args == ("rev-parse", "HEAD"):
            return head
        if args == ("diff", "--name-only", f"{base}..{head}", "--"):
            return "\n".join(sorted(expected_authority))
        raise AssertionError(args)

    monkeypatch.setattr(recovery, "_git", fake_git)
    monkeypatch.setattr(
        recovery,
        "_status_paths",
        lambda root: expected_candidate if root == ROOT else set(),
    )
    verify_exact_authority_delta(
        authority,
        ROOT,
        allowed_worktree_delta=expected_candidate,
    )

    with pytest.raises(
        PrelaunchRecoveryError,
        match="authority worktree delta must be exact",
    ):
        verify_exact_authority_delta(
            authority,
            ROOT,
            allowed_worktree_delta=expected_candidate - {
                "scripts/benchmark_ck07r1_lifecycle_scale.py"
            },
        )


def test_recovery_uses_new_noncolliding_paths_and_same_token() -> None:
    authority = _authority()
    paths = authority["launch_contract"]["exclusive_paths"]
    assert set(paths.values()) == {
        "output/ck07r1/lifecycle-requalification-v2.json",
        "output/ck07r1/lifecycle-requalification-v2.launch-token.json",
        "output/ck07r1/lifecycle-requalification-v2.stdout.txt",
        "output/ck07r1/lifecycle-requalification-v2.stderr.txt",
    }
    assert authority["run_token"]["id"] == "ck07r1-all-profile-e2e-1"
    assert authority["run_token"]["successful_launches_observed"] == 0
    assert authority["run_token"]["new_recovery_invocations_permitted"] == 1


def test_recovery_handshake_binds_verified_parent_snapshot_without_weakening() -> None:
    contract = _authority()["handshake_contract"]
    assert contract["pre_fork_parent_snapshot_required"] is True
    assert contract["child_process_creation"] == "fork_without_exec_before_release"
    assert contract["required_child_fields"] == [
        "pid",
        "parent_pid",
        "owner",
        "cwd",
        "platform_process_command_signature",
    ]
    assert contract["child_signature_rule"] == (
        "exact_equality_to_the_verified_parent_platform_process_command_signature"
    )
    assert contract["lexical_interpreter_and_sys_prefix_gate"] == "unchanged_required"
    assert contract["ambiguous_or_extra_match"] == "fail_closed"


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("worker_thread_id", "replacement-worker"),
        ("cwd", "/wrong"),
        ("argv", [".venv/bin/python", "wrong.py"]),
        ("environment", {"LC_ALL": "C"}),
        ("interpreter", "/usr/bin/python3"),
        ("venv_prefix", "/wrong/.venv"),
        ("authority_integrity", "failed"),
        ("candidate_cohort", "partial"),
        ("candidate_delta", "extra"),
        ("preserved_ledger", "rewritten"),
        ("new_paths_present", ["output/ck07r1/lifecycle-requalification-v2.json"]),
        ("matching_processes", [{"pid": 1}]),
        ("token_status", "consumed"),
        ("token_consumed", True),
        ("prior_invocation_state", "completed"),
        ("prior_successful_child", True),
        ("retry", "allowed"),
        ("restart", "allowed"),
        ("replacement", "allowed"),
        ("synthetic_fixture", False),
        ("live_or_real_data", True),
        ("disk_available_bytes", MINIMUM_CAPACITY_BYTES - 1),
    ],
)
def test_recovery_prelaunch_negative_mutations_fail_closed(field: str, replacement: Any) -> None:
    authority = _authority()
    observation = _valid_observation(authority)
    observation[field] = replacement
    with pytest.raises(PrelaunchRecoveryError, match="recovery prelaunch gate"):
        evaluate_recovery_prelaunch(authority, observation)


def test_recovery_forbidden_environment_fails_closed() -> None:
    authority = _authority()
    observation = _valid_observation(authority)
    observation["environment_present"] = {
        **observation["environment_present"],
        "CODEX_HOME": "/synthetic/forbidden",
    }
    with pytest.raises(PrelaunchRecoveryError, match="forbidden environment"):
        evaluate_recovery_prelaunch(authority, observation)


def test_recovery_capacity_gate_is_fail_closed() -> None:
    assert (
        verify_minimum_capacity(ROOT, observed_bytes=MINIMUM_CAPACITY_BYTES)
        == MINIMUM_CAPACITY_BYTES
    )
    with pytest.raises(PrelaunchRecoveryError, match="at least 10 GiB"):
        verify_minimum_capacity(ROOT, observed_bytes=MINIMUM_CAPACITY_BYTES - 1)


def test_recovery_requires_exact_frozen_lexical_candidate_root() -> None:
    authority = _authority()
    frozen = Path(authority["launch_contract"]["cwd"])
    verify_frozen_candidate_root(authority, frozen)

    with pytest.raises(
        PrelaunchRecoveryError,
        match="exact frozen lexical cwd",
    ):
        verify_frozen_candidate_root(authority, frozen.parent / "wrong-worktree")


def test_recovery_decision_is_first_successful_launch_not_retry_or_refund() -> None:
    authority = _authority()
    assert evaluate_recovery_prelaunch(authority, _valid_observation(authority)) == {
        "decision": "recovery_launch_authorized_once",
        "run_token_id": "ck07r1-all-profile-e2e-1",
        "new_command_invocations_permitted": 1,
        "consume_only_after_successful_child_handshake": True,
        "prior_prelaunch_failure_is_not_a_launched_process_retry": True,
        "refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }


def test_schema_rejects_policy_scope_token_and_lineage_weakening() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    mutations = [
        lambda value: value["decision"].__setitem__("launch_authorized_in_authority_task", True),
        lambda value: value["decision"].__setitem__(
            "new_invocation_is_launched_process_retry", True
        ),
        lambda value: value["run_token"].__setitem__("maximum_new_end_to_end_runs", 2),
        lambda value: value["run_token"].__setitem__("refund", True),
        lambda value: value["run_token"].__setitem__("token_consumed", True),
        lambda value: value["preserved_v1_ledger"].__setitem__("sha256", "0" * 64),
        lambda value: value["candidate_cohort"].pop(),
        lambda value: value["launch_contract"]["exclusive_paths"].__setitem__(
            "ledger",
            "output/ck07r1/lifecycle-requalification-v1.launch-token.json",
        ),
        lambda value: value["handshake_contract"].__setitem__(
            "lexical_interpreter_and_sys_prefix_gate", "waived"
        ),
        lambda value: value["scope"]["authority_write_scope"].append(
            "scripts/benchmark_ck07r1_lifecycle_scale.py"
        ),
    ]
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(Draft202012Validator(schema).iter_errors(changed))


def test_authority_task_remains_non_consuming() -> None:
    authority = _authority()
    assert authority["run_token"]["token_consumed"] is False
    assert authority["decision"]["runtime_acceptance"] == "not_claimed"
    assert authority["decision"]["implementation_acceptance"] == "not_claimed"
    assert "launch_or_child_in_authority_task" in authority["scope"]["forbidden"]
    assert Path(AUTHORITY_PATH).name.endswith("-v1.json")
