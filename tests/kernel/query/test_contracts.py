from __future__ import annotations

import pytest

from codex_usage_tracker.kernel.query.contracts import (
    ComparisonWindow,
    Filter,
    Operation,
    QueryRequest,
)


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
