from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.ck07r1_post_terminal_completion import (
    AUTHORITY_PATH,
    SCHEMA_PATH,
    PostTerminalCompletionError,
    load_authority,
    verify_authority_delta,
    verify_decision,
    verify_historical_successor_bindings,
    verify_integrated_cohort,
    verify_publication_evidence,
    verify_roadmap_transition,
    verify_source_authorities,
    verify_terminal_history,
)

ROOT = Path(__file__).resolve().parents[2]


def _authority() -> dict[str, object]:
    return load_authority(ROOT)


def test_post_terminal_authority_is_versioned_strict_and_exact() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)
    assert authority["schema"].endswith(".v1")
    assert authority["status"] == "roadmap_transition_authorized"
    assert authority["authority_base_sha"] == ("1d0466b1b2992b48c5272dc4598606eeaea4dae2")
    assert authority["authority_base_tree_sha"] == ("d1b06f0927ae660f9e09d642bb1ef79a04413b5f")


def test_source_authorities_and_integrated_seven_path_cohort_are_exact() -> None:
    authority = _authority()
    verify_source_authorities(authority, ROOT)
    verify_historical_successor_bindings(authority, ROOT)
    verify_integrated_cohort(authority, ROOT)
    assert len(authority["source_authorities"]) == 6
    assert len(authority["integrated_cohort"]["paths"]) == 7
    assert {record["path"] for record in authority["integrated_cohort"]["paths"]} == set(
        authority["scope"]["immutable_integrated_scope"]
    )


def test_terminal_history_remains_consumed_failed_and_receipt_absent() -> None:
    authority = _authority()
    verify_terminal_history(authority, ROOT)
    history = authority["terminal_history"]
    assert history["v1"]["state"] == "prelaunch_failed"
    assert history["v1"]["token_consumed"] is False
    assert history["v2"]["state"] == "failed_after_launch"
    assert history["v2"]["token_consumed"] is True
    assert history["remaining_invocations"] == 0
    assert history["token_refund"] is False
    assert history["retry"] == history["restart"] == history["replacement"] == "none"
    assert all(not (ROOT / path).exists() for path in history["required_absent_paths"])


def test_publication_and_hosted_evidence_bind_exact_lineage() -> None:
    authority = _authority()
    verify_publication_evidence(authority, ROOT)
    publications = authority["publication_evidence"]
    assert [
        publications[name]["pull_request"]
        for name in (
            "terminal_correction_authority",
            "clean_commit_authority",
            "corrected_implementation",
        )
    ] == [447, 450, 448]
    assert [
        publications[name]["ci_run"]
        for name in (
            "terminal_correction_authority",
            "clean_commit_authority",
            "corrected_implementation",
        )
    ] == [32302049140, 32401646264, 32402374087]
    assert publications["corrected_implementation"]["merge_sha"] == (
        "1d0466b1b2992b48c5272dc4598606eeaea4dae2"
    )


def test_decision_completes_dependency_without_runtime_acceptance() -> None:
    authority = _authority()
    verify_decision(authority)
    decision = authority["decision"]
    transition = authority["roadmap_transition"]
    assert decision["corrective_implementation_state"] == (
        "accepted_for_CK-07R1_roadmap_dependency"
    )
    assert decision["runtime_acceptance"] == "not_claimed"
    assert decision["planner_valid_receipt"] == "absent"
    assert decision["post_single_run"] == "unavailable"
    assert decision["final_accepted"] == "unavailable"
    assert decision["failed_after_launch_reclassified"] is False
    assert decision["new_command_invocations_permitted"] == 0
    assert decision["launch_authorized"] is False
    assert decision["token_consumed"] is True
    assert transition["completed"] == ["CK-07R1"]
    assert transition["new_ready"] == ["CK-08R4"]
    assert transition["still_blocked"] == ["CK-08RG", "CK-09"]


def test_authority_delta_accepts_only_exact_dirty_or_committed_transition() -> None:
    authority = _authority()
    expected = set(authority["scope"]["authority_write_scope"])
    base = authority["authority_base_sha"]
    assert (
        verify_authority_delta(
            authority,
            ROOT,
            observed_head=base,
            observed_worktree=expected,
        )
        == "dirty_prepublication"
    )
    assert (
        verify_authority_delta(
            authority,
            ROOT,
            observed_head="f" * 40,
            observed_worktree=set(),
            observed_committed=expected,
            base_is_ancestor=True,
        )
        == "clean_committed"
    )
    for worktree, committed in (
        (expected - {next(iter(expected))}, None),
        (expected | {"extra.txt"}, None),
        (set(), expected - {next(iter(expected))}),
        ({"extra.txt"}, expected),
    ):
        with pytest.raises(PostTerminalCompletionError):
            verify_authority_delta(
                authority,
                ROOT,
                observed_head=base if committed is None else "f" * 40,
                observed_worktree=worktree,
                observed_committed=committed,
                base_is_ancestor=True,
            )
    with pytest.raises(PostTerminalCompletionError, match="not an ancestor"):
        verify_authority_delta(
            authority,
            ROOT,
            observed_head="f" * 40,
            observed_worktree=set(),
            observed_committed=expected,
            base_is_ancestor=False,
        )


def test_roadmap_transition_exposes_only_ck08r4() -> None:
    verify_roadmap_transition(_authority(), ROOT)


def test_schema_rejects_acceptance_run_scope_and_readiness_weakening() -> None:
    authority = _authority()
    schema = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    mutations = (
        lambda value: value["decision"].__setitem__("runtime_acceptance", "claimed"),
        lambda value: value["decision"].__setitem__("final_accepted", "available"),
        lambda value: value["decision"].__setitem__("failed_after_launch_reclassified", True),
        lambda value: value["decision"].__setitem__("new_command_invocations_permitted", 1),
        lambda value: value["decision"].__setitem__("launch_authorized", True),
        lambda value: value["decision"].__setitem__("token_consumed", False),
        lambda value: value["terminal_history"].__setitem__("remaining_invocations", 1),
        lambda value: value["terminal_history"].__setitem__("token_refund", True),
        lambda value: value["integrated_cohort"]["paths"].pop(),
        lambda value: value["source_authorities"].pop(),
        lambda value: value["source_authorities"][0].__setitem__("path", "AGENTS.md"),
        lambda value: value["integrated_cohort"]["paths"][0].__setitem__(
            "path", "src/codex_usage_tracker/agent_kernel/publication/planner.py"
        ),
        lambda value: value["historical_successor_bindings"][0].__setitem__(
            "successor_sha256", "0" * 64
        ),
        lambda value: value["terminal_history"]["required_absent_paths"].__setitem__(
            0, "output/ck07r1/fabricated.json"
        ),
        lambda value: value["publication_evidence"]["corrected_implementation"].__setitem__(
            "ci_run", 1
        ),
        lambda value: value["deterministic_acceptance_evidence"]["path_proof"].__setitem__(
            0, "weakened"
        ),
        lambda value: value["residual_risks"].__setitem__(0, "weakened"),
        lambda value: value["required_transition_gates"].__setitem__(0, "weakened"),
        lambda value: value["roadmap_transition"]["new_ready"].append("CK-08RG"),
        lambda value: value["scope"]["authority_write_scope"].append(
            "scripts/benchmark_ck07r1_lifecycle_scale.py"
        ),
        lambda value: value["scope"]["authority_write_scope"].__setitem__(
            0, "src/codex_usage_tracker/agent_kernel/publication/planner.py"
        ),
        lambda value: value["scope"]["immutable_integrated_scope"].__setitem__(
            0, "output/ck07r1/fabricated.json"
        ),
        lambda value: value["scope"]["forbidden"].__setitem__(0, "weakened"),
    )
    for mutate in mutations:
        changed = deepcopy(authority)
        mutate(changed)
        assert list(Draft202012Validator(schema).iter_errors(changed))


def test_authority_file_name_is_versioned() -> None:
    assert Path(AUTHORITY_PATH).name.endswith("-v1.json")
