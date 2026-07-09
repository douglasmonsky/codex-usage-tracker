"""Transition gate helpers for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.state_buckets import STATE_BUCKET_MIN_SUPPORT
from codex_usage_tracker.usage_drain.utils import number, rounded

RISK_GATE_THRESHOLDS = (
    0.0,
    0.05,
    0.1,
    0.15,
    0.2,
    0.25,
    0.3,
    0.35,
    0.4,
    0.45,
    0.5,
    0.55,
    0.6,
    0.65,
    0.7,
    0.75,
    0.8,
    0.85,
    0.9,
    0.95,
    1.0,
)

TRANSITION_DELTA_RISK_GATE_THRESHOLD = 0.5

TRANSITION_DELTA_RISK_GATE_THRESHOLDS = RISK_GATE_THRESHOLDS


def risk_gated_transition_delta_prediction(
    *,
    continuation_prediction: float,
    alternate_prediction: float,
    risk: float,
    threshold: float,
) -> float:
    if risk >= threshold:
        return alternate_prediction
    return continuation_prediction


def best_transition_delta_gate_threshold_from_sums(
    error_sums: dict[float, float],
    *,
    training_count: int,
) -> tuple[float, dict[str, Any]]:
    if training_count < STATE_BUCKET_MIN_SUPPORT:
        return TRANSITION_DELTA_RISK_GATE_THRESHOLD, {
            "source": "fallback_fixed_threshold",
            "metric": "mae",
            "support": training_count,
            "error": None,
        }
    candidates = [
        (threshold, error_sum / training_count) for threshold, error_sum in error_sums.items()
    ]
    threshold, error_value = min(
        candidates,
        key=lambda item: (
            item[1],
            abs(item[0] - TRANSITION_DELTA_RISK_GATE_THRESHOLD),
            item[0],
        ),
    )
    return threshold, {
        "source": "prior_best_threshold",
        "metric": "mae",
        "support": training_count,
        "error": rounded(error_value),
    }


def update_transition_delta_gate_threshold_sums(
    absolute_error_sums: dict[float, float],
    *,
    row: dict[str, Any],
) -> None:
    actual = number(row.get("actual"))
    predictions = row.get("predictions") or {}
    continuation_prediction = number(predictions.get("one_percent_regime_grace"))
    alternate_prediction = number(predictions.get("empirical_history_state_mode"))
    details = row.get("prediction_details") or {}
    gate_detail = details.get("transition_gated_history_state_mode") or {}
    risk = number(gate_detail.get("risk"))
    for threshold in TRANSITION_DELTA_RISK_GATE_THRESHOLDS:
        prediction = risk_gated_transition_delta_prediction(
            continuation_prediction=continuation_prediction,
            alternate_prediction=alternate_prediction,
            risk=risk,
            threshold=threshold,
        )
        absolute_error_sums[threshold] += abs(prediction - actual)


def transition_delta_gate_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = _transition_delta_gate_details(rows, model_name)
    if not details:
        return _empty_transition_delta_gate_diagnostics()

    summary = _transition_delta_gate_detail_summary(details)
    return {
        "n": len(details),
        "override_share": _override_share(summary["source_counts"], len(details)),
        "mean_risk": _mean_or_none(summary["risks"]),
        "mean_threshold": _mean_or_none(summary["thresholds"]),
        "source_counts": _transition_delta_gate_source_rows(
            summary["source_counts"], detail_count=len(details)
        ),
    }


def _transition_delta_gate_details(
    rows: list[dict[str, Any]], model_name: str
) -> list[dict[str, Any]]:
    return [(row.get("prediction_details") or {}).get(model_name) or {} for row in rows]


def _empty_transition_delta_gate_diagnostics() -> dict[str, Any]:
    return {
        "n": 0,
        "override_share": None,
        "mean_risk": None,
        "mean_threshold": None,
        "source_counts": [],
    }


def _transition_delta_gate_detail_summary(
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    source_counts: dict[str, int] = {}
    risks: list[float] = []
    thresholds: list[float] = []
    for detail in details:
        source = str(detail.get("source") or "missing")
        source_counts[source] = source_counts.get(source, 0) + 1
        risks.append(number(detail.get("risk")))
        if detail.get("risk_threshold") is not None:
            thresholds.append(number(detail.get("risk_threshold")))
    return {
        "source_counts": source_counts,
        "risks": risks,
        "thresholds": thresholds,
    }


def _override_share(source_counts: dict[str, int], detail_count: int) -> float | None:
    override_count = sum(
        count for source, count in source_counts.items() if source.endswith("_history_state_mode")
    )
    return rounded(override_count / detail_count)


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return rounded(sum(values) / len(values))


def _transition_delta_gate_source_rows(
    source_counts: dict[str, int], *, detail_count: int
) -> list[dict[str, Any]]:
    return [
        {
            "source": source,
            "count": count,
            "share": rounded(count / detail_count),
        }
        for source, count in sorted(source_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
