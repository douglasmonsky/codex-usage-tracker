"""Boundary-delta walk-forward prediction helpers."""

from __future__ import annotations

import math
from typing import Any

from codex_usage_tracker.usage_drain_state_buckets import (
    STATE_BUCKET_MIN_SUPPORT,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_prediction as _state_bucket_prediction,
)
from codex_usage_tracker.usage_drain_state_diagnostics import (
    state_signature as _state_signature,
)
from codex_usage_tracker.usage_drain_transition_gates import RISK_GATE_THRESHOLDS
from codex_usage_tracker.usage_drain_utils import (
    number as _number,
)
from codex_usage_tracker.usage_drain_utils import (
    rounded as _rounded,
)
from codex_usage_tracker.usage_drain_utils import (
    value_mode as _value_mode,
)

BOUNDARY_RISK_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "previous_label_risk": (
        ("previous_label",),
    ),
    "segment_age_risk": (
        ("previous_segment_position_bucket",),
        ("previous_segment_wall_time_bucket",),
    ),
    "label_segment_age_risk": (
        ("previous_label", "previous_segment_position_bucket"),
        ("previous_label",),
    ),
    "reset_segment_age_risk": (
        ("previous_label", "previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket",),
    ),
    "calendar_segment_age_risk": (
        ("previous_label", "previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket",),
    ),
}
BOUNDARY_DELTA_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "segment_age_mode": (
        ("previous_segment_position_bucket",),
        ("previous_segment_wall_time_bucket",),
    ),
    "label_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket"),
        ("previous_label",),
    ),
    "reset_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket",),
    ),
    "calendar_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket",),
    ),
}
BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "boundary_conditioned_label_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket"),
        ("previous_label",),
        ("previous_segment_position_bucket",),
    ),
}
BOUNDARY_DELTA_RISK_GATE_THRESHOLD = 0.5
BOUNDARY_DELTA_RISK_GATE_THRESHOLDS = RISK_GATE_THRESHOLDS


def boundary_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.get("is_boundary")) / len(rows)




def state_bucket_boundary_risk(
    previous_rows: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    signatures: tuple[tuple[str, ...], ...],
    fallback_rate: float,
) -> tuple[float, dict[str, Any]]:
    for signature in signatures:
        matches = [
            previous
            for previous in previous_rows
            if _state_signature(previous, signature) == _state_signature(row, signature)
        ]
        if len(matches) < STATE_BUCKET_MIN_SUPPORT:
            continue
        risk = boundary_rate(matches)
        return risk, {
            "source": "matched_boundary_state",
            "signature": list(signature),
            "support": len(matches),
            "risk": _rounded(risk),
        }
    return fallback_rate, {
        "source": "fallback_prior_rate",
        "signature": [],
        "support": 0,
        "risk": _rounded(fallback_rate),
    }
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
        previous_delta = _number(row.get("previous_delta_percent"))
        prior_boundary_rate = boundary_rate(previous_rows)
        if previous_state_rows:
            prior_values = [
                _number(previous.get("actual")) for previous in previous_state_rows
            ]
            prior_mode = _value_mode(prior_values)
            prior_mode_detail = {
                "source": "all_prior_delta_mode",
                "signature": [],
                "support": len(previous_state_rows),
                "matched_mode": _rounded(prior_mode),
            }
        else:
            prior_mode = previous_delta
            prior_mode_detail = {
                "source": "fallback_previous_delta",
                "signature": [],
                "support": 0,
                "matched_mode": None,
            }
        predictions = {
            "previous_delta": previous_delta,
            "prior_mode_delta": prior_mode,
        }
        details = {
            "previous_delta": {
                "source": "previous_delta",
                "signature": [],
                "support": 1,
                "matched_mode": _rounded(previous_delta),
            },
            "prior_mode_delta": prior_mode_detail,
        }
        for model_name, signatures in BOUNDARY_DELTA_MODEL_SIGNATURES.items():
            prediction, detail = _state_bucket_prediction(
                previous_state_rows,
                row,
                signatures=signatures,
                fallback_prediction=previous_delta,
            )
            predictions[model_name] = prediction
            details[model_name] = detail
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
        label_segment_age_prediction = _number(predictions.get("label_segment_age_mode"))
        boundary_conditioned_prediction = _number(
            predictions.get("boundary_conditioned_label_segment_age_mode")
        )
        label_segment_age_risk, label_segment_age_risk_detail = (
            state_bucket_boundary_risk(
                previous_rows,
                row,
                signatures=BOUNDARY_RISK_MODEL_SIGNATURES["label_segment_age_risk"],
                fallback_rate=prior_boundary_rate,
            )
        )
        risk_gated_prediction = (
            label_segment_age_prediction
            if label_segment_age_risk >= BOUNDARY_DELTA_RISK_GATE_THRESHOLD
            else previous_delta
        )
        risk_weighted_prediction = previous_delta + (
            label_segment_age_risk * (label_segment_age_prediction - previous_delta)
        )
        risk_weighted_boundary_conditioned_prediction = previous_delta + (
            label_segment_age_risk * (boundary_conditioned_prediction - previous_delta)
        )
        adaptive_mae_threshold, adaptive_mae_threshold_detail = (
            best_boundary_delta_gate_threshold_from_sums(
                threshold_absolute_error_sums,
                training_count=threshold_training_count,
                metric="mae",
            )
        )
        adaptive_rmse_threshold, adaptive_rmse_threshold_detail = (
            best_boundary_delta_gate_threshold_from_sums(
                threshold_squared_error_sums,
                training_count=threshold_training_count,
                metric="rmse",
            )
        )
        adaptive_mae_prediction = risk_gated_boundary_delta_prediction(
            previous_delta=previous_delta,
            alternate_prediction=label_segment_age_prediction,
            risk=label_segment_age_risk,
            threshold=adaptive_mae_threshold,
        )
        adaptive_rmse_prediction = risk_gated_boundary_delta_prediction(
            previous_delta=previous_delta,
            alternate_prediction=label_segment_age_prediction,
            risk=label_segment_age_risk,
            threshold=adaptive_rmse_threshold,
        )
        predictions["risk_gated_label_segment_age_mode"] = risk_gated_prediction
        predictions["risk_weighted_label_segment_age_mode"] = risk_weighted_prediction
        predictions["risk_weighted_boundary_conditioned_mode"] = (
            risk_weighted_boundary_conditioned_prediction
        )
        predictions["adaptive_mae_gate_label_segment_age_mode"] = (
            adaptive_mae_prediction
        )
        predictions["adaptive_rmse_gate_label_segment_age_mode"] = (
            adaptive_rmse_prediction
        )
        details["risk_gated_label_segment_age_mode"] = {
            "source": "risk_gate_override"
            if label_segment_age_risk >= BOUNDARY_DELTA_RISK_GATE_THRESHOLD
            else "risk_gate_previous_delta",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        details["risk_weighted_label_segment_age_mode"] = {
            "source": "risk_weighted_blend",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        details["risk_weighted_boundary_conditioned_mode"] = {
            "source": "risk_weighted_boundary_conditioned_blend",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(boundary_conditioned_prediction),
        }
        details["adaptive_mae_gate_label_segment_age_mode"] = {
            "source": "adaptive_risk_gate_override"
            if label_segment_age_risk >= adaptive_mae_threshold
            else "adaptive_risk_gate_previous_delta",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": adaptive_mae_threshold,
            "training_metric": adaptive_mae_threshold_detail.get("metric"),
            "training_error": adaptive_mae_threshold_detail.get("error"),
            "training_support": adaptive_mae_threshold_detail.get("support"),
            "threshold_source": adaptive_mae_threshold_detail.get("source"),
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        details["adaptive_rmse_gate_label_segment_age_mode"] = {
            "source": "adaptive_risk_gate_override"
            if label_segment_age_risk >= adaptive_rmse_threshold
            else "adaptive_risk_gate_previous_delta",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": adaptive_rmse_threshold,
            "training_metric": adaptive_rmse_threshold_detail.get("metric"),
            "training_error": adaptive_rmse_threshold_detail.get("error"),
            "training_support": adaptive_rmse_threshold_detail.get("support"),
            "threshold_source": adaptive_rmse_threshold_detail.get("source"),
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        output_row = {
            **row,
            "boundary_delta_predictions": predictions,
            "boundary_delta_prediction_details": details,
            "prediction_details": details,
        }
        output.append(output_row)
        update_boundary_delta_gate_threshold_sums(
            threshold_absolute_error_sums,
            threshold_squared_error_sums,
            row=output_row,
        )
        previous_state_rows.append(
            {
                "actual": _number(row.get("delta_percent")),
                "state": row,
            }
        )
        if row.get("is_boundary"):
            previous_boundary_state_rows.append(
                {
                    "actual": _number(row.get("delta_percent")),
                    "state": row,
                }
            )
        previous_rows.append(row)
    return output


def risk_gated_boundary_delta_prediction(
    *,
    previous_delta: float,
    alternate_prediction: float,
    risk: float,
    threshold: float,
) -> float:
    if risk >= threshold:
        return alternate_prediction
    return previous_delta


def best_boundary_delta_gate_threshold_from_sums(
    error_sums: dict[float, float],
    *,
    training_count: int,
    metric: str,
) -> tuple[float, dict[str, Any]]:
    if training_count < STATE_BUCKET_MIN_SUPPORT:
        return BOUNDARY_DELTA_RISK_GATE_THRESHOLD, {
            "source": "fallback_fixed_threshold",
            "metric": metric,
            "support": training_count,
            "error": None,
        }
    candidates: list[tuple[float, float]] = []
    for threshold, error_sum in error_sums.items():
        if metric == "rmse":
            error_value = math.sqrt(error_sum / training_count)
        else:
            error_value = error_sum / training_count
        candidates.append((threshold, error_value))
    threshold, error_value = min(
        candidates,
        key=lambda item: (
            item[1],
            abs(item[0] - BOUNDARY_DELTA_RISK_GATE_THRESHOLD),
            item[0],
        ),
    )
    return threshold, {
        "source": "prior_best_threshold",
        "metric": metric,
        "support": training_count,
        "error": _rounded(error_value),
    }


def update_boundary_delta_gate_threshold_sums(
    absolute_error_sums: dict[float, float],
    squared_error_sums: dict[float, float],
    *,
    row: dict[str, Any],
) -> None:
    actual = _number(row.get("delta_percent"))
    previous_delta = _number(row.get("previous_delta_percent"))
    alternate_prediction = _number(
        (row.get("boundary_delta_predictions") or {}).get("label_segment_age_mode")
    )
    detail = (row.get("boundary_delta_prediction_details") or {}).get(
        "risk_gated_label_segment_age_mode"
    ) or {}
    risk = _number(detail.get("risk"))
    for threshold in BOUNDARY_DELTA_RISK_GATE_THRESHOLDS:
        prediction = risk_gated_boundary_delta_prediction(
            previous_delta=previous_delta,
            alternate_prediction=alternate_prediction,
            risk=risk,
            threshold=threshold,
        )
        error = prediction - actual
        absolute_error_sums[threshold] += abs(error)
        squared_error_sums[threshold] += error * error
