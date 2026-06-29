"""Boundary-delta summary diagnostics for usage-drain modeling."""

from __future__ import annotations

import math
from typing import Any

from codex_usage_tracker import usage_drain_boundary_delta as boundary_delta
from codex_usage_tracker import usage_drain_boundary_scopes as boundary_scopes
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_regression import regression_metrics as _regression_metrics
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_model_diagnostics as _state_bucket_model_diagnostics,
)
from codex_usage_tracker.usage_drain_utils import number as _number
from codex_usage_tracker.usage_drain_utils import rounded as _rounded

BOUNDARY_RISK_SCOPE_STARTS = {
    "all_after_first": 1,
    "all_after_10": 10,
    "time_ordered_holdout_20": 0.8,
    "latest_500": -500,
    "latest_100": -100,
}
BOUNDARY_DELTA_RESIDUAL_MODELS = (
    "previous_delta",
    "risk_weighted_label_segment_age_mode",
    "risk_weighted_boundary_conditioned_mode",
    "adaptive_mae_gate_label_segment_age_mode",
)
BOUNDARY_DELTA_ERROR_CONTEXT_FIELDS = (
    "boundary_state",
    "transition",
    "previous_label",
    "current_label",
    "previous_segment_position_bucket",
    "previous_segment_wall_time_bucket",
    "window_elapsed_bucket",
    "reset_remaining_bucket",
    "day_of_week",
    "hour_bucket",
    "previous_span_wall_time_bucket",
    "previous_call_duration_bucket",
    "one_percent_streak_bucket",
    "same_delta_streak_bucket",
    "low_delta_streak_bucket",
)




def boundary_walk_forward_delta_prediction_summary(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    prediction_rows = boundary_delta.boundary_walk_forward_delta_prediction_rows(rows)
    return {
        "target": "next_visible_usage_delta_percent",
        "prediction_models": {
            "previous_delta": "Predicts the previous visible usage delta.",
            "prior_mode_delta": "Predicts the modal prior next-span delta.",
            "segment_age_mode": (
                "Uses the modal prior next-span delta from matching segment age."
            ),
            "label_segment_age_mode": (
                "Uses the modal prior next-span delta from matching previous label "
                "plus segment-position age."
            ),
            "reset_segment_age_mode": (
                "Uses the modal prior next-span delta from matching segment age "
                "plus reset-window context."
            ),
            "calendar_segment_age_mode": (
                "Uses the modal prior next-span delta from matching segment age "
                "plus day/hour context."
            ),
            "risk_gated_label_segment_age_mode": (
                "Uses previous delta unless previous-label plus segment-age boundary "
                "risk is at least 50%, then uses the matched label/segment-age mode."
            ),
            "risk_weighted_label_segment_age_mode": (
                "Blends previous delta with matched label/segment-age mode according "
                "to the prior boundary-risk estimate."
            ),
            "adaptive_mae_gate_label_segment_age_mode": (
                "Selects the prior-best boundary-risk threshold by MAE, then gates "
                "between previous delta and matched label/segment-age mode."
            ),
            "adaptive_rmse_gate_label_segment_age_mode": (
                "Selects the prior-best boundary-risk threshold by RMSE, then gates "
                "between previous delta and matched label/segment-age mode."
            ),
            "boundary_conditioned_label_segment_age_mode": (
                "Uses the modal prior next-span delta from matching prior boundary "
                "rows only."
            ),
            "risk_weighted_boundary_conditioned_mode": (
                "Blends previous delta with the boundary-conditioned mode according "
                "to the prior boundary-risk estimate."
            ),
        },
        "scopes": {
            scope_name: _boundary_delta_prediction_scope(
                prediction_rows,
                start_index=boundary_scopes.boundary_scope_start_index(rows, start),
            )
            for scope_name, start in BOUNDARY_RISK_SCOPE_STARTS.items()
        },
    }



def _boundary_delta_prediction_scope(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = _boundary_delta_scope_rows(rows, start_index=start_index)
    actual = _boundary_delta_actual_values(scope_rows)
    model_names = _boundary_delta_model_names(scope_rows)
    return {
        "start_index": start_index,
        "n": len(scope_rows),
        "actual": _value_distribution(actual),
        "models": _boundary_delta_scope_model_metrics(
            scope_rows,
            actual,
            model_names,
        ),
        "prediction_detail_diagnostics": _boundary_delta_prediction_details(
            scope_rows,
            model_names,
        ),
        "risk_gate_diagnostics": _boundary_delta_risk_gate_model_diagnostics(
            scope_rows,
            model_names,
        ),
        "residual_diagnostics": _boundary_delta_residual_model_diagnostics(
            scope_rows,
            model_names,
        ),
    }


def _boundary_delta_scope_rows(
    rows: list[dict[str, Any]], *, start_index: int
) -> list[dict[str, Any]]:
    return [row for row in rows if int(row["index"]) >= start_index]


def _boundary_delta_actual_values(rows: list[dict[str, Any]]) -> list[float]:
    return [_number(row.get("delta_percent")) for row in rows]


def _boundary_delta_scope_model_metrics(
    rows: list[dict[str, Any]],
    actual: list[float],
    model_names: list[str],
) -> dict[str, dict[str, Any]]:
    return {
        model_name: _regression_metrics(
            actual,
            [
                _number((row.get("boundary_delta_predictions") or {}).get(model_name))
                for row in rows
            ],
        )
        for model_name in model_names
    }


def _boundary_delta_prediction_details(
    rows: list[dict[str, Any]], model_names: list[str]
) -> dict[str, dict[str, Any]]:
    return {
        model_name: _state_bucket_model_diagnostics(rows, model_name)
        for model_name in model_names
        if model_name in boundary_delta.BOUNDARY_DELTA_MODEL_SIGNATURES
        or model_name in boundary_delta.BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES
    }


def _boundary_delta_risk_gate_model_diagnostics(
    rows: list[dict[str, Any]], model_names: list[str]
) -> dict[str, dict[str, Any]]:
    risk_gate_models = {
        "risk_gated_label_segment_age_mode",
        "risk_weighted_label_segment_age_mode",
        "risk_weighted_boundary_conditioned_mode",
        "adaptive_mae_gate_label_segment_age_mode",
        "adaptive_rmse_gate_label_segment_age_mode",
    }
    return {
        model_name: _boundary_delta_risk_gate_diagnostics(rows, model_name)
        for model_name in risk_gate_models
        if model_name in model_names
    }


def _boundary_delta_residual_model_diagnostics(
    rows: list[dict[str, Any]], model_names: list[str]
) -> dict[str, dict[str, Any]]:
    return {
        model_name: _boundary_delta_residual_diagnostics(rows, model_name)
        for model_name in BOUNDARY_DELTA_RESIDUAL_MODELS
        if model_name in model_names
    }


def _boundary_delta_model_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for name in row.get("boundary_delta_predictions") or {}:
            if name not in names:
                names.append(str(name))
    return names





def _boundary_delta_risk_gate_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("boundary_delta_prediction_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "n": 0,
            "override_share": None,
            "mean_risk": None,
            "mean_support": None,
            "mean_threshold": None,
            "source_counts": [],
        }
    source_counts: dict[str, int] = {}
    risks: list[float] = []
    supports: list[int] = []
    thresholds: list[float] = []
    for detail in details:
        source = str(detail.get("source") or "missing")
        source_counts[source] = source_counts.get(source, 0) + 1
        risks.append(_number(detail.get("risk")))
        supports.append(int(detail.get("support") or 0))
        thresholds.append(_number(detail.get("risk_threshold")))
    override_count = sum(
        count for source, count in source_counts.items() if source.endswith("_override")
    )
    return {
        "n": len(details),
        "override_share": _rounded(override_count / len(details)),
        "mean_risk": _rounded(sum(risks) / len(risks)),
        "mean_support": _rounded(sum(supports) / len(supports)),
        "mean_threshold": _rounded(sum(thresholds) / len(thresholds)),
        "source_counts": [
            {
                "source": source,
                "count": count,
                "share": _rounded(count / len(details)),
            }
            for source, count in sorted(
                source_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def _boundary_delta_residual_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for row in rows:
        predicted = _number((row.get("boundary_delta_predictions") or {}).get(model_name))
        actual = _number(row.get("delta_percent"))
        error = predicted - actual
        errors.append(
            {
                "index": int(row["index"]),
                "actual": actual,
                "predicted": predicted,
                "previous_delta_percent": _number(row.get("previous_delta_percent")),
                "error": error,
                "abs_error": abs(error),
                "metadata": row,
            }
        )
    if not errors:
        return {
            "n": 0,
            "total_abs_error": None,
            "exact_match_share": None,
            "within_one_point_share": None,
            "large_error_share": None,
            "top_error_groups": {},
            "largest_errors": [],
        }
    total_abs_error = sum(item["abs_error"] for item in errors)
    return {
        "n": len(errors),
        "total_abs_error": _rounded(total_abs_error),
        "exact_match_share": _rounded(
            sum(1 for item in errors if item["abs_error"] == 0) / len(errors)
        ),
        "within_one_point_share": _rounded(
            sum(1 for item in errors if item["abs_error"] <= 1.0) / len(errors)
        ),
        "large_error_share": _rounded(
            sum(1 for item in errors if item["abs_error"] >= 5.0) / len(errors)
        ),
        "top_error_groups": {
            field_name: _boundary_delta_top_error_groups(errors, field_name)
            for field_name in BOUNDARY_DELTA_ERROR_CONTEXT_FIELDS
        },
        "largest_errors": _largest_boundary_delta_errors(errors),
    }


def _boundary_delta_top_error_groups(
    errors: list[dict[str, Any]], field_name: str
) -> list[dict[str, Any]]:
    grouped = _group_boundary_delta_errors(errors, field_name)
    total_abs_error = _boundary_delta_abs_error_sum(errors)
    rows = [
        _boundary_delta_error_group_row(
            field_name=field_name,
            key=key,
            items=items,
            total_count=len(errors),
            total_abs_error=total_abs_error,
        )
        for key, items in grouped.items()
    ]
    rows.sort(key=lambda row: _boundary_delta_error_group_sort_key(row, field_name))
    return rows[:10]


def _group_boundary_delta_errors(
    errors: list[dict[str, Any]], field_name: str
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in errors:
        metadata = item.get("metadata", {})
        key = _boundary_delta_error_group_key(metadata, field_name)
        grouped.setdefault(key, []).append(item)
    return grouped


def _boundary_delta_error_group_key(metadata: object, field_name: str) -> str:
    if not isinstance(metadata, dict):
        metadata = {}
    if field_name == "boundary_state":
        return "boundary" if metadata.get("is_boundary") else "same_label"
    return str(metadata.get(field_name) or "missing")


def _boundary_delta_error_group_row(
    *,
    field_name: str,
    key: str,
    items: list[dict[str, Any]],
    total_count: int,
    total_abs_error: float,
) -> dict[str, Any]:
    abs_error_sum = _boundary_delta_abs_error_sum(items)
    return {
        field_name: key,
        "count": len(items),
        "count_share": _rounded(len(items) / total_count),
        "share_abs_error": _rounded(
            abs_error_sum / total_abs_error if total_abs_error else None
        ),
        "mean_abs_error": _rounded(abs_error_sum / len(items)),
        "rmse": _rounded(_boundary_delta_rmse(items)),
        "max_abs_error": _rounded(max(item["abs_error"] for item in items)),
        "mean_actual": _rounded(sum(item["actual"] for item in items) / len(items)),
        "mean_predicted": _rounded(sum(item["predicted"] for item in items) / len(items)),
    }


def _boundary_delta_abs_error_sum(items: list[dict[str, Any]]) -> float:
    return sum(float(item["abs_error"]) for item in items)


def _boundary_delta_rmse(items: list[dict[str, Any]]) -> float:
    return math.sqrt(sum(item["error"] * item["error"] for item in items) / len(items))


def _boundary_delta_error_group_sort_key(
    row: dict[str, Any], field_name: str
) -> tuple[float, float, int, str]:
    return (
        -_number(row["share_abs_error"]),
        -_number(row["mean_abs_error"]),
        -int(_number(row.get("count"))),
        str(row.get(field_name) or ""),
    )


def _largest_boundary_delta_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(errors, key=lambda item: item["abs_error"], reverse=True)[:10]
    return [
        {
            "index": item["index"],
            "date": item["metadata"].get("date"),
            "day_of_week": item["metadata"].get("day_of_week"),
            "hour_bucket": item["metadata"].get("hour_bucket"),
            "transition": item["metadata"].get("transition"),
            "previous_segment_position_bucket": item["metadata"].get(
                "previous_segment_position_bucket"
            ),
            "boundary_state": "boundary"
            if item["metadata"].get("is_boundary")
            else "same_label",
            "previous_delta_percent": _rounded(item["previous_delta_percent"]),
            "actual_delta_percent": _rounded(item["actual"]),
            "predicted_delta_percent": _rounded(item["predicted"]),
            "abs_error": _rounded(item["abs_error"]),
        }
        for item in rows
    ]
