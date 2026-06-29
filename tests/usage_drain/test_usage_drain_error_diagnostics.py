from __future__ import annotations

from codex_usage_tracker.usage_drain.error_diagnostics import (
    prediction_error_diagnostics,
    span_error_metadata,
)
from codex_usage_tracker.usage_drain.types import UsageDeltaSpan


def test_span_error_metadata_reports_time_reset_and_usage_buckets() -> None:
    span = UsageDeltaSpan(
        start_event_timestamp="2026-06-01T10:00:00Z",
        end_event_timestamp="2026-06-01T10:00:30Z",
        baseline_used_percent=42.0,
        end_used_percent=43.0,
        delta_usage_percent=1.0,
        row_count=1,
        standard_usage_credits=100.0,
        non_candidate_standard_credits=0.0,
        candidate_standard_credits={},
        documented_fast_weighted_credits={},
        candidate_row_counts={},
        documented_fast_weighted_token_totals={},
        models={},
        effort_counts={},
        token_totals={},
        timing_totals={},
        rate_limit_plan_type="pro",
        rate_limit_limit_id="codex",
        usage_window_source="primary",
        usage_window_minutes=300,
    )

    metadata = span_error_metadata(span)

    assert metadata == {
        "date": "2026-06-01",
        "day_of_week": "0",
        "hour_bucket": "10",
        "reset_phase": "fourth_quarter",
        "baseline_used_bucket": "40_45_pct",
        "window_elapsed_bucket": "fourth_quarter",
        "reset_remaining_bucket": "0_min",
        "rate_limit_plan_type": "pro",
        "rate_limit_limit_id": "codex",
        "usage_window_source": "primary",
    }


def test_prediction_error_diagnostics_reports_summary_groups_and_largest() -> None:
    rows = [
        _prediction_row(
            index=1,
            actual=1.0,
            predicted=1.0,
            previous_actual=1.0,
            metadata={
                "date": "2026-06-01",
                "day_of_week": "0",
                "hour_bucket": "10",
                "reset_phase": "early",
                "one_percent_streak_bucket": "1",
                "same_delta_streak_bucket": "1",
            },
        ),
        _prediction_row(
            index=2,
            actual=2.0,
            predicted=2.2,
            previous_actual=1.0,
            metadata={
                "date": "2026-06-01",
                "day_of_week": "0",
                "hour_bucket": "11",
                "reset_phase": "middle",
                "one_percent_streak_bucket": "2",
                "same_delta_streak_bucket": "1",
            },
        ),
        _prediction_row(
            index=3,
            actual=10.0,
            predicted=3.0,
            previous_actual=2.0,
            metadata={
                "date": "2026-06-02",
                "day_of_week": "1",
                "hour_bucket": "11",
                "reset_phase": "late",
                "one_percent_streak_bucket": "large",
                "same_delta_streak_bucket": "2",
            },
        ),
    ]

    result = prediction_error_diagnostics(rows, "model")

    assert result["n"] == 3
    assert result["exact_match_share"] == 0.333333
    assert result["within_quarter_point_share"] == 0.666667
    assert result["within_one_point_share"] == 0.666667
    assert result["large_error_share"] == 0.333333
    assert result["top_transition_errors"][0] == {
        "previous_delta_percent": 2.0,
        "actual_delta_percent": 10.0,
        "count": 1,
        "mean_abs_error": 7.0,
        "max_abs_error": 7.0,
    }
    assert result["top_error_dates"][0] == {
        "date": "2026-06-02",
        "count": 1,
        "mean_abs_error": 7.0,
        "max_abs_error": 7.0,
    }
    assert result["largest_errors"][0] == {
        "index": 3,
        "date": "2026-06-02",
        "hour_bucket": "11",
        "day_of_week": "1",
        "reset_phase": "late",
        "previous_delta_percent": 2.0,
        "actual_delta_percent": 10.0,
        "predicted_delta_percent": 3.0,
        "abs_error": 7.0,
    }


def test_prediction_error_diagnostics_handles_empty_inputs() -> None:
    assert prediction_error_diagnostics([], "model") == {
        "n": 0,
        "exact_match_share": None,
        "within_quarter_point_share": None,
        "within_one_point_share": None,
        "large_error_share": None,
        "top_transition_errors": [],
        "top_error_dates": [],
        "error_by_day_of_week": [],
        "error_by_hour": [],
        "error_by_reset_phase": [],
        "error_by_one_percent_streak": [],
        "error_by_same_delta_streak": [],
        "largest_errors": [],
    }


def _prediction_row(
    *,
    index: int,
    actual: float,
    predicted: float,
    previous_actual: float,
    metadata: dict[str, str],
) -> dict[str, object]:
    return {
        "index": index,
        "actual": actual,
        "previous_actual": previous_actual,
        "predictions": {"model": predicted},
        "metadata": metadata,
    }
