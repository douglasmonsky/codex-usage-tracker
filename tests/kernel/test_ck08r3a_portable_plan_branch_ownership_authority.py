from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_PATH = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "portable-plan-branch-ownership-authority.json"
)
_SCHEMA_PATH = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "portable-plan-branch-ownership-authority.schema.json"
)
_INHERITED_PATH = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "bounded-session-merge-sort-portability-authority.json"
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _authority() -> dict[str, Any]:
    return _json(_AUTHORITY_PATH)


def _schema() -> dict[str, Any]:
    return _json(_SCHEMA_PATH)


def _errors(value: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_schema()).iter_errors(value))


def test_branch_ownership_authority_is_independently_valid_and_inherits_exact_cohort() -> None:
    authority = _authority()
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)

    assert authority["status"] == "permitted_not_accepted"
    assert authority["contract_mode"] == "predecessor_rejection_only"
    assert authority["authority_base_sha"] == (
        "d638f6a5c5079e1d1c80ba74704314ae091c9d4a"
    )
    inherited = _json(_INHERITED_PATH)
    assert hashlib.sha256(_INHERITED_PATH.read_bytes()).hexdigest() == (
        authority["inherited_authority"]["sha256"]
    )
    assert authority["selected_cohort"]["production_identities"] == inherited[
        "selected_cohort"
    ]["production_identities"]
    assert authority["selected_cohort"]["support_identities"][1:] == inherited[
        "selected_cohort"
    ]["support_identities"][1:]
    assert authority["selected_cohort"]["support_identities"][0] == {
        "path": "tests/agent_kernel/evidence/test_service.py",
        "role": "evidence_service_test",
        "sha256": "bc01c3149101f0fd6c787e23a00c7bd2b2ec21628e8508223b8828df1f13390b",
    }
    assert authority["selected_cohort"]["corrected_support_transition"] == {
        "path": "tests/agent_kernel/evidence/test_service.py",
        "predecessor_sha256": "2a97bfaa0804d693fbd30d97096e28e42c4f515288302073e04e7ea9f9880f69",
        "selected_sha256": "bc01c3149101f0fd6c787e23a00c7bd2b2ec21628e8508223b8828df1f13390b",
        "reason": "full EXPLAIN topology proves the sole portable marker belongs to the unique leftmost session-event branch and rejects calls/tools/lifecycle/ambiguous ownership mutations",
        "authority_pr_inclusion": "identity_only",
    }


def test_branch_ownership_proof_is_structural_and_fail_closed() -> None:
    authority = _authority()
    proof = authority["branch_ownership_proof"]
    assert proof["method"].startswith("EXPLAIN QUERY PLAN")
    assert proof["session_event_input_route"] == (
        "unique leftmost-child ancestry from the compound-query root"
    )
    assert proof["candidate_parent_count"] == 1
    assert proof["unique_structural_candidate"] is True
    assert proof["marker_parent_must_equal_session_branch_parent"] is True
    assert proof["marker_must_follow_manifestation_lookup"] is True
    assert proof["all_other_direct_branch_details_reject"] is True
    assert authority["physical_contract"]["generic_explain_relaxation"] is False
    assert authority["physical_contract"]["host_version_special_case"] is False
    assert authority["physical_contract"]["production_ddl_schema_unchanged"] is True
    assert set(authority["negative_tests"]) >= {
        "marker_under_calls_branch",
        "marker_under_tools_branch",
        "marker_under_lifecycle_branch",
        "second_marker",
        "marker_detached_from_session_chain",
        "ambiguous_structural_owner",
    }
    assert all(value == "reject" for key, value in authority["negative_tests"].items() if key != "database_owner")


def test_branch_ownership_schema_rejects_identity_scope_and_plan_mutations() -> None:
    authority = _authority()
    mutations: list[dict[str, Any]] = []

    for index, field, value in (
        (0, "role", "schema_contract"),
        (0, "path", "src/codex_usage_tracker/agent_kernel/storage/schema.py"),
        (0, "sha256", authority["selected_cohort"]["production_identities"][1]["sha256"]),
    ):
        mutated = copy.deepcopy(authority)
        mutated["selected_cohort"]["production_identities"][index][field] = value
        mutations.append(mutated)

    for mutate in (
        lambda value: value["selected_cohort"]["production_identities"].append(
            {
                "path": "src/codex_usage_tracker/agent_kernel/storage/database.py",
                "role": "database_owner",
                "sha256": "0" * 64,
            }
        ),
        lambda value: value["selected_cohort"]["support_identities"][0].__setitem__(
            "sha256", value["selected_cohort"]["corrected_support_transition"]["predecessor_sha256"]
        ),
        lambda value: value["branch_ownership_proof"].__setitem__(
            "session_event_input_route", "any plan branch"
        ),
        lambda value: value["branch_ownership_proof"].__setitem__(
            "marker_parent_must_equal_session_branch_parent", False
        ),
        lambda value: value["branch_ownership_proof"].__setitem__(
            "candidate_parent_count", 2
        ),
        lambda value: value["physical_contract"].__setitem__("max_markers", 2),
        lambda value: value["physical_contract"]["allowed_views"].append("calls"),
        lambda value: value["physical_contract"].__setitem__(
            "generic_explain_relaxation", True
        ),
        lambda value: value["physical_contract"].__setitem__(
            "host_version_special_case", True
        ),
        lambda value: value["scope"]["authority_write_scope"].append(
            "src/codex_usage_tracker/agent_kernel/storage/database.py"
        ),
        lambda value: value["scope"]["forbidden"].remove(
            "generic EXPLAIN relaxation"
        ),
        lambda value: value["preflight"].__setitem__(
            "authority_bytes_byte_identical", False
        ),
        lambda value: value["preserved_boundaries"].__setitem__(
            "ck07_status", "ready"
        ),
        lambda value: value["role_policy"]["vocabulary"].__setitem__(
            0, "../../evidence_service_source"
        ),
    ):
        mutated = copy.deepcopy(authority)
        mutate(mutated)
        mutations.append(mutated)

    assert all(_errors(value) for value in mutations)


def test_branch_ownership_authority_scope_excludes_candidate_and_live_paths() -> None:
    authority = _authority()
    scope = authority["scope"]
    assert not any(
        path.startswith("src/") or path == "tests/agent_kernel/evidence/test_service.py"
        for path in scope["authority_write_scope"]
    )
    assert "tests/agent_kernel/evidence/test_service.py" in scope["preflight_only_candidate_scope"]
    assert "src/codex_usage_tracker/agent_kernel/storage/database.py" in scope["forbidden"]
    assert authority["preflight"]["no_consuming_operation"] is True
    assert authority["preflight"]["pr_417_remains_held"] is True
    for path in (_AUTHORITY_PATH, _SCHEMA_PATH):
        content = path.read_text(encoding="utf-8")
        assert "/Users/" not in content
        assert "\\Users\\" not in content
