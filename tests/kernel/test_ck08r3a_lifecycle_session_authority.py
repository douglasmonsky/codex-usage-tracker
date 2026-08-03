from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "lifecycle-session-boundedness-authority.json"
)
_SCHEMA = _ROOT / (
    "docs/decisions/evidence/ck08r3a/"
    "lifecycle-session-boundedness-authority.schema.json"
)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _errors(value: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_json(_SCHEMA)).iter_errors(value))


def test_lifecycle_session_authority_is_independently_valid_and_exact() -> None:
    authority = _json(_AUTHORITY)
    schema = _json(_SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)

    assert authority["authority_base_sha"] == (
        "7d5a4b1717db78891fd2c38d8803d7fe2f922986"
    )
    assert authority["status"] == "permitted_not_accepted"
    assert authority["role_policy"] == {
        "closed": True,
        "path_free": True,
        "vocabulary": [
            "evidence_service_source",
            "publication_preparation",
            "publication_writer",
            "analytical_ddl",
            "schema_contract",
            "domain_models",
            "lifecycle_storage",
            "evidence_service_test",
            "fact_adapter_support_test",
            "published_fixture",
            "publication_writer_test",
            "independent_ddl_test",
            "tiny_accounting_test",
            "fact_backed_publication_test",
            "storage_identity_test",
            "storage_lifecycle_test",
        ],
    }

    cohort = authority["selected_cohort"]
    assert cohort["atomic"] is True
    assert cohort["mixed_cohort"] == "reject"
    assert [item["path"] for item in cohort["production_identities"]] == [
        "src/codex_usage_tracker/agent_kernel/evidence/service.py",
        "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
        "src/codex_usage_tracker/agent_kernel/publication/writer.py",
        "src/codex_usage_tracker/agent_kernel/storage/analytical.sql",
        "src/codex_usage_tracker/agent_kernel/storage/schema.py",
        "src/codex_usage_tracker/agent_kernel/domain/models.py",
        "src/codex_usage_tracker/agent_kernel/storage/lifecycle.py",
    ]
    assert [item["path"] for item in cohort["support_identities"]] == [
        "tests/agent_kernel/evidence/test_service.py",
        "tests/agent_kernel/fact_adapters/support.py",
        "tests/agent_kernel/fixtures/published_v2.py",
        "tests/agent_kernel/publication/test_writer.py",
        "tests/agent_kernel/storage/test_database_schema.py",
        "tests/agent_kernel/storage/test_tiny_accounting.py",
        "tests/agent_kernel/test_fact_backed_publication_v2.py",
        "tests/agent_kernel/storage/test_identity.py",
        "tests/agent_kernel/storage/test_lifecycle.py",
    ]

    assert authority["schema_contract"]["lifecycle_persisted_columns"] == [
        "session_id TEXT NOT NULL",
        "FOREIGN KEY (session_id) REFERENCES sessions(session_id)",
    ]
    assert authority["schema_contract"]["lifecycle_index"] == (
        "evidence_lifecycle_by_session_order"
    )
    assert authority["join_only_candidate"]["direct_use"] == "forbidden"
    assert "USE TEMP B-TREE FOR ORDER BY" in authority["join_only_candidate"]["rejection"]
    assert authority["negative_tests"]["malformed_independent_ddl_handoff_fragment"] == (
        "e85210d2d"
    )
    assert authority["negative_tests"]["database_owner"] == "storage/database.py"


def test_lifecycle_session_schema_rejects_broader_scope_and_cohort_mutations() -> None:
    authority = _json(_AUTHORITY)
    mutations: list[dict[str, Any]] = []

    role_swap = copy.deepcopy(authority)
    role_swap["selected_cohort"]["production_identities"][0]["role"] = "schema_contract"
    mutations.append(role_swap)

    path_swap = copy.deepcopy(authority)
    path_swap["selected_cohort"]["production_identities"][0]["path"] = (
        "src/codex_usage_tracker/agent_kernel/storage/database.py"
    )
    mutations.append(path_swap)

    hash_swap = copy.deepcopy(authority)
    hash_swap["selected_cohort"]["production_identities"][0]["sha256"] = (
        authority["selected_cohort"]["production_identities"][1]["sha256"]
    )
    mutations.append(hash_swap)

    for mutate in (
        lambda value: value["scope"]["implementation_reapply_scope"].append(
            "src/codex_usage_tracker/agent_kernel/storage/database.py"
        ),
        lambda value: value["scope"]["forbidden"].__setitem__(0, "allow migration"),
        lambda value: value["physical_contract"].__setitem__(
            "marker_free_explain", False
        ),
        lambda value: value["selected_cohort"].__setitem__("mixed_cohort", "allow"),
        lambda value: value["negative_tests"].__setitem__(
            "generic_explain_relaxation", "allowed"
        ),
    ):
        mutated = copy.deepcopy(authority)
        mutate(mutated)
        mutations.append(mutated)

    assert all(_errors(value) for value in mutations)


def test_linked_ck07_and_preflight_are_current_but_not_accepted() -> None:
    authority = _json(_AUTHORITY)
    ck07 = authority["ck07_transition"]
    assert ck07["status"] == "blocked_hold"
    assert ck07["authority_main_sha256"].startswith("408d18e4")
    assert ck07["r3a_atomic_cohort_sha256"] == (
        "6689d61fbf6d7948e1958a9d0bc58b4ea326a7f04221914b74c0651e0be1e37c"
    )
    assert ck07["previous_r3a_candidate_sha256"].startswith("e204e0da")
    assert ck07["historical_d192_sha256"].startswith("d192c858")
    assert ck07["direct_use_of_d192"] == "forbidden"
    assert ck07["run_token"] == {
        "maximum_new_end_to_end_runs": 1,
        "status": "unspent_unavailable",
        "launch_authorized": False,
    }
    assert authority["preflight"] == {
        "base_sha": "7d5a4b1717db78891fd2c38d8803d7fe2f922986",
        "worktree_role": "fresh exact-main integration worktree",
        "reapplied_exact_cohort": True,
        "authority_bytes_byte_identical": True,
        "status": "passed",
        "foreign_history_counts": [0, 1000, 5000],
        "focused_physical_boundaries": True,
        "no_consuming_operation": True,
    }
