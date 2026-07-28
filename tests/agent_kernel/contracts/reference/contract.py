from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tests.agent_kernel.contracts.reference.field_contract import (
    FieldContractError,
    build_field_contract_cases,
    validate_field_contract_cases,
)
from tests.agent_kernel.contracts.reference.identity import semantic_id

_FIELD_KEYS = frozenset(
    {
        "basis",
        "identity_participation",
        "missing",
        "name",
        "semantics",
        "vector_ids",
    }
)
_IDENTITY_PARTICIPATION = frozenset({"included", "excluded"})
_CANONICAL_GRADES = frozenset({"exact", "deterministic", "configured_estimate"})


def canonical_json_bytes(value: object) -> bytes:
    """Return the canonical JSON representation used by contract fixtures."""

    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return payload


def vector_bundle_digest(vector_paths: Iterable[Path]) -> str:
    """Hash names and canonical payloads so file moves or byte drift are visible."""

    digest = hashlib.sha256()
    for path in sorted(vector_paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(canonical_json_bytes(_load_object(path)))
    return digest.hexdigest()


def _duplicate_values(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _payload_with_schema(
    payloads: list[dict[str, Any]],
    schema: str,
) -> dict[str, Any] | None:
    matches = [payload for payload in payloads if payload.get("schema") == schema]
    if len(matches) != 1:
        return None
    return matches[0]


def contract_failures(
    contract: dict[str, Any],
    question_catalog: dict[str, Any],
    vector_paths: list[Path],
) -> list[str]:
    """Return deterministic logical-contract completeness and linkage failures."""

    failures: list[str] = []
    if contract.get("schema") != "codex-usage-tracker.agent-kernel.logical.v1":
        failures.append("logical contract schema identity is not v1")
    if contract.get("version") != 1:
        failures.append("logical contract version is not 1")
    if contract.get("database_identity") != "codex-usage-tracker.agent-kernel.v1":
        failures.append("replacement database identity is not locked")

    vector_payloads = [_load_object(path) for path in vector_paths]
    vector_ids = {
        vector_id
        for payload in vector_payloads
        for vector_id in payload.get("vector_ids", [])
    }
    duplicate_vector_ids = _duplicate_values(
        vector_id
        for payload in vector_payloads
        for vector_id in payload.get("vector_ids", [])
    )
    if duplicate_vector_ids:
        failures.append(f"duplicate vector IDs: {sorted(duplicate_vector_ids)}")
    if not vector_paths:
        failures.append("logical contract has no vector bundles")
    elif contract.get("vector_bundle_sha256") != vector_bundle_digest(vector_paths):
        failures.append("logical contract vector bundle digest is stale")

    entities = contract.get("entities", [])
    entity_ids = [entity.get("id") for entity in entities]
    if any(not isinstance(entity_id, str) for entity_id in entity_ids):
        failures.append("every logical entity must have a string ID")
    duplicate_entity_ids = _duplicate_values(
        entity_id for entity_id in entity_ids if isinstance(entity_id, str)
    )
    if duplicate_entity_ids:
        failures.append(f"duplicate logical entity IDs: {sorted(duplicate_entity_ids)}")
    known_entity_ids = {
        entity_id for entity_id in entity_ids if isinstance(entity_id, str)
    }

    referenced_vectors: set[str] = set()
    for entity in entities:
        entity_id = entity.get("id", "<unknown>")
        if not entity.get("owner"):
            failures.append(f"{entity_id} has no logical owner")
        if not entity.get("semantics"):
            failures.append(f"{entity_id} has no semantics")
        entity_vectors = entity.get("vector_ids", [])
        if not entity_vectors:
            failures.append(f"{entity_id} has no executable vector")
        referenced_vectors.update(entity_vectors)
        fields = entity.get("fields", [])
        names = [field.get("name") for field in fields]
        if not fields:
            failures.append(f"{entity_id} has no field contracts")
        duplicates = _duplicate_values(name for name in names if isinstance(name, str))
        if duplicates:
            failures.append(f"{entity_id} has duplicate fields: {sorted(duplicates)}")
        field_by_name = {
            field.get("name"): field
            for field in fields
            if isinstance(field.get("name"), str)
        }
        identity = entity.get("identity")
        if not isinstance(identity, dict):
            failures.append(f"{entity_id} has no identity contract")
        else:
            expected_identity_keys = {
                "derived_id_field",
                "input_fields",
                "kind",
            }
            if set(identity) != expected_identity_keys:
                failures.append(f"{entity_id} has incomplete identity metadata")
            identity_kind = identity.get("kind")
            identity_inputs = identity.get("input_fields")
            derived_id_field = identity.get("derived_id_field")
            if not isinstance(identity_kind, str) or not identity_kind:
                failures.append(f"{entity_id} has no identity kind")
            if (
                not isinstance(identity_inputs, list)
                or not identity_inputs
                or any(not isinstance(name, str) for name in identity_inputs)
            ):
                failures.append(f"{entity_id} has invalid identity inputs")
                identity_inputs = []
            elif len(identity_inputs) != len(set(identity_inputs)):
                failures.append(f"{entity_id} repeats an identity input")
            unknown_identity_inputs = set(identity_inputs) - set(field_by_name)
            if unknown_identity_inputs:
                failures.append(
                    f"{entity_id} identity names unknown fields: "
                    f"{sorted(unknown_identity_inputs)}"
                )
            included_fields = [
                name
                for name, field in field_by_name.items()
                if field.get("identity_participation") == "included"
            ]
            if included_fields != identity_inputs:
                failures.append(
                    f"{entity_id} identity input order differs from included fields"
                )
            if derived_id_field is not None:
                if derived_id_field not in field_by_name:
                    failures.append(f"{entity_id} derived identity field is unknown")
                elif derived_id_field in identity_inputs:
                    failures.append(
                        f"{entity_id} derived identity participates in its own identity"
                    )
                elif (
                    field_by_name[derived_id_field].get("identity_participation")
                    != "excluded"
                ):
                    failures.append(
                        f"{entity_id} derived identity field is not excluded"
                    )
        for field in fields:
            field_name = field.get("name", "<unknown>")
            if set(field) != _FIELD_KEYS:
                failures.append(f"{entity_id}.{field_name} has incomplete field metadata")
            if not field.get("semantics"):
                failures.append(f"{entity_id}.{field_name} has no semantics")
            if field.get("identity_participation") not in _IDENTITY_PARTICIPATION:
                failures.append(
                    f"{entity_id}.{field_name} has invalid identity participation"
                )
            if not field.get("missing"):
                failures.append(f"{entity_id}.{field_name} has no missing-value rule")
            if not field.get("basis"):
                failures.append(f"{entity_id}.{field_name} has no basis")
            field_vectors = field.get("vector_ids", [])
            referenced_vectors.update(field_vectors)

    identity_payload = _payload_with_schema(
        vector_payloads,
        "codex-usage-tracker.agent-kernel.identity-vectors.v1",
    )
    if identity_payload is None:
        failures.append("logical contract needs exactly one identity vector bundle")
        identity_vectors: list[dict[str, Any]] = []
    else:
        identity_vectors = identity_payload.get("identity_vectors", [])
        identity_vector_entities = [
            vector.get("entity") for vector in identity_vectors
        ]
        if identity_vector_entities != entity_ids:
            failures.append(
                "identity vectors must cover every entity once in contract order"
            )
        for vector in identity_vectors:
            entity_id = vector.get("entity")
            entity = next(
                (item for item in entities if item.get("id") == entity_id),
                None,
            )
            if entity is None:
                failures.append(f"identity vector resolves unknown entity {entity_id}")
                continue
            identity = entity.get("identity", {})
            if vector.get("kind") != identity.get("kind"):
                failures.append(f"{entity_id} identity vector kind drifted")
            if vector.get("identity_input_fields") != identity.get("input_fields"):
                failures.append(f"{entity_id} identity vector field order drifted")
            identity_tuple = vector.get("identity_tuple")
            if not isinstance(identity_tuple, list):
                failures.append(f"{entity_id} identity vector tuple is invalid")
                continue
            if len(identity_tuple) != len(identity.get("input_fields", [])):
                failures.append(f"{entity_id} identity vector tuple length drifted")
                continue
            try:
                computed_id = semantic_id(identity["kind"], identity_tuple)
            except (KeyError, TypeError, ValueError) as exc:
                failures.append(f"{entity_id} identity vector is invalid: {exc}")
            else:
                if computed_id != vector.get("expected_id"):
                    failures.append(f"{entity_id} exact identity vector drifted")

    field_payload = _payload_with_schema(
        vector_payloads,
        "codex-usage-tracker.agent-kernel.field-contract-vectors.v1",
    )
    if field_payload is None:
        failures.append("logical contract needs exactly one field vector bundle")
    elif identity_payload is not None:
        field_cases = field_payload.get("field_contract_vectors", [])
        expected_cases = build_field_contract_cases(entities, identity_vectors)
        if field_cases != expected_cases:
            failures.append("checked-in field contract vectors are stale")
        else:
            try:
                assertion_count = validate_field_contract_cases(
                    entities,
                    identity_vectors,
                    field_cases,
                )
            except (FieldContractError, KeyError, TypeError, ValueError) as exc:
                failures.append(f"field contract vector execution failed: {exc}")
            else:
                expected_assertion_count = sum(
                    len(entity.get("fields", [])) for entity in entities
                )
                if assertion_count != expected_assertion_count:
                    failures.append(
                        "field contract assertions do not cover every field"
                    )

    primitive_map = contract.get("logical_primitives", {})
    catalog_primitives = set(question_catalog.get("logical_primitives", []))
    if set(primitive_map) != catalog_primitives:
        failures.append(
            "CK-01/logical primitive IDs differ: "
            f"catalog_only={sorted(catalog_primitives - set(primitive_map))}, "
            f"contract_only={sorted(set(primitive_map) - catalog_primitives)}"
        )
    for primitive_id, entity_id in primitive_map.items():
        if entity_id not in known_entity_ids:
            failures.append(
                f"logical primitive {primitive_id} resolves to unknown entity {entity_id}"
            )

    contract_measurements = contract.get("measurements", {})
    catalog_measurements = set(question_catalog.get("measurements", []))
    if set(contract_measurements) != catalog_measurements:
        failures.append("CK-01/logical measurement IDs differ")
    bit_positions = [
        measurement.get("bit")
        for measurement in contract_measurements.values()
        if isinstance(measurement, dict)
    ]
    if bit_positions != list(range(len(bit_positions))):
        failures.append("measurement-mask bit positions must be contiguous and ordered")
    for measurement_id, measurement in contract_measurements.items():
        if measurement.get("grade") not in _CANONICAL_GRADES:
            failures.append(f"{measurement_id} has an invalid canonical grade")
        if not measurement.get("basis"):
            failures.append(f"{measurement_id} has no basis")
        if not measurement.get("missing"):
            failures.append(f"{measurement_id} has no missing-value rule")
        measurement_vectors = measurement.get("vector_ids", [])
        if not measurement_vectors:
            failures.append(f"{measurement_id} has no executable vector")
        referenced_vectors.update(measurement_vectors)

    if set(contract.get("capabilities", {})) != set(
        question_catalog.get("capabilities", [])
    ):
        failures.append("CK-01/logical capability IDs differ")
    contract_selectors = contract.get("selector_kinds", {})
    if set(contract_selectors) != set(question_catalog.get("selector_kinds", [])):
        failures.append("CK-01/logical selector-kind IDs differ")
    for selector_id, selector in contract_selectors.items():
        if selector.get("entity") not in known_entity_ids:
            failures.append(f"{selector_id} resolves unknown selector entity")
        if not selector.get("prefix") or not selector.get("identity_kind"):
            failures.append(f"{selector_id} has an incomplete wire contract")

    for decision in contract.get("decisions", []):
        if not decision.get("id") or not decision.get("rationale"):
            failures.append("every CK-02 decision needs an ID and rationale")
        referenced_vectors.update(decision.get("vector_ids", []))

    unknown_vectors = referenced_vectors - vector_ids
    if unknown_vectors:
        failures.append(f"contract references unknown vectors: {sorted(unknown_vectors)}")
    unowned_vectors = vector_ids - referenced_vectors
    if unowned_vectors:
        failures.append(f"vectors lack contract ownership: {sorted(unowned_vectors)}")
    return failures
