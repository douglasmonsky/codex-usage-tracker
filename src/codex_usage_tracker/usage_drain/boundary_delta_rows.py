"""Boundary-delta walk-forward row construction."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.boundary_delta_core import (
    BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES,
    BOUNDARY_DELTA_MODEL_SIGNATURES,
    BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
    BOUNDARY_DELTA_RISK_GATE_THRESHOLDS,
    BOUNDARY_RISK_MODEL_SIGNATURES,
    best_boundary_delta_gate_threshold_from_sums,
    boundary_rate,
    risk_gated_boundary_delta_prediction,
    state_bucket_boundary_risk,
    update_boundary_delta_gate_threshold_sums,
)
from codex_usage_tracker.usage_drain.state_buckets import (
    state_bucket_prediction as _state_bucket_prediction,
)
from codex_usage_tracker.usage_drain.utils import number as _number
from codex_usage_tracker.usage_drain.utils import rounded as _rounded
from codex_usage_tracker.usage_drain.utils import value_mode as _value_mode


def _prior_delta_mode_detail(
    previous_state_rows: list[dict[str, Any]],
    previous_delta: float,
) -> tuple[float, dict[str, Any]]:
    if not previous_state_rows:
        return previous_delta, {
            "source": "fallback_previous_delta",
            "signature": [],
            "support": 0,
            "matched_mode": None,
        }

    prior_values = [_number(previous.get("actual")) for previous in previous_state_rows]
    prior_mode = _value_mode(prior_values)
    return prior_mode, {
        "source": "all_prior_delta_mode",
        "signature": [],
        "support": len(previous_state_rows),
        "matched_mode": _rounded(prior_mode),
    }


def _initial_boundary_delta_predictions(
    row: dict[str, Any],
    previous_state_rows: list[dict[str, Any]],
) -> tuple[float, dict[str, float], dict[str, dict[str, Any]]]:
    previous_delta = _number(row.get("previous_delta_percent"))
    prior_mode, prior_mode_detail = _prior_delta_mode_detail(
        previous_state_rows,
        previous_delta,
    )
    return (
        previous_delta,
        {
            "previous_delta": previous_delta,
            "prior_mode_delta": prior_mode,
        },
        {
            "previous_delta": {
                "source": "previous_delta",
                "signature": [],
                "support": 1,
                "matched_mode": _rounded(previous_delta),
            },
            "prior_mode_delta": prior_mode_detail,
        },
    )


def _add_state_delta_predictions(
    predictions: dict[str, float],
    details: dict[str, dict[str, Any]],
    *,
    previous_state_rows: list[dict[str, Any]],
    row: dict[str, Any],
    previous_delta: float,
) -> None:
    for model_name, signatures in BOUNDARY_DELTA_MODEL_SIGNATURES.items():
        prediction, detail = _state_bucket_prediction(
            previous_state_rows,
            row,
            signatures=signatures,
            fallback_prediction=previous_delta,
        )
        predictions[model_name] = prediction
        details[model_name] = detail


def _add_boundary_conditioned_delta_predictions(
    predictions: dict[str, float],
    details: dict[str, dict[str, Any]],
    *,
    previous_boundary_state_rows: list[dict[str, Any]],
    row: dict[str, Any],
    previous_delta: float,
) -> None:
    for model_name, signatures in BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES.items():
        prediction, detail = _state_bucket_prediction(
            previous_boundary_state_rows,
            row,
            signatures=signatures,
            fallback_prediction=previous_delta,
        )
        predictions[model_name] = prediction
        details[model_name] = {
            **detail,
            "conditioned_on": "prior_boundary_rows",
        }


def _risk_detail_support(risk_detail: dict[str, Any]) -> int:
    return int(risk_detail.get("support") or 0)


def _risk_weighted_prediction(
    *,
    previous_delta: float,
    alternate_prediction: float,
    risk: float,
) -> float:
    return previous_delta + (risk * (alternate_prediction - previous_delta))


def _risk_gate_detail(
    *,
    source: str,
    risk: float,
    risk_detail: dict[str, Any],
    matched_mode: float,
) -> dict[str, Any]:
    return {
        "source": source,
        "risk_model": "label_segment_age_risk",
        "risk": _rounded(risk),
        "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
        "risk_detail": risk_detail,
        "support": _risk_detail_support(risk_detail),
        "matched_mode": _rounded(matched_mode),
    }


def _adaptive_risk_gate_detail(
    *,
    source: str,
    risk: float,
    risk_threshold: float,
    threshold_detail: dict[str, Any],
    risk_detail: dict[str, Any],
    matched_mode: float,
) -> dict[str, Any]:
    return {
        "source": source,
        "risk_model": "label_segment_age_risk",
        "risk": _rounded(risk),
        "risk_threshold": risk_threshold,
        "training_metric": threshold_detail.get("metric"),
        "training_error": threshold_detail.get("error"),
        "training_support": threshold_detail.get("support"),
        "threshold_source": threshold_detail.get("source"),
        "risk_detail": risk_detail,
        "support": _risk_detail_support(risk_detail),
        "matched_mode": _rounded(matched_mode),
    }


def _adaptive_boundary_delta_thresholds(
    *,
    threshold_absolute_error_sums: dict[float, float],
    threshold_squared_error_sums: dict[float, float],
    training_count: int,
) -> tuple[tuple[float, dict[str, Any]], tuple[float, dict[str, Any]]]:
    return (
        best_boundary_delta_gate_threshold_from_sums(
            threshold_absolute_error_sums,
            training_count=training_count,
            metric="mae",
        ),
        best_boundary_delta_gate_threshold_from_sums(
            threshold_squared_error_sums,
            training_count=training_count,
            metric="rmse",
        ),
    )


def _add_risk_adjusted_delta_predictions(
    predictions: dict[str, float],
    details: dict[str, dict[str, Any]],
    *,
    previous_rows: list[dict[str, Any]],
    row: dict[str, Any],
    previous_delta: float,
    threshold_training_count: int,
    threshold_absolute_error_sums: dict[float, float],
    threshold_squared_error_sums: dict[float, float],
) -> None:
    label_prediction = _number(predictions.get("label_segment_age_mode"))
    boundary_conditioned_prediction = _number(
        predictions.get("boundary_conditioned_label_segment_age_mode")
    )
    risk, risk_detail = state_bucket_boundary_risk(
        previous_rows,
        row,
        signatures=BOUNDARY_RISK_MODEL_SIGNATURES["label_segment_age_risk"],
        fallback_rate=boundary_rate(previous_rows),
    )
    (mae_threshold, mae_detail), (rmse_threshold, rmse_detail) = (
        _adaptive_boundary_delta_thresholds(
            threshold_absolute_error_sums=threshold_absolute_error_sums,
            threshold_squared_error_sums=threshold_squared_error_sums,
            training_count=threshold_training_count,
        )
    )
    predictions["risk_gated_label_segment_age_mode"] = risk_gated_boundary_delta_prediction(
        previous_delta=previous_delta,
        alternate_prediction=label_prediction,
        risk=risk,
        threshold=BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
    )
    predictions["risk_weighted_label_segment_age_mode"] = _risk_weighted_prediction(
        previous_delta=previous_delta,
        alternate_prediction=label_prediction,
        risk=risk,
    )
    predictions["risk_weighted_boundary_conditioned_mode"] = _risk_weighted_prediction(
        previous_delta=previous_delta,
        alternate_prediction=boundary_conditioned_prediction,
        risk=risk,
    )
    predictions["adaptive_mae_gate_label_segment_age_mode"] = risk_gated_boundary_delta_prediction(
        previous_delta=previous_delta,
        alternate_prediction=label_prediction,
        risk=risk,
        threshold=mae_threshold,
    )
    predictions["adaptive_rmse_gate_label_segment_age_mode"] = risk_gated_boundary_delta_prediction(
        previous_delta=previous_delta,
        alternate_prediction=label_prediction,
        risk=risk,
        threshold=rmse_threshold,
    )
    details["risk_gated_label_segment_age_mode"] = _risk_gate_detail(
        source="risk_gate_override"
        if risk >= BOUNDARY_DELTA_RISK_GATE_THRESHOLD
        else "risk_gate_previous_delta",
        risk=risk,
        risk_detail=risk_detail,
        matched_mode=label_prediction,
    )
    details["risk_weighted_label_segment_age_mode"] = _risk_gate_detail(
        source="risk_weighted_blend",
        risk=risk,
        risk_detail=risk_detail,
        matched_mode=label_prediction,
    )
    details["risk_weighted_boundary_conditioned_mode"] = _risk_gate_detail(
        source="risk_weighted_boundary_conditioned_blend",
        risk=risk,
        risk_detail=risk_detail,
        matched_mode=boundary_conditioned_prediction,
    )
    details["adaptive_mae_gate_label_segment_age_mode"] = _adaptive_risk_gate_detail(
        source="adaptive_risk_gate_override"
        if risk >= mae_threshold
        else "adaptive_risk_gate_previous_delta",
        risk=risk,
        risk_threshold=mae_threshold,
        threshold_detail=mae_detail,
        risk_detail=risk_detail,
        matched_mode=label_prediction,
    )
    details["adaptive_rmse_gate_label_segment_age_mode"] = _adaptive_risk_gate_detail(
        source="adaptive_risk_gate_override"
        if risk >= rmse_threshold
        else "adaptive_risk_gate_previous_delta",
        risk=risk,
        risk_threshold=rmse_threshold,
        threshold_detail=rmse_detail,
        risk_detail=risk_detail,
        matched_mode=label_prediction,
    )


def _boundary_delta_output_row(
    row: dict[str, Any],
    *,
    predictions: dict[str, float],
    details: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        **row,
        "boundary_delta_predictions": predictions,
        "boundary_delta_prediction_details": details,
        "prediction_details": details,
    }


def _append_boundary_delta_history(
    *,
    previous_rows: list[dict[str, Any]],
    previous_state_rows: list[dict[str, Any]],
    previous_boundary_state_rows: list[dict[str, Any]],
    row: dict[str, Any],
) -> None:
    state_row = {
        "actual": _number(row.get("delta_percent")),
        "state": row,
    }
    previous_state_rows.append(state_row)
    if row.get("is_boundary"):
        previous_boundary_state_rows.append(state_row)
    previous_rows.append(row)


def boundary_walk_forward_delta_prediction_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_rows: list[dict[str, Any]] = []
    previous_state_rows: list[dict[str, Any]] = []
    previous_boundary_state_rows: list[dict[str, Any]] = []
    threshold_absolute_error_sums = {
        threshold: 0.0 for threshold in BOUNDARY_DELTA_RISK_GATE_THRESHOLDS
    }
    threshold_squared_error_sums = {
        threshold: 0.0 for threshold in BOUNDARY_DELTA_RISK_GATE_THRESHOLDS
    }
    for threshold_training_count, row in enumerate(rows):
        previous_delta, predictions, details = _initial_boundary_delta_predictions(
            row,
            previous_state_rows,
        )
        _add_state_delta_predictions(
            predictions,
            details,
            previous_state_rows=previous_state_rows,
            row=row,
            previous_delta=previous_delta,
        )
        _add_boundary_conditioned_delta_predictions(
            predictions,
            details,
            previous_boundary_state_rows=previous_boundary_state_rows,
            row=row,
            previous_delta=previous_delta,
        )
        _add_risk_adjusted_delta_predictions(
            predictions,
            details,
            previous_rows=previous_rows,
            row=row,
            previous_delta=previous_delta,
            threshold_training_count=threshold_training_count,
            threshold_absolute_error_sums=threshold_absolute_error_sums,
            threshold_squared_error_sums=threshold_squared_error_sums,
        )
        output_row = _boundary_delta_output_row(
            row,
            predictions=predictions,
            details=details,
        )
        output.append(output_row)
        update_boundary_delta_gate_threshold_sums(
            threshold_absolute_error_sums,
            threshold_squared_error_sums,
            row=output_row,
        )
        _append_boundary_delta_history(
            previous_rows=previous_rows,
            previous_state_rows=previous_state_rows,
            previous_boundary_state_rows=previous_boundary_state_rows,
            row=row,
        )
    return output
