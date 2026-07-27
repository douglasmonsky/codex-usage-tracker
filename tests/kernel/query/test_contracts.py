from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest

from codex_usage_tracker.kernel.application.codec import query_request
from codex_usage_tracker.kernel.query.catalog import exploration_guidance
from codex_usage_tracker.kernel.query.contracts import (
    ComparisonWindow,
    Filter,
    Operation,
    QueryRequest,
)

_GUIDED_TEMPLATE_IDS = (
    "allowance",
    "concentration",
    "model_effort",
    "period_comparison",
    "subagents",
    "tools",
    "turns",
)


def test_exploration_guidance_is_static_compact_and_decision_complete() -> None:
    first = exploration_guidance()
    second = exploration_guidance()

    assert first == second
    assert first["schema"] == "codex-usage-tracker.query-guidance.v1"
    assert tuple(first["templates"]) == _GUIDED_TEMPLATE_IDS
    assert set(first["datasets"]) == {
        "activities",
        "allowance",
        "calls",
        "phases",
        "threads",
        "tools",
        "turns",
    }
    assert first["limits"] == {
        "max_batch_queries": 8,
        "max_dimensions_per_query": 3,
        "max_filters_per_query": 8,
        "max_measures_per_query": 8,
        "max_rows_per_query": 500,
        "max_response_bytes": 1_000_000,
    }
    assert first["filter_grammar"] == {
        "required_keys": ("field", "operator", "value"),
        "scalar_operators": ("eq", "gte", "gt", "lte", "lt"),
        "set_operator": {
            "name": "in",
            "value_type": "array",
            "min_items": 1,
            "max_items": 25,
        },
    }
    assert len(
        json.dumps(first, separators=(",", ":"), sort_keys=True).encode()
    ) <= 24_000
    assert all(
        template["kind"] == "query_template"
        and template["evidence_policy"] == "after_ranking"
        and template["requests"]
        for template in first["templates"].values()
    )
    assert first["datasets"]["phases"]["requires_scope_filter"] is True
    assert "default_request" not in first["datasets"]["phases"]


def test_phase_scope_can_be_composed_only_from_returned_guidance() -> None:
    guidance = json.loads(json.dumps(exploration_guidance()))
    phase = guidance["datasets"]["phases"]
    filters = _materialize(
        phase["scope_filter_templates"]["time_window"],
        {
            "start": "2026-01-01T00:00:00Z",
            "end": "2026-01-08T00:00:00Z",
        },
    )
    request = {
        "dataset": "phases",
        "operation": phase["operations"][0],
        "dimensions": ["phase", "thread"],
        "measures": ["activities", "total_tokens"],
        "filters": filters,
        "limit": guidance["limits"]["max_rows_per_query"],
    }

    query_request(request).normalized()


def test_every_guided_template_materializes_to_a_valid_query_batch() -> None:
    templates = exploration_guidance()["templates"]
    parameters = {
        "current_end": "2026-01-15T00:00:00Z",
        "current_start": "2026-01-08T00:00:00Z",
        "previous_end": "2026-01-08T00:00:00Z",
        "previous_start": "2026-01-01T00:00:00Z",
    }

    for template in templates.values():
        requests = _materialize(template["requests"], parameters)
        assert 1 <= len(requests) <= 8
        for request in requests:
            query_request(request).normalized()


def test_every_console_dataset_default_is_a_valid_query() -> None:
    datasets = exploration_guidance()["datasets"]

    assert {
        name
        for name, metadata in datasets.items()
        if "default_request" in metadata
    } == {"activities", "allowance", "calls", "threads", "tools", "turns"}
    for metadata in datasets.values():
        if default_request := metadata.get("default_request"):
            query_request(default_request).normalized()


def _materialize(value: Any, parameters: dict[str, str]) -> Any:
    if isinstance(value, str) and value.startswith("$"):
        return parameters[value[1:]]
    if isinstance(value, list):
        return [_materialize(item, parameters) for item in value]
    if isinstance(value, dict):
        return {
            key: _materialize(item, parameters)
            for key, item in deepcopy(value).items()
        }
    return value


def test_request_normalizes_allowlisted_fields_and_bounds() -> None:
    request = QueryRequest(
        dataset="calls",
        operation=Operation.ROWS,
        dimensions=("effort", "model", "model"),
        measures=("calls", "total_tokens"),
        filters=(
            Filter("model", "eq", "gpt-synthetic"),
            Filter("event_at", "gte", "2026-01-01T00:00:00Z"),
        ),
        limit=25,
    )

    normalized = request.normalized()

    assert normalized.dimensions == ("effort", "model")
    assert normalized.measures == ("calls", "total_tokens")
    assert normalized.limit == 25


def test_comparison_requires_two_bounded_non_overlapping_windows() -> None:
    request = QueryRequest(
        dataset="calls",
        operation=Operation.COMPARISON,
        dimensions=("model",),
        measures=("total_tokens",),
        comparison=ComparisonWindow(
            current_start="2026-01-08T00:00:00Z",
            current_end="2026-01-15T00:00:00Z",
            previous_start="2026-01-01T00:00:00Z",
            previous_end="2026-01-08T00:00:00Z",
        ),
    )

    assert request.normalized().comparison == request.comparison

    offset = QueryRequest(
        dataset="calls",
        operation=Operation.COMPARISON,
        measures=("calls",),
        comparison=ComparisonWindow(
            "2026-01-08T19:00:00-05:00",
            "2026-01-15T19:00:00-05:00",
            "2026-01-01T19:00:00-05:00",
            "2026-01-08T19:00:00-05:00",
        ),
    ).normalized()
    assert offset.comparison == ComparisonWindow(
        "2026-01-09T00:00:00Z",
        "2026-01-16T00:00:00Z",
        "2026-01-02T00:00:00Z",
        "2026-01-09T00:00:00Z",
    )

    for comparison in (
        None,
        ComparisonWindow("2026-01-08", "2026-01-01", "2025-12-25", "2026-01-01"),
        ComparisonWindow("2026-01-08", "2026-01-15", "2026-01-10", "2026-01-17"),
    ):
        invalid = QueryRequest(
            dataset="calls",
            operation=Operation.COMPARISON,
            measures=("calls",),
            comparison=comparison,
        )
        with pytest.raises(ValueError, match="comparison"):
            invalid.normalized()


def test_operation_shapes_reject_ambiguous_or_unbounded_cross_products() -> None:
    invalid = (
        QueryRequest("calls", Operation.AGGREGATE, ("model",), ()),
        QueryRequest("calls", Operation.SHARE, ("model", "effort"), ("calls",)),
        QueryRequest("calls", Operation.DISTRIBUTION, (), ("calls",)),
        QueryRequest("activities", Operation.TIMELINE, ("activity",), ("activities",)),
        QueryRequest("phases", Operation.TIMELINE, ("phase",), ("activities",)),
    )

    for request in invalid:
        with pytest.raises(ValueError):
            request.normalized()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("dataset", "raw_logs"),
        ("operation", "sql"),
        ("dimensions", ("prompt",)),
        ("measures", ("narrative",)),
        ("limit", 0),
        ("limit", 501),
    ],
)
def test_request_rejects_unknown_or_unbounded_contract(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "dataset": "calls",
        "operation": Operation.ROWS,
        "dimensions": ("model",),
        "measures": ("calls",),
        "limit": 25,
    }
    values[field] = value

    with pytest.raises(ValueError):
        QueryRequest(**values).normalized()
