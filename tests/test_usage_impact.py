from __future__ import annotations

import pytest

from codex_usage_tracker.dashboard_diagnostics import dashboard_parser_diagnostics
from codex_usage_tracker.usage_impact import (
    annotate_rows_with_usage_impact,
    usage_impact_estimate,
)


def _row(
    record_id: str,
    *,
    session_id: str = "session-a",
    timestamp: str = "2026-06-15T12:00:00Z",
    line_number: int = 1,
    credits: float | None = 1.0,
    cost: float | None = 0.1,
    primary_used: float | None = None,
    secondary_used: float | None = None,
    primary_resets: int = 1781562696,
    secondary_resets: int = 1781887793,
    plan_type: str | None = "pro",
    limit_id: str | None = "codex",
) -> dict[str, object]:
    return {
        "record_id": record_id,
        "session_id": session_id,
        "event_timestamp": timestamp,
        "line_number": line_number,
        "usage_credits": credits,
        "estimated_cost_usd": cost,
        "rate_limit_primary_used_percent": primary_used,
        "rate_limit_primary_window_minutes": 300 if primary_used is not None else None,
        "rate_limit_primary_resets_at": primary_resets if primary_used is not None else None,
        "rate_limit_secondary_used_percent": secondary_used,
        "rate_limit_secondary_window_minutes": 10080 if secondary_used is not None else None,
        "rate_limit_secondary_resets_at": secondary_resets if secondary_used is not None else None,
        "rate_limit_plan_type": plan_type,
        "rate_limit_limit_id": limit_id,
    }


def test_usage_impact_allocates_observed_delta_by_codex_credits() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", timestamp="2026-06-15T12:00:00Z", line_number=1, credits=99, primary_used=3, secondary_used=29),
            _row("weighted-low", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=1),
            _row("weighted-high", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=3, primary_used=5, secondary_used=30),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["weighted-low"], "primary") == pytest.approx(0.5)
    assert usage_impact_estimate(by_id["weighted-high"], "primary") == pytest.approx(1.5)
    assert usage_impact_estimate(by_id["weighted-low"], "secondary") == pytest.approx(0.25)
    assert usage_impact_estimate(by_id["weighted-high"], "secondary") == pytest.approx(0.75)
    assert by_id["weighted-high"]["usage_impact"]["secondary"]["basis"] == "credits"  # type: ignore[index]
    assert by_id["baseline"]["usage_impact"]["primary"] is None  # type: ignore[index]


def test_usage_impact_uses_cost_when_credits_are_unavailable() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", cost=9, credits=None, primary_used=2),
            _row("a", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=None, cost=0.25),
            _row("b", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=None, cost=0.75, primary_used=3),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["a"], "primary") == pytest.approx(0.25)
    assert usage_impact_estimate(by_id["b"], "primary") == pytest.approx(0.75)
    assert by_id["a"]["usage_impact"]["primary"]["basis"] == "cost"  # type: ignore[index]


def test_usage_impact_uses_matching_calibrated_history_after_observed_interval() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", primary_used=10),
            _row("direct", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=2, primary_used=12),
            _row("later", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=3),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["direct"], "primary") == pytest.approx(2.0)
    assert usage_impact_estimate(by_id["later"], "primary") == pytest.approx(3.0)
    assert by_id["later"]["usage_impact"]["primary"]["source"] == "calibrated_history"  # type: ignore[index]
    assert by_id["later"]["usage_impact"]["primary"]["basis"] == "credits"  # type: ignore[index]


def test_usage_impact_calibrates_legacy_rows_with_missing_scope() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row(
                "legacy",
                timestamp="2026-06-14T12:00:00Z",
                line_number=1,
                credits=3,
                plan_type=None,
                limit_id=None,
            ),
            _row("baseline", timestamp="2026-06-15T12:00:00Z", line_number=2, primary_used=10),
            _row("direct", timestamp="2026-06-15T12:01:00Z", line_number=3, credits=2, primary_used=12),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert by_id["baseline"]["usage_impact"]["primary"] is None  # type: ignore[index]
    assert usage_impact_estimate(by_id["legacy"], "primary") == pytest.approx(3.0)
    assert by_id["legacy"]["usage_impact"]["primary"]["source"] == "calibrated_history"  # type: ignore[index]


def test_usage_impact_does_not_calibrate_across_plan_or_limit_changes() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", primary_used=10, plan_type="pro", limit_id="codex-pro"),
            _row(
                "direct",
                timestamp="2026-06-15T12:01:00Z",
                line_number=2,
                credits=2,
                primary_used=12,
                plan_type="pro",
                limit_id="codex-pro",
            ),
            _row(
                "changed-plan",
                timestamp="2026-06-15T12:02:00Z",
                line_number=3,
                credits=3,
                plan_type="plus",
                limit_id="codex-plus",
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["direct"], "primary") == pytest.approx(2.0)
    assert usage_impact_estimate(by_id["changed-plan"], "primary") is None


def test_usage_impact_does_not_fall_back_to_token_proxy() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", cost=None, credits=None, primary_used=2),
            _row("a", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=None, cost=None),
            _row("b", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=None, cost=None, primary_used=3),
        ]
    )

    assert all(usage_impact_estimate(row, "primary") is None for row in rows)


def test_usage_impact_does_not_estimate_across_reset_boundaries() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("s1-base", session_id="s1", primary_used=2, primary_resets=100),
            _row("s1-reset", session_id="s1", timestamp="2026-06-15T12:01:00Z", line_number=2, primary_used=1, primary_resets=200),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["s1-reset"], "primary") is None


def test_usage_impact_allocates_account_window_movement_across_sessions() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", session_id="s1", primary_used=10),
            _row(
                "other-session-call",
                session_id="s2",
                timestamp="2026-06-15T12:01:00Z",
                line_number=2,
                credits=1,
            ),
            _row(
                "current-session-call",
                session_id="s1",
                timestamp="2026-06-15T12:02:00Z",
                line_number=3,
                credits=3,
                primary_used=12,
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["other-session-call"], "primary") == pytest.approx(0.5)
    assert usage_impact_estimate(by_id["current-session-call"], "primary") == pytest.approx(1.5)


def test_usage_impact_allows_rolling_reset_timestamp_drift() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", primary_used=2, primary_resets=1781562697),
            _row(
                "later",
                timestamp="2026-06-15T16:57:00Z",
                line_number=2,
                primary_used=6,
                primary_resets=1781581633,
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["later"], "primary") == pytest.approx(4.0)


def test_usage_impact_keeps_weekly_reset_timestamp_as_boundary() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", secondary_used=0, secondary_resets=1781406754),
            _row(
                "next-week",
                timestamp="2026-06-15T12:01:00Z",
                line_number=2,
                secondary_used=28,
                secondary_resets=1781887793,
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["next-week"], "secondary") is None


def test_dashboard_parser_diagnostics_hides_benign_duplicate_cumulative_total() -> None:
    diagnostics = dashboard_parser_diagnostics(
        {
            "parser_duplicate_cumulative_total": "47",
            "parser_invalid_integer": "2",
            "parser_unknown_event_shape": "0",
        }
    )

    assert diagnostics == {"invalid_integer": 2}
