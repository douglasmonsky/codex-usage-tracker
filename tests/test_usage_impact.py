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


def test_usage_impact_uses_codex_family_calibration_for_alternate_codex_ids() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("baseline-1", timestamp="2026-06-15T12:00:00Z", line_number=1, credits=None, cost=None, primary_used=10, secondary_used=20),
            _row("direct-1", timestamp="2026-06-15T12:01:00Z", line_number=2, credits=2, primary_used=12, secondary_used=22),
            _row("baseline-2", timestamp="2026-06-15T12:02:00Z", line_number=3, credits=None, cost=None, primary_used=12, secondary_used=22),
            _row("direct-2", timestamp="2026-06-15T12:03:00Z", line_number=4, credits=2, primary_used=14, secondary_used=24),
            _row("baseline-3", timestamp="2026-06-15T12:04:00Z", line_number=5, credits=None, cost=None, primary_used=14, secondary_used=24),
            _row("direct-3", timestamp="2026-06-15T12:05:00Z", line_number=6, credits=2, primary_used=16, secondary_used=26),
            _row("baseline-4", timestamp="2026-06-15T12:06:00Z", line_number=7, credits=None, cost=None, primary_used=16, secondary_used=26),
            _row("direct-4", timestamp="2026-06-15T12:07:00Z", line_number=8, credits=2, primary_used=18, secondary_used=28),
            _row("baseline-5", timestamp="2026-06-15T12:08:00Z", line_number=9, credits=None, cost=None, primary_used=18, secondary_used=28),
            _row("direct-5", timestamp="2026-06-15T12:09:00Z", line_number=10, credits=2, primary_used=20, secondary_used=30),
            _row(
                "alternate-baseline",
                timestamp="2026-06-16T08:20:00Z",
                line_number=11,
                credits=None,
                cost=None,
                primary_used=0,
                secondary_used=0,
                limit_id="codex_bengalfox",
            ),
            _row(
                "alternate-call",
                timestamp="2026-06-16T08:21:00Z",
                line_number=12,
                credits=2,
                primary_used=0,
                secondary_used=0,
                limit_id="codex_bengalfox",
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}
    primary = by_id["alternate-call"]["usage_impact"]["primary"]  # type: ignore[index]
    secondary = by_id["alternate-call"]["usage_impact"]["secondary"]  # type: ignore[index]

    assert usage_impact_estimate(by_id["alternate-call"], "primary") == pytest.approx(2.0)
    assert usage_impact_estimate(by_id["alternate-call"], "secondary") == pytest.approx(2.0)
    assert primary["limit_id"] == "codex_bengalfox"
    assert primary["calibration_limit_id"] == "codex"
    assert primary["calibration_plan_type"] == "pro"
    assert primary["source_note"] == "calibrated_from_codex_limit_family"
    assert secondary["calibration_sample_count"] == 5


def test_usage_impact_infers_recent_codex_plan_for_alternate_id_without_plan() -> None:
    rows = annotate_rows_with_usage_impact(
        [
            _row("lite-baseline-1", timestamp="2026-06-15T10:00:00Z", line_number=1, credits=None, cost=None, primary_used=10, secondary_used=20, plan_type="prolite"),
            _row("lite-direct-1", timestamp="2026-06-15T10:01:00Z", line_number=2, credits=10, primary_used=11, secondary_used=21, plan_type="prolite"),
            _row("lite-baseline-2", timestamp="2026-06-15T10:02:00Z", line_number=3, credits=None, cost=None, primary_used=11, secondary_used=21, plan_type="prolite"),
            _row("lite-direct-2", timestamp="2026-06-15T10:03:00Z", line_number=4, credits=10, primary_used=12, secondary_used=22, plan_type="prolite"),
            _row("lite-baseline-3", timestamp="2026-06-15T10:04:00Z", line_number=5, credits=None, cost=None, primary_used=12, secondary_used=22, plan_type="prolite"),
            _row("lite-direct-3", timestamp="2026-06-15T10:05:00Z", line_number=6, credits=10, primary_used=13, secondary_used=23, plan_type="prolite"),
            _row("lite-baseline-4", timestamp="2026-06-15T10:06:00Z", line_number=7, credits=None, cost=None, primary_used=13, secondary_used=23, plan_type="prolite"),
            _row("lite-direct-4", timestamp="2026-06-15T10:07:00Z", line_number=8, credits=10, primary_used=14, secondary_used=24, plan_type="prolite"),
            _row("lite-baseline-5", timestamp="2026-06-15T10:08:00Z", line_number=9, credits=None, cost=None, primary_used=14, secondary_used=24, plan_type="prolite"),
            _row("lite-direct-5", timestamp="2026-06-15T10:09:00Z", line_number=10, credits=10, primary_used=15, secondary_used=25, plan_type="prolite"),
            _row("pro-baseline-1", timestamp="2026-06-16T08:00:00Z", line_number=11, credits=None, cost=None, primary_used=30, secondary_used=40, plan_type="pro"),
            _row("pro-direct-1", timestamp="2026-06-16T08:01:00Z", line_number=12, credits=2, primary_used=32, secondary_used=42, plan_type="pro"),
            _row("pro-baseline-2", timestamp="2026-06-16T08:02:00Z", line_number=13, credits=None, cost=None, primary_used=32, secondary_used=42, plan_type="pro"),
            _row("pro-direct-2", timestamp="2026-06-16T08:03:00Z", line_number=14, credits=2, primary_used=34, secondary_used=44, plan_type="pro"),
            _row("pro-baseline-3", timestamp="2026-06-16T08:04:00Z", line_number=15, credits=None, cost=None, primary_used=34, secondary_used=44, plan_type="pro"),
            _row("pro-direct-3", timestamp="2026-06-16T08:05:00Z", line_number=16, credits=2, primary_used=36, secondary_used=46, plan_type="pro"),
            _row("pro-baseline-4", timestamp="2026-06-16T08:06:00Z", line_number=17, credits=None, cost=None, primary_used=36, secondary_used=46, plan_type="pro"),
            _row("pro-direct-4", timestamp="2026-06-16T08:07:00Z", line_number=18, credits=2, primary_used=38, secondary_used=48, plan_type="pro"),
            _row("pro-baseline-5", timestamp="2026-06-16T08:08:00Z", line_number=19, credits=None, cost=None, primary_used=38, secondary_used=48, plan_type="pro"),
            _row("pro-direct-5", timestamp="2026-06-16T08:09:00Z", line_number=20, credits=2, primary_used=40, secondary_used=50, plan_type="pro"),
            _row(
                "alternate-baseline",
                timestamp="2026-06-16T10:55:00Z",
                line_number=21,
                credits=None,
                cost=None,
                primary_used=0,
                secondary_used=0,
                plan_type=None,
                limit_id="codex_bengalfox",
            ),
            _row(
                "alternate-call",
                timestamp="2026-06-16T10:56:00Z",
                line_number=22,
                credits=2,
                primary_used=0,
                secondary_used=0,
                plan_type=None,
                limit_id="codex_bengalfox",
            ),
        ]
    )
    by_id = {str(row["record_id"]): row for row in rows}
    primary = by_id["alternate-call"]["usage_impact"]["primary"]  # type: ignore[index]
    secondary = by_id["alternate-call"]["usage_impact"]["secondary"]  # type: ignore[index]

    assert usage_impact_estimate(by_id["alternate-call"], "primary") == pytest.approx(2.0)
    assert usage_impact_estimate(by_id["alternate-call"], "secondary") == pytest.approx(2.0)
    assert primary["plan_type"] is None
    assert primary["limit_id"] == "codex_bengalfox"
    assert primary["calibration_plan_type"] == "pro"
    assert primary["calibration_limit_id"] == "codex"
    assert secondary["calibration_plan_type"] == "pro"


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
