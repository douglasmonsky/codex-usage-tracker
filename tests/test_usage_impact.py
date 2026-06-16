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


def test_usage_impact_does_not_calibrate_from_sparse_observed_history() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", primary_used=10),
            _row("direct", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=2, primary_used=12),
            _row("later", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=3),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    direct = by_id["direct"]["usage_impact"]["primary"]  # type: ignore[index]
    assert usage_impact_estimate(by_id["direct"], "primary") is None
    assert direct["observed_interval_estimate_percent"] == pytest.approx(2.0)
    assert direct["source_note"] == "suppressed_unvalidated_single_call_observed_jump"
    assert usage_impact_estimate(by_id["later"], "primary") is None


def test_usage_impact_uses_matching_calibrated_history_after_enough_observed_intervals() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline-1", timestamp="2026-06-15T12:00:00Z", line_number=1, credits=None, cost=None, primary_used=10),
            _row("direct-1", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=2, primary_used=12),
            _row("baseline-2", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=None, cost=None, primary_used=12),
            _row("direct-2", timestamp="2026-06-15T12:03:00Z", line_number=4, credits=2, primary_used=14),
            _row("baseline-3", timestamp="2026-06-15T12:04:00Z", line_number=5, credits=None, cost=None, primary_used=14),
            _row("direct-3", timestamp="2026-06-15T12:05:00Z", line_number=6, credits=2, primary_used=16),
            _row("baseline-4", timestamp="2026-06-15T12:06:00Z", line_number=7, credits=None, cost=None, primary_used=16),
            _row("direct-4", timestamp="2026-06-15T12:07:00Z", line_number=8, credits=2, primary_used=18),
            _row("baseline-5", timestamp="2026-06-15T12:08:00Z", line_number=9, credits=None, cost=None, primary_used=18),
            _row("direct-5", timestamp="2026-06-15T12:09:00Z", line_number=10, credits=2, primary_used=20),
            _row("later", timestamp="2026-06-15T12:10:00Z", line_number=11, credits=3),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["later"], "primary") == pytest.approx(3.0)
    assert by_id["later"]["usage_impact"]["primary"]["source"] == "calibrated_history"  # type: ignore[index]
    assert by_id["later"]["usage_impact"]["primary"]["basis"] == "credits"  # type: ignore[index]
    assert by_id["later"]["usage_impact"]["primary"]["calibration_sample_count"] == 5  # type: ignore[index]


def test_usage_impact_calibration_includes_flat_observed_intervals() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", timestamp="2026-06-15T12:00:00Z", line_number=1, credits=None, cost=None, primary_used=10),
            _row("flat-1", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=9, primary_used=10),
            _row("rise-1", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=1, primary_used=11),
            _row("flat-2", timestamp="2026-06-15T12:03:00Z", line_number=4, credits=9, primary_used=11),
            _row("rise-2", timestamp="2026-06-15T12:04:00Z", line_number=5, credits=1, primary_used=12),
            _row("flat-3", timestamp="2026-06-15T12:05:00Z", line_number=6, credits=9, primary_used=12),
            _row("rise-3", timestamp="2026-06-15T12:06:00Z", line_number=7, credits=1, primary_used=13),
            _row("flat-4", timestamp="2026-06-15T12:07:00Z", line_number=8, credits=9, primary_used=13),
            _row("rise-4", timestamp="2026-06-15T12:08:00Z", line_number=9, credits=1, primary_used=14),
            _row("flat-5", timestamp="2026-06-15T12:09:00Z", line_number=10, credits=9, primary_used=14),
            _row("rise-5", timestamp="2026-06-15T12:10:00Z", line_number=11, credits=1, primary_used=15),
            _row("later", timestamp="2026-06-15T12:11:00Z", line_number=12, credits=10),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["later"], "primary") == pytest.approx(1.0)
    assert by_id["later"]["usage_impact"]["primary"]["source"] == "calibrated_history"  # type: ignore[index]
    assert by_id["later"]["usage_impact"]["primary"]["calibration_sample_count"] == 10  # type: ignore[index]


def test_usage_impact_replaces_noisy_observed_jump_with_calibrated_estimate() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", timestamp="2026-06-15T12:00:00Z", line_number=1, credits=None, cost=None, primary_used=10),
            _row("flat-1", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=9, primary_used=10),
            _row("rise-1", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=1, primary_used=11),
            _row("flat-2", timestamp="2026-06-15T12:03:00Z", line_number=4, credits=9, primary_used=11),
            _row("rise-2", timestamp="2026-06-15T12:04:00Z", line_number=5, credits=1, primary_used=12),
            _row("flat-3", timestamp="2026-06-15T12:05:00Z", line_number=6, credits=9, primary_used=12),
            _row("rise-3", timestamp="2026-06-15T12:06:00Z", line_number=7, credits=1, primary_used=13),
            _row("flat-4", timestamp="2026-06-15T12:07:00Z", line_number=8, credits=9, primary_used=13),
            _row("rise-4", timestamp="2026-06-15T12:08:00Z", line_number=9, credits=1, primary_used=14),
            _row("flat-5", timestamp="2026-06-15T12:09:00Z", line_number=10, credits=9, primary_used=14),
            _row("rise-5", timestamp="2026-06-15T12:10:00Z", line_number=11, credits=1, primary_used=15),
            _row("noisy-jump", timestamp="2026-06-15T12:11:00Z", line_number=12, credits=1, primary_used=25),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}
    noisy = by_id["noisy-jump"]["usage_impact"]["primary"]  # type: ignore[index]

    assert usage_impact_estimate(by_id["noisy-jump"], "primary") == pytest.approx(15 / 51)
    assert noisy["source"] == "calibrated_history"
    assert noisy["source_note"] == "calibrated_after_noisy_observed_interval"
    assert noisy["observed_interval_estimate_percent"] == pytest.approx(10.0)


def test_usage_impact_does_not_calibrate_legacy_rows_from_known_scope() -> None:
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
            _row("baseline-1", timestamp="2026-06-15T12:00:00Z", line_number=2, credits=None, cost=None, primary_used=10),
            _row("direct-1", timestamp="2026-06-15T12:01:00Z", line_number=3, credits=2, primary_used=12),
            _row("baseline-2", timestamp="2026-06-15T12:02:00Z", line_number=4, credits=None, cost=None, primary_used=12),
            _row("direct-2", timestamp="2026-06-15T12:03:00Z", line_number=5, credits=2, primary_used=14),
            _row("baseline-3", timestamp="2026-06-15T12:04:00Z", line_number=6, credits=None, cost=None, primary_used=14),
            _row("direct-3", timestamp="2026-06-15T12:05:00Z", line_number=7, credits=2, primary_used=16),
            _row("baseline-4", timestamp="2026-06-15T12:06:00Z", line_number=8, credits=None, cost=None, primary_used=16),
            _row("direct-4", timestamp="2026-06-15T12:07:00Z", line_number=9, credits=2, primary_used=18),
            _row("baseline-5", timestamp="2026-06-15T12:08:00Z", line_number=10, credits=None, cost=None, primary_used=18),
            _row("direct-5", timestamp="2026-06-15T12:09:00Z", line_number=11, credits=2, primary_used=20),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert by_id["baseline-1"]["usage_impact"]["primary"] is None  # type: ignore[index]
    assert usage_impact_estimate(by_id["legacy"], "primary") is None


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

    direct = by_id["direct"]["usage_impact"]["primary"]  # type: ignore[index]
    assert usage_impact_estimate(by_id["direct"], "primary") is None
    assert direct["observed_interval_estimate_percent"] == pytest.approx(2.0)
    assert direct["source_note"] == "suppressed_unvalidated_single_call_observed_jump"
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


def test_usage_impact_negative_delta_clears_pending_interval_before_later_growth() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("before-reset-base", primary_used=8),
            _row("before-reset-call", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=5),
            _row(
                "reset",
                timestamp="2026-06-15T12:02:00Z",
                line_number=3,
                credits=None,
                cost=None,
                primary_used=2,
                primary_resets=1781563000,
            ),
            _row("after-reset-call", timestamp="2026-06-15T12:03:00Z", line_number=4, credits=1),
            _row(
                "after-reset-snapshot",
                timestamp="2026-06-15T12:04:00Z",
                line_number=5,
                credits=None,
                cost=None,
                primary_used=3,
                primary_resets=1781563000,
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["before-reset-call"], "primary") is None
    assert usage_impact_estimate(by_id["after-reset-call"], "primary") == pytest.approx(1.0)


def test_usage_impact_treats_large_primary_reset_rollback_as_boundary() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", primary_used=1, primary_resets=1780527008),
            _row("call", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=5),
            _row(
                "rollback-snapshot",
                timestamp="2026-06-15T12:02:00Z",
                line_number=3,
                primary_used=94,
                primary_resets=1780508966,
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["call"], "primary") is None
    assert usage_impact_estimate(by_id["rollback-snapshot"], "primary") is None


def test_usage_impact_ignores_same_week_stale_decrease_before_return_to_high_watermark() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline", secondary_used=26),
            _row("first-call", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=1),
            _row(
                "first-rise",
                timestamp="2026-06-15T12:02:00Z",
                line_number=3,
                credits=None,
                cost=None,
                secondary_used=30,
            ),
            _row(
                "stale-lower",
                timestamp="2026-06-15T12:03:00Z",
                line_number=4,
                credits=None,
                cost=None,
                secondary_used=26,
            ),
            _row("second-call", timestamp="2026-06-15T12:04:00Z", line_number=5, credits=1),
            _row(
                "same-high-watermark",
                timestamp="2026-06-15T12:05:00Z",
                line_number=6,
                credits=None,
                cost=None,
                secondary_used=30,
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}

    assert usage_impact_estimate(by_id["first-call"], "secondary") == pytest.approx(4.0)
    assert usage_impact_estimate(by_id["second-call"], "secondary") is None


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

    later = by_id["later"]["usage_impact"]["primary"]  # type: ignore[index]
    assert usage_impact_estimate(by_id["later"], "primary") is None
    assert later["observed_interval_estimate_percent"] == pytest.approx(4.0)
    assert later["source_note"] == "suppressed_unvalidated_single_call_observed_jump"


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
