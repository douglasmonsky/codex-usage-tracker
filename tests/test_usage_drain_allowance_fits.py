from __future__ import annotations

from codex_usage_tracker.usage_drain_allowance_fits import (
    allowance_online_capacity_credit_to_delta_fit,
    allowance_piecewise_credit_to_delta_fit,
)


def test_allowance_piecewise_fit_preserves_segment_model_contract() -> None:
    rows = [
        {
            "delta_usage_percent": 1.0,
            "standard_usage_credits": 10.0,
            "credits_per_visible_percent": 10.0,
        },
        {
            "delta_usage_percent": 2.0,
            "standard_usage_credits": 20.0,
            "credits_per_visible_percent": 10.0,
        },
        {
            "delta_usage_percent": 1.0,
            "standard_usage_credits": 40.0,
            "credits_per_visible_percent": 40.0,
        },
        {
            "delta_usage_percent": 2.0,
            "standard_usage_credits": 80.0,
            "credits_per_visible_percent": 40.0,
        },
    ]

    fit = allowance_piecewise_credit_to_delta_fit(rows, [(0, 2), (2, 4)])

    assert fit["target"] == "visible_delta_percent"
    assert len(fit["segment_models"]) == 2
    assert fit["segment_models"][0] == {
        "segment_index": 1,
        "n": 2,
        "mean_credits_per_visible_percent": 10.0,
        "no_intercept_slope_delta_percent_per_credit": 0.1,
        "no_intercept_implied_credits_per_percent": 10.0,
    }
    assert fit["segment_models"][1] == {
        "segment_index": 2,
        "n": 2,
        "mean_credits_per_visible_percent": 40.0,
        "no_intercept_slope_delta_percent_per_credit": 0.025,
        "no_intercept_implied_credits_per_percent": 40.0,
    }
    models = fit["models"]
    assert set(models) == {
        "global_no_intercept_credit_slope",
        "global_ceiling_no_intercept_credit_slope",
        "piecewise_mean_capacity_denominator",
        "piecewise_ceiling_mean_capacity_denominator",
        "piecewise_leave_one_out_capacity_denominator",
        "piecewise_no_intercept_credit_slope",
        "piecewise_ceiling_no_intercept_credit_slope",
    }
    assert models["piecewise_mean_capacity_denominator"]["metrics"]["r2"] == 1.0
    assert models["piecewise_ceiling_mean_capacity_denominator"]["metrics"]["r2"] == 1.0
    assert models["piecewise_no_intercept_credit_slope"]["metrics"]["r2"] == 1.0
    assert models["global_no_intercept_credit_slope"]["metrics"]["r2"] < 1.0


def test_allowance_online_capacity_fit_preserves_model_contract() -> None:
    rows = [
        {
            "span_index": 0,
            "delta_usage_percent": 1.0,
            "standard_usage_credits": 10.0,
            "credits_per_visible_percent": 10.0,
            "start_event_timestamp": "2026-06-01T00:00:00Z",
            "end_event_timestamp": "2026-06-01T00:01:00Z",
        },
        {
            "span_index": 1,
            "delta_usage_percent": 2.0,
            "standard_usage_credits": 20.0,
            "credits_per_visible_percent": 10.0,
            "start_event_timestamp": "2026-06-01T00:01:00Z",
            "end_event_timestamp": "2026-06-01T00:02:00Z",
        },
        {
            "span_index": 2,
            "delta_usage_percent": 4.0,
            "standard_usage_credits": 40.0,
            "credits_per_visible_percent": 10.0,
            "start_event_timestamp": "2026-06-01T00:02:00Z",
            "end_event_timestamp": "2026-06-01T00:03:00Z",
        },
    ]

    fit = allowance_online_capacity_credit_to_delta_fit(rows, [(0, 2), (2, 3)])

    assert fit["target"] == "visible_delta_percent"
    assert fit["prediction_rows"] == 2
    assert fit["skipped_initial_rows"] == 1
    assert set(fit["models"]) == {
        "previous_capacity_denominator",
        "rolling3_mean_capacity_denominator",
        "rolling10_mean_capacity_denominator",
        "rolling10_median_capacity_denominator",
        "ewma_capacity_denominator",
        "previous_capacity_denominator_ceiling",
        "rolling3_mean_capacity_denominator_ceiling",
        "rolling10_mean_capacity_denominator_ceiling",
        "rolling10_median_capacity_denominator_ceiling",
        "ewma_capacity_denominator_ceiling",
    }
    previous = fit["models"]["previous_capacity_denominator"]
    assert previous["metrics"]["mae"] == 0.0
    assert previous["known_breakpoint_diagnostics"]["known_breakpoint_row_count"] == 1
    assert previous["known_breakpoint_diagnostics"]["non_breakpoint_row_count"] == 1
