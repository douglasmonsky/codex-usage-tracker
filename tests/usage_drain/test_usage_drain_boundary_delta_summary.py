from __future__ import annotations

from codex_usage_tracker.usage_drain.boundary_delta_summary import (
    _boundary_delta_prediction_scope,
    _boundary_delta_residual_diagnostics,
    _boundary_delta_risk_gate_diagnostics,
    _boundary_delta_top_error_groups,
)


def test_boundary_delta_top_error_groups_summarizes_error_concentration() -> None:
    errors = [
        {
            "error": 4.0,
            "abs_error": 4.0,
            "actual": 6.0,
            "predicted": 2.0,
            "metadata": {"transition": "same_to_boundary", "is_boundary": True},
        },
        {
            "error": 2.0,
            "abs_error": 2.0,
            "actual": 5.0,
            "predicted": 3.0,
            "metadata": {"transition": "same_to_boundary", "is_boundary": True},
        },
        {
            "error": 1.0,
            "abs_error": 1.0,
            "actual": 2.0,
            "predicted": 1.0,
            "metadata": {"transition": "stable", "is_boundary": False},
        },
    ]

    result = _boundary_delta_top_error_groups(errors, "transition")

    assert result == [
        {
            "transition": "same_to_boundary",
            "count": 2,
            "count_share": 0.666667,
            "share_abs_error": 0.857143,
            "mean_abs_error": 3.0,
            "rmse": 3.162278,
            "max_abs_error": 4.0,
            "mean_actual": 5.5,
            "mean_predicted": 2.5,
        },
        {
            "transition": "stable",
            "count": 1,
            "count_share": 0.333333,
            "share_abs_error": 0.142857,
            "mean_abs_error": 1.0,
            "rmse": 1.0,
            "max_abs_error": 1.0,
            "mean_actual": 2.0,
            "mean_predicted": 1.0,
        },
    ]


def test_boundary_delta_top_error_groups_maps_boundary_state() -> None:
    errors = [
        {
            "error": 2.0,
            "abs_error": 2.0,
            "actual": 3.0,
            "predicted": 1.0,
            "metadata": {"is_boundary": True},
        },
        {
            "error": 1.0,
            "abs_error": 1.0,
            "actual": 1.0,
            "predicted": 0.0,
            "metadata": {"is_boundary": False},
        },
    ]

    result = _boundary_delta_top_error_groups(errors, "boundary_state")

    assert [row["boundary_state"] for row in result] == ["boundary", "same_label"]


def test_boundary_delta_residual_diagnostics_reports_error_payload() -> None:
    rows = [
        {
            "index": 1,
            "date": "2026-06-01",
            "day_of_week": "0",
            "hour_bucket": "10",
            "delta_percent": 3.0,
            "previous_delta_percent": 2.0,
            "boundary_delta_predictions": {"previous_delta": 1.0},
            "boundary_state": "boundary",
            "transition": "same_to_boundary",
            "is_boundary": True,
            "previous_segment_position_bucket": "0_5_calls",
        },
        {
            "index": 2,
            "date": "2026-06-01",
            "day_of_week": "0",
            "hour_bucket": "11",
            "delta_percent": 4.0,
            "previous_delta_percent": 3.0,
            "boundary_delta_predictions": {"previous_delta": 4.0},
            "boundary_state": "same_label",
            "transition": "stable",
            "is_boundary": False,
            "previous_segment_position_bucket": "5_10_calls",
        },
        {
            "index": 3,
            "date": "2026-06-01",
            "day_of_week": "0",
            "hour_bucket": "12",
            "delta_percent": 5.0,
            "previous_delta_percent": 4.0,
            "boundary_delta_predictions": {"previous_delta": 7.0},
            "boundary_state": "boundary",
            "transition": "same_to_boundary",
            "is_boundary": True,
            "previous_segment_position_bucket": "0_5_calls",
        },
    ]

    result = _boundary_delta_residual_diagnostics(rows, "previous_delta")

    assert result["n"] == 3
    assert result["total_abs_error"] == 4.0
    assert result["exact_match_share"] == 0.333333
    assert result["within_one_point_share"] == 0.333333
    assert result["large_error_share"] == 0.0
    assert result["top_error_groups"]["transition"][0] == {
        "transition": "same_to_boundary",
        "count": 2,
        "count_share": 0.666667,
        "share_abs_error": 1.0,
        "mean_abs_error": 2.0,
        "rmse": 2.0,
        "max_abs_error": 2.0,
        "mean_actual": 4.0,
        "mean_predicted": 4.0,
    }
    assert result["largest_errors"][0] == {
        "index": 1,
        "date": "2026-06-01",
        "day_of_week": "0",
        "hour_bucket": "10",
        "transition": "same_to_boundary",
        "previous_segment_position_bucket": "0_5_calls",
        "boundary_state": "boundary",
        "previous_delta_percent": 2.0,
        "actual_delta_percent": 3.0,
        "predicted_delta_percent": 1.0,
        "abs_error": 2.0,
    }


def test_boundary_delta_risk_gate_diagnostics_summarizes_sources() -> None:
    rows = [
        {
            "boundary_delta_prediction_details": {
                "risk_model": {
                    "source": "matched_state",
                    "risk": 0.2,
                    "support": 4,
                    "risk_threshold": 0.3,
                }
            }
        },
        {
            "boundary_delta_prediction_details": {
                "risk_model": {
                    "source": "manual_override",
                    "risk": 0.8,
                    "support": 2,
                    "risk_threshold": 0.5,
                }
            }
        },
        {
            "boundary_delta_prediction_details": {
                "risk_model": {
                    "source": "matched_state",
                    "risk": 0.5,
                    "support": 0,
                    "risk_threshold": 0.7,
                }
            }
        },
    ]

    result = _boundary_delta_risk_gate_diagnostics(rows, "risk_model")

    assert result == {
        "n": 3,
        "override_share": 0.333333,
        "mean_risk": 0.5,
        "mean_support": 2.0,
        "mean_threshold": 0.5,
        "source_counts": [
            {"source": "matched_state", "count": 2, "share": 0.666667},
            {"source": "manual_override", "count": 1, "share": 0.333333},
        ],
    }


def test_boundary_delta_prediction_scope_summarizes_models_and_filters_rows() -> None:
    rows = [
        {
            "index": 0,
            "delta_percent": 2.0,
            "boundary_delta_predictions": {
                "previous_delta": 1.0,
                "risk_gated_label_segment_age_mode": 2.0,
            },
            "boundary_delta_prediction_details": {
                "risk_gated_label_segment_age_mode": {
                    "risk": 0.7,
                    "threshold": 0.5,
                    "mode": "matched",
                }
            },
            "boundary_state": "same",
            "transition": "same_to_boundary",
            "is_boundary": True,
        },
        {
            "index": 1,
            "delta_percent": 4.0,
            "boundary_delta_predictions": {
                "previous_delta": 5.0,
                "risk_gated_label_segment_age_mode": 3.0,
            },
            "boundary_delta_prediction_details": {
                "risk_gated_label_segment_age_mode": {
                    "risk": 0.2,
                    "threshold": 0.5,
                    "mode": "previous",
                }
            },
            "boundary_state": "boundary",
            "transition": "boundary_to_same",
            "is_boundary": False,
        },
    ]

    result = _boundary_delta_prediction_scope(rows, start_index=0)

    assert result["start_index"] == 0
    assert result["n"] == 2
    assert result["actual"] == {
        "n": 2,
        "mean": 3.0,
        "stddev": 1.0,
        "min": 2.0,
        "max": 4.0,
    }
    assert sorted(result["models"]) == [
        "previous_delta",
        "risk_gated_label_segment_age_mode",
    ]
    assert result["models"]["previous_delta"]["mae"] == 1.0
    assert sorted(result["risk_gate_diagnostics"]) == [
        "risk_gated_label_segment_age_mode"
    ]
    assert result["risk_gate_diagnostics"]["risk_gated_label_segment_age_mode"][
        "mean_risk"
    ] == 0.45
    assert sorted(result["residual_diagnostics"]) == ["previous_delta"]

    filtered = _boundary_delta_prediction_scope(rows, start_index=1)

    assert filtered["start_index"] == 1
    assert filtered["n"] == 1
    assert filtered["actual"]["mean"] == 4.0
    assert filtered["models"]["previous_delta"]["mean_predicted"] == 5.0
