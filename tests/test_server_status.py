from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_status


def test_status_payload_normalizes_include_archived_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["status"] = kwargs
        return {"total_events": 4, "max_event_timestamp": "2026-06-01T00:00:00Z"}

    def query_observed(**kwargs: Any) -> dict[str, object]:
        calls["observed"] = kwargs
        return {"weekly_percent": 37}

    monkeypatch.setattr(server_status, "query_usage_status", query_status)
    monkeypatch.setattr(server_status, "query_latest_observed_usage", query_observed)
    monkeypatch.setattr(
        server_status,
        "refresh_metadata",
        lambda db_path: {
            "latest_refresh_at": "2026-06-01T01:00:00Z",
            "parser_adapter": "jsonl",
            "parser_skipped_events": "3",
            "parser_duplicate_events": "0",
        },
    )

    payload = server_status.status_payload(
        "include_archived=true",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
    )

    assert calls["status"]["include_archived"] is True
    assert calls["observed"]["include_archived"] is True
    assert payload["schema"] == "codex-usage-tracker-status-v1"
    assert payload["latest_refresh_at"] == "2026-06-01T01:00:00Z"
    assert payload["max_event_timestamp"] == "2026-06-01T00:00:00Z"
    assert payload["observed_usage"] == {"weekly_percent": 37}
    assert payload["parser_adapter"] == "jsonl"
    assert payload["parser_diagnostics"] == {"skipped_events": 3}


def test_status_payload_uses_include_archived_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["include_archived"] = kwargs["include_archived"]
        return {}

    monkeypatch.setattr(server_status, "query_usage_status", query_status)
    monkeypatch.setattr(server_status, "query_latest_observed_usage", lambda **kwargs: {})
    monkeypatch.setattr(server_status, "refresh_metadata", lambda db_path: {})

    payload = server_status.status_payload(
        "",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
    )

    assert calls["include_archived"] is True
    assert payload["include_archived"] is True
    assert payload["parser_diagnostics"] == {}
