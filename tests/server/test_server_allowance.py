from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.server import allowance as server_allowance
from codex_usage_tracker.server.query_cache import AggregateQueryCache
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_allowance_history_payload_returns_normalized_rows(tmp_path: Path) -> None:
    db_path = _allowance_db(tmp_path)

    payload = server_allowance.allowance_history_payload(
        "window_kind=weekly&privacy_mode=strict",
        db_path=db_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=False,
        privacy_mode="normal",
    )

    assert payload["schema"] == "codex-usage-tracker-allowance-history-v1"
    assert payload["privacy_mode"] == "strict"
    assert payload["row_count"] == 2
    rows = payload["rows"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    assert "record_id" not in rows[0]


@pytest.mark.parametrize("limit_query", ["limit=0", "limit=None", "limit=none"])
def test_allowance_diagnostics_and_export_accept_unbounded_limits(
    tmp_path: Path,
    limit_query: str,
) -> None:
    db_path = _allowance_db(tmp_path)
    common = {
        "db_path": db_path,
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "include_archived_default": False,
    }

    diagnostics = server_allowance.allowance_diagnostics_payload(
        f"window_kind=weekly&privacy_mode=strict&{limit_query}",
        privacy_mode="strict",
        **common,
    )
    export = server_allowance.allowance_export_payload(
        f"window_kind=weekly&{limit_query}",
        **common,
    )

    diagnostics_summary = diagnostics["summary"]
    export_summary = export["summary"]
    assert isinstance(diagnostics_summary, dict)
    assert isinstance(export_summary, dict)
    assert diagnostics_summary["observation_count"] == 2
    assert export_summary["observation_count"] == 2


def test_allowance_history_rejects_zero_limit_and_documents_maximum(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="limit must be between 1 and 1000"):
        server_allowance.allowance_history_payload(
            "window_kind=weekly&limit=0",
            db_path=_allowance_db(tmp_path),
            allowance_path=tmp_path / "allowance.json",
            rate_card_path=tmp_path / "rate-card.json",
            include_archived_default=False,
            privacy_mode="strict",
        )


def test_allowance_diagnostics_payload_validates_window_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="window_kind must be one of"):
        server_allowance.allowance_diagnostics_payload(
            "window_kind=bad",
            db_path=tmp_path / "usage.sqlite3",
            allowance_path=tmp_path / "allowance.json",
            rate_card_path=tmp_path / "rate-card.json",
            include_archived_default=False,
            privacy_mode="strict",
        )


def test_allowance_export_payload_is_strict_privacy(tmp_path: Path) -> None:
    db_path = _allowance_db(tmp_path)

    payload = server_allowance.allowance_export_payload(
        "",
        db_path=db_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=False,
    )

    assert payload["schema"] == "codex-usage-tracker-allowance-evidence-export-v1"
    assert payload["privacy_mode"] == "strict"
    assert "summary" in payload


def test_allowance_diagnostics_handler_reuses_generation_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds = 0
    payloads: list[dict[str, object]] = []

    def diagnostics_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        nonlocal builds
        builds += 1
        return {"schema": "codex-usage-tracker-allowance-diagnostics-v1"}

    monkeypatch.setattr(server_allowance, "allowance_diagnostics_payload", diagnostics_payload)
    request = {
        "db_path": tmp_path / "usage.sqlite3",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "include_archived_default": True,
        "privacy_mode": "normal",
        "query_cache": AggregateQueryCache(max_entries=2, max_payload_bytes=1_024),
        "send_error": lambda *_args: None,
        "send_exception": lambda *_args: None,
        "send_json": lambda _status, payload: payloads.append(payload),
    }

    server_allowance.handle_allowance_diagnostics_request("limit=0", **request)
    server_allowance.handle_allowance_diagnostics_request("limit=0", **request)

    assert builds == 1
    assert [_query_cache_status(payload) for payload in payloads] == ["miss", "hit"]
    assert all(
        payload["schema"] == "codex-usage-tracker-allowance-diagnostics-v1" for payload in payloads
    )


def _query_cache_status(payload: dict[str, object]) -> object:
    metadata = payload["query_cache"]
    assert isinstance(metadata, dict)
    return metadata["status"]


def _allowance_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="rec-1",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp="2026-06-01T00:00:00Z",
                cumulative_total_tokens=100,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=10.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            ),
            _usage_event(
                record_id="rec-2",
                session_id="session-1",
                thread_key="thread:allowance",
                event_timestamp="2026-06-01T00:01:00Z",
                cumulative_total_tokens=200,
                rate_limit_plan_type="pro",
                rate_limit_limit_id="codex",
                rate_limit_primary_used_percent=11.0,
                rate_limit_primary_window_minutes=10080,
                rate_limit_primary_resets_at=1000,
            ),
        ],
        db_path=db_path,
    )
    return db_path
