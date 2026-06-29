from codex_usage_tracker.usage_drain_transition_gates import (
    transition_delta_gate_diagnostics,
)


def test_transition_delta_gate_diagnostics_handles_empty_rows() -> None:
    assert transition_delta_gate_diagnostics([], "model") == {
        "n": 0,
        "override_share": None,
        "mean_risk": None,
        "mean_threshold": None,
        "source_counts": [],
    }


def test_transition_delta_gate_diagnostics_summarizes_sources() -> None:
    rows = [
        {
            "prediction_details": {
                "model": {
                    "source": "transition_gate_history_state_mode",
                    "risk": 0.8,
                    "risk_threshold": 0.5,
                }
            }
        },
        {
            "prediction_details": {
                "model": {
                    "source": "transition_gate_continuation",
                    "risk": 0.2,
                    "risk_threshold": 0.5,
                }
            }
        },
        {
            "prediction_details": {
                "model": {
                    "source": "transition_gate_continuation",
                    "risk": 0.4,
                }
            }
        },
        {"prediction_details": {"other": {"source": "ignored"}}},
    ]

    assert transition_delta_gate_diagnostics(rows, "model") == {
        "n": 4,
        "override_share": 0.25,
        "mean_risk": 0.35,
        "mean_threshold": 0.5,
        "source_counts": [
            {"source": "transition_gate_continuation", "count": 2, "share": 0.5},
            {"source": "missing", "count": 1, "share": 0.25},
            {
                "source": "transition_gate_history_state_mode",
                "count": 1,
                "share": 0.25,
            },
        ],
    }
