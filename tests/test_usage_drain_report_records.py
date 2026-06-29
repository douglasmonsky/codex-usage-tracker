from codex_usage_tracker.usage_drain_reports import (
    _prediction_model_record,
    _token_accounting_highlights,
)
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan


def test_prediction_model_record_reports_compact_metrics() -> None:
    assert _prediction_model_record(
        "demo",
        [1.0, 2.0, 3.0],
        [1.0, 4.0, 3.0],
    ) == {
        "name": "demo",
        "kind": "compact_dashboard_baseline",
        "validation": "same_series_compact",
        "mae": 0.666667,
        "rmse": 1.154701,
        "r2": -1.0,
        "pearson": 0.654654,
        "within_1pt": 0.666667,
        "within_5pts": 1.0,
    }


def test_prediction_model_record_handles_empty_series() -> None:
    assert _prediction_model_record("empty", [], []) == {
        "name": "empty",
        "kind": "compact_dashboard_baseline",
        "validation": "same_series_compact",
        "mae": None,
        "rmse": None,
        "r2": None,
        "pearson": None,
        "within_1pt": None,
        "within_5pts": None,
    }


def test_token_accounting_highlights_reports_totals_and_credit_fit() -> None:
    rows = [
        {
            "input_tokens": 100,
            "cached_input_tokens": 40,
            "uncached_input_tokens": 60,
            "output_tokens": 20,
            "reasoning_output_tokens": 5,
            "total_tokens": 120,
            "usage_credits": 0.02,
        },
        {
            "input_tokens": 300,
            "cached_input_tokens": 100,
            "uncached_input_tokens": 200,
            "output_tokens": 50,
            "reasoning_output_tokens": 10,
            "total_tokens": 350,
            "usage_credits": 0.07,
        },
    ]
    spans = [
        _span(credits=10.0, delta=1.0),
        _span(credits=20.0, delta=2.0),
    ]

    assert _token_accounting_highlights(rows, spans) == {
        "feature_units": "tokens",
        "features": [
            "uncached_input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ],
        "totals": {
            "input_tokens": 400.0,
            "cached_input_tokens": 140.0,
            "uncached_input_tokens": 260.0,
            "output_tokens": 70.0,
            "reasoning_output_tokens": 15.0,
            "total_tokens": 470.0,
            "usage_credits": 0.09,
        },
        "credits_to_visible_delta": {
            "span_count": 2,
            "r2": 1.0,
            "pearson": 1.0,
        },
        "unweighted": {},
        "high_medium_fast_weighted": {},
    }


def _span(*, credits: float, delta: float) -> UsageDeltaSpan:
    return UsageDeltaSpan(
        start_event_timestamp="2026-06-01T00:00:00Z",
        end_event_timestamp="2026-06-01T00:01:00Z",
        baseline_used_percent=0.0,
        end_used_percent=delta,
        delta_usage_percent=delta,
        row_count=1,
        standard_usage_credits=credits,
        non_candidate_standard_credits={},
        candidate_standard_credits={},
        documented_fast_weighted_credits={},
        candidate_row_counts={},
        documented_fast_weighted_token_totals={},
    )
