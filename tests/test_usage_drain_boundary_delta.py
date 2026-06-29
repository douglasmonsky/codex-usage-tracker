from __future__ import annotations

from codex_usage_tracker.usage_drain_boundary_delta import (
    boundary_walk_forward_delta_prediction_rows,
)


def test_boundary_delta_rows_preserve_matched_risk_and_adaptive_details() -> None:
    rows = [
        {
            "record_id": "one",
            "previous_delta_percent": 1.0,
            "delta_percent": 3.0,
            "previous_label": "boundary",
            "previous_segment_position_bucket": "late",
            "previous_segment_wall_time_bucket": "long",
            "window_elapsed_bucket": "mid",
            "day_of_week": "Mon",
            "hour_bucket": "12",
            "is_boundary": True,
        },
        {
            "record_id": "two",
            "previous_delta_percent": 1.0,
            "delta_percent": 3.0,
            "previous_label": "boundary",
            "previous_segment_position_bucket": "late",
            "previous_segment_wall_time_bucket": "long",
            "window_elapsed_bucket": "mid",
            "day_of_week": "Mon",
            "hour_bucket": "12",
            "is_boundary": True,
        },
        {
            "record_id": "three",
            "previous_delta_percent": 1.0,
            "delta_percent": 3.0,
            "previous_label": "boundary",
            "previous_segment_position_bucket": "late",
            "previous_segment_wall_time_bucket": "long",
            "window_elapsed_bucket": "mid",
            "day_of_week": "Mon",
            "hour_bucket": "12",
            "is_boundary": True,
        },
    ]

    output = boundary_walk_forward_delta_prediction_rows(rows)

    latest = output[-1]
    predictions = latest["boundary_delta_predictions"]
    details = latest["boundary_delta_prediction_details"]
    assert latest["prediction_details"] is details
    assert predictions["label_segment_age_mode"] == 3.0
    assert predictions["boundary_conditioned_label_segment_age_mode"] == 3.0
    assert predictions["risk_gated_label_segment_age_mode"] == 3.0
    assert predictions["risk_weighted_label_segment_age_mode"] == 3.0
    assert predictions["adaptive_mae_gate_label_segment_age_mode"] == 3.0
    assert details["label_segment_age_mode"]["source"] == "matched_state"
    assert details["label_segment_age_mode"]["support"] == 2
    assert details["risk_gated_label_segment_age_mode"]["risk"] == 1.0
    assert details["risk_gated_label_segment_age_mode"]["risk_detail"]["support"] == 2
    assert (
        details["boundary_conditioned_label_segment_age_mode"]["conditioned_on"]
        == "prior_boundary_rows"
    )
    assert (
        details["adaptive_mae_gate_label_segment_age_mode"]["threshold_source"]
        == "prior_best_threshold"
    )
