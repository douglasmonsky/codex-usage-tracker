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


def _changed_paths(authority_base_sha: str) -> set[str]:
    paths: set[str] = set()
    for command in (
        ["git", "diff", "--name-only", f"{authority_base_sha}...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
    ):
        result = subprocess.run(command, cwd=_REPO_ROOT, check=True, capture_output=True, text=True)
        paths.update(line for line in result.stdout.splitlines() if line)
    return paths


def test_ckqg1_authority_is_exact_and_binds_the_selected_successor() -> None:
    authority = _json(_AUTHORITY_PATH)
    schema = _json(_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    validator.validate(authority)

    assert authority["status"] == "permitted_not_accepted"
    assert authority["decision"] == "authorize_exact_successor_baseline_only"
    assert authority["authority_base_sha"] == "479cc58a887ab49e1bf6fae90ed87cd1cf389fd5"
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
    assert _sha256("src/codex_usage_tracker/agent_kernel/publication/writer.py") == (
        authority["decision_basis"]["accepted_main_change"]["source_sha256"]
    )
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
    assert changed_paths == set(scope["authority_write_scope"])
    assert authority_changed_path_failures(
        changed_paths, set(scope["authority_write_scope"])
    ) == []
    assert authority_changed_path_failures(
        changed_paths | {"src/codex_usage_tracker/agent_kernel/publication/writer.py"},
        set(scope["authority_write_scope"]),
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
    ):
        changed = deepcopy(authority)
        mutate(changed)
        assert list(validator.iter_errors(changed))
