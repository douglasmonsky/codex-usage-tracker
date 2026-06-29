"""Walk-forward prediction diagnostics for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain_error_diagnostics import (
    prediction_error_diagnostics as _prediction_error_diagnostics,
)
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_grace import (
    one_percent_grace_calibration as _one_percent_grace_calibration,
)
from codex_usage_tracker.usage_drain_regression import regression_metrics as _regression_metrics
from codex_usage_tracker.usage_drain_state_buckets import (
    STATE_BUCKET_MODEL_SIGNATURES,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_model_diagnostics as _state_bucket_model_diagnostics,
)
from codex_usage_tracker.usage_drain_state_diagnostics import (
    state_ambiguity_summary as _state_ambiguity_summary,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    transition_delta_gate_diagnostics as _transition_delta_gate_diagnostics,
)
from codex_usage_tracker.usage_drain_transition_metrics import (
    transition_risk_summary as _transition_risk_summary,
)
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import (
    number as _number,
)
from codex_usage_tracker.usage_drain_walk_forward_rows import (
    walk_forward_prediction_rows as _walk_forward_prediction_rows,
)


def walk_forward_prediction_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    rows = walk_forward_prediction_rows(spans)
    scopes = {
        "all_after_first": 1,
        "all_after_10": 10,
        "all_after_50": 50,
        "time_ordered_holdout_20": max(1, min(len(spans) - 1, int(len(spans) * 0.8)))
        if spans
        else 0,
        "latest_500": max(len(spans) - 500, 1),
        "latest_100": max(len(spans) - 100, 1),
    }
    return {
        "model_descriptions": {
            "constant_one_percent": "Always predicts a 1% visible counter increase.",
            "previous_delta": "Predicts the previous closed positive usage delta.",
            "rolling3_mean_delta": "Predicts the mean of the previous 3 deltas.",
            "rolling10_mean_delta": "Predicts the mean of the previous 10 deltas.",
            "rolling10_median_delta": "Predicts the median of the previous 10 deltas.",
            "rolling10_mode_delta": "Predicts the most common previous 10-delta value.",
            "hybrid_streak_regime": (
                "Predicts 1% after at least three prior 1% deltas; otherwise "
                "uses previous delta after a repeated same-delta streak; "
                "otherwise uses rolling3 mean."
            ),
            "one_percent_regime_grace": (
                "Predicts 1% during a long 1% regime and for one small break "
                "after the regime; otherwise uses previous delta."
            ),
            "adaptive_low_delta_mode": (
                "Uses rolling10 mode when at least 80% of the previous 10 deltas "
                "are <=1%; otherwise uses previous delta."
            ),
            "adaptive_stable_mode": (
                "Uses rolling10 mode when rolling10 standard deviation is <=1%; "
                "otherwise uses previous delta."
            ),
            "empirical_history_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta "
                "and streak buckets, falling back to simpler history buckets."
            ),
            "empirical_calendar_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta, "
                "day-of-week, and hour buckets, with history fallbacks."
            ),
            "empirical_reset_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta, "
                "baseline, reset-phase, and reset-remaining buckets."
            ),
            "empirical_previous_work_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta "
                "plus the prior span's wall-time and call-duration buckets."
            ),
            "transition_gated_history_state_mode": (
                "Uses the 1% continuation grace rule unless matched history-state "
                "transition risk is at least 50%, then uses matched history-state mode."
            ),
            "transition_weighted_history_state_mode": (
                "Blends the 1% continuation grace rule with matched history-state "
                "mode according to matched history-state transition risk."
            ),
            "adaptive_mae_transition_gate_history_state_mode": (
                "Learns the prior-best transition-risk threshold by MAE, then gates "
                "between the 1% continuation grace rule and matched history-state mode."
            ),
        },
        "scopes": {
            name: _walk_forward_scope_metrics(rows, start_index=start_index)
            for name, start_index in scopes.items()
        },
        "one_percent_grace_calibration": _one_percent_grace_calibration(spans, scopes),
        "transition_risk": _transition_risk_summary(rows, scopes),
        "state_ambiguity": _state_ambiguity_summary(rows, scopes),
    }


def walk_forward_prediction_rows(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    return _walk_forward_prediction_rows(spans)








def _walk_forward_scope_metrics(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    actual = [_number(row.get("actual")) for row in scope_rows]
    model_names = list(scope_rows[0]["predictions"].keys()) if scope_rows else []
    return {
        "start_index": start_index,
        "actual": _value_distribution(actual),
        "models": {
            model_name: _regression_metrics(
                actual,
                [
                    _number(row.get("predictions", {}).get(model_name))
                    for row in scope_rows
                ],
            )
            for model_name in model_names
        },
        "error_diagnostics": {
            model_name: _prediction_error_diagnostics(scope_rows, model_name)
            for model_name in (
                "constant_one_percent",
                "previous_delta",
                "rolling3_mean_delta",
                "rolling10_mode_delta",
                "hybrid_streak_regime",
                "one_percent_regime_grace",
                "adaptive_low_delta_mode",
                "empirical_history_state_mode",
                "empirical_calendar_state_mode",
                "empirical_reset_state_mode",
                "empirical_previous_work_state_mode",
                "transition_gated_history_state_mode",
                "transition_weighted_history_state_mode",
                "adaptive_mae_transition_gate_history_state_mode",
            )
            if model_name in model_names
        },
        "transition_gate_diagnostics": {
            model_name: _transition_delta_gate_diagnostics(scope_rows, model_name)
            for model_name in (
                "transition_gated_history_state_mode",
                "transition_weighted_history_state_mode",
                "adaptive_mae_transition_gate_history_state_mode",
            )
            if model_name in model_names
        },
        "state_bucket_diagnostics": {
            model_name: _state_bucket_model_diagnostics(scope_rows, model_name)
            for model_name in STATE_BUCKET_MODEL_SIGNATURES
            if model_name in model_names
        },
    }
