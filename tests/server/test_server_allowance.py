from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.server import allowance as server_allowance
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
    assert "record_id" not in payload["rows"][0]


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
