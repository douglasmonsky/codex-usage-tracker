from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.reports.api import build_action_brief_report
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event, _write_pricing


def test_action_brief_returns_compact_aggregate_actions(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    event = replace(
        _usage_event(
            record_id="large-low-output",
            session_id="session-1",
            thread_key="thread:Waste check",
            event_timestamp="2026-05-17T18:00:00Z",
            cumulative_total_tokens=30_000,
        ),
        input_tokens=29_500,
        cached_input_tokens=0,
        output_tokens=50,
        reasoning_output_tokens=25,
        total_tokens=29_550,
        cumulative_input_tokens=29_500,
        cumulative_cached_input_tokens=0,
        cumulative_output_tokens=50,
        cumulative_reasoning_output_tokens=25,
    )
    upsert_usage_events([event], db_path=db_path)

    report = build_action_brief_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        evidence_limit=3,
        privacy_mode="strict",
    ).payload

    assert report["schema"] == "codex-usage-tracker-action-brief-v1"
    assert report["content_mode"] == "aggregate_action_brief"
    assert report["includes_indexed_content"] is False
    assert report["includes_raw_fragments"] is False
    assert report["summary"]["top_action_family"] == "large_low_output_context_pressure"
    assert report["actions"][0]["family"] == "large_low_output_context_pressure"
    assert "usage_large_low_output_calls" in report["recommended_next_tools"]
    assert report["actions"][0]["recommended_workflow_change"]
    assert report["actions"][0]["how_to_verify"]
    serialized = str(report)
    assert "raw_command" not in serialized
    assert "raw_tool_output" not in serialized
    assert "full_path" not in serialized
