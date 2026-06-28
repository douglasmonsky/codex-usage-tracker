"""Walk-forward prediction diagnostics for usage-drain modeling."""

from __future__ import annotations

from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain_error_diagnostics import (
    prediction_error_diagnostics as _prediction_error_diagnostics,
)
from codex_usage_tracker.usage_drain_error_diagnostics import (
    span_error_metadata as _span_error_metadata,
)
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_feature_history import (
    is_one_percent_delta as _is_one_percent_delta,
)
from codex_usage_tracker.usage_drain_feature_history import (
    same_value_tail_streak as _same_value_tail_streak,
)
from codex_usage_tracker.usage_drain_feature_history import (
    tail_streak as _tail_streak,
)
from codex_usage_tracker.usage_drain_grace import (
    REGIME_GRACE_MAX_BREAK_DELTA,
    REGIME_GRACE_SPANS,
    REGIME_GRACE_STREAK_THRESHOLD,
)
from codex_usage_tracker.usage_drain_grace import (
    one_percent_grace_calibration as _one_percent_grace_calibration,
)
from codex_usage_tracker.usage_drain_grace import (
    one_percent_regime_grace_prediction as _one_percent_regime_grace_prediction,
)
from codex_usage_tracker.usage_drain_history_state import (
    delta_bucket as _delta_bucket,
)
from codex_usage_tracker.usage_drain_history_state import (
    history_state_for_span as _history_state_for_span,
)
from codex_usage_tracker.usage_drain_history_state import (
    previous_call_duration_bucket as _previous_call_duration_bucket,
)
from codex_usage_tracker.usage_drain_history_state import (
    previous_span_wall_time_bucket as _previous_span_wall_time_bucket,
)
from codex_usage_tracker.usage_drain_history_state import (
    streak_bucket as _streak_bucket,
)
from codex_usage_tracker.usage_drain_regression import regression_metrics as _regression_metrics
from codex_usage_tracker.usage_drain_state_buckets import (
    STATE_BUCKET_MODEL_SIGNATURES,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_model_diagnostics as _state_bucket_model_diagnostics,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_predictions as _state_bucket_predictions,
)
from codex_usage_tracker.usage_drain_state_diagnostics import (
    state_ambiguity_summary as _state_ambiguity_summary,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    TRANSITION_DELTA_RISK_GATE_THRESHOLD,
    TRANSITION_DELTA_RISK_GATE_THRESHOLDS,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    best_transition_delta_gate_threshold_from_sums as _best_transition_delta_gate_threshold_from_sums,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    risk_gated_transition_delta_prediction as _risk_gated_transition_delta_prediction,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    transition_delta_gate_diagnostics as _transition_delta_gate_diagnostics,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    update_transition_delta_gate_threshold_sums as _update_transition_delta_gate_threshold_sums,
)
from codex_usage_tracker.usage_drain_transition_metrics import (
    transition_risk_predictions as _transition_risk_predictions,
)
from codex_usage_tracker.usage_drain_transition_metrics import (
    transition_risk_summary as _transition_risk_summary,
)
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import (
    number as _number,
)
from codex_usage_tracker.usage_drain_utils import (
    rounded as _rounded,
)
from codex_usage_tracker.usage_drain_utils import (
    value_mode as _value_mode,
)
from codex_usage_tracker.usage_drain_utils import (
    value_stddev as _value_stddev,
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
    rows: list[dict[str, Any]] = []
    previous_deltas: list[float] = []
    previous_state_rows: list[dict[str, Any]] = []
    transition_gate_absolute_error_sums = {
        threshold: 0.0 for threshold in TRANSITION_DELTA_RISK_GATE_THRESHOLDS
    }
    for index, span in enumerate(spans):
        actual = span.delta_usage_percent
        metadata = _span_error_metadata(span)
        if previous_deltas:
            recent3 = previous_deltas[-3:]
            recent10 = previous_deltas[-10:]
            rolling10_mode = _value_mode(recent10)
            rolling10_stddev = _value_stddev(recent10)
            rolling10_low_share = sum(1 for value in recent10 if value <= 1.0) / len(
                recent10
            )
            one_percent_streak = _tail_streak(
                previous_deltas, predicate=_is_one_percent_delta
            )
            low_delta_streak = _tail_streak(
                previous_deltas, predicate=lambda value: value <= 1.0
            )
            same_delta_streak = _same_value_tail_streak(previous_deltas)
            hybrid_streak = (
                1.0
                if one_percent_streak >= 3
                else previous_deltas[-1]
                if same_delta_streak >= 2
                else sum(recent3) / len(recent3)
            )
            one_percent_grace = _one_percent_regime_grace_prediction(
                previous_deltas,
                streak_threshold=REGIME_GRACE_STREAK_THRESHOLD,
                grace_spans=REGIME_GRACE_SPANS,
                max_break_delta=REGIME_GRACE_MAX_BREAK_DELTA,
            )
            state = {
                **metadata,
                "previous_delta_value": previous_deltas[-1],
                "previous_delta_bucket": _delta_bucket(previous_deltas[-1]),
                "one_percent_streak_count": one_percent_streak,
                "one_percent_streak_bucket": _streak_bucket(one_percent_streak),
                "low_delta_streak_count": low_delta_streak,
                "low_delta_streak_bucket": _streak_bucket(low_delta_streak),
                "same_delta_streak_count": same_delta_streak,
                "same_delta_streak_bucket": _streak_bucket(same_delta_streak),
                "previous_span_wall_time_bucket": _previous_span_wall_time_bucket(
                    spans, index
                ),
                "previous_call_duration_bucket": _previous_call_duration_bucket(
                    spans, index
                ),
            }
            predictions = {
                "constant_one_percent": 1.0,
                "previous_delta": previous_deltas[-1],
                "rolling3_mean_delta": sum(recent3) / len(recent3),
                "rolling10_mean_delta": sum(recent10) / len(recent10),
                "rolling10_median_delta": float(median(recent10)),
                "rolling10_mode_delta": rolling10_mode,
                "hybrid_streak_regime": hybrid_streak,
                "one_percent_regime_grace": one_percent_grace,
                "adaptive_low_delta_mode": rolling10_mode
                if rolling10_low_share >= 0.8
                else previous_deltas[-1],
                "adaptive_stable_mode": rolling10_mode
                if rolling10_stddev <= 1.0
                else previous_deltas[-1],
            }
            state_predictions, state_prediction_details = _state_bucket_predictions(
                previous_state_rows,
                state,
                fallback_prediction=previous_deltas[-1],
            )
            predictions.update(state_predictions)
            transition_risks, transition_risk_details = _transition_risk_predictions(
                previous_state_rows,
                state,
            )
            history_state_prediction = _number(
                predictions.get("empirical_history_state_mode")
            )
            continuation_prediction = _number(predictions.get("one_percent_regime_grace"))
            history_state_risk = _number(transition_risks.get("history_state_risk"))
            adaptive_threshold, adaptive_threshold_detail = (
                _best_transition_delta_gate_threshold_from_sums(
                    transition_gate_absolute_error_sums,
                    training_count=len(rows),
                )
            )
            transition_gate_prediction = _risk_gated_transition_delta_prediction(
                continuation_prediction=continuation_prediction,
                alternate_prediction=history_state_prediction,
                risk=history_state_risk,
                threshold=TRANSITION_DELTA_RISK_GATE_THRESHOLD,
            )
            transition_weighted_prediction = continuation_prediction + (
                history_state_risk
                * (history_state_prediction - continuation_prediction)
            )
            adaptive_gate_prediction = _risk_gated_transition_delta_prediction(
                continuation_prediction=continuation_prediction,
                alternate_prediction=history_state_prediction,
                risk=history_state_risk,
                threshold=adaptive_threshold,
            )
            predictions["transition_gated_history_state_mode"] = (
                transition_gate_prediction
            )
            predictions["transition_weighted_history_state_mode"] = (
                transition_weighted_prediction
            )
            predictions["adaptive_mae_transition_gate_history_state_mode"] = (
                adaptive_gate_prediction
            )
            history_state_risk_detail = (
                transition_risk_details.get("history_state_risk") or {}
            )
            prediction_details = {
                **state_prediction_details,
                "transition_gated_history_state_mode": {
                    "source": "transition_gate_history_state_mode"
                    if history_state_risk >= TRANSITION_DELTA_RISK_GATE_THRESHOLD
                    else "transition_gate_continuation",
                    "risk_model": "history_state_risk",
                    "risk": _rounded(history_state_risk),
                    "risk_threshold": TRANSITION_DELTA_RISK_GATE_THRESHOLD,
                    "risk_detail": history_state_risk_detail,
                    "continuation_model": "one_percent_regime_grace",
                    "alternate_model": "empirical_history_state_mode",
                },
                "transition_weighted_history_state_mode": {
                    "source": "transition_weighted_blend",
                    "risk_model": "history_state_risk",
                    "risk": _rounded(history_state_risk),
                    "risk_detail": history_state_risk_detail,
                    "continuation_model": "one_percent_regime_grace",
                    "alternate_model": "empirical_history_state_mode",
                },
                "adaptive_mae_transition_gate_history_state_mode": {
                    "source": "adaptive_transition_gate_history_state_mode"
                    if history_state_risk >= adaptive_threshold
                    else "adaptive_transition_gate_continuation",
                    "risk_model": "history_state_risk",
                    "risk": _rounded(history_state_risk),
                    "risk_threshold": adaptive_threshold,
                    "training_metric": adaptive_threshold_detail.get("metric"),
                    "training_error": adaptive_threshold_detail.get("error"),
                    "training_support": adaptive_threshold_detail.get("support"),
                    "threshold_source": adaptive_threshold_detail.get("source"),
                    "risk_detail": history_state_risk_detail,
                    "continuation_model": "one_percent_regime_grace",
                    "alternate_model": "empirical_history_state_mode",
                },
            }
            row = {
                "index": index,
                "actual": actual,
                "previous_actual": previous_deltas[-1],
                "metadata": state,
                "predictions": predictions,
                "prediction_details": prediction_details,
                "transition_risks": transition_risks,
                "transition_risk_details": transition_risk_details,
            }
            rows.append(row)
            _update_transition_delta_gate_threshold_sums(
                transition_gate_absolute_error_sums,
                row=row,
            )
        previous_state_rows.append(
            {
                "actual": actual,
                "state": _history_state_for_span(spans, index, metadata, previous_deltas),
            }
        )
        previous_deltas.append(actual)
    return rows








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
