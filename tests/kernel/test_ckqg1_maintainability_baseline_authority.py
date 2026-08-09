from __future__ import annotations

import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.check_kernel_scope import authority_changed_path_failures

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_PATH = "docs/decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json"
_SCHEMA_PATH = _AUTHORITY_PATH.removesuffix(".json") + ".schema.json"


def _json(path: str) -> dict:
    return json.loads((_REPO_ROOT / path).read_text(encoding="utf-8"))


def _sha256(path: str) -> str:
    return hashlib.sha256((_REPO_ROOT / path).read_bytes()).hexdigest()


def _serialized(document: dict) -> bytes:
    return (json.dumps(document, indent=2) + "\n").encode()


def _authority_head() -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", _AUTHORITY_PATH],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _changed_paths(authority_base_sha: str) -> set[str]:
    paths: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", f"{authority_base_sha}...{_authority_head()}"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ):
        result = subprocess.run(
            command,
            cwd=_REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        paths.update(line for line in result.stdout.splitlines() if line)
    return paths


def test_ckqg1_authority_is_exact_and_binds_the_selected_successor() -> None:
    authority = _json(_AUTHORITY_PATH)
    schema = _json(_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(authority)

    assert authority["status"] == "permitted_not_accepted"
    assert authority["decision"] == "authorize_exact_writer_transition_only"
    assert authority["authority_base_sha"] == "dd771073c9b3126599d2a0a8282edba04a48a09d"
    assert authority["decision_basis"]["accepted_main_change"] == {
        "path": "src/codex_usage_tracker/agent_kernel/publication/writer.py",
        "symbol": "PublicationWriter._validate_turn_provenance",
        "score": 35,
        "count": 1,
        "source_sha256": "13da341fc2a3c50d8d7de7fd6a6fc2b0aca0dbc832a9b56597cd96ab67d17488",
        "introduced_commit": "38537f6cee42ad4ba2fb6e45354e410053c7a7cd",
        "accepted_main_sha": "479cc58a887ab49e1bf6fae90ed87cd1cf389fd5",
        "accepted_pr": 417,
        "linked_authority": {
            "path": "docs/decisions/evidence/ck08r3a/final-shared-authority.json",
            "sha256": "ee479cbd4b41b63a1701df97abda01b27be7e559783d44503144bdf0c0bdef98",
        },
    }

    transition = authority["baseline_transition"]
    assert transition["metadata_sha256"] == (
        "a86abfe8565347950964245a11698aae587086e36f4cf3a48e5df6853ddd1c2d"
    )
    predecessor = transition["predecessor"]
    successor = transition["successor"]
    assert hashlib.sha256(_serialized(predecessor["document"])).hexdigest() == predecessor["sha256"]
    assert hashlib.sha256(_serialized(successor["document"])).hexdigest() == successor["sha256"]
    assert _sha256("config/agent-kernel/maintainability-baseline-v1.json") == (
        transition["successor"]["sha256"]
    )
    assert _sha256("src/codex_usage_tracker/agent_kernel/publication/writer.py") in {
        authority["decision_basis"]["accepted_main_change"]["source_sha256"],
        authority["cross_packet_writer_transition"]["writer_transition"]["successor_sha256"],
    }
    assert transition["transition_finding"] == {
        "id": "publication/writer.py:PublicationWriter._validate_turn_provenance",
        "score": 35,
        "count": 1,
        "predecessor_presence": "absent",
        "successor_presence": "exactly_once",
    }
    assert transition["predecessor"]["document"]["baseline_findings"] == [
        finding
        for finding in transition["successor"]["document"]["baseline_findings"]
        if finding["id"] != transition["transition_finding"]["id"]
    ]
    assert transition["successor"]["document"]["baseline_findings"].count(
        {"id": transition["transition_finding"]["id"], "score": 35, "count": 1}
    ) == 1
    assert authority["invariants"]["active_thresholds"] == {
        "block": "C",
        "module": "B",
        "average": "B",
    }
    assert authority["invariants"]["no_text_exemptions"] is True
    assert authority["invariants"]["release_size_ratchet"] == {
        "active_package_ceilings": {"wheel_bytes": 1000000, "sdist_bytes": 2000000},
        "historical_ck08r0_ratchet": {
            "wheel_bytes": 383000,
            "sdist_bytes": 820000,
            "maximum_headroom_percent": 25,
            "catalog_count_headroom": 0,
        },
        "package_policy": {
            "path": "docs/decisions/evidence/kernel-release-candidate-package-budget-supersession.json",
            "sha256": "4c1b40c31e8bd5357a6cbef4ee5083a95b6a703230666dca776f9b722b4f146a",
            "active_config_path": "config/kernel-release-candidate-budget.json",
            "active_config_sha256": "7e6e577ee47f9a0a22814ee6848c9b9759f4653c575bf564e5b768ec3987561d",
            "effective_date": "2026-08-01",
            "historical_package_ceilings": {"wheel_bytes": 383000, "sdist_bytes": 828000},
        },
        "preserved_non_package_budget": "bound_by_exact_package_policy_artifact",
    }
    assert _sha256(
        "docs/decisions/evidence/kernel-release-candidate-package-budget-supersession.json"
    ) == authority["invariants"]["release_size_ratchet"]["package_policy"]["sha256"]
    assert _sha256("config/kernel-release-candidate-budget.json") == authority["invariants"][
        "release_size_ratchet"
    ]["package_policy"]["active_config_sha256"]
    assert authority["invariants"]["privacy"].startswith("synthetic or repository-private")
    assert authority["invariants"]["spike_checks"] == "the CK-08R0 frozen-spike checks remain active"
    assert authority["non_generalizable"]["exact_transition_only"] is True
    assert authority["preflight"]["status"] == "passed"
    assert authority["preflight"]["authority_bytes_byte_identical"] is True

    assert _sha256("docs/decisions/evidence/ck08r0/corrective-gates-v1.json") == (
        "8f2bc6762b3b12f3c42ad72fb23ccaa49bfde3124280082fa65766bb9ceb9936"
    )
    for artifact in authority["linked_authorities"]:
        assert _sha256(artifact["path"]) == artifact["sha256"]

    scope = authority["scope"]
    assert transition["path"] not in scope["authority_write_scope"]
    assert "src/codex_usage_tracker/agent_kernel/publication/writer.py" in scope["forbidden"]
    assert "baseline/checker implementation edits in this authority PR" in scope["forbidden"]
    assert "config/agent-kernel/maintainability-baseline-v1.json" in scope[
        "preflight_only_candidate_scope"
    ]
    changed_paths = _changed_paths(authority["authority_base_sha"])
    allowed_paths = set(scope["authority_write_scope"])
    assert changed_paths <= allowed_paths
    assert authority_changed_path_failures(changed_paths, allowed_paths) == []
    assert authority_changed_path_failures(
        changed_paths | {"src/codex_usage_tracker/agent_kernel/publication/writer.py"},
        allowed_paths,
    ) == [
        "authority scope forbids changed path: "
        "src/codex_usage_tracker/agent_kernel/publication/writer.py"
    ]
    for doc_path in (
        "docs/INDEX.md",
        "docs/roadmap/REMAINING_EXECUTION_PLAN.md",
        "docs/roadmap/TASK_PACKETS.md",
        "docs/roadmap/tasks/ck-qg1-enforce-agent-kernel-maintainability.md",
    ):
        body = (_REPO_ROOT / doc_path).read_text(encoding="utf-8")
        assert "decisions/evidence/ckqg1/maintainability-baseline-transition-authority.json" in body

    changed = deepcopy(authority)
    changed["baseline_transition"]["predecessor"]["sha256"] = "0" * 64
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["baseline_transition"]["successor"]["document"]["baseline_findings"].pop()
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["baseline_transition"]["transition_finding"]["score"] = 36
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["invariants"]["active_thresholds"]["block"] = "D"
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["invariants"]["privacy"] = "real logs are permitted"
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["invariants"]["spike_checks"] = "disabled"
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["scope"]["authority_write_scope"].append(
        "src/codex_usage_tracker/agent_kernel/publication/writer.py"
    )
    assert list(validator.iter_errors(changed))

    changed = deepcopy(authority)
    changed["preflight"]["cases"][5]["observed"] = "pass"
    assert list(validator.iter_errors(changed))

def _git_show_sha(ref: str, path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return hashlib.sha256(result.stdout).hexdigest()


def test_ckqg1_binds_the_reviewed_r1b_writer_successor_without_baseline_growth() -> None:
    authority = _json(_AUTHORITY_PATH)
    schema = _json(_SCHEMA_PATH)
    transition = authority["cross_packet_writer_transition"]
    r1b = _json(transition["r1b_authority"]["path"])
    r1b_schema_path = transition["r1b_authority"]["schema_path"]
    r1b_schema = _json(r1b_schema_path)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator.check_schema(r1b_schema)
    Draft202012Validator(schema).validate(authority)
    Draft202012Validator(r1b_schema).validate(r1b)

    assert transition["packet"] == "CK-08R1B"
    assert transition["state"] == "exact_writer_successor_without_baseline_change"
    assert _sha256(transition["r1b_authority"]["path"]) == transition["r1b_authority"]["sha256"]
    assert _sha256(r1b_schema_path) == transition["r1b_authority"]["schema_sha256"]
    assert r1b["status"] == "permitted_not_accepted"
    assert r1b["worker_handoff"]["resume_existing_worker"] == "019fc419-0dab-73e3-a6cc-ce574f18c89f"
    assert r1b["writer_closure_correction"]["source_pr"] == 430
    assert r1b["writer_closure_correction"]["selected_successor_paths"] == 23

    writer_transition = transition["writer_transition"]
    assert writer_transition == {
        "path": "src/codex_usage_tracker/agent_kernel/publication/writer.py",
        "predecessor_sha256": "13da341fc2a3c50d8d7de7fd6a6fc2b0aca0dbc832a9b56597cd96ab67d17488",
        "successor_sha256": "d163e6c566665a65062952be1618b9f2c4032eabd841408e2f274bcd29748a73",
        "r1b_selected_cohort_predecessor_sha256": "13da341fc2a3c50d8d7de7fd6a6fc2b0aca0dbc832a9b56597cd96ab67d17488",
        "r1b_selected_cohort_successor_sha256": "d163e6c566665a65062952be1618b9f2c4032eabd841408e2f274bcd29748a73",
    }
    assert transition["source_pr"] == {
        "number": 430,
        "base_sha": "97ea3aed8f67c7840a34b610e7e0588b7eaf3c4d",
        "head_sha": "925270e6ad13074ddec756e0cd89165c29d9b144",
        "head_tree_sha": "aba15a107365a5cfccea80d5bbf57c7fb5f92e82",
        "head_changed_paths": 31,
        "url": "https://github.com/douglasmonsky/codex-usage-tracker/pull/430",
    }

    cohort = r1b["selected_successor_cohort"]["files"]
    assert len(cohort) == transition["r1b_authority"]["selected_successor_paths"] == 23
    for item in cohort:
        assert _git_show_sha("5eb9ffb4afc35e20db57ee936388c345d3c2c609", item["path"]) == item[
            "predecessor_sha256"
        ]
        assert _git_show_sha("925270e6ad13074ddec756e0cd89165c29d9b144", item["path"]) == item[
            "sha256"
        ]

    current_writer_sha = _sha256("src/codex_usage_tracker/agent_kernel/publication/writer.py")
    assert current_writer_sha in {
        writer_transition["predecessor_sha256"],
        writer_transition["successor_sha256"],
    }
    assert _sha256(transition["checker_binding"]["path"]) == transition["checker_binding"]["sha256"]
    assert _sha256(transition["baseline_binding"]["path"]) == transition["baseline_binding"]["sha256"]
    assert transition["baseline_binding"]["new_findings"] == []
    assert transition["baseline_binding"]["worsened_findings"] == []
    assert transition["baseline_binding"]["improved_findings"] == []
    if current_writer_sha == writer_transition["predecessor_sha256"]:
        assert transition["authorized_states"][0]["id"] == "current_main"
    else:
        assert current_writer_sha == writer_transition["successor_sha256"]
        assert transition["authorized_states"][1]["id"] == "pr430_reviewed_successor"
        assert _sha256(transition["r1b_authority"]["path"]) == transition["authorized_states"][1][
            "r1b_authority_sha256"
        ]

    from scripts.check_kernel_maintainability import (
        DEFAULT_SOURCE_ROOT,
        maintainability_failures,
        normalized_findings,
    )

    assert maintainability_failures() == []
    findings = normalized_findings(DEFAULT_SOURCE_ROOT)
    baseline = _json("config/agent-kernel/maintainability-baseline-v1.json")
    assert findings == baseline["baseline_findings"]
    assert hashlib.sha256(
        json.dumps(findings, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest() == transition["baseline_binding"]["normalized_findings_sha256"]

    assert transition["combined_preflight"] == {
        "status": "passed",
        "authority_bytes_byte_identical": True,
        "finding_count": 20,
        "normalized_findings_sha256": "17bf73aa73ce9f70bb9837379acf976662418e6288913c77fa70efd4b5b443cc",
        "cases": [
            {"id": "current_main_bound_state", "expected": "pass", "observed": "pass"},
            {"id": "pr430_reviewed_successor_same_baseline", "expected": "pass", "observed": "pass"},
            {
                "id": "pr430_successor_with_predecessor_baseline",
                "expected": "fail_closed:mismatch",
                "observed": "fail_closed:mismatch",
            },
            {
                "id": "writer_digest_mutation",
                "expected": "reject_fail_closed:identity",
                "observed": "reject_fail_closed:identity",
            },
            {
                "id": "r1b_authority_digest_mutation",
                "expected": "reject_fail_closed:identity",
                "observed": "reject_fail_closed:identity",
            },
            {
                "id": "pr430_head_mutation",
                "expected": "reject_fail_closed:identity",
                "observed": "reject_fail_closed:identity",
            },
            {
                "id": "new_unlisted_finding",
                "expected": "fail_closed:baseline",
                "observed": "fail_closed:baseline",
            },
            {
                "id": "worsened_finding",
                "expected": "fail_closed:baseline",
                "observed": "fail_closed:baseline",
            },
        ],
    }


def test_ckqg1_authority_rejects_unbound_future_changes() -> None:
    authority = _json(_AUTHORITY_PATH)
    validator = Draft202012Validator(_json(_SCHEMA_PATH))

    for mutate in (
        lambda value: value["decision_basis"]["accepted_main_change"].__setitem__(
            "source_sha256", "0" * 64
        ),
        lambda value: value["decision_basis"].__setitem__("not_generic_baseline_growth", False),
        lambda value: value["non_generalizable"].__setitem__("exact_transition_only", False),
        lambda value: value["negative_mutations"].pop(),
        lambda value: value["worker_handoff"].__setitem__("implementation_acceptance", "accepted"),
        lambda value: value["cross_packet_writer_transition"]["writer_transition"].__setitem__(
            "successor_sha256", "0" * 64
        ),
        lambda value: value["cross_packet_writer_transition"]["r1b_authority"].__setitem__(
            "sha256", "0" * 64
        ),
        lambda value: value["cross_packet_writer_transition"]["source_pr"].__setitem__(
            "head_sha", "0" * 40
        ),
        lambda value: value["cross_packet_writer_transition"]["baseline_binding"].__setitem__(
            "sha256", "0" * 64
        ),
    ):
        changed = deepcopy(authority)
        mutate(changed)
        assert list(validator.iter_errors(changed))
