from __future__ import annotations

from codex_usage_tracker.usage_drain_boundary_summary import (
    _boundary_risk_detail_diagnostics,
)


def test_boundary_risk_detail_diagnostics_summarizes_matched_boundary_states() -> None:
    rows = [
        {
            "boundary_risk_details": {
                "model": {
                    "source": "matched_boundary_state",
                    "signature": ["previous_label", "window_elapsed_bucket"],
                    "support": 6,
                }
            }
        },
        {
            "boundary_risk_details": {
                "model": {
                    "source": "matched_boundary_state",
                    "signature": [],
                    "support": 2,
                }
            }
        },
        {
            "boundary_risk_details": {
                "model": {
                    "source": "fallback_prior_rate",
                    "signature": [],
                    "support": 0,
                }
            }
        },
    ]

    result = _boundary_risk_detail_diagnostics(rows, "model")

    assert result == {
        "matched_state_share": 0.666667,
        "mean_support": 4.0,
        "top_signatures": [
            {
                "signature": "missing",
                "count": 1,
                "share": 0.333333,
            },
            {
                "signature": "previous_label,window_elapsed_bucket",
                "count": 1,
                "share": 0.333333,
            },
        ],
    }
