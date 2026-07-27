"""Strict JSON-to-kernel request conversion and result serialization."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, cast

from ..evidence import EvidenceRequest
from ..query import ComparisonWindow, Filter, QueryRequest


def query_request(payload: dict[str, Any]) -> QueryRequest:
    comparison_payload = payload.get("comparison")
    comparison = (
        ComparisonWindow(
            current_start=_text(comparison_payload, "current_start"),
            current_end=_text(comparison_payload, "current_end"),
            previous_start=_text(comparison_payload, "previous_start"),
            previous_end=_text(comparison_payload, "previous_end"),
        )
        if isinstance(comparison_payload, dict)
        else None
    )
    raw_filters = payload.get("filters", [])
    if not isinstance(raw_filters, list):
        raise ValueError("query filters must be an array")
    filters = tuple(_filter(item) for item in raw_filters)
    return QueryRequest(
        dataset=_text(payload, "dataset"),
        operation=_text(payload, "operation"),
        dimensions=_strings(payload.get("dimensions", []), "dimensions"),
        measures=_strings(payload.get("measures", []), "measures"),
        filters=filters,
        order_by=_optional_text(payload.get("order_by"), "order_by"),
        descending=_boolean(payload.get("descending", True), "descending"),
        limit=_integer(payload.get("limit", 100), "limit"),
        cursor=_optional_text(payload.get("cursor"), "cursor"),
        comparison=comparison,
    )


def evidence_request(payload: dict[str, Any]) -> EvidenceRequest:
    return EvidenceRequest(
        selector=_text(payload, "selector"),
        view=payload.get("view", "summary"),
        limit=_integer(payload.get("limit", 100), "limit"),
        cursor=_optional_text(payload.get("cursor"), "cursor"),
        live=_boolean(payload.get("live", False), "live"),
    )


def json_value(value: Any) -> Any:
    if is_dataclass(value):
        return json_value(asdict(cast(Any, value)))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value


def _filter(payload: Any) -> Filter:
    if not isinstance(payload, dict):
        raise ValueError("query filter must be an object")
    value = payload.get("value")
    if isinstance(value, list):
        value = tuple(value)
    if not isinstance(value, (str, int, float, tuple)):
        raise ValueError("query filter value is invalid")
    return Filter(
        field=_text(payload, "field"),
        operator=_text(payload, "operator"),
        value=value,
    )


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"query {label} must be a string array")
    return tuple(value)


def _text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    return value


def _integer(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer")
    return value


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value
