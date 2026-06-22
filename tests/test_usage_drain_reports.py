from __future__ import annotations

import json
from pathlib import Path

from store_dashboard_helpers import _usage_event, _write_pricing

from codex_usage_tracker.store import upsert_usage_events
from codex_usage_tracker.usage_drain_reports import build_usage_drain_dashboard_report


def test_usage_drain_dashboard_report_builds_bounded_thread_curves(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    events = [
        _event("alpha-1", "thread:Alpha", "2026-06-01T00:00:00Z", 100, 10.0),
        _event("alpha-2", "thread:Alpha", "2026-06-01T00:01:00Z", 220, 11.0),
        _event("beta-1", "thread:Beta", "2026-06-01T00:02:00Z", 340, 12.0),
        _event("alpha-3", "thread:Alpha", "2026-06-01T00:03:00Z", 460, 13.0),
    ]
    upsert_usage_events(events, db_path=db_path)

    report = build_usage_drain_dashboard_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )

    assert report["summary"]["usage_rows"] == 4
    assert report["summary"]["positive_usage_spans"] == 3
    assert report["summary"]["estimated_cost_usd"] > 0
    curves = report["thread_cost_curves"]
    assert curves["total_threads"] == 2
    assert curves["shown_threads"] == 2
    alpha = next(row for row in curves["threads"] if row["thread"] == "Alpha")
    assert alpha["call_count"] == 3
    assert alpha["estimated_cost_usd"] > 0
    assert alpha["points"][0]["call_index"] == 1
    assert alpha["points"][-1]["call_index"] == 3
    time_series = report["time_series"]
    assert time_series["visible_usage"]["points"]
    assert time_series["weekly_credit_projection"]["points"]
    weekly_point = time_series["weekly_credit_projection"]["points"][0]
    assert weekly_point["projected_weekly_credits"] > 0
    assert weekly_point["confidence"] == "low"
    payload_text = json.dumps(report)
    assert "SECRET RAW PROMPT" not in payload_text
    assert "source_file" not in payload_text


def test_weekly_projection_uses_high_water_usage_deltas(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    events = [
        _event("base", "thread:Alpha", "2026-06-01T00:00:00Z", 100, 0.0, secondary_used_percent=0.0),
        _event("up-1", "thread:Alpha", "2026-06-01T00:01:00Z", 220, 1.0, secondary_used_percent=1.0),
        _event("down", "thread:Alpha", "2026-06-01T00:02:00Z", 340, 0.0, secondary_used_percent=0.0),
        _event("repeat", "thread:Alpha", "2026-06-01T00:03:00Z", 460, 1.0, secondary_used_percent=1.0),
        _event("up-2", "thread:Alpha", "2026-06-01T00:04:00Z", 580, 2.0, secondary_used_percent=2.0),
    ]
    upsert_usage_events(events, db_path=db_path)

    report = build_usage_drain_dashboard_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )

    points = report["time_series"]["weekly_credit_projection"]["points"]
    assert len(points) == 1
    assert points[0]["observed_usage_delta_percent"] == 2.0
    assert points[0]["span_count"] == 2


def test_weekly_time_series_ignores_stale_reset_window_snapshots(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    events = [
        _event(
            "stale",
            "thread:Alpha",
            "2026-05-01T00:00:00Z",
            100,
            50.0,
            secondary_used_percent=90.0,
        ),
        _event("base", "thread:Alpha", "2026-06-01T00:00:00Z", 220, 0.0, secondary_used_percent=0.0),
        _event("up", "thread:Alpha", "2026-06-01T00:01:00Z", 340, 1.0, secondary_used_percent=1.0),
    ]
    upsert_usage_events(events, db_path=db_path)

    report = build_usage_drain_dashboard_report(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )

    visible_points = report["time_series"]["visible_usage"]["points"]
    assert visible_points[0]["timestamp"] == "2026-05-01T00:00:00Z"
    assert visible_points[0]["weekly_used_percent"] is None
    projection_points = report["time_series"]["weekly_credit_projection"]["points"]
    assert len(projection_points) == 1
    assert projection_points[0]["observed_usage_delta_percent"] == 1.0


def _event(
    record_id: str,
    thread_key: str,
    timestamp: str,
    cumulative_total_tokens: int,
    used_percent: float,
    *,
    secondary_used_percent: float | None = None,
    secondary_resets_at: int = 1780876800,
):
    return _usage_event(
        record_id=record_id,
        session_id=f"session-{thread_key}",
        thread_key=thread_key,
        event_timestamp=timestamp,
        cumulative_total_tokens=cumulative_total_tokens,
        rate_limit_plan_type="pro",
        rate_limit_limit_id="codex",
        rate_limit_primary_used_percent=used_percent,
        rate_limit_primary_window_minutes=300,
        rate_limit_primary_resets_at=1781562696,
        rate_limit_secondary_used_percent=(
            used_percent + 10 if secondary_used_percent is None else secondary_used_percent
        ),
        rate_limit_secondary_window_minutes=10080,
        rate_limit_secondary_resets_at=secondary_resets_at,
    )
