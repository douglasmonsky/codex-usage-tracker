from __future__ import annotations

from datetime import datetime, timedelta, timezone

from codex_usage_tracker.allowance_intelligence.estimation import build_weekly_estimation

NOW = datetime(2026, 7, 15, 12, tzinfo=timezone.utc)


def _cycle(
    cycle_id: str,
    ended: str,
    *,
    used: float = 50,
    status: str = "completed",
    quality: str = "high",
) -> dict[str, object]:
    return {
        "cycle_id": cycle_id,
        "window_kind": "weekly",
        "last_observed_at": ended,
        "latest_used_percent": used,
        "quality_grade": quality,
        "status": status,
        "cycle_state": status,
    }


def _interval(
    cycle_id: str,
    ended: str,
    *,
    start: float,
    end: float,
    credits: float | None = 100,
    coverage: float | None = 1,
    confidence: float | None = 1,
    cumulative: float | None = None,
    point_kind: str = "positive",
    started: str | None = None,
) -> dict[str, object]:
    end_at = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    return {
        "cycle_id": cycle_id,
        "window_kind": "weekly",
        "start_observed_at": started or (end_at - timedelta(hours=1)).isoformat(),
        "end_observed_at": ended,
        "start_used_percent": start,
        "end_used_percent": end,
        "visible_percent_delta": end - start,
        "estimated_credits": credits,
        "price_coverage": coverage,
        "confidence": confidence,
        "cumulative_credits": cumulative,
        "eligible_for_calibration": 1,
        "eligible_for_forecasting": 1,
        "point_kind": point_kind,
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
        cycles + [_cycle("future", "2026-07-14T00:00:00+00:00")],
        intervals
        + [_interval("future", "2026-07-13T00:00:00+00:00", start=0, end=50, credits=1000)],
        now=NOW,
    )
    assert before["reconstructions"][1] == after["reconstructions"][1]
    assert before["reconstructions"][1]["prior_capacity_credits_per_percent"] == 2
    assert before["reconstructions"][1]["anchor_correction"] == -50


def test_advancing_now_does_not_reweight_an_older_reconstruction() -> None:
    cycles = [
        _cycle("old", "2026-05-01T00:00:00+00:00"),
        _cycle("middle", "2026-05-15T00:00:00+00:00"),
        _cycle("recent", "2026-07-14T00:00:00+00:00"),
        _cycle("target", "2026-07-15T00:00:00+00:00"),
    ]
    intervals = [
        _interval("old", "2026-04-30T00:00:00+00:00", start=0, end=10, credits=20),
        _interval("middle", "2026-05-14T00:00:00+00:00", start=0, end=10, credits=40),
        _interval("recent", "2026-07-13T00:00:00+00:00", start=0, end=10, credits=1000),
        _interval("target", "2026-07-14T12:00:00+00:00", start=0, end=10, credits=100),
    ]
    initial = build_weekly_estimation(cycles, intervals, now=NOW)
    later = build_weekly_estimation(
        cycles,
        intervals,
        now=datetime(2027, 1, 15, 12, tzinfo=timezone.utc),
    )
    assert initial["reconstructions"][-1] == later["reconstructions"][-1]


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
        _cycle("open", "2026-07-12T00:00:00+00:00", status="open"),
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
    assert result["capacity"]["credits_per_percent"] == 4
    assert result["capacity"]["robust_median_credits_per_percent"] == 3
    assert result["capacity"]["total_ratio_credits_per_percent"] == 3


def test_current_estimate_starts_at_latest_observation_and_uses_only_later_credits() -> None:
    cycles = [
        _cycle("a", "2026-07-10T00:00:00+00:00"),
        _cycle("b", "2026-07-11T00:00:00+00:00"),
        _cycle("current", "2026-07-15T10:00:00+00:00", used=40, status="open"),
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
        _cycle("current", "2026-07-15T10:00:00+00:00", used=40, status="open"),
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


def test_cumulative_credit_samples_reconstruct_the_historical_path() -> None:
    result = build_weekly_estimation(
        [
            _cycle("prior", "2026-07-01T00:00:00+00:00"),
            _cycle("target", "2026-07-08T00:00:00+00:00"),
        ],
        [
            _interval("prior", "2026-06-30T00:00:00+00:00", start=0, end=10, credits=100),
            _interval(
                "target",
                "2026-07-07T00:00:00+00:00",
                start=20,
                end=30,
                credits=100,
                cumulative=25,
            ),
        ],
        now=NOW,
    )
    reconstructed = result["reconstructions"][1]
    assert reconstructed["prior_capacity_credits_per_percent"] == 10
    assert reconstructed["estimated_used_percent"] == 22.5
    assert reconstructed["anchor_correction"] == 0


def test_current_estimate_stops_at_a_censored_post_observation_boundary() -> None:
    result = build_weekly_estimation(
        [
            _cycle("a", "2026-07-10T00:00:00+00:00"),
            _cycle("b", "2026-07-11T00:00:00+00:00"),
            _cycle("current", "2026-07-15T10:00:00+00:00", used=40, status="open"),
        ],
        [
            _interval("a", "2026-07-09T00:00:00+00:00", start=0, end=10, credits=100),
            _interval("b", "2026-07-10T00:00:00+00:00", start=0, end=10, credits=100),
            _interval(
                "current",
                "2026-07-15T10:30:00+00:00",
                start=40,
                end=40,
                credits=10,
                point_kind="censored",
            ),
            _interval("current", "2026-07-15T11:00:00+00:00", start=40, end=41, credits=10),
        ],
        now=NOW,
    )
    assert result["weekly_estimate"]["used_percent"] is None
    assert result["weekly_estimate"]["reason"] == "post_observation_boundary"


def test_capacity_uses_recency_quality_and_coverage_weights() -> None:
    cycles = [
        _cycle("recent", "2026-07-14T00:00:00+00:00"),
        _cycle("older", "2026-07-01T00:00:00+00:00", quality="medium"),
        _cycle("oldest", "2026-06-01T00:00:00+00:00", quality="medium"),
    ]
    intervals = [
        _interval("recent", "2026-07-13T00:00:00+00:00", start=0, end=50, credits=100),
        _interval("older", "2026-06-30T00:00:00+00:00", start=0, end=10, credits=200, coverage=.5),
        _interval("oldest", "2026-05-31T00:00:00+00:00", start=0, end=10, credits=1000, coverage=.5),
    ]
    result = build_weekly_estimation(cycles, intervals, now=NOW)
    assert result["capacity"]["credits_per_percent"] == 2
    assert result["capacity"]["total_ratio_credits_per_percent"] == 18.571429


def test_low_quality_interval_cannot_outweigh_two_supported_cycles() -> None:
    result = build_weekly_estimation(
        [
            _cycle("supported-a", "2026-05-15T00:00:00+00:00"),
            _cycle("supported-b", "2026-05-20T00:00:00+00:00"),
            _cycle("low-quality", "2026-07-14T00:00:00+00:00"),
        ],
        [
            _interval("supported-a", "2026-05-14T00:00:00+00:00", start=0, end=10, credits=20),
            _interval("supported-b", "2026-05-19T00:00:00+00:00", start=0, end=10, credits=40),
            _interval(
                "low-quality",
                "2026-07-13T00:00:00+00:00",
                start=0,
                end=10,
                credits=1000,
                confidence=0.1,
            ),
        ],
        now=NOW,
    )
    assert result["capacity"]["credits_per_percent"] == 4


def test_pace_uses_only_the_most_recent_comparable_completed_cycle() -> None:
    cycles = [
        _cycle("old", "2026-07-13T00:00:00+00:00"),
        _cycle("comparable", "2026-07-14T00:00:00+00:00"),
        _cycle("current", "2026-07-15T11:30:00+00:00", status="open"),
    ]
    intervals = [
        _interval("old", "2026-07-12T23:00:00+00:00", start=0, end=99, credits=99),
        _interval(
            "comparable",
            "2026-07-13T22:00:00+00:00",
            start=0,
            end=99,
            credits=99,
            point_kind="censored",
        ),
        _interval("comparable", "2026-07-13T23:00:00+00:00", start=0, end=7, credits=7),
        _interval("current", "2026-07-15T10:00:00+00:00", start=0, end=3, credits=3),
        _interval("current", "2026-07-15T11:00:00+00:00", start=3, end=7, credits=4),
    ]
    pace = build_weekly_estimation(cycles, intervals, now=NOW)["pace_scenarios"]
    comparable = pace["contributing_windows"]["comparable_prior_cycle"]
    assert comparable == {"value": 7, "sample_count": 1, "cycle_id": "comparable"}
    assert pace["contributing_windows"]["current_cycle"]["sample_count"] == 2


def test_pace_is_normalized_by_elapsed_time() -> None:
    cycles = [
        _cycle("comparable", "2026-07-14T00:00:00+00:00"),
        _cycle("current", "2026-07-15T11:30:00+00:00", status="open"),
    ]
    intervals = [
        _interval(
            "comparable",
            "2026-07-13T23:00:00+00:00",
            start=0,
            end=10,
            credits=10,
            started="2026-07-13T13:00:00+00:00",
        ),
        _interval("current", "2026-07-15T10:00:00+00:00", start=0, end=3, credits=3),
        _interval("current", "2026-07-15T11:00:00+00:00", start=3, end=7, credits=4),
    ]
    pace = build_weekly_estimation(cycles, intervals, now=NOW)["pace_scenarios"]
    assert pace["unit"] == "percent_per_hour"
    assert pace["contributing_windows"]["comparable_prior_cycle"]["value"] == 1
