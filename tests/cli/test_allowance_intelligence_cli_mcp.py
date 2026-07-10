from __future__ import annotations

from pathlib import Path

from codex_usage_tracker.cli.parser import build_parser
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_allowance_intelligence_cli_commands_parse() -> None:
    parser = build_parser()

    diagnostics = parser.parse_args(
        ["allowance-diagnostics", "--window-kind", "weekly", "--limit", "0", "--json"]
    )
    export = parser.parse_args(["allowance-export", "--output", "/tmp/allowance-evidence.json"])

    assert diagnostics.command == "allowance-diagnostics"
    assert diagnostics.window_kind == "weekly"
    assert diagnostics.limit == 0
    assert diagnostics.as_json is True
    assert export.command == "allowance-export"
    assert export.output == Path("/tmp/allowance-evidence.json")


def test_usage_allowance_mcp_tools_return_contracts(tmp_path: Path, monkeypatch) -> None:
    from codex_usage_tracker.cli import mcp_allowance, mcp_server

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
    monkeypatch.setattr(mcp_allowance, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_allowance, "DEFAULT_ALLOWANCE_PATH", tmp_path / "allowance.json")
    monkeypatch.setattr(mcp_allowance, "DEFAULT_RATE_CARD_PATH", tmp_path / "rate-card.json")

    history = mcp_server.usage_allowance_history(window_kind="weekly")
    diagnostics = mcp_server.usage_allowance_diagnostics(window_kind="weekly")
    export = mcp_server.usage_allowance_export(window_kind="weekly")

    assert history["schema"] == "codex-usage-tracker-allowance-history-v1"
    assert diagnostics["schema"] == "codex-usage-tracker-allowance-diagnostics-v1"
    assert export["schema"] == "codex-usage-tracker-allowance-evidence-export-v1"
    assert export["privacy_mode"] == "strict"
