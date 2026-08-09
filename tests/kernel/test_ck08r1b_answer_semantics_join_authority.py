from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_PATH = (
    ROOT / "docs/decisions/evidence/ck08r1b/answer-semantics-join-authority.json"
)
SCHEMA_PATH = AUTHORITY_PATH.with_name("answer-semantics-join-authority.schema.json")


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _cohort_state(
    files: list[dict[str, str]],
    observed: dict[str, str],
) -> str:
    states: set[str] = set()
    for item in files:
        actual = observed[item["path"]]
        if actual == item["predecessor_sha256"]:
            states.add("predecessor")
        elif actual == item["sha256"]:
            states.add("successor")
        else:
            raise AssertionError(f"unbound cohort identity: {item['path']}")
    assert len(states) == 1, "mixed predecessor/successor cohort is forbidden"
    return states.pop()


def test_authority_validates_and_binds_live_r1a_and_r1c_inputs() -> None:
    authority = _load(AUTHORITY_PATH)
    Draft202012Validator(_load(SCHEMA_PATH)).validate(authority)

    producer = authority["producer_authority"]
    assert isinstance(producer, dict)
    artifacts = producer["artifacts"]
    assert isinstance(artifacts, list)
    assert all(_sha256(item["path"]) == item["sha256"] for item in artifacts)

    independent = authority["independent_truth_authority"]
    assert isinstance(independent, dict)
    roots = independent["accepted_roots"]
    assert isinstance(roots, list)
    assert all(_sha256(item["path"]) == item["sha256"] for item in roots)
    assert independent["preserved"] == [
        "recursive closure and accessibility verification",
        "forbidden import and role-overlap guards",
        "grading sentinel and grading-inaccessible behavior",
        "production-source mutation independence",
        "facts-only evaluation from R1A declarations",
    ]


def test_join_is_exact_non_accepting_and_reuses_only_the_held_worker() -> None:
    authority = _load(AUTHORITY_PATH)
    assert authority["status"] == "permitted_not_accepted"
    held = authority["held_candidate"]
    handoff = authority["worker_handoff"]
    assert isinstance(held, dict)
    assert isinstance(handoff, dict)
    assert held["worker_thread"] == "019fc419-0dab-73e3-a6cc-ce574f18c89f"
    assert len(held["candidate_paths"]) == 9
    assert held["authority_pr_candidate_bytes"] == "forbidden"
    subprocess.run(
        ["git", "cat-file", "-e", f"{held['candidate_base_sha']}^{{commit}}"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", held["candidate_base_sha"], "HEAD"],
        cwd=ROOT,
        check=True,
    )
    assert handoff == {
        "resume_existing_worker": "019fc419-0dab-73e3-a6cc-ce574f18c89f",
        "resume_after": "this authority is squash-merged and fresh exact-main identities are verified",
        "next_authorized_action": "reconstruct the held candidate in a fresh latest-exact-main worktree, apply only the bound consumer/evaluator/materialization corrections, and run the complete implementation gates",
        "replacement_worker": "forbidden",
        "implementation_acceptance": "not_granted_by_this_authority",
        "new_authority_task": "forbidden",
        "downstream_dispatch": "forbidden",
    }


def test_successor_cohort_and_consumer_ownership_are_bounded() -> None:
    authority = _load(AUTHORITY_PATH)
    cohort = authority["selected_successor_cohort"]
    join = authority["consumer_join"]
    assert isinstance(cohort, dict)
    assert isinstance(join, dict)
    files = cohort["files"]
    assert isinstance(files, list)
    assert len(files) == 18
    paths = {item["path"] for item in files}
    assert {
        "src/codex_usage_tracker/agent_kernel/query/compiler.py",
        "experiments/physical-architecture/candidate_a/queries.py",
        "tests/agent_kernel/fact_adapters/test_contracts.py",
        "tests/agent_kernel/fixtures/independent/semantic.py",
        "tests/agent_kernel/test_ck08r1c_independent_evaluator.py",
        "scripts/generate_ck07a_fixture.py",
        "tests/agent_kernel/fixtures/tiny-v2/manifest.json",
        "tests/agent_kernel/fixtures/tiny-v2/oracle-bundle.json",
        "tests/agent_kernel/fixtures/tiny-v2/question-scenarios.json",
    } <= paths
    assert join["oracle_requalification"]["copied_expected_rows"] == "forbidden"
    assert (
        join["oracle_requalification"]["grading_source_imported_into_production"]
        == "forbidden"
    )
    assert cohort["focused_validation"] == {
        "result": "182 passed",
        "case_count": 80,
        "independent_rows_equal_production_rows": True,
        "independent_grades_equal_frozen_grades": True,
        "fixture_source_jsonl_unchanged": True,
        "review_mutations": [
            "Q-WF-02 no-match and same-window foreign-session selector isolation",
            "Q-WF-02 valid before-window and after-window tool exclusion",
            "Q-REV-03 missing, null, and mask-value mismatch while capability is unavailable",
        ],
    }


def test_successor_cohort_is_all_or_none_and_rejects_unbound_bytes() -> None:
    authority = _load(AUTHORITY_PATH)
    files = authority["selected_successor_cohort"]["files"]
    assert isinstance(files, list)
    observed = {item["path"]: _sha256(item["path"]) for item in files}
    assert _cohort_state(files, observed) == "predecessor"

    mixed = dict(observed)
    mixed[files[0]["path"]] = files[0]["sha256"]
    with pytest.raises(AssertionError, match="mixed predecessor/successor"):
        _cohort_state(files, mixed)

    unbound = dict(observed)
    unbound[files[0]["path"]] = "0" * 64
    with pytest.raises(AssertionError, match="unbound cohort identity"):
        _cohort_state(files, unbound)


def test_fail_closed_mutations_and_downstream_locks_are_complete() -> None:
    authority = _load(AUTHORITY_PATH)
    mutations = authority["negative_mutations"]
    assert isinstance(mutations, list)
    text = "\n".join(mutations)
    for required in (
        "session hierarchy",
        "measurement_mask",
        "session selector",
        "half-open window",
        "start coordinate",
        "terminal coordinate",
        "terminal without start",
        "terminal ordered before start",
        "grading sentinel",
        "production-source mutation",
        "canonical-fact mutation",
        "copied expected row",
        "closure membership",
    ):
        assert required in text

    scope = authority["scope"]
    gates = authority["required_gates"]
    assert isinstance(scope, dict)
    assert isinstance(gates, dict)
    locks = "\n".join(scope["locks"])
    assert all(packet in locks for packet in ("CK-08R4", "CK-08RG", "CK-09", "CK-07"))
    assert "full 80-case" in "\n".join(gates["implementation"])
