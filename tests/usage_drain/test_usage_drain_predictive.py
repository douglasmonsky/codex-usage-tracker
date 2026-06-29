from codex_usage_tracker.usage_drain.predictive import (
    capacity_residual_diagnostics,
)


def test_capacity_residual_diagnostics_reports_error_concentration() -> None:
    rows = [
        {
            "date": "2026-06-01",
            "hour_bucket": "morning",
            "rate_limit_plan_type": "pro",
        },
        {
            "date": "2026-06-01",
            "hour_bucket": "evening",
            "rate_limit_plan_type": "pro",
        },
        {
            "date": "2026-06-02",
            "hour_bucket": "morning",
            "rate_limit_plan_type": "plus",
        },
    ]

    result = capacity_residual_diagnostics(
        rows,
        actual=[10.0, 20.0, 30.0],
        predicted=[12.0, 5.0, 60.0],
    )

    assert result["n"] == 3
    assert result["mean_error"] == 5.666667
    assert result["within_5_credits_share"] == 0.333333
    assert result["within_10_credits_share"] == 0.333333
    assert result["large_error_share"] == 0.333333
    assert result["top_error_groups"]["date"][0] == {
        "date": "2026-06-02",
        "count": 1,
        "mean_abs_error": 30.0,
        "mean_error": 30.0,
        "max_abs_error": 30.0,
        "mean_actual": 30.0,
        "meanpredicted": 60.0,
    }
    assert result["top_error_groups"]["hour_bucket"][0]["hour_bucket"] == "morning"
    assert result["largest_errors"][0]["abs_error_credits"] == 30.0
    assert result["largest_errors"][0]["rate_limit_plan_type"] == "plus"


def test_capacity_residual_diagnostics_handles_empty_inputs() -> None:
    assert capacity_residual_diagnostics([], [], []) == {
        "n": 0,
        "mean_error": None,
        "within_5_credits_share": None,
        "within_10_credits_share": None,
        "large_error_share": None,
        "top_error_groups": {},
        "largest_errors": [],
    }
