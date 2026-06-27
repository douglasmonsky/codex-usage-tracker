"""State bucket prediction helpers for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain_feature_history import is_one_percent_delta
from codex_usage_tracker.usage_drain_state_diagnostics import state_signature
from codex_usage_tracker.usage_drain_utils import number, rounded, value_mode

STATE_BUCKET_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "empirical_history_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "same_delta_streak_bucket",
            "low_delta_streak_bucket",
        ),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
    "empirical_calendar_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "day_of_week",
            "hour_bucket",
        ),
        ("previous_delta_bucket", "day_of_week", "hour_bucket"),
        ("day_of_week", "hour_bucket"),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
    "empirical_reset_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "baseline_used_bucket",
            "window_elapsed_bucket",
            "reset_remaining_bucket",
        ),
        ("previous_delta_bucket", "window_elapsed_bucket", "reset_remaining_bucket"),
        ("previous_delta_bucket", "baseline_used_bucket"),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
    "empirical_previous_work_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "previous_span_wall_time_bucket",
            "previous_call_duration_bucket",
        ),
        ("previous_delta_bucket", "previous_span_wall_time_bucket"),
        ("previous_delta_bucket", "previous_call_duration_bucket"),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
}

STATE_BUCKET_MIN_SUPPORT = 2

TRANSITION_RISK_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "history_state_risk": STATE_BUCKET_MODEL_SIGNATURES[
        "empirical_history_state_mode"
    ],
    "calendar_state_risk": STATE_BUCKET_MODEL_SIGNATURES[
        "empirical_calendar_state_mode"
    ],
    "reset_state_risk": STATE_BUCKET_MODEL_SIGNATURES["empirical_reset_state_mode"],
    "previous_work_state_risk": STATE_BUCKET_MODEL_SIGNATURES[
        "empirical_previous_work_state_mode"
    ],
}

def state_bucket_predictions(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    fallback_prediction: float,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    predictions: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}
    for model_name, signatures in STATE_BUCKET_MODEL_SIGNATURES.items():
        prediction, detail = state_bucket_prediction(
            previous_state_rows,
            state,
            signatures=signatures,
            fallback_prediction=fallback_prediction,
        )
        predictions[model_name] = prediction
        details[model_name] = detail
    return predictions, details

def state_bucket_transition_risk(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    signatures: tuple[tuple[str, ...], ...],
    fallback_rate: float,
) -> tuple[float, dict[str, Any]]:
    for signature in signatures:
        matches = [
            row
            for row in previous_state_rows
            if state_signature(row.get("state", {}), signature)
            == state_signature(state, signature)
        ]
        if len(matches) < STATE_BUCKET_MIN_SUPPORT:
            continue
        risk = transition_rate(matches)
        return risk, {
            "source": "matched_state",
            "signature": list(signature),
            "support": len(matches),
            "risk": rounded(risk),
        }
    return fallback_rate, {
        "source": "fallback_prior_rate",
        "signature": [],
        "support": 0,
        "risk": rounded(fallback_rate),
    }

def transition_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if not is_one_percent_delta(number(row.get("actual")))) / len(rows)

def state_bucket_prediction(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    signatures: tuple[tuple[str, ...], ...],
    fallback_prediction: float,
) -> tuple[float, dict[str, Any]]:
    for signature in signatures:
        matches = [
            row
            for row in previous_state_rows
            if state_signature(row.get("state", {}), signature)
            == state_signature(state, signature)
        ]
        if len(matches) < STATE_BUCKET_MIN_SUPPORT:
            continue
        actual_values = [number(row.get("actual")) for row in matches]
        prediction = value_mode(actual_values)
        return prediction, {
            "source": "matched_state",
            "signature": list(signature),
            "support": len(matches),
            "matched_mode": rounded(prediction),
        }
    return fallback_prediction, {
        "source": "fallback_previous_delta",
        "signature": [],
        "support": 0,
        "matched_mode": None,
    }

def state_bucket_model_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("prediction_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "n": 0,
            "matched_state_share": None,
            "mean_support": None,
            "top_signatures": [],
        }
    matched = [detail for detail in details if detail.get("source") == "matched_state"]
    signature_counts: dict[str, int] = {}
    for detail in matched:
        label = ",".join(str(item) for item in detail.get("signature") or [])
        signature_counts[label or "missing"] = signature_counts.get(label or "missing", 0) + 1
    top_signatures = [
        {"signature": signature, "count": count, "share": rounded(count / len(details))}
        for signature, count in sorted(
            signature_counts.items(), key=lambda item: (-item[1], item[0])
        )[:8]
    ]
    return {
        "n": len(details),
        "matched_state_share": rounded(len(matched) / len(details)),
        "mean_support": rounded(
            sum(int(detail.get("support") or 0) for detail in matched) / len(matched)
            if matched
            else None
        ),
        "fallback_share": rounded((len(details) - len(matched)) / len(details)),
        "top_signatures": top_signatures,
    }

def transition_risk_detail_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("transition_risk_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "matched_state_share": None,
            "mean_support": None,
            "top_signatures": [],
        }
    matched = [detail for detail in details if detail.get("source") == "matched_state"]
    signature_counts: dict[str, int] = {}
    for detail in matched:
        label = ",".join(str(item) for item in detail.get("signature") or [])
        signature_counts[label or "missing"] = (
            signature_counts.get(label or "missing", 0) + 1
        )
    return {
        "matched_state_share": rounded(len(matched) / len(details)),
        "mean_support": rounded(
            sum(int(detail.get("support") or 0) for detail in matched) / len(matched)
            if matched
            else None
        ),
        "top_signatures": [
            {
                "signature": signature,
                "count": count,
                "share": rounded(count / len(details)),
            }
            for signature, count in sorted(
                signature_counts.items(), key=lambda item: (-item[1], item[0])
            )[:8]
        ],
    }
