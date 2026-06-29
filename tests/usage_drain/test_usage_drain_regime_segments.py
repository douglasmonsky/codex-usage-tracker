from codex_usage_tracker.usage_drain.regime_segments import (
    _piecewise_adaptation_by_position,
    regime_streak_summary,
)
from codex_usage_tracker.usage_drain.types import UsageDeltaSpan


def _span(index: int, delta: float) -> UsageDeltaSpan:
    return UsageDeltaSpan(
        start_event_timestamp=f"2026-06-01T00:0{index}:00Z",
        end_event_timestamp=f"2026-06-01T00:0{index}:30Z",
        baseline_used_percent=float(index),
        end_used_percent=float(index) + delta,
        delta_usage_percent=delta,
        row_count=1,
        standard_usage_credits=100.0 * delta,
        non_candidate_standard_credits=0.0,
        candidate_standard_credits={},
        documented_fast_weighted_credits={},
        candidate_row_counts={},
        documented_fast_weighted_token_totals={},
        models={},
        effort_counts={},
        token_totals={},
        timing_totals={},
    )


def test_regime_streak_summary_preserves_runs_and_breaks() -> None:
    summary = regime_streak_summary(
        [_span(1, 1.0), _span(2, 1.0), _span(3, 1.0), _span(4, 1.0), _span(5, 2.0), _span(6, 1.0)]
    )

    one_percent_runs = summary["one_percent_runs"]
    assert one_percent_runs["count"] == 2
    assert one_percent_runs["long_run_min_length"] == 3
    assert one_percent_runs["long_run_count"] == 1
    assert one_percent_runs["max_span_count"] == 4
    assert one_percent_runs["current_streak"] == 1
    assert one_percent_runs["latest_run"]["start_index"] == 5
    assert one_percent_runs["top_runs"][0]["span_count"] == 4
    assert summary["breaks_after_long_one_percent_runs"] == [
        {
            "preceding_start_index": 0,
            "preceding_end_index": 3,
            "preceding_span_count": 4,
            "break_index": 4,
            "break_delta_percent": 2.0,
            "break_timestamp": "2026-06-01T00:05:00Z",
            "break_date": "2026-06-01",
        }
    ]


def test_piecewise_adaptation_by_position_groups_rows_by_segment_position() -> None:
    prediction_rows = {
        index: {
            "actual": float(index + 1),
            "predictions": {
                "constant_one_percent": 1.0,
                "previous_delta": float(index + 1),
                "one_percent_regime_grace": 1.0,
                "empirical_reset_state_mode": 1.0,
            },
        }
        for index in range(6)
    }
    segments = [
        {"label": "stable", "start_index": 0, "end_index": 2},
        {"label": "shift", "start_index": 3, "end_index": 5},
    ]

    report = _piecewise_adaptation_by_position(prediction_rows, segments)

    assert report["position_buckets"] == [
        "first_span",
        "second_span",
        "third_span",
        "fourth_fifth_span",
        "sixth_plus_span",
    ]
    assert report["all_segments"]["first_span"]["prediction_rows"] == 2
    assert report["all_segments"]["second_span"]["prediction_rows"] == 2
    assert report["all_segments"]["third_span"]["best_by_mae"] == "previous_delta:0.0"
    assert report["by_label"]["stable"]["first_span"]["prediction_rows"] == 1
    assert report["by_label"]["shift"]["third_span"]["prediction_rows"] == 1
