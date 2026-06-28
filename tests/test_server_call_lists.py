from __future__ import annotations

from typing import Any

import pytest

from codex_usage_tracker import server_call_lists


def test_calls_payload_applies_derived_filters_and_pagination() -> None:
    calls: dict[str, Any] = {}

    def live_query_params(params: dict[str, list[str]]) -> dict[str, object]:
        calls["params"] = params
        return {"limit": 2, "offset": 3, "filters": {"model": "gpt-5.5"}}

    def live_call_rows(**kwargs: Any) -> tuple[list[dict[str, object]], int]:
        calls["rows"] = kwargs
        return ([{"record_id": "one"}, {"record_id": "two"}], 8)

    payload = server_call_lists.calls_payload(
        "pricing_status=priced&credit_confidence=exact",
        live_query_params=live_query_params,
        live_call_rows=live_call_rows,
    )

    assert calls["rows"]["pricing_status"] == "priced"
    assert calls["rows"]["credit_confidence"] == "exact"
    assert payload["schema"] == "codex-usage-tracker-calls-v1"
    assert payload["row_count"] == 2
    assert payload["total_matched_rows"] == 8
    assert payload["has_more"] is True
    assert payload["next_offset"] == 5
    assert payload["filters"] == {
        "model": "gpt-5.5",
        "pricing_status": "priced",
        "credit_confidence": "exact",
    }
    assert payload["raw_context_included"] is False


def test_thread_calls_payload_forwards_thread_key_and_omits_filters() -> None:
    calls: dict[str, Any] = {}

    def live_query_params(
        params: dict[str, list[str]],
        *,
        thread_key: str,
    ) -> dict[str, object]:
        calls["thread_key"] = thread_key
        return {"limit": None, "offset": 0, "filters": {"thread_key": thread_key}}

    def live_call_rows(**kwargs: Any) -> tuple[list[dict[str, object]], int]:
        calls["rows"] = kwargs
        return ([{"record_id": "one"}], 1)

    payload = server_call_lists.thread_calls_payload(
        "thread=thread-a",
        live_query_params=live_query_params,
        live_call_rows=live_call_rows,
    )

    assert calls["thread_key"] == "thread-a"
    assert calls["rows"]["pricing_status"] is None
    assert calls["rows"]["credit_confidence"] is None
    assert payload["schema"] == "codex-usage-tracker-thread-calls-v1"
    assert payload["thread_key"] == "thread-a"
    assert payload["limit"] is None
    assert payload["has_more"] is False
    assert "filters" not in payload


def test_thread_calls_payload_requires_thread_key() -> None:
    with pytest.raises(server_call_lists.MissingThreadKeyError, match="thread_key required"):
        server_call_lists.thread_calls_payload(
            "",
            live_query_params=lambda params, **kwargs: {},
            live_call_rows=lambda **kwargs: ([], 0),
        )


def test_calls_payload_rejects_invalid_derived_filter() -> None:
    with pytest.raises(ValueError, match="pricing_status"):
        server_call_lists.calls_payload(
            "pricing_status=weird",
            live_query_params=lambda params: {"limit": 1, "offset": 0, "filters": {}},
            live_call_rows=lambda **kwargs: ([], 0),
        )
