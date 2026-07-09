"""Walk-forward row construction for usage-drain diagnostics."""

from __future__ import annotations

from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain.error_diagnostics import (
    span_error_metadata as _span_error_metadata,
)
from codex_usage_tracker.usage_drain.feature_history import (
    is_one_percent_delta as _is_one_percent_delta,
)
from codex_usage_tracker.usage_drain.feature_history import (
    same_value_tail_streak as _same_value_tail_streak,
)
from codex_usage_tracker.usage_drain.feature_history import (
    tail_streak as _tail_streak,
)
from codex_usage_tracker.usage_drain.grace import (
    REGIME_GRACE_MAX_BREAK_DELTA,
    REGIME_GRACE_SPANS,
    REGIME_GRACE_STREAK_THRESHOLD,
)
from codex_usage_tracker.usage_drain.grace import (
    one_percent_regime_grace_prediction as _one_percent_regime_grace_prediction,
)
from codex_usage_tracker.usage_drain.history_state import (
    delta_bucket as _delta_bucket,
)
from codex_usage_tracker.usage_drain.history_state import (
    history_state_for_span as _history_state_for_span,
)
from codex_usage_tracker.usage_drain.history_state import (
    previous_call_duration_bucket as _previous_call_duration_bucket,
)
from codex_usage_tracker.usage_drain.history_state import (
    previous_span_wall_time_bucket as _previous_span_wall_time_bucket,
)
from codex_usage_tracker.usage_drain.history_state import (
    streak_bucket as _streak_bucket,
)
from codex_usage_tracker.usage_drain.state_buckets import (
    state_bucket_predictions as _state_bucket_predictions,
)
from codex_usage_tracker.usage_drain.transition_gates import (
    TRANSITION_DELTA_RISK_GATE_THRESHOLD,
    TRANSITION_DELTA_RISK_GATE_THRESHOLDS,
)
from codex_usage_tracker.usage_drain.transition_gates import (
    best_transition_delta_gate_threshold_from_sums as _best_transition_delta_gate_threshold_from_sums,
)
from codex_usage_tracker.usage_drain.transition_gates import (
    risk_gated_transition_delta_prediction as _risk_gated_transition_delta_prediction,
)
from codex_usage_tracker.usage_drain.transition_gates import (
    update_transition_delta_gate_threshold_sums as _update_transition_delta_gate_threshold_sums,
)
from codex_usage_tracker.usage_drain.transition_metrics import (
    transition_risk_predictions as _transition_risk_predictions,
)
from codex_usage_tracker.usage_drain.types import UsageDeltaSpan
from codex_usage_tracker.usage_drain.utils import number as _number
from codex_usage_tracker.usage_drain.utils import rounded as _rounded
from codex_usage_tracker.usage_drain.utils import value_mode as _value_mode
from codex_usage_tracker.usage_drain.utils import value_stddev as _value_stddev


def walk_forward_prediction_rows(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_deltas: list[float] = []
    previous_state_rows: list[dict[str, Any]] = []
    transition_gate_absolute_error_sums = _initial_transition_gate_error_sums()

    for index, span in enumerate(spans):
        actual = span.delta_usage_percent
        metadata = _span_error_metadata(span)
        if previous_deltas:
            row = _walk_forward_prediction_row(
                spans=spans,
                index=index,
                actual=actual,
                metadata=metadata,
                rows=rows,
                previous_deltas=previous_deltas,
                previous_state_rows=previous_state_rows,
                transition_gate_absolute_error_sums=transition_gate_absolute_error_sums,
            )
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


def _initial_transition_gate_error_sums() -> dict[float, float]:
    return {threshold: 0.0 for threshold in TRANSITION_DELTA_RISK_GATE_THRESHOLDS}


def _walk_forward_prediction_row(
    *,
    spans: list[UsageDeltaSpan],
    index: int,
    actual: float,
    metadata: dict[str, Any],
    rows: list[dict[str, Any]],
    previous_deltas: list[float],
    previous_state_rows: list[dict[str, Any]],
    transition_gate_absolute_error_sums: dict[float, float],
) -> dict[str, Any]:
    history = _walk_forward_history_metrics(previous_deltas)
    state = _walk_forward_state(
        spans=spans,
        index=index,
        metadata=metadata,
        previous_deltas=previous_deltas,
        history=history,
    )
    predictions = _walk_forward_base_predictions(previous_deltas, history)
    state_prediction_details = _add_state_bucket_predictions(
        predictions=predictions,
        previous_state_rows=previous_state_rows,
        state=state,
        fallback_prediction=previous_deltas[-1],
    )
    transition_risks, transition_risk_details = _transition_risk_predictions(
        previous_state_rows, state
    )
    transition_predictions, transition_details = _walk_forward_transition_predictions(
        predictions=predictions,
        transition_risks=transition_risks,
        transition_risk_details=transition_risk_details,
        transition_gate_absolute_error_sums=transition_gate_absolute_error_sums,
        training_count=len(rows),
    )
    predictions.update(transition_predictions)
    prediction_details = {**state_prediction_details, **transition_details}
    return {
        "index": index,
        "actual": actual,
        "previous_actual": previous_deltas[-1],
        "metadata": state,
        "predictions": predictions,
        "prediction_details": prediction_details,
        "transition_risks": transition_risks,
        "transition_risk_details": transition_risk_details,
    }


def _walk_forward_history_metrics(previous_deltas: list[float]) -> dict[str, Any]:
    recent3 = previous_deltas[-3:]
    recent10 = previous_deltas[-10:]
    rolling10_mode = _value_mode(recent10)
    one_percent_streak = _tail_streak(previous_deltas, predicate=_is_one_percent_delta)
    same_delta_streak = _same_value_tail_streak(previous_deltas)
    return {
        "recent3": recent3,
        "recent10": recent10,
        "rolling10_mode": rolling10_mode,
        "rolling10_stddev": _value_stddev(recent10),
        "rolling10_low_share": _low_delta_share(recent10),
        "one_percent_streak": one_percent_streak,
        "low_delta_streak": _tail_streak(previous_deltas, predicate=lambda value: value <= 1.0),
        "same_delta_streak": same_delta_streak,
        "hybrid_streak": _hybrid_streak_prediction(
            previous_deltas=previous_deltas,
            recent3=recent3,
            one_percent_streak=one_percent_streak,
            same_delta_streak=same_delta_streak,
        ),
        "one_percent_grace": _one_percent_regime_grace_prediction(
            previous_deltas,
            streak_threshold=REGIME_GRACE_STREAK_THRESHOLD,
            grace_spans=REGIME_GRACE_SPANS,
            max_break_delta=REGIME_GRACE_MAX_BREAK_DELTA,
        ),
    }


def _low_delta_share(recent_deltas: list[float]) -> float:
    return sum(1 for value in recent_deltas if value <= 1.0) / len(recent_deltas)


def _hybrid_streak_prediction(
    *,
    previous_deltas: list[float],
    recent3: list[float],
    one_percent_streak: int,
    same_delta_streak: int,
) -> float:
    if one_percent_streak >= 3:
        return 1.0
    if same_delta_streak >= 2:
        return previous_deltas[-1]
    return sum(recent3) / len(recent3)


def _walk_forward_state(
    *,
    spans: list[UsageDeltaSpan],
    index: int,
    metadata: dict[str, Any],
    previous_deltas: list[float],
    history: dict[str, Any],
) -> dict[str, Any]:
    one_percent_streak = int(history["one_percent_streak"])
    low_delta_streak = int(history["low_delta_streak"])
    same_delta_streak = int(history["same_delta_streak"])
    return {
        **metadata,
        "previous_delta_value": previous_deltas[-1],
        "previous_delta_bucket": _delta_bucket(previous_deltas[-1]),
        "one_percent_streak_count": one_percent_streak,
        "one_percent_streak_bucket": _streak_bucket(one_percent_streak),
        "low_delta_streak_count": low_delta_streak,
        "low_delta_streak_bucket": _streak_bucket(low_delta_streak),
        "same_delta_streak_count": same_delta_streak,
        "same_delta_streak_bucket": _streak_bucket(same_delta_streak),
        "previous_span_wall_time_bucket": _previous_span_wall_time_bucket(spans, index),
        "previous_call_duration_bucket": _previous_call_duration_bucket(spans, index),
    }


def _walk_forward_base_predictions(
    previous_deltas: list[float], history: dict[str, Any]
) -> dict[str, float]:
    recent3 = history["recent3"]
    recent10 = history["recent10"]
    rolling10_mode = float(history["rolling10_mode"])
    return {
        "constant_one_percent": 1.0,
        "previous_delta": previous_deltas[-1],
        "rolling3_mean_delta": sum(recent3) / len(recent3),
        "rolling10_mean_delta": sum(recent10) / len(recent10),
        "rolling10_median_delta": float(median(recent10)),
        "rolling10_mode_delta": rolling10_mode,
        "hybrid_streak_regime": float(history["hybrid_streak"]),
        "one_percent_regime_grace": float(history["one_percent_grace"]),
        "adaptive_low_delta_mode": _mode_when(
            bool(history["rolling10_low_share"] >= 0.8),
            mode=rolling10_mode,
            fallback=previous_deltas[-1],
        ),
        "adaptive_stable_mode": _mode_when(
            bool(history["rolling10_stddev"] <= 1.0),
            mode=rolling10_mode,
            fallback=previous_deltas[-1],
        ),
    }


def _mode_when(condition: bool, *, mode: float, fallback: float) -> float:
    if condition:
        return mode
    return fallback


def _add_state_bucket_predictions(
    *,
    predictions: dict[str, float],
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    fallback_prediction: float,
) -> dict[str, Any]:
    state_predictions, state_prediction_details = _state_bucket_predictions(
        previous_state_rows,
        state,
        fallback_prediction=fallback_prediction,
    )
    predictions.update(state_predictions)
    return state_prediction_details


def _walk_forward_transition_predictions(
    *,
    predictions: dict[str, float],
    transition_risks: dict[str, Any],
    transition_risk_details: dict[str, Any],
    transition_gate_absolute_error_sums: dict[float, float],
    training_count: int,
) -> tuple[dict[str, float], dict[str, Any]]:
    history_state_prediction = _number(predictions.get("empirical_history_state_mode"))
    continuation_prediction = _number(predictions.get("one_percent_regime_grace"))
    history_state_risk = _number(transition_risks.get("history_state_risk"))
    adaptive_threshold, adaptive_threshold_detail = _best_transition_delta_gate_threshold_from_sums(
        transition_gate_absolute_error_sums,
        training_count=training_count,
    )
    transition_predictions = _transition_delta_predictions(
        continuation_prediction=continuation_prediction,
        history_state_prediction=history_state_prediction,
        history_state_risk=history_state_risk,
        adaptive_threshold=adaptive_threshold,
    )
    transition_details = _transition_prediction_details(
        history_state_risk=history_state_risk,
        adaptive_threshold=adaptive_threshold,
        adaptive_threshold_detail=adaptive_threshold_detail,
        transition_risk_details=transition_risk_details,
    )
    return transition_predictions, transition_details


def _transition_delta_predictions(
    *,
    continuation_prediction: float,
    history_state_prediction: float,
    history_state_risk: float,
    adaptive_threshold: float,
) -> dict[str, float]:
    return {
        "transition_gated_history_state_mode": _risk_gated_transition_delta_prediction(
            continuation_prediction=continuation_prediction,
            alternate_prediction=history_state_prediction,
            risk=history_state_risk,
            threshold=TRANSITION_DELTA_RISK_GATE_THRESHOLD,
        ),
        "transition_weighted_history_state_mode": continuation_prediction
        + history_state_risk * (history_state_prediction - continuation_prediction),
        "adaptive_mae_transition_gate_history_state_mode": (
            _risk_gated_transition_delta_prediction(
                continuation_prediction=continuation_prediction,
                alternate_prediction=history_state_prediction,
                risk=history_state_risk,
                threshold=adaptive_threshold,
            )
        ),
    }


def _transition_prediction_details(
    *,
    history_state_risk: float,
    adaptive_threshold: float,
    adaptive_threshold_detail: dict[str, Any],
    transition_risk_details: dict[str, Any],
) -> dict[str, Any]:
    history_state_risk_detail = transition_risk_details.get("history_state_risk") or {}
    return {
        "transition_gated_history_state_mode": {
            "source": _gate_source(
                risk=history_state_risk,
                threshold=TRANSITION_DELTA_RISK_GATE_THRESHOLD,
                gated_source="transition_gate_history_state_mode",
                continuation_source="transition_gate_continuation",
            ),
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
            "source": _gate_source(
                risk=history_state_risk,
                threshold=adaptive_threshold,
                gated_source="adaptive_transition_gate_history_state_mode",
                continuation_source="adaptive_transition_gate_continuation",
            ),
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


def _gate_source(
    *, risk: float, threshold: float, gated_source: str, continuation_source: str
) -> str:
    if risk >= threshold:
        return gated_source
    return continuation_source
