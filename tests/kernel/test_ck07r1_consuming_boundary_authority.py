from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scripts.ck07r1_consuming_boundary import (
    AUTHORITY_PATH,
    MINIMUM_CAPACITY_BYTES,
    SCHEMA_PATH,
    ConsumingBoundaryError,
    evaluate_prelaunch,
    load_authority,
    verify_bound_authority_bytes,
    verify_candidate_cohort,
    verify_current_exact_main,
    verify_exact_authority_delta,
    verify_exact_candidate_delta,
    verify_post_merge_candidate_head,
)

ROOT = Path(__file__).resolve().parents[2]


def _authority() -> dict[str, Any]:
    return load_authority(ROOT)


def _valid_observation(authority: dict[str, Any]) -> dict[str, Any]:
    cwd = authority["worker"]["frozen_cwd"]
    return {
        "cwd": cwd,
        "argv": authority["launch_contract"]["argv"],
        "environment": authority["launch_contract"]["environment"]["required"],
        "environment_present": authority["launch_contract"]["environment"]["required"],
        "interpreter": cwd + "/.venv/bin/python",
        "venv_prefix": cwd + "/.venv",
        "prequalification_base_sha": authority["worker"][
            "prequalification_base_sha"
        ],
        "candidate_head_transition": (
            "non_destructive_fast_forward_to_exact_merged_main"
        ),
        "matching_processes": [],
        "output_paths_present": [],
        "receipt": "absent",
        "token_status": "unspent_unavailable",
        "token_consumed": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
        "authority_integrity": "passed",
        "candidate_cohort": "passed",
        "candidate_delta": "passed",
        "synthetic_fixture": True,
        "live_or_real_data": False,
        "disk_available_bytes": MINIMUM_CAPACITY_BYTES,
    }


def test_consuming_boundary_schema_is_strict_and_exact() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    assert authority["schema"].endswith(".v1")
    assert authority["authority_base_sha"] == (
        "67bb1a36255b05634ee18c615e57cb01dbe0ebda"
    )
    assert authority["status"] == "permitted_not_accepted"
    assert authority["transition"]["launch_authorized"] is True
    assert authority["transition"]["runtime_acceptance"] == "not_claimed"
    assert authority["governance"]["worker_identity"].startswith(
        "normative_coordinator_orchestration_binding"
    )
    assert authority["worker"]["runtime_identity_claim"] == "none"


def test_consuming_boundary_preserves_every_bound_authority_byte() -> None:
    verify_bound_authority_bytes(_authority(), ROOT)


def test_consuming_boundary_binds_only_exact_atomic_candidate() -> None:
    authority = _authority()
    assert [record["sha256"] for record in authority["candidate_cohort"]] == [
        "66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea",
        "f108dbb45d7586a15eb370c94fc124268a249f2f6f1ee97e7b8b28a3874b737c",
        "4c51488988397e0ccaf40266a4f68bb1d6d342e4be1db36dd1cf36ab63aa335a",
    ]
    verify_exact_candidate_delta(
        authority,
        ROOT,
        observed=set(authority["scope"]["combined_preflight_candidate_scope"]),
    )
    for changed in (
        set(),
        {authority["scope"]["combined_preflight_candidate_scope"][0]},
        {
            *authority["scope"]["combined_preflight_candidate_scope"],
            "docs/decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json",
        },
    ):
        with pytest.raises(ConsumingBoundaryError, match="candidate Git delta"):
            verify_exact_candidate_delta(authority, ROOT, observed=changed)


def test_authority_delta_rejects_missing_and_extra_paths() -> None:
    authority = _authority()
    expected = set(authority["scope"]["authority_write_scope"])
    verify_exact_authority_delta(authority, ROOT, committed=False, observed=expected)
    for changed in (
        expected - {next(iter(expected))},
        expected | {"src/codex_usage_tracker/agent_kernel/publication/writer.py"},
    ):
        with pytest.raises(ConsumingBoundaryError, match="authority Git delta"):
            verify_exact_authority_delta(
                authority, ROOT, committed=False, observed=changed
            )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("cwd", "/wrong/worktree"),
        ("argv", [".venv/bin/python", "wrong.py"]),
        ("environment", {"LC_ALL": "C"}),
        ("interpreter", "/usr/bin/python3"),
        ("venv_prefix", "/wrong/.venv"),
        ("prequalification_base_sha", "0" * 40),
        ("candidate_head_transition", "stale_prequalification_head"),
        ("matching_processes", [{"pid": 123}]),
        ("output_paths_present", ["output/ck07r1/lifecycle-requalification-v1.json"]),
        ("receipt", {"fabricated": True}),
        ("token_status", "consumed"),
        ("token_consumed", True),
        ("retry", "allowed"),
        ("restart", "allowed"),
        ("replacement", "allowed"),
        ("authority_integrity", "failed"),
        ("candidate_cohort", "partial"),
        ("candidate_delta", "extra"),
        ("synthetic_fixture", False),
        ("live_or_real_data", True),
        ("disk_available_bytes", MINIMUM_CAPACITY_BYTES - 1),
    ],
)
def test_prelaunch_negative_mutations_fail_closed(
    field: str, replacement: Any
) -> None:
    authority = _authority()
    observation = _valid_observation(authority)
    observation[field] = replacement
    with pytest.raises(ConsumingBoundaryError, match="prelaunch gate failed"):
        evaluate_prelaunch(authority, observation)


def test_forbidden_environment_fails_closed() -> None:
    authority = _authority()
    observation = _valid_observation(authority)
    observation["environment_present"] = {
        **observation["environment_present"],
        "CODEX_HOME": "/synthetic/not-used",
    }
    with pytest.raises(ConsumingBoundaryError, match="forbidden environment"):
        evaluate_prelaunch(authority, observation)


def test_exact_prelaunch_authorizes_only_one_nonrefundable_launch() -> None:
    authority = _authority()
    decision = evaluate_prelaunch(authority, _valid_observation(authority))
    assert decision == {
        "decision": "launch_authorized_once",
        "run_token_id": "ck07r1-all-profile-e2e-1",
        "maximum_new_end_to_end_runs": 1,
        "consume_only_after_successful_child_handshake": True,
        "refund": False,
        "retry": "none",
        "restart": "none",
        "replacement": "none",
    }
    assert authority["run_token"]["prelaunch_status"] == "unspent_unavailable"
    assert authority["run_token"]["token_consumed"] is False


def test_live_authorization_requires_fetched_and_remote_exact_main() -> None:
    exact_main = "a" * 40
    assert (
        verify_current_exact_main(
            ROOT,
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main=exact_main,
        )
        == exact_main
    )
    with pytest.raises(ConsumingBoundaryError, match="fresh exact"):
        verify_current_exact_main(
            ROOT,
            observed_head=exact_main,
            observed_tracking_main=exact_main,
            observed_remote_main="b" * 40,
        )


def test_physical_post_merge_fast_forward_preserves_exact_dirty_cohort(
    tmp_path: Path,
) -> None:
    remote = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    candidate = tmp_path / "candidate"
    subprocess.run(("git", "init", "--bare", str(remote)), check=True)
    seed.mkdir()
    subprocess.run(("git", "init"), cwd=seed, check=True, capture_output=True)
    subprocess.run(
        ("git", "config", "user.email", "synthetic@example.invalid"),
        cwd=seed,
        check=True,
    )
    subprocess.run(
        ("git", "config", "user.name", "Synthetic Test"),
        cwd=seed,
        check=True,
    )
    preparation = (
        seed / "src/codex_usage_tracker/agent_kernel/publication/preparation.py"
    )
    preparation.parent.mkdir(parents=True)
    preparation.write_text("predecessor\n", encoding="utf-8")
    subprocess.run(("git", "add", "."), cwd=seed, check=True)
    subprocess.run(
        ("git", "commit", "-m", "base"),
        cwd=seed,
        check=True,
        capture_output=True,
    )
    base = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=seed,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(("git", "branch", "-M", "main"), cwd=seed, check=True)
    subprocess.run(
        ("git", "remote", "add", "origin", str(remote)),
        cwd=seed,
        check=True,
    )
    subprocess.run(
        ("git", "push", "-u", "origin", "main"),
        cwd=seed,
        check=True,
        capture_output=True,
    )
    (seed / "authority.txt").write_text("merged authority\n", encoding="utf-8")
    subprocess.run(("git", "add", "authority.txt"), cwd=seed, check=True)
    subprocess.run(
        ("git", "commit", "-m", "authority"),
        cwd=seed,
        check=True,
        capture_output=True,
    )
    merged = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=seed,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        ("git", "push", "origin", "main"),
        cwd=seed,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ("git", "clone", "--branch", "main", str(remote), str(candidate)),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ("git", "checkout", "--detach", base),
        cwd=candidate,
        check=True,
        capture_output=True,
    )

    authority = deepcopy(_authority())
    authority["worker"]["prequalification_base_sha"] = base
    authority["worker"]["frozen_cwd"] = str(candidate)
    contents = (b"successor preparation\n", b"benchmark\n", b"lifecycle test\n")
    before: dict[str, str] = {}
    for record, content in zip(authority["candidate_cohort"], contents, strict=True):
        path = candidate / record["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        record["sha256"] = hashlib.sha256(content).hexdigest()
        before[record["path"]] = record["sha256"]

    subprocess.run(
        ("git", "merge", "--ff-only", merged),
        cwd=candidate,
        check=True,
        capture_output=True,
    )
    assert verify_post_merge_candidate_head(authority, candidate) == merged
    verify_candidate_cohort(authority, candidate)
    verify_exact_candidate_delta(authority, candidate)
    assert {
        record["path"]: hashlib.sha256(
            (candidate / record["path"]).read_bytes()
        ).hexdigest()
        for record in authority["candidate_cohort"]
    } == before


def test_schema_rejects_scope_status_acceptance_and_launch_weakening() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    mutations = [
        lambda value: value.__setitem__("status", "final_accepted"),
        lambda value: value["approval"].__setitem__(
            "runtime_acceptance", "accepted"
        ),
        lambda value: value["worker"].__setitem__(
            "thread_id", "replacement-worker"
        ),
        lambda value: value["worker"].__setitem__(
            "runtime_identity_claim", "self_asserted_runtime_identity"
        ),
        lambda value: value["governance"].__setitem__(
            "runtime_attestation", "required"
        ),
        lambda value: value["candidate_cohort"].pop(),
        lambda value: value["candidate_cohort"].append(
            {"path": "extra.py", "sha256": "0" * 64}
        ),
        lambda value: value["run_token"].__setitem__(
            "maximum_new_end_to_end_runs", 2
        ),
        lambda value: value["run_token"].__setitem__("refund", True),
        lambda value: value["run_token"].__setitem__("retry", "allowed"),
        lambda value: value["launch_contract"].__setitem__("cwd", "/wrong"),
        lambda value: value["transition"].__setitem__(
            "candidate_head_transition", "reset_or_rebase"
        ),
        lambda value: value["scope"]["authority_write_scope"].append(
            "src/codex_usage_tracker/agent_kernel/publication/writer.py"
        ),
        lambda value: value["scope"]["combined_preflight_candidate_scope"].pop(),
        lambda value: value["failure_policy"].__setitem__(
            "fabricated_receipt", "allow"
        ),
        lambda value: value["failure_policy"].__setitem__(
            "non_fast_forward_or_candidate_byte_drift", "allow"
        ),
    ]
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(Draft202012Validator(schema).iter_errors(changed))


def test_candidate_byte_verification_rejects_other_digest(
    tmp_path: Path,
) -> None:
    authority = deepcopy(_authority())
    for index, record in enumerate(authority["candidate_cohort"]):
        path = tmp_path / record["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"synthetic candidate {index}\n".encode())
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    first = tmp_path / authority["candidate_cohort"][0]["path"]
    first.write_bytes(b"other synthetic digest\n")
    with pytest.raises(ConsumingBoundaryError, match="identity mismatch"):
        verify_candidate_cohort(authority, tmp_path)


def test_authority_task_itself_remains_non_consuming() -> None:
    authority = _authority()
    assert authority["approval"]["implementation_acceptance"] == "not_claimed"
    assert authority["approval"]["runtime_acceptance"] == "not_claimed"
    assert authority["run_token"]["token_consumed"] is False
    assert "token_consumption_or_child_launch_in_the_authority_task" in authority[
        "scope"
    ]["forbidden"]
    assert Path(AUTHORITY_PATH).name.endswith("-v1.json")


def test_worker_ownership_is_orchestration_bound_not_runtime_self_asserted() -> None:
    authority = _authority()
    script = (ROOT / "scripts/ck07r1_consuming_boundary.py").read_text(
        encoding="utf-8"
    )
    assert authority["worker"]["thread_id"] == (
        "019fbfe2-8fe4-7de2-9264-d58572366727"
    )
    assert authority["worker"]["identity_enforcement"].endswith(
        "not_runtime_authentication"
    )
    assert authority["governance"]["runtime_attestation"].startswith(
        "not_required_not_claimed"
    )
    assert "--worker-id" not in script
