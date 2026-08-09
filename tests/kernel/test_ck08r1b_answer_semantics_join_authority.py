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
    successor_by_path = {
        item["path"]: item["sha256"]
        for item in authority["selected_successor_cohort"]["files"]
    }
    assert all(
        _sha256(item["path"])
        in {item["sha256"], successor_by_path.get(item["path"], item["sha256"])}
        for item in roots
    )
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


def test_import_order_identity_correction_is_exact_and_non_semantic() -> None:
    authority = _load(AUTHORITY_PATH)
    correction = authority["identity_correction"]
    review_correction = authority["review_correction"]
    acceptance_correction = authority["acceptance_correction"]
    writer_closure_correction = authority["writer_closure_correction"]
    cohort = authority["selected_successor_cohort"]

    assert isinstance(correction, dict)
    assert isinstance(cohort, dict)
    assert correction == {
        "base_sha": "97ea3aed8f67c7840a34b610e7e0588b7eaf3c4d",
        "source_pr": 430,
        "worker_head_sha": "78d01ab9e19b37da776abe638f0feb436b4780bd",
        "path": "scripts/generate_ck07a_fixture.py",
        "failure": "hosted_ruff_i001_import_order",
        "superseded_successor_sha256": (
            "37cfd57351491c25141fde2d6ef0812d3f4e6e6b60921a2ce6e1af670b3cc28d"
        ),
        "selected_successor_sha256": (
            "f7adde83efb963121e841aec8d71ebd2e2be1fa3a1c2745d8e5ec05e6884cb68"
        ),
        "superseded_patch_sha256": (
            "d3ba81015172cd6e0be2dbaa3beb0aa321cc0232c7820d7ce7cba5630c0674d2"
        ),
        "selected_patch_sha256": (
            "38c0db5c2242a962b20fa2abd05c264fb08e36f6d9dc542fe5763ca69986c690"
        ),
        "changed_successor_paths": 1,
        "unchanged_successor_paths": 17,
        "semantic_change": "none",
        "worker_pr_edit": "forbidden",
    }
    assert isinstance(review_correction, dict)
    assert isinstance(acceptance_correction, dict)
    assert isinstance(writer_closure_correction, dict)
    assert cohort["preflight_base_sha"] == writer_closure_correction["base_sha"]
    assert cohort["patch_sha256"] == writer_closure_correction["selected_patch_sha256"]
    assert review_correction["superseded_patch_sha256"] == correction["selected_patch_sha256"]
    assert (
        acceptance_correction["superseded_selected_patch_sha256"]
        == review_correction["selected_patch_sha256"]
    )
    assert (
        writer_closure_correction["superseded_selected_patch_sha256"]
        == acceptance_correction["selected_patch_sha256"]
    )
    assert set(writer_closure_correction["added_successor_paths"]) == {
        "src/codex_usage_tracker/agent_kernel/publication/writer.py",
        "tests/agent_kernel/publication/test_writer.py",
    }
    assert set(writer_closure_correction["changed_successor_paths"]) == {
        "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
        "src/codex_usage_tracker/agent_kernel/publication/writer.py",
        "tests/agent_kernel/publication/test_writer.py",
    }
    assert set(acceptance_correction["changed_successor_paths"]) == {
        "src/codex_usage_tracker/agent_kernel/domain/plan_derivations_structural.py",
        "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
        "tests/agent_kernel/contracts/test_plan_derivations_structural.py",
        "tests/agent_kernel/fixtures/independent/semantic.py",
        "tests/agent_kernel/publication/test_preparation.py",
        "tests/agent_kernel/test_ck08r1c_independent_evaluator.py",
    }
    assert review_correction["worker_head_sha"] == (
        "3a86a10b12122d6ff9bec70f5f62105157af25c8"
    )

    selected = {
        item["path"]: item["sha256"]
        for item in cohort["files"]
        if isinstance(item, dict)
    }
    assert selected[correction["path"]] == correction["selected_successor_sha256"]
    assert correction["superseded_successor_sha256"] not in selected.values()
    assert correction["superseded_patch_sha256"] != cohort["patch_sha256"]


def test_successor_cohort_and_consumer_ownership_are_bounded() -> None:
    authority = _load(AUTHORITY_PATH)
    cohort = authority["selected_successor_cohort"]
    join = authority["consumer_join"]
    assert isinstance(cohort, dict)
    assert isinstance(join, dict)
    files = cohort["files"]
    assert isinstance(files, list)
    assert len(files) == 23
    paths = {item["path"] for item in files}
    assert {
        "src/codex_usage_tracker/agent_kernel/query/compiler.py",
        "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
        "src/codex_usage_tracker/agent_kernel/publication/writer.py",
        "experiments/physical-architecture/candidate_a/queries.py",
        "tests/agent_kernel/fixtures/independent/semantic.py",
        "tests/agent_kernel/fixtures/oracles/database_replay.py",
        "tests/agent_kernel/publication/test_preparation.py",
        "tests/agent_kernel/publication/test_writer.py",
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
        "result": "171 passed focused preflight",
        "case_count": 80,
        "independent_rows_equal_production_rows": True,
        "independent_grades_equal_frozen_grades": True,
        "fixture_source_jsonl_unchanged": True,
        "review_mutations": [
            "Q-WF-02 start-before/terminal-inside and start-inside/terminal-after straddling",
            "production publication complete hierarchy plus dangling and cyclic rejection",
            "independent evaluator duplicate call, tool, and state-change stable-ID rejection",
            "Q-REV-03 direct fact answers and bound internal formula diagnostics",
            "late relationship cycle, reverse-order chain, ambiguous new parent, and missing-parent rejection",
            "production and independent required tool start/terminal null timestamp rejection",
            "writer-owned existing non-root closure, reverse late chain, reparented descendants, unaffected-row preservation, and write-set parity",
        ],
    }


def test_successor_cohort_is_all_or_none_and_rejects_unbound_bytes() -> None:
    authority = _load(AUTHORITY_PATH)
    files = authority["selected_successor_cohort"]["files"]
    assert isinstance(files, list)
    observed = {item["path"]: _sha256(item["path"]) for item in files}
    state = _cohort_state(files, observed)
    assert state in {"predecessor", "successor"}

    mixed = dict(observed)
    mixed[files[0]["path"]] = (
        files[0]["sha256"]
        if state == "predecessor"
        else files[0]["predecessor_sha256"]
    )
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
        "writer snapshot",
        "reparented subtree",
        "session hierarchy",
        "measurement_mask",
        "session selector",
        "half-open window",
        "straddling",
        "start coordinate",
        "terminal coordinate",
        "terminal without start",
        "terminal ordered before start",
        "formula diagnostics",
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
