from codex_usage_tracker.usage_drain.token_components import (
    token_component_regression_summary,
)
from codex_usage_tracker.usage_drain.types import UsageDeltaSpan


def test_token_component_summary_reports_weighted_proxy_metadata() -> None:
    span = UsageDeltaSpan(
        start_event_timestamp="2026-06-01T00:00:00Z",
        end_event_timestamp="2026-06-01T00:01:00Z",
        baseline_used_percent=0.0,
        end_used_percent=1.0,
        delta_usage_percent=1.0,
        row_count=1,
        standard_usage_credits=10.0,
        non_candidate_standard_credits={},
        candidate_standard_credits={},
        documented_fast_weighted_credits={"high_medium_candidates": 25.0},
        candidate_row_counts={"high_medium_candidates": 2},
        documented_fast_weighted_token_totals={
            "high_medium_candidates": {
                "uncached_input_tokens": 1_000_000.0,
                "cached_input_tokens": 0.0,
                "reasoning_output_tokens": 0.0,
                "nonreasoning_output_tokens": 0.0,
            },
        },
    )

    summary = token_component_regression_summary([span])

    unweighted = summary["variants"]["unweighted"]
    assert unweighted["weighted_proxy"] is None
    assert unweighted["candidate_rows"] == 0
    assert unweighted["candidate_spans"] == 0
    assert unweighted["credit_accounting"]["target"] == "standard_usage_credits"

    weighted = summary["variants"]["high_medium_fast_weighted"]
    assert weighted["weighted_proxy"] == "high_medium_candidates"
    assert weighted["candidate_rows"] == 2
    assert weighted["candidate_spans"] == 1
    assert weighted["credit_accounting"]["target"] == "high_medium_fast_weighted_credits"
