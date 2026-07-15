from __future__ import annotations

from datetime import datetime, timezone

from codex_usage_tracker.allowance_intelligence.estimation import build_weekly_estimation

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def _cycle(
    cycle_id: str, ended: str, *, used: float = 50, status: str = "completed"
) -> dict[str, object]:
    return {
        "cycle_id": cycle_id,
        "window_kind": "weekly",
        "last_observed_at": ended,
        "latest_used_percent": used,
        "quality_grade": "high",
        "status": status,
        "cycle_state": "accepted",
    }


def _interval(
    cycle_id: str,
    ended: str,
    *,
    start: float,
    end: float,
    credits: float | None = 100,
    coverage: float | None = 1,
) -> dict[str, object]:
    return {
        "cycle_id": cycle_id,
        "window_kind": "weekly",
        "end_observed_at": ended,
        "start_used_percent": start,
        "end_used_percent": end,
        "visible_percent_delta": end - start,
        "estimated_credits": credits,
        "price_coverage": coverage,
        "eligible_for_calibration": 1,
        "eligible_for_forecasting": 1,
        "point_kind": "positive",
    }


def test_estimates_are_prior_only_and_future_rows_do_not_change_history() -> None:
    cycles = [
        _cycle("one", "2026-07-01T00:00:00+00:00"),
        _cycle("two", "2026-07-08T00:00:00+00:00"),
    ]
    intervals = [
        _interval("one", "2026-06-30T00:00:00+00:00", start=0, end=50, credits=100),
        _interval("two", "2026-07-07T00:00:00+00:00", start=0, end=50, credits=200),
    ]
    before = build_weekly_estimation(cycles, intervals, now=NOW)
    after = build_weekly_estimation(
        cycles + [_cycle("future", "2026-07-20T00:00:00+00:00")],
        intervals
        + [_interval("future", "2026-07-19T00:00:00+00:00", start=0, end=50, credits=1000)],
        now=NOW,
    )
    assert before["reconstructions"][1] == after["reconstructions"][1]
    assert before["reconstructions"][1]["prior_capacity_credits_per_percent"] == 2
    assert before["reconstructions"][1]["anchor_correction"] == -50


def test_missing_pricing_is_an_explicit_coverage_gap_not_imputed() -> None:
    result = build_weekly_estimation(
        [_cycle("one", "2026-07-01T00:00:00+00:00")],
        [
            _interval(
                "one", "2026-06-30T00:00:00+00:00", start=0, end=50, credits=None, coverage=None
            )
        ],
        now=NOW,
    )
    assert result["capacity"]["price_coverage"] == 0
    assert result["coverage_gaps"]["missing_pricing_interval_count"] == 1
    assert result["weekly_estimate"]["used_percent"] is None
    assert result["weekly_estimate"]["reason"] == "insufficient_prior_capacity"


def test_fewer_than_two_completed_cycles_are_descriptive_and_not_forecastable() -> None:
    result = build_weekly_estimation(
        [_cycle("one", "2026-07-01T00:00:00+00:00")],
        [_interval("one", "2026-06-30T00:00:00+00:00", start=0, end=50, credits=100)],
        now=NOW,
    )
    assert result["capacity"]["status"] == "descriptive"
    assert result["forecast"]["used_percent"] is None
    assert result["forecast"]["reason"] == "insufficient_prior_cycle_evidence"


def test_sufficient_history_calculates_walk_forward_validation_and_pace_scenarios() -> None:
    cycles = [
        _cycle(f"cycle-{index}", f"2026-07-15T{8 + index:02d}:30:00+00:00") for index in range(4)
    ]
    intervals = [
        _interval(
            f"cycle-{index}",
            f"2026-07-15T{8 + index:02d}:00:00+00:00",
            start=0,
            end=50,
            credits=100,
        )
        for index in range(4)
    ]
    result = build_weekly_estimation(cycles, intervals, now=NOW)
    validation = result["validation"]
    assert validation["sample_size"] == 3
    assert validation["mean_absolute_error"] is not None
    assert set(validation["interval_coverage"]) == {"50", "80", "95"}
    assert set(validation["baselines"]) == {
        "unchanged_counter",
        "previous_interval",
        "recent_observed_pace",
        "previous_cycle_pace",
    }
    # Three walk-forward points leave only two strictly earlier residuals for
    # the later holdout, so promotion remains deliberately descriptive.
    assert validation["status"] == "descriptive"
    assert result["pace_scenarios"]["status"] == "conditional"
    assert result["forecast"]["quantiles"] is None


def test_open_cycle_never_calibrates_and_dense_cycle_cannot_dominate() -> None:
    cycles = [
        _cycle("completed-a", "2026-07-10T00:00:00+00:00"),
        _cycle("completed-b", "2026-07-11T00:00:00+00:00"),
        _cycle("open", "2026-07-12T00:00:00+00:00", status="accepted"),
    ]
    intervals = [
        _interval("completed-a", "2026-07-09T00:00:00+00:00", start=0, end=50, credits=100),
        _interval("completed-b", "2026-07-10T00:00:00+00:00", start=0, end=50, credits=200),
        *[
            _interval("open", f"2026-07-11T{hour:02d}:00:00+00:00", start=0, end=50, credits=500)
            for hour in range(10)
        ],
    ]
    result = build_weekly_estimation(cycles, intervals, now=NOW)
    assert result["capacity"]["completed_cycle_count"] == 2
    assert result["capacity"]["credits_per_percent"] == 3
    assert result["capacity"]["total_ratio_credits_per_percent"] == 3


def test_current_estimate_starts_at_latest_observation_and_uses_only_later_credits() -> None:
    cycles = [
        _cycle("a", "2026-07-10T00:00:00+00:00"),
        _cycle("b", "2026-07-11T00:00:00+00:00"),
        _cycle("current", "2026-07-15T10:00:00+00:00", used=40, status="accepted"),
    ]
    intervals = [
        _interval("a", "2026-07-09T00:00:00+00:00", start=0, end=10, credits=100),
        _interval("b", "2026-07-10T00:00:00+00:00", start=0, end=10, credits=100),
        _interval("current", "2026-07-15T09:00:00+00:00", start=30, end=40, credits=100),
        _interval("current", "2026-07-15T11:00:00+00:00", start=40, end=50, credits=100),
    ]
    result = build_weekly_estimation(cycles, intervals, now=NOW)
    assert result["weekly_estimate"] == {
        "used_percent": 50,
        "clipped": False,
        "reason": None,
        "observed_at": "2026-07-15T10:00:00+00:00",
        "post_observation_credits": 100,
    }


def test_walk_forward_holdout_does_not_use_its_own_residual_band() -> None:
    cycles = [_cycle(f"c{index}", f"2026-07-{index + 1:02d}T23:00:00+00:00") for index in range(5)]
    intervals = [
        _interval(f"c{index}", f"2026-07-{index + 1:02d}T22:00:00+00:00", start=0, end=10, credits=100)
        for index in range(4)
    ] + [_interval("c4", "2026-07-05T22:00:00+00:00", start=0, end=90, credits=100)]
    result = build_weekly_estimation(cycles, intervals, now=NOW)
    holdout = result["validation"]["holdout"]
    assert holdout["sample_size"] == 1
    assert holdout["interval_coverage"]["50"] == 0
    assert holdout["residual_quantiles"]["p90"] == 0
    assert result["validation"]["status"] == "descriptive"


def test_missing_post_observation_pricing_keeps_the_current_estimate_observed_only() -> None:
    cycles = [
        _cycle("a", "2026-07-10T00:00:00+00:00"),
        _cycle("b", "2026-07-11T00:00:00+00:00"),
        _cycle("current", "2026-07-15T10:00:00+00:00", used=40, status="accepted"),
    ]
    intervals = [
        _interval("a", "2026-07-09T00:00:00+00:00", start=0, end=10, credits=100),
        _interval("b", "2026-07-10T00:00:00+00:00", start=0, end=10, credits=100),
        _interval("current", "2026-07-15T11:00:00+00:00", start=40, end=50, credits=None, coverage=None),
    ]
    result = build_weekly_estimation(cycles, intervals, now=NOW)
    assert result["weekly_estimate"] == {
        "used_percent": None,
        "clipped": False,
        "reason": "missing_post_observation_coverage",
    }
