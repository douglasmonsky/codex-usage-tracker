from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_PATH = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "bounded-session-merge-sort-portability-authority.json"
)
_SCHEMA_PATH = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "bounded-session-merge-sort-portability-authority.schema.json"
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _authority() -> dict[str, Any]:
    return _json(_AUTHORITY_PATH)


def _errors(value: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_json(_SCHEMA_PATH)).iter_errors(value))


def test_portability_authority_is_independently_valid_and_exact() -> None:
    authority = _authority()
    schema = _json(_SCHEMA_PATH)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)

    assert authority["schema"] == (
        "codex-usage-tracker.ck08r3a-"
        "bounded-session-merge-sort-portability-authority.v1"
    )
    assert authority["authority_base_sha"] == (
        "a152c7558281ded8a9d9000fc668843145cc43dd"
    )
    assert authority["status"] == "permitted_not_accepted"
    assert authority["contract_mode"] == "predecessor_rejection_only"
    assert authority["supersedes"]["field"] == (
        "selected.physical_evidence.marker_free_explain"
    )

    role_policy = authority["role_policy"]
    assert role_policy["closed"] is True
    assert role_policy["path_free"] is True
    assert all("/" not in role and "\\" not in role for role in role_policy["vocabulary"])

    cohort = authority["selected_cohort"]
    assert cohort["atomic"] is True
    assert cohort["mixed_cohort"] == "reject"
    assert len(cohort["production_identities"]) == 7
    assert len(cohort["support_identities"]) == 9
    assert cohort["support_identities"][0] == {
        "path": "tests/agent_kernel/evidence/test_service.py",
        "role": "evidence_service_test",
        "sha256": "2a97bfaa0804d693fbd30d97096e28e42c4f515288302073e04e7ea9f9880f69",
    }
    assert cohort["revised_support_transition"]["predecessor_sha256"] == (
        "cfc2dbce0a583742abfa90e1db6c04a80d9f07577ab8ff65a086d097b2739a3a"
    )
    assert cohort["revised_support_transition"]["authority_pr_inclusion"] == (
        "identity_only"
    )

    contract = authority["physical_contract"]
    assert contract["allowed_views"] == ["timeline", "allowance_interval"]
    assert contract["allowed_page_shape"] == "deep"
    assert contract["allowed_directions"] == ["forward", "backward"]
    assert contract["max_markers"] == 1
    assert contract["zero_markers_allowed"] is True
    assert contract["marker_branch"] == "session_branch_only"
    assert contract["session_branch_cardinality"] == "at_most_one"
    assert contract["session_branch_lookup_chain"] == [
        "SEARCH s USING PRIMARY KEY (session_id=?)",
        "SEARCH o USING PRIMARY KEY (occurrence_id=?) LEFT-JOIN",
        "SEARCH sm USING INDEX source_manifestations_by_occurrence_key (manifestation_key=?) LEFT-JOIN",
    ]
    assert contract["lifecycle_branch_lookup"] == (
        "SEARCH lt USING INDEX evidence_lifecycle_by_session_order (session_id=?)"
    )
    assert contract["foreign_history"] == {
        "rows": [0, 1000, 5000],
        "portable_sqlite_callbacks": [21, 21, 21],
        "portable_returned_rows": [7, 7, 7],
        "portable_has_more": [True, True, True],
        "cursor_round_trip": True,
        "callback_growth": "reject",
    }
    assert contract["plan_matrix"]["sqlite_3_45_1"]["timeline"] == {
        "first_forward": 0,
        "first_backward": 0,
        "deep_forward": 1,
        "deep_backward": 1,
    }
    assert contract["plan_matrix"]["sqlite_3_45_1"]["allowance_interval"] == {
        "first_forward": 0,
        "first_backward": 0,
        "deep_forward": 1,
        "deep_backward": 1,
    }
    assert contract["plan_matrix"]["sqlite_3_45_1"]["all_other_supported_shapes"] == 0
    assert contract["plan_matrix"]["sqlite_3_53_3"]["all_required_shapes"] == 0
    assert contract["generic_explain_relaxation"] is False
    assert contract["host_version_special_case"] is False
    assert contract["additional_session_order_keys"] is False

    sqlite = authority["sqlite_evidence"]
    assert sqlite["portable_boundary"] == {
        "python_version": "3.14.6",
        "sqlite_version": "3.45.1",
        "sqlite_source_id": (
            "2024-01-30 16:01:20 "
            "e876e51a0ed5c5b3126f52e532044363a014bc594cfefa87ffb5b82257cc467a"
        ),
        "stat4_enabled": False,
        "compile_options": ["TEMP_STORE=1", "THREADSAFE=1"],
        "deep_exception_marker_count": 1,
        "first_and_other_marker_count": 0,
    }
    assert sqlite["local_newer_boundary"]["sqlite_version"] == "3.53.3"
    assert sqlite["local_newer_boundary"]["stat4_enabled"] is True
    assert sqlite["local_newer_boundary"]["all_required_marker_count"] == 0


def test_portability_schema_rejects_identity_and_exception_mutations() -> None:
    authority = _authority()
    mutations: list[dict[str, Any]] = []

    for index, field, value in (
        (0, "role", "schema_contract"),
        (0, "path", "src/codex_usage_tracker/agent_kernel/storage/schema.py"),
        (
            0,
            "sha256",
            authority["selected_cohort"]["production_identities"][1]["sha256"],
        ),
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
            "sha256", "cfc2dbce0a583742abfa90e1db6c04a80d9f07577ab8ff65a086d097b2739a3a"
        ),
        lambda value: value["physical_contract"].__setitem__("max_markers", 2),
        lambda value: value["physical_contract"]["allowed_views"].append("calls"),
        lambda value: value["physical_contract"]["session_branch_lookup_chain"].pop(),
        lambda value: value["physical_contract"].__setitem__(
            "lifecycle_branch_lookup", "SCAN lifecycle_transitions"
        ),
        lambda value: value["physical_contract"]["foreign_history"].__setitem__(
            "portable_sqlite_callbacks", [21, 22, 21]
        ),
        lambda value: value["physical_contract"].__setitem__(
            "result_truth_unchanged", False
        ),
        lambda value: value["sqlite_evidence"]["portable_boundary"].__setitem__(
            "sqlite_version", ">=3.45.1"
        ),
        lambda value: value["physical_contract"]["forbidden_markers"].remove(
            "USE TEMP B-TREE FOR ORDER BY outside the session branch"
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
        lambda value: value["ck07_transition"]["run_token"].__setitem__(
            "launch_authorized", True
        ),
        lambda value: value["role_policy"]["vocabulary"].__setitem__(
            0, "../../evidence_service_source"
        ),
    ):
        mutated = copy.deepcopy(authority)
        mutate(mutated)
        mutations.append(mutated)

    assert all(_errors(value) for value in mutations)


def test_portability_authority_preserves_rejection_ck07_and_scope_boundaries() -> None:
    authority = _authority()
    assert authority["negative_tests"]["database_owner"] == "storage/database.py"
    assert authority["negative_tests"]["migration_or_compatibility"] == "reject"
    assert authority["preflight"]["reapplied_candidate_path_count"] == 16
    assert authority["preflight"]["status"] == "passed"
    assert authority["preflight"]["authority_bytes_byte_identical"] is True
    assert authority["preflight"]["no_consuming_operation"] is True
    assert authority["preflight"]["pr_417_remains_held"] is True

    ck07 = authority["ck07_transition"]
    assert ck07["status"] == "blocked_hold"
    assert ck07["mixed_state"] == "reject"
    assert ck07["direct_use_of_d192"] == "forbidden"
    assert ck07["run_token"] == {
        "maximum_new_end_to_end_runs": 1,
        "status": "unspent_unavailable",
        "launch_authorized": False,
        "output_authorized": False,
        "ledger_mutation_authorized": False,
    }

    scope = authority["scope"]
    assert "src/codex_usage_tracker/agent_kernel/storage/database.py" in scope["forbidden"]
    assert not any(path.startswith("src/") for path in scope["authority_write_scope"])
    assert scope["authority_write_scope"][-2:] == [
        "tests/kernel/test_kernel_scope.py",
        "tests/kernel/test_documentation_authority.py",
    ]
    assert authority["no_live_operation"] is True
