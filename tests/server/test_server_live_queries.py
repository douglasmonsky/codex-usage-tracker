from __future__ import annotations

import pytest

from codex_usage_tracker.server.live_queries import live_query_params


def test_live_query_params_normalizes_usage_api_filters() -> None:
    payload = live_query_params(
        {
            "q": ["needle"],
            "since": ["2026-06-01"],
            "until": ["2026-06-02"],
            "model": ["gpt-5.5"],
            "effort": ["high"],
            "source": ["git"],
            "thread": ["thread-a"],
            "include_archived": ["true"],
            "limit": ["25"],
            "offset": ["10"],
            "sort": ["tokens"],
            "direction": ["asc"],
        },
        include_archived_default=False,
    )

    assert payload["limit"] == 25
    assert payload["offset"] == 10
    assert payload["search"] == "needle"
    assert payload["thread"] == "thread-a"
    assert payload["include_archived"] is True
    assert payload["sort"] == "tokens"
    assert payload["direction"] == "asc"
    assert payload["filters"] == {
        "q": "needle",
        "since": "2026-06-01",
        "until": "2026-06-02",
        "model": "gpt-5.5",
        "effort": "high",
        "source": "git",
        "thread": "thread-a",
        "thread_key": None,
        "include_archived": True,
        "sort": "tokens",
        "direction": "asc",
    }


def test_live_query_params_thread_key_overrides_thread_filter() -> None:
    payload = live_query_params(
        {
            "search": ["fallback"],
            "thread": ["ignored"],
            "include_archived": ["false"],
            "limit": ["all"],
        },
        include_archived_default=True,
        thread_key="thread-key",
    )

    assert payload["limit"] is None
    assert payload["offset"] == 0
    assert payload["search"] == "fallback"
    assert payload["thread"] is None
    assert payload["thread_key"] == "thread-key"
    assert payload["include_archived"] is False
    assert payload["filters"]["thread"] is None
    assert payload["filters"]["thread_key"] == "thread-key"


def test_live_query_params_rejects_invalid_api_limit() -> None:
    with pytest.raises(ValueError, match="limit"):
        live_query_params({"limit": ["zero"]}, include_archived_default=False)
