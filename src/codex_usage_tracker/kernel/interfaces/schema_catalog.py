"""Source-of-truth JSON schemas for generated public interface assets."""

from __future__ import annotations

from typing import Any

SCHEMAS: dict[str, dict[str, Any]] = {
    "usage_status": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "usage_refresh": {
        "type": "object",
        "properties": {
            "wait_seconds": {
                "type": "number",
                "minimum": 0,
                "maximum": 30,
            }
        },
        "additionalProperties": False,
    },
    "usage_query": {
        "type": "object",
        "properties": {
            "requests": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                },
            }
        },
        "required": ["requests"],
        "additionalProperties": False,
    },
    "usage_evidence": {
        "type": "object",
        "properties": {
            "selector": {"type": "string", "maxLength": 256},
            "view": {
                "type": "string",
                "enum": [
                    "summary",
                    "timeline",
                    "calls",
                    "tools",
                    "activities",
                    "allowance",
                ],
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": ["string", "null"]},
            "live": {"type": "boolean"},
        },
        "required": ["selector"],
        "additionalProperties": False,
    },
    "usage_allowance": {
        "type": "object",
        "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
            "cursor": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    },
    "usage_job_status": {
        "type": "object",
        "properties": {
            "job_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 128,
            },
            "wait_seconds": {
                "type": "number",
                "minimum": 0,
                "maximum": 30,
            },
            "include_result": {"type": "boolean"},
        },
        "required": ["job_id"],
        "additionalProperties": False,
    },
}


def validate_input(name: str, payload: dict[str, Any]) -> None:
    try:
        schema = SCHEMAS[name]
    except KeyError as exc:
        raise ValueError("unknown kernel tool") from exc
    _validate(payload, schema, name)


def _validate(value: Any, schema: dict[str, Any], label: str) -> None:
    expected = schema.get("type")
    if expected is not None and not _matches_type(value, expected):
        raise ValueError(f"{label} has invalid type")
    if isinstance(value, dict):
        _validate_object(value, schema, label)
    elif isinstance(value, list):
        _validate_array(value, schema, label)
    else:
        _validate_scalar(value, schema, label)


def _validate_object(
    value: dict[str, Any],
    schema: dict[str, Any],
    label: str,
) -> None:
    properties = schema.get("properties", {})
    missing = [key for key in schema.get("required", []) if key not in value]
    if missing:
        raise ValueError(f"{label} is missing {missing[0]}")
    unexpected = sorted(set(value) - set(properties))
    if schema.get("additionalProperties") is False and unexpected:
        raise ValueError(f"{label} has unexpected property {unexpected[0]}")
    for key, item in value.items():
        child = properties.get(key)
        if child is not None:
            _validate(item, child, f"{label}.{key}")


def _validate_array(
    value: list[Any],
    schema: dict[str, Any],
    label: str,
) -> None:
    if len(value) < int(schema.get("minItems", 0)):
        raise ValueError(f"{label} has too few items")
    if len(value) > int(schema.get("maxItems", len(value))):
        raise ValueError(f"{label} has too many items")
    item_schema = schema.get("items")
    if isinstance(item_schema, dict):
        for index, item in enumerate(value):
            _validate(item, item_schema, f"{label}[{index}]")


def _validate_scalar(value: Any, schema: dict[str, Any], label: str) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{label} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{label} exceeds maximum")
    if not isinstance(value, str):
        return
    if len(value) < int(schema.get("minLength", 0)):
        raise ValueError(f"{label} is too short")
    if len(value) > int(schema.get("maxLength", len(value))):
        raise ValueError(f"{label} is too long")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} is unsupported")


def _matches_type(value: Any, expected: Any) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    return any(
        {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "null": value is None,
        }.get(name, False)
        for name in names
    )
