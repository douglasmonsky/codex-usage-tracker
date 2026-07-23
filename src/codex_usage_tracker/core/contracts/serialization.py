"""Deterministic JSON serialization and payload-budget helpers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass


class PayloadBudgetError(ValueError):
    """Raised when a serialized payload exceeds its byte budget."""

    def __init__(self, name: str, actual: int, maximum: int) -> None:
        self.name = name
        self.actual = actual
        self.maximum = maximum
        super().__init__(f"{name} payload budget exceeded: actual={actual}, maximum={maximum}")


def _json_value(value: object, path: str = "payload") -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name), f"{path}.{item.name}")
            for item in sorted(fields(value), key=lambda item: item.name)
        }
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError(f"{path} mapping keys must be strings")
        return {
            key: _json_value(value[key], f"{path}.{key}")
            for key in sorted(value)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} must contain only finite numeric values")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"{path} contains unsupported value type {type(value).__name__}")


def payload_mapping(value: object) -> dict[str, object]:
    """Return a recursively sorted, finite, JSON-compatible mapping."""
    payload = _json_value(value)
    if not isinstance(payload, dict):
        raise TypeError("payload must serialize to a mapping")
    return payload


def serialized_json(payload: object) -> str:
    """Serialize with stable key order and compact UTF-8-preserving JSON."""
    return json.dumps(
        _json_value(payload),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def serialized_size(payload: object) -> int:
    """Return the deterministic serialized UTF-8 byte count."""
    return len(serialized_json(payload).encode("utf-8"))


def enforce_payload_budget(payload: object, maximum: int, name: str) -> None:
    """Raise with actual and maximum byte counts when a budget is exceeded."""
    if maximum < 0:
        raise ValueError("maximum must be non-negative")
    actual = serialized_size(payload)
    if actual > maximum:
        raise PayloadBudgetError(name=name, actual=actual, maximum=maximum)
