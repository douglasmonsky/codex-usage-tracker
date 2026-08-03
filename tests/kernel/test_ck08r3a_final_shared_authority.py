from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_ROOT = Path(__file__).resolve().parents[2]
_AUTHORITY_PATH = _ROOT / "docs/decisions/evidence/ck08r3a/final-shared-authority.json"
_SCHEMA_PATH = _ROOT / "docs/decisions/evidence/ck08r3a/final-shared-authority.schema.json"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _authority() -> dict[str, Any]:
    return _read_json(_AUTHORITY_PATH)


def _schema() -> dict[str, Any]:
    return _read_json(_SCHEMA_PATH)


def _errors(value: dict[str, Any]) -> list[Any]:
    return list(Draft202012Validator(_schema()).iter_errors(value))


def _sha256(relative_path: str) -> str:
    return hashlib.sha256((_ROOT / relative_path).read_bytes()).hexdigest()


def test_final_shared_authority_is_independently_schema_valid_and_exact() -> None:
    schema = _schema()
    authority = _authority()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(authority)

    assert authority["schema"] == "codex-usage-tracker.ck08r3a-final-shared-authority.v2"
    assert authority["authority_version"] == 2
    assert authority["authority_base_sha"] == "ee4a064bf8850bceb362fbe73e40a57fe4af55d6"
    assert authority["status"] == "permitted_not_accepted"
    assert authority["contract_mode"] == "predecessor_rejection_only"
    assert schema["additionalProperties"] is False
    assert "docs/roadmap/tasks/ck-07r1a0-freeze-lifecycle-path-authority.md" in authority[
        "scope"
    ]["authority_write_scope"]

    r3a = authority["r3a"]
    predecessor = r3a["predecessor"]
    selected = r3a["selected"]
    assert r3a["implementation_task"] == "019fbe2b-20e8-78b2-a687-0231b159d0c7"
    assert selected["status"] == "permitted_not_accepted"
    assert len(predecessor["production_identities"]) == 5
    assert len(predecessor["support_identities"]) == 7
    assert len(selected["production_identities"]) == 5
    assert len(selected["support_identities"]) == 7

    expected_selected = [
        (
            "src/codex_usage_tracker/agent_kernel/evidence/service.py",
            "evidence_service_source",
            "659c1957157bc36aecbc37824ef04479853ec7ae1ff6ddad5be5882d7ca844b3",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
            "publication_preparation",
            "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/publication/writer.py",
            "publication_writer",
            "458d7b91701fe143d16d13c9b30ea549541c3f9395e019f2d8bfe06f4120b7e6",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/analytical.sql",
            "analytical_ddl",
            "40254b62510e9c92b049e3608dfad99a208de2fd2d2762f376d32dc81a7d5838",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/schema.py",
            "schema_contract",
            "af0877db25df1010e282a48c72c020785be92c211d70a733e309c40f82611fbe",
        ),
    ]
    assert [
        (item["path"], item["role"], item["sha256"])
        for item in selected["production_identities"]
    ] == expected_selected

    expected_predecessor = [
        (
            "src/codex_usage_tracker/agent_kernel/evidence/service.py",
            "evidence_service_source",
            "ea32223d1afd997f310419bff0b6b260193e527c8333c9f561bcab280447dfa3",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/publication/preparation.py",
            "publication_preparation",
            "408d18e44c87da234d220c29298ebac1780e9426e2dce767b0bfc3ae65e8a872",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/publication/writer.py",
            "publication_writer",
            "3b073188a0250e26c89f0af75ecf9a36507b9cb0251576ae26305fe97068c01a",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/analytical.sql",
            "analytical_ddl",
            "4341ce05b119c44c83865b434751cd8569bad5445de26be2e8ceaa9345ada820",
        ),
        (
            "src/codex_usage_tracker/agent_kernel/storage/schema.py",
            "schema_contract",
            "3f5d9b47cec3ab36784024b75842cc22dcc57e6d07e39afc4b248addc3517ffe",
        ),
    ]
    assert [
        (item["path"], item["role"], item["sha256"])
        for item in predecessor["production_identities"]
    ] == expected_predecessor

    for item in selected["production_identities"]:
        actual = _sha256(item["path"])
        predecessor_item = next(
            candidate
            for candidate in predecessor["production_identities"]
            if candidate["path"] == item["path"]
        )
        assert actual in {item["sha256"], predecessor_item["sha256"]}

    assert selected["schema_contract"] == {
        "sha256": "7a2e1c8a84bc681b33e7c69552f65791c3f9a1a715d641da3a898237896d85dc",
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
            "evidence_lifecycle_timeline_order",
            "evidence_source_occurrences_by_logical_order",
            "evidence_tools_by_resource_order",
            "evidence_state_changes_by_resource_order",
            "evidence_allowance_observations_order",
        ],
    }
    assert selected["independent_ddl"] == {
        "test_path": "tests/agent_kernel/storage/test_database_schema.py",
        "test_sha256": "d1e7e852d2d95df489f366e40a89e25238842b0c10d40ad5c58b0d3761b2cea9",
        "declaration_digest": "8b5a5650f7f41428832f276a1ad31bb08dded05ef92f078de6c8ca1a3effb1dc",
        "execution_checked": True,
        "equality_checked": True,
        "candidate_self_reference": False,
        "literal_turn_order": {"event_kind_order": 20, "transition_rank": 0},
        "persisted_turn_columns": [
            "start_source_rank NOT NULL",
            "start_source_order NOT NULL",
            "end_source_order NULLABLE",
            "CHECK end_source_order IS NULL OR start_source_order <= end_source_order",
        ],
    }


def test_final_shared_rank_and_fixture_contracts_cover_zero_and_positive() -> None:
    authority = _authority()
    selected = authority["r3a"]["selected"]
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
    assert "ambiguous_manifestation" in provenance["negative_cases"]
    assert "unresolved_manifestation" in provenance["negative_cases"]

    fixtures = selected["publication_fixtures"]
    assert fixtures["variant_count"] == 80
    assert fixtures["oracle_order"]["count"] == 80
    assert fixtures["oracle_order"]["tuple_digest"] == (
        "d5dc9695f8d383b6a2cf9840c8ab9e816d32f561fa0fe814db8fe64f125af7b8"
    )
    assert [state["name"] for state in fixtures["states"]] == [
        "predecessor",
        "selected",
        "revoked",
    ]
    assert fixtures["mixed_state"] == "reject"
    assert selected["physical_evidence"]["marker_free_first_and_deep_forward_backward"] is True
    assert selected["physical_evidence"]["query_only_one_snapshot"] is True
    assert selected["physical_evidence"]["valid_empty_rate_card_pages"] is True


def test_final_shared_schema_rejects_scope_identity_rank_and_boundary_mutations() -> None:
    authority = _authority()
    mutations: list[tuple[str, Any]] = []

    swapped_role = deepcopy(authority)
    swapped_role["r3a"]["selected"]["production_identities"][0]["role"] = "schema_contract"
    mutations.append(("role swap", swapped_role))

    swapped_path = deepcopy(authority)
    swapped_path["r3a"]["selected"]["production_identities"][0]["path"] = (
        "src/codex_usage_tracker/agent_kernel/storage/schema.py"
    )
    mutations.append(("path swap", swapped_path))

    swapped_hash = deepcopy(authority)
    swapped_hash["r3a"]["selected"]["production_identities"][0]["sha256"] = (
        authority["r3a"]["selected"]["production_identities"][1]["sha256"]
    )
    mutations.append(("hash swap", swapped_hash))

    for name, mutated in (
        ("database owner", deepcopy(authority)),
        ("scope substitution", deepcopy(authority)),
        ("forbidden scope", deepcopy(authority)),
        ("rebuild rule", deepcopy(authority)),
        ("rank domain", deepcopy(authority)),
        ("rank zero", deepcopy(authority)),
        ("rank positive", deepcopy(authority)),
        ("mixed fixture", deepcopy(authority)),
    ):
        if name == "database owner":
            mutated["scope"]["implementation_reapply_scope"].append(
                "src/codex_usage_tracker/agent_kernel/storage/database.py"
            )
        elif name == "scope substitution":
            mutated["scope"]["authority_write_scope"][0] = "src/codex_usage_tracker/agent_kernel/storage/database.py"
        elif name == "forbidden scope":
            mutated["scope"]["forbidden"][0] = "allow migration"
        elif name == "rebuild rule":
            mutated["r3a"]["predecessor_rejection"]["rebuild_rule"] = "migrate in place"
        elif name == "rank domain":
            mutated["r3a"]["selected"]["turn_provenance"]["rank_domain"] = "positive_only"
        elif name == "rank zero":
            mutated["r3a"]["selected"]["turn_provenance"]["rank_zero_valid"] = False
        elif name == "rank positive":
            mutated["r3a"]["selected"]["turn_provenance"]["rank_positive_preserved"] = False
        else:
            mutated["r3a"]["selected"]["publication_fixtures"]["mixed_state"] = "allow"
        mutations.append((name, mutated))

    for name, mutated in mutations:
        assert _errors(mutated), name


def test_final_shared_authority_freezes_predecessor_rejection_and_ck07_two_state() -> None:
    authority = _authority()
    rejection = authority["r3a"]["predecessor_rejection"]
    assert rejection["application_boundary"] == "before_application_query_mutation_repair_or_promotion"
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
    assert rejection["rebuild_rule"] == (
        "fresh replacement artifacts are built from admitted synthetic/source facts under the current exact schema, validated, hashed, fsynced, and promoted by the existing fenced pointer/recovery mechanism"
    )

    ck07 = authority["ck07_shared_preparation"]
    assert ck07["status"] == "blocked_hold"
    assert ck07["authority_main"]["sha256"] == (
        "408d18e44c87da234d220c29298ebac1780e9426e2dce767b0bfc3ae65e8a872"
    )
    assert ck07["r3a_atomic_cohort"]["sha256"] == (
        "e204e0da8f6dce7b6c4cf7a981803d2d8c08b45cb3a2ca370fe1838fd6cf2174"
    )
    assert ck07["r3a_atomic_cohort"]["direct_ck07_use"] == "forbidden"
    assert ck07["historical_d192"]["direct_use"] == "forbidden"
    assert ck07["future_ck07_requalification"]["new_digest_required"] is True
    assert ck07["run_token"] == {
        "maximum_new_end_to_end_runs": 1,
        "status": "unspent_unavailable",
        "consumption": "successful_process_launch_only",
        "launch_authorized_by_this_authority": False,
    }
