from __future__ import annotations

from typing import cast

import pytest

from codex_usage_tracker.application.errors import RequestValidationError
from codex_usage_tracker.application.requests import (
    EvidenceRequest,
    HistoryScope,
    PrivacyMode,
    QueryRequest,
    RequestScope,
    StatusRequest,
)


def test_scope_rejects_reversed_dates() -> None:
    with pytest.raises(RequestValidationError, match="since must not be after until"):
        RequestScope(
            since="2026-07-22T00:00:00Z",
            until="2026-07-21T00:00:00Z",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("history", "recent", "unsupported history"),
        ("privacy_mode", "raw", "unsupported privacy_mode"),
    ),
)
def test_scope_rejects_unsupported_modes(field: str, value: str, message: str) -> None:
    kwargs: dict[str, object] = {field: value}
    with pytest.raises(RequestValidationError, match=message):
        RequestScope(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("threshold", (float("nan"), float("inf"), float("-inf")))
def test_status_rejects_nonfinite_freshness_threshold(threshold: float) -> None:
    with pytest.raises(RequestValidationError, match="freshness_threshold_seconds must be finite"):
        StatusRequest(freshness_threshold_seconds=threshold)


def test_status_rejects_boolean_freshness_threshold() -> None:
    with pytest.raises(
        RequestValidationError,
        match="freshness_threshold_seconds must be a number",
    ):
        StatusRequest(freshness_threshold_seconds=True)


def test_status_rejects_fractional_freshness_threshold() -> None:
    with pytest.raises(
        RequestValidationError,
        match="freshness_threshold_seconds must be a whole number",
    ):
        StatusRequest(freshness_threshold_seconds=0.5)


def test_status_normalizes_integral_numeric_freshness_threshold() -> None:
    request = StatusRequest(freshness_threshold_seconds=12.0)

    assert request.freshness_threshold_seconds == 12
    assert type(request.freshness_threshold_seconds) is int


@pytest.mark.parametrize("thread_key", ("thread:safe\nsecond-line", "../../outside"))
def test_scope_rejects_unsafe_thread_identifier(thread_key: str) -> None:
    with pytest.raises(RequestValidationError, match="thread_key contains unsafe characters"):
        RequestScope(thread_key=thread_key)


def test_interactive_request_limits_are_bounded() -> None:
    with pytest.raises(RequestValidationError, match="limit must be between 1 and 200"):
        QueryRequest(entity="call", measures=("tokens",), limit=201)
    with pytest.raises(ValueError, match="limit must be between 1 and 200"):
        EvidenceRequest("call", "record-1", limit=201)


@pytest.mark.parametrize("limit", (True, 20.0, 20.5, "20"))
def test_interactive_request_limits_require_exact_integers(limit: object) -> None:
    with pytest.raises(RequestValidationError, match="limit must be an integer"):
        QueryRequest(
            entity="call",
            measures=("tokens",),
            limit=limit,  # type: ignore[arg-type]
        )


def test_scope_serialization_is_normalized_and_deterministic() -> None:
    scope = RequestScope(
        since="2026-07-21T00:00:00+00:00",
        until="2026-07-22T00:00:00Z",
        history=cast(HistoryScope, "active"),
        privacy_mode=cast(PrivacyMode, "strict"),
        project="  /tmp/project  ",
        thread_key=" thread:Alpha ",
        model=" gpt-5.6 ",
        effort=" high ",
    )

    assert scope.to_payload() == {
        "filters": {
            "effort": "high",
            "model": "gpt-5.6",
            "project": "/tmp/project",
            "thread_key": "thread:Alpha",
        },
        "history": "active",
        "privacy_mode": "strict",
        "schema": "codex-usage-tracker.scope.v1",
        "since": "2026-07-21T00:00:00Z",
        "until": "2026-07-22T00:00:00Z",
    }
