"""Validation helpers for tracked JSON payload contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

NoneType = type(None)
Number = (int, float)


def validate_json_payload_contract(
    payload: object, contracts: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """Return contract validation errors for one CLI or MCP JSON payload."""
    if not isinstance(payload, Mapping):
        return ["payload must be a JSON object"]

    schema_field = "schema"
    schema = payload.get(schema_field)
    if not isinstance(schema, str) or not schema:
        schema_field = "schema_id"
        schema = payload.get(schema_field)
    if not isinstance(schema, str) or not schema:
        return ["payload.schema must be non-empty string"]

    contract = contracts.get(schema)
    if contract is None:
        return [f"payload.{schema_field} is not tracked: {schema}"]

    return [
        *_validate_required_contract_fields(payload, schema=schema, contract=contract),
        *_validate_nested_contract_fields(payload, schema=schema, contract=contract),
    ]


def _validate_required_contract_fields(
    payload: Mapping[str, object], *, schema: str, contract: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    for field, expected in contract.get("required", {}).items():
        errors.extend(
            _validate_contract_field(
                payload,
                field_path=f"{schema}.{field}",
                field=field,
                expected=expected,
            )
        )
    return errors


def _validate_nested_contract_fields(
    payload: Mapping[str, object], *, schema: str, contract: Mapping[str, Any]
) -> list[str]:
    errors: list[str] = []
    for field, nested in contract.get("nested", {}).items():
        value = payload.get(field)
        if not isinstance(value, Mapping):
            continue
        for nested_field, expected in nested.items():
            errors.extend(
                _validate_contract_field(
                    value,
                    field_path=f"{schema}.{field}.{nested_field}",
                    field=nested_field,
                    expected=expected,
                )
            )
    return errors


def _validate_contract_field(
    payload: Mapping[str, object], *, field_path: str, field: str, expected: object
) -> list[str]:
    if field not in payload:
        return [f"{field_path} is required"]
    value = payload[field]
    if _matches_type(value, expected):
        return []
    return [_contract_type_error(field_path, value, expected)]


def _contract_type_error(field_path: str, value: object, expected: object) -> str:
    return f"{field_path} must be {_describe_type(expected)}, got {type(value).__name__}"


def _matches_type(value: object, expected: object) -> bool:
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected is float:
        return isinstance(value, Number) and not isinstance(value, bool)
    if isinstance(expected, tuple):
        return any(_matches_type(value, item) for item in expected)
    if expected is NoneType:
        return value is None
    if isinstance(expected, type):
        return isinstance(value, expected)
    return False


def _describe_type(expected: object) -> str:
    if expected is int:
        return "int"
    if expected is float:
        return "float"
    if expected is NoneType:
        return "null"
    if isinstance(expected, tuple):
        return " or ".join(_describe_type(item) for item in expected)
    if isinstance(expected, type):
        return expected.__name__
    return repr(expected)
