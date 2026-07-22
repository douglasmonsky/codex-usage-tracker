from __future__ import annotations

import base64
import json
from dataclasses import FrozenInstanceError
from types import MappingProxyType
from typing import cast

import pytest

from codex_usage_tracker.application.errors import RequestValidationError
from codex_usage_tracker.application.query_models import (
    QUERY_ENTITY_CAPABILITIES,
    QueryFilters,
    QueryMeasure,
    QueryRequest,
)
from codex_usage_tracker.application.query_validation import (
    QueryValidationError,
    validate_query_request,
)


def test_capabilities_are_immutable_and_exact() -> None:
    assert isinstance(QUERY_ENTITY_CAPABILITIES, MappingProxyType)
    assert set(QUERY_ENTITY_CAPABILITIES) == {
        "call",
        "thread",
        "project",
        "model",
        "effort",
        "origin",
        "service_tier",
        "subagent",
    }
    with pytest.raises(TypeError):
        QUERY_ENTITY_CAPABILITIES["call"] = QUERY_ENTITY_CAPABILITIES["thread"]  # type: ignore[index]


def test_query_rejects_arbitrary_measure() -> None:
    request = QueryRequest(
        entity="thread",
        measures=(cast(QueryMeasure, "raw_prompt"),),
        filters=QueryFilters(),
    )
    with pytest.raises(QueryValidationError, match="unsupported measure"):
        validate_query_request(request)


def test_query_rejects_measure_entity_mismatch() -> None:
    with pytest.raises(QueryValidationError, match="unsupported measure"):
        validate_query_request(
            QueryRequest(entity="call", measures=("call_count",), filters=QueryFilters())
        )


@pytest.mark.parametrize("limit", [0, 201, True])
def test_query_rejects_invalid_limits(limit: object) -> None:
    with pytest.raises(RequestValidationError, match="limit"):
        validate_query_request(
            QueryRequest(
                entity="call",
                measures=("tokens",),
                filters=QueryFilters(),
                limit=limit,  # type: ignore[arg-type]
            )
        )


def test_query_rejects_unsupported_group_and_order() -> None:
    with pytest.raises(QueryValidationError, match="group_by"):
        validate_query_request(
            QueryRequest(
                entity="model", measures=("tokens",), filters=QueryFilters(), group_by=("raw_sql",)
            )
        )

    with pytest.raises(QueryValidationError, match="order_by"):
        validate_query_request(
            QueryRequest(
                entity="model",
                measures=("estimated_cost",),
                filters=QueryFilters(),
                order_by="estimated_cost",
            )
        )


def test_estimate_only_query_defaults_to_truthful_identity_order() -> None:
    normalized = validate_query_request(
        QueryRequest(
            entity="model",
            measures=("estimated_cost", "estimated_credits"),
            filters=QueryFilters(),
        )
    )

    assert normalized.order_by == "model"
    with pytest.raises(QueryValidationError, match="order_by"):
        validate_query_request(
            QueryRequest(
                entity="thread", measures=("tokens",), filters=QueryFilters(), order_by="raw_column"
            )
        )


def test_query_rejects_contradictory_filters_and_malformed_cursor() -> None:
    with pytest.raises(QueryValidationError, match="since"):
        validate_query_request(
            QueryRequest(
                entity="call",
                measures=("tokens",),
                filters=QueryFilters(since="2026-07-22T12:00:00Z", until="2026-07-21T12:00:00Z"),
            )
        )
    with pytest.raises(QueryValidationError, match="cursor"):
        validate_query_request(
            QueryRequest(
                entity="call", measures=("tokens",), filters=QueryFilters(), cursor="eyJ2IjoxfQ!!"
            )
        )


def test_query_rejects_unimplemented_named_range() -> None:
    with pytest.raises(QueryValidationError, match="range"):
        validate_query_request(
            QueryRequest(
                entity="call",
                measures=("tokens",),
                filters=QueryFilters(range="last_7_days"),
            )
        )


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"v": 1, "f": "a" * 64, "r": None, "s": 1}, "structure"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": 1, "i": "x", "extra": 1}, "structure"),
        ({"v": True, "f": "a" * 64, "r": None, "s": 1, "i": "x"}, "v"),
        ({"v": 1, "f": "short", "r": None, "s": 1, "i": "x"}, "f"),
        ({"v": 1, "f": "a" * 64, "r": {"bad": True}, "s": 1, "i": "x"}, "r"),
        ({"v": 1, "f": "a" * 64, "r": "x" * 257, "s": 1, "i": "x"}, "r"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": [1], "i": "x"}, "s"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": {"bad": True}, "i": "x"}, "s"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": 2**63, "i": "x"}, "s"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": "x" * 1025, "i": "x"}, "s"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": 1, "i": ""}, "i"),
        ({"v": 1, "f": "a" * 64, "r": None, "s": 1, "i": "x" * 1025}, "i"),
    ],
)
def test_query_rejects_structurally_malformed_cursor_fields(
    payload: dict[str, object], field: str
) -> None:
    token = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )

    with pytest.raises(QueryValidationError, match=rf"cursor\.{field}"):
        validate_query_request(
            QueryRequest(
                entity="call",
                measures=("tokens",),
                filters=QueryFilters(),
                cursor=token,
            )
        )


def test_query_rejects_non_text_cursor_token() -> None:
    with pytest.raises(QueryValidationError, match=r"cursor\.encoding"):
        validate_query_request(
            QueryRequest(
                entity="call",
                measures=("tokens",),
                filters=QueryFilters(),
                cursor=cast(str, 123),
            )
        )


@pytest.mark.parametrize(
    ("order_by", "sort_value"),
    [("tokens", "110"), ("record_id", 110)],
)
def test_query_rejects_cursor_sort_incompatible_with_ordering(
    order_by: str, sort_value: object
) -> None:
    payload = {"v": 1, "f": "a" * 64, "r": None, "s": sort_value, "i": "call-1"}
    token = (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )

    with pytest.raises(QueryValidationError, match=r"cursor\.s"):
        validate_query_request(
            QueryRequest(
                entity="call",
                measures=("tokens",),
                filters=QueryFilters(),
                order_by=order_by,
                cursor=token,
            )
        )


def test_validation_canonicalizes_equivalent_timestamps() -> None:
    normalized = validate_query_request(
        QueryRequest(
            entity="call",
            measures=("tokens",),
            filters=QueryFilters(
                since="2026-07-22T08:00:00-04:00",
                until="2026-07-22T12:30:00+00:00",
            ),
        )
    )

    assert normalized.filters.since == "2026-07-22T12:00:00Z"
    assert normalized.filters.until == "2026-07-22T12:30:00Z"
    with pytest.raises(QueryValidationError, match="cursor"):
        validate_query_request(
            QueryRequest(
                entity="call", measures=("tokens",), filters=QueryFilters(), cursor="not-a-cursor"
            )
        )


def test_query_request_is_frozen() -> None:
    request = QueryRequest(entity="call", measures=("tokens",), filters=QueryFilters())
    with pytest.raises(FrozenInstanceError):
        request.limit = 2  # type: ignore[misc]
