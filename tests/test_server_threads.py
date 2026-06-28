from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_threads


def test_threads_payload_normalizes_query_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_threads(**kwargs: Any) -> list[dict[str, object]]:
        calls.update(kwargs)
        return [{"thread_key": "thread-1"}]

    monkeypatch.setattr(server_threads, "query_thread_summaries", query_threads)

    payload = server_threads.threads_payload(
        "limit=7&offset=3&include_archived=true&q=preferred&search=ignored&sort=calls&direction=asc",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
    )

    assert payload["schema"] == "codex-usage-tracker-threads-v1"
    assert payload["rows"] == [{"thread_key": "thread-1"}]
    assert payload["row_count"] == 1
    assert payload["limit"] == 7
    assert payload["offset"] == 3
    assert payload["include_archived"] is True
    assert payload["raw_context_included"] is False
    assert calls["search"] == "preferred"
    assert calls["sort"] == "calls"
    assert calls["direction"] == "asc"


def test_threads_payload_uses_defaults_and_all_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_threads(**kwargs: Any) -> list[dict[str, object]]:
        calls.update(kwargs)
        return []

    monkeypatch.setattr(server_threads, "query_thread_summaries", query_threads)

    payload = server_threads.threads_payload(
        "limit=all",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
    )

    assert payload["limit"] is None
    assert payload["offset"] == 0
    assert payload["include_archived"] is True
    assert calls["limit"] is None
    assert calls["search"] is None
    assert calls["sort"] == "tokens"
    assert calls["direction"] == "desc"


def test_threads_payload_rejects_invalid_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit must be .*positive integer.*all"):
        server_threads.threads_payload(
            "limit=0",
            db_path=tmp_path / "usage.sqlite3",
            include_archived_default=False,
        )
