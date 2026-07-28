from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tests.agent_kernel.contracts.reference.contract import (
    canonical_json_bytes,
    contract_failures,
    vector_bundle_digest,
)
from tests.agent_kernel.contracts.reference.field_contract import (
    build_field_contract_cases,
    validate_field_contract_cases,
)
from tests.agent_kernel.contracts.reference.identity import (
    IdentityCollisionError,
    IdentityRegistry,
    semantic_id,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = (
    _REPO_ROOT / "config" / "agent-kernel" / "logical-contract-v1.json"
)
_CATALOG_PATH = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json"
)
_VECTOR_ROOT = Path(__file__).with_name("vectors")


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_logical_contract_is_complete_and_reconciles_ck01() -> None:
    contract = _load(_CONTRACT_PATH)
    catalog = _load(_CATALOG_PATH)
    vector_paths = sorted(_VECTOR_ROOT.glob("*.json"))

    assert contract_failures(contract, catalog, vector_paths) == []
    assert contract["vector_bundle_sha256"] == vector_bundle_digest(vector_paths)
    assert canonical_json_bytes(contract) == canonical_json_bytes(
        json.loads(canonical_json_bytes(contract))
    )


def test_versioned_identity_vectors_are_exact() -> None:
    payload = _load(_VECTOR_ROOT / "identity-v1.json")
    contract = _load(_CONTRACT_PATH)
    entities = {entity["id"]: entity for entity in contract["entities"]}

    for vector in payload["identity_vectors"]:
        entity = entities[vector["entity"]]
        identity = entity["identity"]
        assert identity["kind"] == vector["kind"]
        assert identity["input_fields"] == vector["identity_input_fields"]
        assert len(identity["input_fields"]) == len(vector["identity_tuple"])
        field_participation = {
            field["name"]: field["identity_participation"]
            for field in entity["fields"]
        }
        assert [
            name
            for name, participation in field_participation.items()
            if participation == "included"
        ] == identity["input_fields"]
        derived_id_field = identity["derived_id_field"]
        if derived_id_field is not None:
            assert derived_id_field not in identity["input_fields"]
            assert field_participation[derived_id_field] == "excluded"
        assert semantic_id(vector["kind"], vector["identity_tuple"]) == vector["expected_id"]
    assert {vector["entity"] for vector in payload["identity_vectors"]} == set(entities)


def test_publication_identity_precedes_nonrecursive_artifact_digest() -> None:
    payload = _load(_VECTOR_ROOT / "identity-v1.json")

    for vector in payload["publication_derivation_vectors"]:
        assert semantic_id("publication", [vector["publication_key"]]) == vector[
            "expected_publication_id"
        ]
        artifact = vector["artifact_without_digest"]
        assert artifact["publication_id"] == vector["expected_publication_id"]
        assert "artifact_digest" not in artifact
        assert hashlib.sha256(canonical_json_bytes(artifact)).hexdigest() == vector[
            "expected_artifact_digest"
        ]


def test_every_admitted_field_has_an_executed_semantic_assertion() -> None:
    contract = _load(_CONTRACT_PATH)
    identities = _load(_VECTOR_ROOT / "identity-v1.json")
    payload = _load(_VECTOR_ROOT / "field-contract-v1.json")
    expected_cases = build_field_contract_cases(
        contract["entities"],
        identities["identity_vectors"],
    )

    assert payload["field_contract_vectors"] == expected_cases
    assert payload["vector_ids"] == [case["id"] for case in expected_cases]
    expected_assertions = sum(
        len(entity["fields"]) for entity in contract["entities"]
    )
    assert validate_field_contract_cases(
        contract["entities"],
        identities["identity_vectors"],
        payload["field_contract_vectors"],
    ) == expected_assertions


def test_hash_collision_never_merges_distinct_identity_tuples() -> None:
    payload = _load(_VECTOR_ROOT / "identity-v1.json")

    for vector in payload["collision_vectors"]:
        registry = IdentityRegistry()
        registry.register(vector["logical_id"], vector["first_tuple"])
        try:
            registry.register(vector["logical_id"], vector["second_tuple"])
        except IdentityCollisionError as exc:
            assert exc.logical_id == vector["logical_id"]
        else:
            raise AssertionError("identity collision did not fail closed")


def test_source_copies_count_once_but_preserve_occurrences() -> None:
    payload = _load(_VECTOR_ROOT / "identity-v1.json")

    for vector in payload["occurrence_vectors"]:
        registry = IdentityRegistry()
        for occurrence in vector["occurrences"]:
            registry.register(
                occurrence["logical_id"],
                occurrence["identity_tuple"],
                occurrence=occurrence["coordinate"],
            )
        entity = registry.entities[vector["expected_logical_id"]]
        assert len(registry.entities) == vector["expected_entity_count"]
        assert entity.occurrences == vector["expected_coordinates"]
