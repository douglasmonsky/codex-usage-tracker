from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_visualization_mcp_tools_route_to_existing_aggregate_sources(monkeypatch) -> None:
    from codex_usage_tracker.cli import mcp_dashboard, mcp_visualization

    calls: list[dict[str, object]] = []

    def report_pack(**kwargs):
        calls.append(kwargs)
        return {
            "schema": "codex-usage-tracker-reports-pack-v1",
            "generated_at": "2026-07-01T12:00:00Z",
            "evidence": {"usage-drain-model": {"rows": []}},
        }

    monkeypatch.setattr(mcp_dashboard, "usage_report_pack", report_pack)

    suggestions = mcp_visualization.usage_visualization_suggest("show token waste")
    result = mcp_visualization.usage_visualization_render(
        "token_waste",
        source_limit=None,
        evidence_limit=5,
    )

    assert suggestions["summary"]["top_kind"] == "token_waste"
    assert result["schema"] == "codex-usage-tracker-visualization-result-v1"
    assert calls[0]["limit"] == 0
    assert calls[0]["evidence_limit"] == 20
    assert calls[0]["privacy_mode"] == "strict"


def test_thread_visualization_uses_calls_when_thread_is_selected(monkeypatch) -> None:
    from codex_usage_tracker.cli import mcp_dashboard, mcp_visualization

    calls: list[dict[str, object]] = []

    def usage_calls(**kwargs):
        calls.append(kwargs)
        return {"schema": "codex-usage-tracker-calls-v1", "rows": []}

    monkeypatch.setattr(mcp_dashboard, "usage_calls", usage_calls)

    result = mcp_visualization.usage_visualization_render(
        "thread_lifecycle",
        thread="thread:example",
        source_limit=0,
    )

    assert result["visualization"]["title"] == "Thread call lifecycle"
    assert calls[0]["thread"] == "thread:example"
    assert calls[0]["sort"] == "time"
    assert calls[0]["direction"] == "asc"


def test_visualization_render_rejects_artifact_formats() -> None:
    from codex_usage_tracker.cli import mcp_visualization

    with pytest.raises(ValueError, match="SVG and PNG"):
        mcp_visualization.usage_visualization_render("token_waste", format="svg")


def test_visualization_mcp_render_uses_the_real_aggregate_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.cli import mcp_dashboard, mcp_visualization

    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="visual-call",
                session_id="visual-session",
                thread_key="thread:visual",
                event_timestamp="2026-07-01T10:00:00Z",
                cumulative_total_tokens=110,
            )
        ],
        db_path=db_path,
    )
    monkeypatch.setattr(mcp_dashboard, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_dashboard, "DEFAULT_PRICING_PATH", tmp_path / "pricing.json")
    monkeypatch.setattr(mcp_dashboard, "DEFAULT_ALLOWANCE_PATH", tmp_path / "allowance.json")
    monkeypatch.setattr(mcp_dashboard, "DEFAULT_RATE_CARD_PATH", tmp_path / "rate-card.json")
    monkeypatch.setattr(mcp_dashboard, "DEFAULT_THRESHOLDS_PATH", tmp_path / "thresholds.json")
    monkeypatch.setattr(mcp_dashboard, "DEFAULT_PROJECTS_PATH", tmp_path / "projects.json")

    result = mcp_visualization.usage_visualization_render(
        "token_waste",
        source_limit=0,
        evidence_limit=5,
    )

    assert result["visualization"]["state"] == {"kind": "ready"}
    assert result["evidence"]["rows"][0]["record_id"] == "visual-call"
    assert result["includes_raw_fragments"] is False
