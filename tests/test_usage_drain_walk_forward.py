import pytest

from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_walk_forward import walk_forward_prediction_rows


def _span(index: int, delta: float) -> UsageDeltaSpan:
    return UsageDeltaSpan(
        start_event_timestamp=f"2026-06-01T10:0{index}:00Z",
        end_event_timestamp=f"2026-06-01T10:0{index}:30Z",
        baseline_used_percent=0.0,
        end_used_percent=delta,
        delta_usage_percent=delta,
        row_count=1,
        standard_usage_credits=100.0 * delta,
        non_candidate_standard_credits=0.0,
        candidate_standard_credits={},
        documented_fast_weighted_credits={},
        candidate_row_counts={},
        documented_fast_weighted_token_totals={},
        models={"gpt-5.5": 1},
        effort_counts={"xhigh": 1},
        token_totals={},
        timing_totals={},
    )


def test_walk_forward_prediction_rows_preserves_public_row_contract() -> None:
    rows = walk_forward_prediction_rows(
        [_span(0, 1.0), _span(1, 1.0), _span(2, 2.0), _span(3, 1.0)]
    )

    assert [row["index"] for row in rows] == [1, 2, 3]
    assert [row["actual"] for row in rows] == [1.0, 2.0, 1.0]
    assert rows[0]["previous_actual"] == 1.0
    assert rows[1]["predictions"]["previous_delta"] == 1.0
    assert rows[1]["predictions"]["rolling3_mean_delta"] == 1.0
    assert rows[2]["predictions"]["previous_delta"] == 2.0
    assert rows[2]["predictions"]["rolling3_mean_delta"] == pytest.approx(4 / 3)
    assert "one_percent_streak_count" in rows[0]["metadata"]
    assert "empirical_history_state_mode" in rows[0]["prediction_details"]
    assert "history_state_risk" in rows[0]["transition_risks"]
