from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.errors import RequestContextError
from codex_usage_tracker.application.query import query_usage
from codex_usage_tracker.application.query_models import QueryFilters, QueryRequest
from codex_usage_tracker.application.query_validation import decode_cursor
from codex_usage_tracker.application.requests import RequestScope
from codex_usage_tracker.core.contracts import serialized_size
from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_query, usage_query
from tests.application.test_query import _seed


def test_query_real_cursor_envelope_reuses_one_revision_context(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    kwargs = {"entity": "call", "measures": ["tokens"], "limit": 1, "db_path": db_path}
    first = build_usage_query(**kwargs)
    cursor = first["result"]["next_cursor"]  # type: ignore[index]
    second = build_usage_query(**kwargs, cursor=cursor)
    assert first["schema"] == "codex-usage-tracker.mcp-envelope.v1"
    assert first["result_schema"] == "codex-usage-tracker.query.v2"
    assert first["data_class"] == "aggregate"
    assert decode_cursor(cursor)["r"] == first["source_revision"]  # type: ignore[arg-type]
    assert first["result"]["rows"] != second["result"]["rows"]  # type: ignore[index]
    assert serialized_size(first) <= 256 * 1024


def test_query_rejects_shapes_and_mismatched_injected_context(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="filters must be an object"):
        build_usage_query(entity="model", measures=["tokens"], filters=[])  # type: ignore[arg-type]
    context = build_request_context(
        db_path=tmp_path / "missing.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        scope=RequestScope(history="all"),
    )
    with pytest.raises(RequestContextError, match="scope does not match"):
        query_usage(
            QueryRequest("model", ("tokens",), QueryFilters()),
            db_path=tmp_path / "missing.sqlite3",
            context=context,
        )


def test_query_public_signature_is_stable() -> None:
    assert tuple(inspect.signature(usage_query).parameters) == (
        "entity",
        "measures",
        "filters",
        "group_by",
        "order_by",
        "order",
        "limit",
        "cursor",
        "history",
    )
