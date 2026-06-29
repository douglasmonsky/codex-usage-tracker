from __future__ import annotations

from codex_usage_tracker.usage_drain_error_diagnostics import span_error_metadata
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan


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
