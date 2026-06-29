from __future__ import annotations

from codex_usage_tracker.usage_drain_boundary_summary import (
    _boundary_risk_detail_diagnostics,
    _boundary_risk_scope,
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


def test_boundary_risk_scope_filters_rows_and_reports_models() -> None:
    rows = [
        _risk_row(0, False, model_risk=0.1, prior_risk=0.2),
        _risk_row(1, True, model_risk=0.8, prior_risk=0.2, support=5),
        _risk_row(
            2,
            False,
            model_risk=0.4,
            prior_risk=0.2,
            detail_source="fallback_prior_rate",
            support=0,
        ),
    ]

    result = _boundary_risk_scope(rows, start_index=1)

    assert result["start_index"] == 1
    assert result["n"] == 2
    assert result["boundary_count"] == 1
    assert result["boundary_rate"] == 0.5
    assert result["models"]["model"] == {
        "n": 2,
        "brier": 0.1,
        "auc": 1.0,
        "average_precision": 1.0,
        "precision_at_top_10pct": 1.0,
        "recall_at_top_10pct": 1.0,
        "top_10pct_positive_rate": 1.0,
        "mean_score_positive": 0.8,
        "mean_score_negative": 0.4,
    }
    assert result["models"]["overall_prior_rate"]["brier"] == 0.34
    assert result["risk_detail_diagnostics"] == {
        "model": {
            "matched_state_share": 0.5,
            "mean_support": 5.0,
            "top_signatures": [
                {
                    "signature": "a",
                    "count": 1,
                    "share": 0.5,
                },
            ],
        },
    }


def _risk_row(
    index: int,
    is_boundary: bool,
    *,
    model_risk: float,
    prior_risk: float,
    detail_source: str = "matched_boundary_state",
    support: int = 3,
) -> dict[str, object]:
    return {
        "index": index,
        "is_boundary": is_boundary,
        "boundary_risks": {
            "model": model_risk,
            "overall_prior_rate": prior_risk,
        },
        "boundary_risk_details": {
            "model": {
                "source": detail_source,
                "signature": ["a"] if detail_source == "matched_boundary_state" else [],
                "support": support,
            },
        },
    }
