"""Core boundary-delta prediction primitives."""

from __future__ import annotations

import math
from typing import Any

from codex_usage_tracker.usage_drain.state_buckets import STATE_BUCKET_MIN_SUPPORT
from codex_usage_tracker.usage_drain.state_diagnostics import (
    state_signature as _state_signature,
)
from codex_usage_tracker.usage_drain.transition_gates import RISK_GATE_THRESHOLDS
from codex_usage_tracker.usage_drain.utils import number as _number
from codex_usage_tracker.usage_drain.utils import rounded as _rounded

BOUNDARY_RISK_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "previous_label_risk": (("previous_label",),),
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
