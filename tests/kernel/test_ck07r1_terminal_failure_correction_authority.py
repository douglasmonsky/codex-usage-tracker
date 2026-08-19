from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import scripts.ck07r1_terminal_failure_correction as terminal_module
from scripts.ck07r1_terminal_failure_correction import (
    AUTHORITY_PATH,
    CLEAN_COMMIT_AUTHORITY_PATH,
    CLEAN_COMMIT_SCHEMA_PATH,
    SCHEMA_PATH,
    TerminalCorrectionError,
    load_authority,
    load_clean_commit_authority,
    verify_clean_candidate_transition,
    verify_clean_commit_authority_bytes,
    verify_clean_commit_authority_delta,
    verify_corrected_cohort,
    verify_exact_authority_delta,
    verify_exact_candidate_delta,
    verify_immutable_authority_bytes,
    verify_terminal_evidence,
)

ROOT = Path(__file__).resolve().parents[2]


def _authority() -> dict[str, Any]:
    return load_authority(ROOT)


def _clean_commit_authority() -> dict[str, Any]:
    return load_clean_commit_authority(ROOT)


def _write(path: Path, value: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return hashlib.sha256(value).hexdigest()


def _synthetic_candidate(authority: dict[str, Any], root: Path) -> None:
    for index, record in enumerate(authority["corrected_candidate_cohort"]):
        payload = f"corrected candidate {index}\n".encode()
        record["sha256"] = _write(root / record["path"], payload)
    v1 = {
        "state": "prelaunch_failed",
        "token_consumed": False,
        "token_status": "unspent_unavailable",
        "launch": {"matching_processes": []},
    }
    v2 = {
        "state": "failed_after_launch",
        "token_consumed": True,
        "token_status": "consumed",
        "token_consumed_at_utc": "2026-08-19T19:44:55Z",
        "retry_allowed": False,
        "restart_allowed": False,
        "replacement_allowed": False,
        "process": {
            "pid": 20482,
            "parent_pid": 20450,
            "run_token_id": "ck07r1-all-profile-e2e-1",
        },
        "launch": {
            "matching_processes": [],
            "prelaunch_recovery": {"candidate_cohort": authority["failed_candidate_cohort"]},
        },
        "failure": {"stage": "evidence_collection"},
    }
    stderr = {
        "exception_type": "AssertionError",
        "failure": "child_exception",
        "message": (
            "reachable planner did not select APPEND_SAFE_SMALL: "
            "APPEND_SAFE_LARGE selected_records=1369 "
            "reason limit_exceeded:selected_records"
        ),
    }
    evidence = authority["terminal_evidence"]
    evidence["v1_ledger"]["sha256"] = _write(
        root / evidence["v1_ledger"]["path"],
        (json.dumps(v1) + "\n").encode(),
    )
    evidence["v2_ledger"]["sha256"] = _write(
        root / evidence["v2_ledger"]["path"],
        (json.dumps(v2) + "\n").encode(),
    )
    evidence["v2_stderr"]["sha256"] = _write(
        root / evidence["v2_stderr"]["path"],
        (json.dumps(stderr) + "\n").encode(),
    )
    evidence["v2_stdout"]["sha256"] = _write(
        root / evidence["v2_stdout"]["path"],
        b"",
    )


def test_terminal_correction_schema_is_versioned_strict_and_exact() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    assert authority["schema"].endswith(".v1")
    assert authority["authority_base_sha"] == ("77cb03cb3dd6bcf5608249056cb3470bc7fee3d8")
    assert authority["status"] == "permitted_not_accepted"


def test_clean_commit_authority_is_versioned_strict_and_preserves_v1() -> None:
    authority = _clean_commit_authority()
    schema = json.loads((ROOT / CLEAN_COMMIT_SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    assert authority["schema"].endswith(".v1")
    assert authority["authority_base_sha"] == (
        "652f2166b58b9ee0d719348a769901577d11e6fd"
    )
    assert authority["implementation_transition"]["head_sha"] == (
        "927aa06f7c4c88319cc30247343c40db8e9b817e"
    )
    assert authority["status"] == "permitted_not_accepted"
    verify_clean_commit_authority_bytes(authority, ROOT)


def test_clean_commit_authority_delta_is_exact() -> None:
    authority = _clean_commit_authority()
    expected = set(authority["scope"]["authority_write_scope"])
    candidate = set(authority["scope"]["candidate_scope"])
    verify_clean_commit_authority_delta(authority, ROOT, observed=expected)
    verify_clean_commit_authority_delta(
        authority,
        ROOT,
        include_committed_candidate=True,
        observed=expected | candidate,
    )
    for changed in (
        expected - {next(iter(expected))},
        expected | {"scripts/benchmark_ck07r1_lifecycle_scale.py"},
    ):
        with pytest.raises(TerminalCorrectionError, match="authority Git delta"):
            verify_clean_commit_authority_delta(authority, ROOT, observed=changed)
    with pytest.raises(TerminalCorrectionError, match="not an ancestor"):
        verify_clean_commit_authority_delta(
            authority,
            ROOT,
            observed=expected,
            base_is_ancestor=False,
        )


def test_exact_authority_delta_admits_only_exact_clean_integrated_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _authority()
    clean_commit = _clean_commit_authority()
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        terminal_module,
        "load_clean_commit_authority",
        lambda _root: clean_commit,
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_clean_commit_authority_bytes",
        lambda _authority, _root: calls.append(("authority_bytes", None)),
    )
    monkeypatch.setattr(
        terminal_module,
        "_clean_candidate_bytes_exact",
        lambda _authority, _root: True,
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_clean_candidate_transition",
        lambda _authority, _root: "clean_integrated",
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_clean_commit_authority_delta",
        lambda _authority, _root, **kwargs: calls.append(
            ("authority_delta", kwargs["include_committed_candidate"])
        ),
    )
    terminal_module.verify_exact_authority_delta(authority, ROOT)
    assert calls == [
        ("authority_bytes", None),
        ("authority_delta", True),
    ]


def test_candidate_representation_accepts_exact_dirty_and_clean_states() -> None:
    authority = _clean_commit_authority()
    candidate = set(authority["scope"]["candidate_scope"])
    authority_scope = set(authority["scope"]["authority_write_scope"])
    base = authority["authority_base_sha"]
    tree = authority["authority_base_tree_sha"]
    head = authority["implementation_transition"]["head_sha"]
    assert (
        verify_clean_candidate_transition(
            authority,
            ROOT,
            observed_head=base,
            observed_head_tree=tree,
            observed_worktree=candidate,
        )
        == "dirty_prepublication"
    )
    assert (
        verify_clean_candidate_transition(
            authority,
            ROOT,
            observed_head=head,
            observed_head_tree="candidate-tree",
            observed_worktree=set(),
            observed_committed_delta=candidate,
            base_is_ancestor=True,
        )
        == "clean_pr_head"
    )
    assert (
        verify_clean_candidate_transition(
            authority,
            ROOT,
            observed_head="integrated-head",
            observed_head_tree="integrated-tree",
            observed_worktree=set(),
            observed_committed_delta=authority_scope | candidate,
            base_is_ancestor=True,
        )
        == "clean_integrated"
    )


def test_candidate_representation_rejects_partial_extra_wrong_base_and_wrong_head() -> None:
    authority = _clean_commit_authority()
    candidate = set(authority["scope"]["candidate_scope"])
    tree = authority["authority_base_tree_sha"]
    for changed in (
        candidate - {next(iter(candidate))},
        candidate | {"output/ck07r1/lifecycle-requalification-v2.json"},
    ):
        with pytest.raises(TerminalCorrectionError, match="all-or-none"):
            verify_clean_candidate_transition(
                authority,
                ROOT,
                observed_head=authority["authority_base_sha"],
                observed_head_tree=tree,
                observed_worktree=changed,
            )
    with pytest.raises(TerminalCorrectionError, match="head tree"):
        verify_clean_candidate_transition(
            authority,
            ROOT,
            observed_head=authority["authority_base_sha"],
            observed_head_tree="wrong-tree",
            observed_worktree=candidate,
        )
    with pytest.raises(TerminalCorrectionError, match="not an ancestor"):
        verify_clean_candidate_transition(
            authority,
            ROOT,
            observed_head=authority["implementation_transition"]["head_sha"],
            observed_head_tree="candidate-tree",
            observed_worktree=set(),
            observed_committed_delta=candidate,
            base_is_ancestor=False,
        )
    with pytest.raises(TerminalCorrectionError, match="lineage/delta"):
        verify_clean_candidate_transition(
            authority,
            ROOT,
            observed_head="wrong-head",
            observed_head_tree="candidate-tree",
            observed_worktree=set(),
            observed_committed_delta=candidate,
            base_is_ancestor=True,
        )


def test_terminal_correction_preserves_accepted_authority_bytes() -> None:
    verify_immutable_authority_bytes(_authority(), ROOT)


def test_terminal_evidence_and_corrected_cohort_are_exact(tmp_path: Path) -> None:
    authority = deepcopy(_authority())
    _synthetic_candidate(authority, tmp_path)
    verify_corrected_cohort(authority, tmp_path)
    v1, v2 = verify_terminal_evidence(authority, tmp_path)
    assert v1["token_consumed"] is False
    assert v2["token_consumed"] is True
    assert v2["state"] == "failed_after_launch"


@pytest.mark.parametrize(
    ("record_name", "replacement"),
    [
        ("v1_ledger", b"rewritten v1\n"),
        ("v2_ledger", b"rewritten v2\n"),
        ("v2_stderr", b"rewritten stderr\n"),
        ("v2_stdout", b"not empty\n"),
    ],
)
def test_terminal_evidence_rewrite_fails_closed(
    tmp_path: Path, record_name: str, replacement: bytes
) -> None:
    authority = deepcopy(_authority())
    _synthetic_candidate(authority, tmp_path)
    record = authority["terminal_evidence"][record_name]
    (tmp_path / record["path"]).write_bytes(replacement)
    with pytest.raises(TerminalCorrectionError, match="byte identity mismatch"):
        verify_terminal_evidence(authority, tmp_path)


def test_terminal_output_or_receipt_fabrication_fails_closed(tmp_path: Path) -> None:
    authority = deepcopy(_authority())
    _synthetic_candidate(authority, tmp_path)
    forbidden = tmp_path / authority["terminal_evidence"]["required_absent_paths"][0]
    forbidden.write_text("fabricated\n", encoding="utf-8")
    with pytest.raises(TerminalCorrectionError, match="forbidden terminal artifact"):
        verify_terminal_evidence(authority, tmp_path)


def test_corrected_candidate_digest_and_atomic_delta_fail_closed(
    tmp_path: Path,
) -> None:
    authority = deepcopy(_authority())
    _synthetic_candidate(authority, tmp_path)
    path = tmp_path / authority["corrected_candidate_cohort"][1]["path"]
    path.write_bytes(b"other benchmark\n")
    with pytest.raises(TerminalCorrectionError, match="candidate byte identity"):
        verify_corrected_cohort(authority, tmp_path)
    expected = set(authority["scope"]["combined_candidate_scope"])
    verify_exact_candidate_delta(authority, ROOT, observed=expected)
    for changed in (
        expected - {next(iter(expected))},
        expected | {"output/ck07r1/lifecycle-requalification-v2.json"},
    ):
        with pytest.raises(TerminalCorrectionError, match="candidate Git delta"):
            verify_exact_candidate_delta(authority, ROOT, observed=changed)


def test_authority_delta_is_exact_and_excludes_implementation() -> None:
    authority = _authority()
    expected = set(authority["scope"]["authority_write_scope"])
    verify_exact_authority_delta(authority, ROOT, observed=expected)
    assert "scripts/benchmark_ck07r1_lifecycle_scale.py" not in expected
    assert "src/codex_usage_tracker/agent_kernel/publication/preparation.py" not in expected
    with pytest.raises(TerminalCorrectionError, match="authority Git delta"):
        verify_exact_authority_delta(
            authority,
            ROOT,
            observed=expected | {"scripts/benchmark_ck07r1_lifecycle_scale.py"},
        )
    with pytest.raises(TerminalCorrectionError, match="not an ancestor"):
        verify_exact_authority_delta(
            authority,
            ROOT,
            observed=expected,
            base_is_ancestor=False,
        )


def test_combined_verifies_authority_binding_before_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = _authority()
    clean_commit = _clean_commit_authority()
    calls: list[str] = []

    monkeypatch.setattr(
        terminal_module,
        "load_clean_commit_authority",
        lambda _root: clean_commit,
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_clean_commit_authority_bytes",
        lambda _authority, _root: calls.append("authority_bytes"),
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_clean_candidate_transition",
        lambda _authority, _root: calls.append("candidate_transition")
        or "clean_integrated",
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_clean_commit_authority_delta",
        lambda _authority, _root, **_kwargs: calls.append("authority_delta"),
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_corrected_cohort",
        lambda _authority, _root: calls.append("cohort"),
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_terminal_evidence",
        lambda _authority, _root: calls.append("evidence"),
    )
    monkeypatch.setattr(
        terminal_module,
        "verify_planner_reproduction",
        lambda _authority, _root: calls.append("planner"),
    )
    monkeypatch.setattr(terminal_module, "_sha256", lambda _path: next(
        record["sha256"]
        for record in clean_commit["implementation_transition"]["paths"]
        if ROOT / record["path"] == _path
    ))
    monkeypatch.setattr(Path, "is_file", lambda _path: True)

    terminal_module.verify_combined(authority, ROOT)
    assert calls[:3] == [
        "authority_bytes",
        "candidate_transition",
        "authority_delta",
    ]


def test_planner_reproduction_binds_correct_large_classification_and_boundary() -> None:
    reproduction = _authority()["planner_reproduction"]
    assert reproduction["tail_limits"]["selected_records"] == 32
    assert reproduction["standard_30_day"] == {
        "operation_class": "append_safe_large",
        "reasons": ["limit_exceeded:selected_records"],
        "selected_records": 1369,
        "expected_wal_bytes": 11214848,
        "observations": 1369,
    }
    assert reproduction["production_first_chunk"]["reasons"] == [
        "limit_exceeded:selected_records",
        "limit_exceeded:expected_wal_bytes",
    ]
    assert reproduction["boundary"] == {
        "record_32": "append_safe_small",
        "record_33": "append_safe_large_limit_exceeded_selected_records",
    }


def test_terminal_state_never_authorizes_another_run_or_acceptance() -> None:
    authority = _authority()
    decision = authority["decision"]
    token = authority["run_token"]
    assert decision["new_command_invocations_permitted"] == 0
    assert decision["launch_authorized"] is False
    assert decision["token_refund"] is False
    assert decision["retry"] == decision["restart"] == decision["replacement"] == "none"
    assert decision["post_single_run"].startswith("unavailable")
    assert decision["final_accepted"] == "unavailable"
    assert decision["runtime_acceptance"] == "not_claimed"
    assert token["token_consumed"] is True
    assert token["remaining_invocations"] == 0
    assert token["successful_launches_observed"] == 1


def test_schema_rejects_token_scope_planner_and_acceptance_weakening() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    mutations = [
        lambda value: value["decision"].__setitem__("launch_authorized", True),
        lambda value: value["decision"].__setitem__("new_command_invocations_permitted", 1),
        lambda value: value["decision"].__setitem__("final_accepted", "available"),
        lambda value: value["run_token"].__setitem__("token_consumed", False),
        lambda value: value["run_token"].__setitem__("non_refundable", False),
        lambda value: value["planner_reproduction"]["tail_limits"].__setitem__(
            "selected_records", 1369
        ),
        lambda value: value["corrected_candidate_cohort"].pop(),
        lambda value: value["scope"]["authority_write_scope"].append(
            "scripts/benchmark_ck07r1_lifecycle_scale.py"
        ),
    ]
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(Draft202012Validator(schema).iter_errors(changed))


def test_authority_file_name_is_versioned() -> None:
    assert Path(AUTHORITY_PATH).name.endswith("-v1.json")


def test_clean_commit_schema_rejects_lineage_scope_and_no_run_weakening() -> None:
    authority = _clean_commit_authority()
    schema = json.loads(
        (ROOT / CLEAN_COMMIT_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    mutations = (
        lambda value: value["implementation_transition"].__setitem__(
            "base_sha", "0" * 40
        ),
        lambda value: value["implementation_transition"].__setitem__(
            "head_sha", "1" * 40
        ),
        lambda value: value["implementation_transition"]["paths"].pop(),
        lambda value: value["scope"]["candidate_scope"].pop(),
        lambda value: value["scope"]["candidate_scope"].append(
            "output/ck07r1/lifecycle-requalification-v2.json"
        ),
        lambda value: value["decision"].__setitem__("token_consumed", False),
        lambda value: value["decision"].__setitem__(
            "new_command_invocations_permitted", 1
        ),
        lambda value: value["decision"].__setitem__("launch_authorized", True),
        lambda value: value["decision"].__setitem__(
            "implementation_acceptance", "claimed"
        ),
        lambda value: value["source_authority"][0].__setitem__(
            "sha256", "2" * 64
        ),
    )
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(Draft202012Validator(schema).iter_errors(changed))


def test_clean_commit_authority_file_name_is_versioned() -> None:
    assert Path(CLEAN_COMMIT_AUTHORITY_PATH).name.endswith("-v1.json")
