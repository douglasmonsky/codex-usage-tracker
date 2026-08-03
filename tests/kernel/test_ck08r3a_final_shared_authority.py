from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_PATH = _ROOT / "docs/decisions/evidence/ck08r3a/final-shared-authority.json"
_SCHEMA_PATH = _ROOT / "docs/decisions/evidence/ck08r3a/final-shared-authority.schema.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _authority() -> dict[str, Any]:
    return _json(_AUTHORITY_PATH)


def _schema() -> dict[str, Any]:
    return _json(_SCHEMA_PATH)


def _errors(value: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_schema()).iter_errors(value))


def test_final_shared_authority_is_schema_valid_and_binds_current_cohort() -> None:
    authority = _authority()
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)

    assert authority["schema"] == "codex-usage-tracker.ck08r3a-final-shared-authority.v3"
    assert authority["authority_version"] == 3
    assert authority["authority_base_sha"] == "7d5a4b1717db78891fd2c38d8803d7fe2f922986"
    assert authority["status"] == "permitted_not_accepted"
    assert authority["contract_mode"] == "predecessor_rejection_only"
    assert "lifecycle_boundedness" in authority["linked_authorities"]

    selected = authority["r3a"]["selected"]
    assert selected["status"] == "permitted_not_accepted"
    assert len(selected["production_identities"]) == 7
    assert len(selected["support_identities"]) == 9
    assert [
        (item["path"], item["role"], item["sha256"])
        for item in selected["production_identities"]
    ] == [
        (
            "src/codex_usage_tracker/agent_kernel/evidence/service.py",
            "evidence_service_source",
            "4458ffb03adeed838fcda992747dbaeb192ccf59728b3a54e1527abc4d0651fb",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
            "publication_preparation",
            "6689d61fbf6d7948e1958a9d0bc58b4ea326a7f04221914b74c0651e0be1e37c",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/publication/writer.py",
            "publication_writer",
            "13da341fc2a3c50d8d7de7fd6a6fc2b0aca0dbc832a9b56597cd96ab67d17488",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/analytical.sql",
            "analytical_ddl",
            "34b6aab813dbd520f1894ac3ccbce1a1b3ff4552a11f0a83597a897a0c8f7486",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/schema.py",
            "schema_contract",
            "9850a431729c7eb8d5347278d0434f0849d1843297645547ee2dcd66a0359b77",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/domain/models.py",
            "domain_models",
            "32eee9fba0cf7e2fc9933cd3f5e02ec39bf847b4c9196cab9917e464b339e9c2",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/lifecycle.py",
            "lifecycle_storage",
            "bf0b6b2cf098e063b072939c005c9500260fb758a3267050ac9ac206a8cba2a7",
        ),
    ]

    assert selected["schema_contract"] == {
        "sha256": "998343ba4b52bb39decfcb436f8a862d41884fc6f6a6b4e88f7e8f8e42446295",
        "analytical_table_count": 42,
        "analytical_index_count": 57,
        "operational_table_count": 6,
        "operational_index_count": 6,
        "evidence_index_count": 13,
        "index_names": [
            "evidence_model_calls_by_session_order",
            "evidence_model_call_tail_by_session_order",
            "evidence_tools_by_session_order",
            "evidence_activities_by_session_order",
            "evidence_state_changes_by_session_order",
            "evidence_compactions_by_session_order",
            "evidence_context_components_by_session_order",
            "evidence_turns_by_session_order",
            "evidence_lifecycle_by_session_order",
            "evidence_source_occurrences_by_logical_order",
            "evidence_tools_by_resource_order",
            "evidence_state_changes_by_resource_order",
            "evidence_allowance_observations_order",
        ],
    }
    assert selected["independent_ddl"] == {
        "test_path": "tests/agent_kernel/storage/test_database_schema.py",
        "test_sha256": "69e53fe786ab2e136529934cda830bf5eeb58bc480135492b6434d2d557fab29",
        "declaration_digest": "799dd9b79bab758fc624f8681e9c8b34a3d19a314a04eac55c4029746f3855d9",
        "execution_checked": True,
        "equality_checked": True,
        "candidate_self_reference": False,
        "literal_turn_order": {"event_kind_order": 20, "transition_rank": 0},
    }


def test_final_shared_rank_fixture_and_physical_contracts_are_exact() -> None:
    selected = _authority()["r3a"]["selected"]
    provenance = selected["turn_provenance"]
    assert provenance["rank_domain"] == "zero_based_nonnegative"
    assert provenance["rank_zero_valid"] is True
    assert provenance["rank_positive_preserved"] is True
    assert provenance["rank_equality"] == (
        "manifestation_observation_persisted_turn_and_evidence_rank_must_match_exactly"
    )
    assert provenance["rank_cases"] == [
        {"source_rank": 0, "preserved": True},
        {"source_rank": 3, "preserved": True},
    ]
    assert "collapse_positive_rank_to_zero" in provenance["negative_cases"]

    fixtures = selected["publication_fixtures"]
    current = next(state for state in fixtures["states"] if state["name"] == "selected")
    assert fixtures["variant_count"] == 80
    assert current["tuple_count"] == 80
    assert current["tuple_digest"] == (
        "b825e940247a7ea15f34fd71d7aa7774c1acfff3b810676515e66d1f93dffb06"
    )
    assert len(current["artifact_manifest_sha256s"]) == 80
    assert fixtures["mixed_cohort"] == "reject"
    assert current["artifacts"]["published_v2"]["sha256"] == (
        "eca815c5a47067bdc56759018e12fd7a25f446eb6d716236869cbef875ce8515"
    )

    physical = selected["physical_evidence"]
    assert physical["foreign_lifecycle_rows"] == [0, 1000, 5000]
    assert physical["strategy"] == (
        "persisted_session_id_with_session_leading_lifecycle_order_index"
    )
    assert physical["marker_free_explain"] is True
    assert physical["limit_plus_one_before_decode"] is True
    assert physical["cursor_reversible"] is True


def test_final_shared_schema_rejects_identity_scope_and_boundary_mutations() -> None:
    authority = _authority()
    mutations: list[dict[str, Any]] = []

    for index, field, value in (
        (0, "role", "schema_contract"),
        (0, "path", "src/codex_usage_tracker/agent_kernel/storage/schema.py"),
        (0, "sha256", authority["r3a"]["selected"]["production_identities"][1]["sha256"]),
    ):
        mutated = copy.deepcopy(authority)
        mutated["r3a"]["selected"]["production_identities"][index][field] = value
        mutations.append(mutated)

    for _name, mutate in (
        (
            "database owner",
            lambda value: value["scope"]["implementation_reapply_scope"].append(
                "src/codex_usage_tracker/agent_kernel/storage/database.py"
            ),
        ),
        (
            "scope substitution",
            lambda value: value["scope"]["authority_write_scope"].__setitem__(
                0, "src/codex_usage_tracker/agent_kernel/storage/database.py"
            ),
        ),
        (
            "forbidden scope",
            lambda value: value["scope"]["forbidden"].__setitem__(0, "allow migration"),
        ),
        (
            "rebuild rule",
            lambda value: value["r3a"]["predecessor_rejection"].__setitem__(
                "rebuild_rule", "migrate in place"
            ),
        ),
        (
            "rank domain",
            lambda value: value["r3a"]["selected"]["turn_provenance"].__setitem__(
                "rank_domain", "positive_only"
            ),
        ),
        (
            "mixed fixture",
            lambda value: value["r3a"]["selected"]["publication_fixtures"].__setitem__(
                "mixed_cohort", "allow"
            ),
        ),
    ):
        mutated = copy.deepcopy(authority)
        mutate(mutated)
        mutations.append(mutated)

    assert all(_errors(value) for value in mutations)


def test_final_shared_rejection_and_ck07_state_remain_fail_closed() -> None:
    authority = _authority()
    rejection = authority["r3a"]["predecessor_rejection"]
    assert rejection["application_boundary"] == (
        "before_application_query_mutation_repair_or_promotion"
    )
    assert rejection["enumeration_hash_schema_validation"] == "not_overclaimed"
    assert rejection["mutation_free"] is True
    assert rejection["forbidden_compatibility"] == [
        "migration",
        "backfill",
        "compatibility_views",
        "temporary_read_only_migration",
        "pointer_identity_refresh",
        "caller_plumbing",
    ]
    assert authority["ck07_shared_preparation"]["status"] == "blocked_hold"
    assert authority["ck07_shared_preparation"]["r3a_atomic_cohort"]["sha256"] == (
        "6689d61fbf6d7948e1958a9d0bc58b4ea326a7f04221914b74c0651e0be1e37c"
    )
    assert authority["ck07_shared_preparation"]["previous_r3a_candidate"] == {
        "sha256": "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174",
        "status": "revoked_for_session_boundedness_requalification",
        "direct_use": "forbidden",
        "reason": "the prior preparation candidate omitted the current session-bounded lifecycle cohort",
    }
    assert authority["ck07_shared_preparation"]["historical_d192"]["direct_use"] == "forbidden"
    assert authority["ck07_shared_preparation"]["run_token"] == {
        "maximum_new_end_to_end_runs": 1,
        "status": "unspent_unavailable",
        "consumption": "successful_process_launch_only",
        "launch_authorized_by_this_authority": False,
    }
