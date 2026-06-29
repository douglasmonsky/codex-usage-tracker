from __future__ import annotations

from codex_usage_tracker.usage_drain.state_buckets import (
    state_bucket_model_diagnostics,
    transition_risk_detail_diagnostics,
)


def test_state_bucket_model_diagnostics_summarizes_matched_state_details() -> None:
    rows = [
        {
            "prediction_details": {
                "model": {
                    "source": "matched_state",
                    "signature": ["previous_delta_bucket", "one_percent_streak_bucket"],
                    "support": 4,
                }
            }
        },
        {
            "prediction_details": {
                "model": {
                    "source": "matched_state",
                    "signature": ["previous_delta_bucket"],
                    "support": 2,
                }
            }
        },
        {
            "prediction_details": {
                "model": {
                    "source": "fallback_previous_delta",
                    "signature": [],
                    "support": 0,
                }
            }
        },
    ]

    result = state_bucket_model_diagnostics(rows, "model")

    assert result == {
        "n": 3,
        "matched_state_share": 0.666667,
        "mean_support": 3.0,
        "fallback_share": 0.333333,
        "top_signatures": [
            {
                "signature": "previous_delta_bucket",
                "count": 1,
                "share": 0.333333,
            },
            {
                "signature": "previous_delta_bucket,one_percent_streak_bucket",
                "count": 1,
                "share": 0.333333,
            },
        ],
    }


def test_transition_risk_detail_diagnostics_summarizes_matched_state_details() -> None:
    rows = [
        {
            "transition_risk_details": {
                "model": {
                    "source": "matched_state",
                    "signature": ["previous_delta_bucket"],
                    "support": 5,
                }
            }
        },
        {
            "transition_risk_details": {
                "model": {
                    "source": "matched_state",
                    "signature": [],
                    "support": 1,
                }
            }
        },
        {
            "transition_risk_details": {
                "model": {
                    "source": "fallback_prior_rate",
                    "signature": [],
                    "support": 0,
                }
            }
        },
    ]

    result = transition_risk_detail_diagnostics(rows, "model")

    assert result == {
        "matched_state_share": 0.666667,
        "mean_support": 3.0,
        "top_signatures": [
            {
                "signature": "missing",
                "count": 1,
                "share": 0.333333,
            },
            {
                "signature": "previous_delta_bucket",
                "count": 1,
                "share": 0.333333,
            },
        ],
    }
