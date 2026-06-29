"""Credit-to-delta fit helpers for allowance breakpoint diagnostics."""

from __future__ import annotations

from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain_regression import (
    fit_linear_coefficients as _fit_linear_regression_coefficients,
)
from codex_usage_tracker.usage_drain_regression import (
    predict_linear as _linear_regression_predictions,
)
from codex_usage_tracker.usage_drain_regression import (
    regression_metrics as _regression_metrics,
)
from codex_usage_tracker.usage_drain_utils import (
    ceil_to_visible_tick as _ceil_to_visible_tick,
)
from codex_usage_tracker.usage_drain_utils import (
    number as _number,
)
from codex_usage_tracker.usage_drain_utils import (
    rounded as _rounded,
)


def _empty_allowance_piecewise_fit() -> dict[str, Any]:
    return {
        "target": "visible_delta_percent",
        "models": {},
        "notes": [
            "No piecewise fit is available without breakpoint segments.",
        ],
    }


def _no_intercept_credit_slope(credits: list[float], delta: list[float]) -> float:
    coefficients = _fit_linear_regression_coefficients(
        [[credit] for credit in credits],
        delta,
        intercept=False,
    )
    return coefficients[0] if coefficients else 0.0


def _piecewise_prediction_lists() -> dict[str, list[float]]:
    return {
        "global_slope_ceiling": [],
        "mean_capacity": [],
        "mean_capacity_ceiling": [],
        "leave_one_out_capacity": [],
        "slope": [],
        "slope_ceiling": [],
    }


def _segment_fit_values(segment_rows: list[dict[str, Any]]) -> dict[str, Any]:
    capacities = [
        _number(row.get("credits_per_visible_percent")) for row in segment_rows
    ]
    credits = [_number(row.get("standard_usage_credits")) for row in segment_rows]
    delta = [_number(row.get("delta_usage_percent")) for row in segment_rows]
    mean_capacity = sum(capacities) / len(capacities) if capacities else 0.0
    return {
        "capacities": capacities,
        "credits": credits,
        "mean_capacity": mean_capacity,
        "slope": _no_intercept_credit_slope(credits, delta),
    }


def _leave_one_out_capacity(
    capacities: list[float],
    *,
    capacity_sum: float,
    offset: int,
    fallback: float,
) -> float:
    if len(capacities) <= 1:
        return fallback
    return (capacity_sum - capacities[offset]) / (len(capacities) - 1)


def _append_piecewise_predictions(
    predictions: dict[str, list[float]],
    *,
    credits: list[float],
    capacities: list[float],
    mean_capacity: float,
    slope: float,
    global_slope: float,
) -> None:
    capacity_sum = sum(capacities)
    for offset, credit in enumerate(credits):
        global_prediction = global_slope * credit
        mean_prediction = credit / mean_capacity if mean_capacity > 0 else 0.0
        slope_prediction = slope * credit
        loo_capacity = _leave_one_out_capacity(
            capacities,
            capacity_sum=capacity_sum,
            offset=offset,
            fallback=mean_capacity,
        )
        predictions["global_slope_ceiling"].append(
            _ceil_to_visible_tick(global_prediction)
        )
        predictions["mean_capacity"].append(mean_prediction)
        predictions["mean_capacity_ceiling"].append(
            _ceil_to_visible_tick(mean_prediction)
        )
        predictions["leave_one_out_capacity"].append(
            credit / loo_capacity if loo_capacity > 0 else 0.0
        )
        predictions["slope"].append(slope_prediction)
        predictions["slope_ceiling"].append(_ceil_to_visible_tick(slope_prediction))


def _piecewise_segment_model(
    *,
    segment_index: int,
    segment_rows: list[dict[str, Any]],
    mean_capacity: float,
    slope: float,
) -> dict[str, Any]:
    return {
        "segment_index": segment_index,
        "n": len(segment_rows),
        "mean_credits_per_visible_percent": _rounded(mean_capacity),
        "no_intercept_slope_delta_percent_per_credit": _rounded(slope),
        "no_intercept_implied_credits_per_percent": _rounded(
            1 / slope if slope > 0 else None
        ),
    }


def allowance_piecewise_credit_to_delta_fit(
    rows: list[dict[str, Any]],
    segments: list[tuple[int, int]],
) -> dict[str, Any]:
    actual = [_number(row.get("delta_usage_percent")) for row in rows]
    if not rows or not segments:
        return _empty_allowance_piecewise_fit()

    predictions = _piecewise_prediction_lists()
    segment_models: list[dict[str, Any]] = []
    global_slope = _no_intercept_credit_slope(
        [_number(row.get("standard_usage_credits")) for row in rows],
        actual,
    )
    for segment_index, (start, end) in enumerate(segments, start=1):
        segment_rows = rows[start:end]
        segment_values = _segment_fit_values(segment_rows)
        mean_capacity = _number(segment_values.get("mean_capacity"))
        slope = _number(segment_values.get("slope"))
        _append_piecewise_predictions(
            predictions,
            credits=segment_values["credits"],
            capacities=segment_values["capacities"],
            mean_capacity=mean_capacity,
            slope=slope,
            global_slope=global_slope,
        )
        segment_models.append(
            _piecewise_segment_model(
                segment_index=segment_index,
                segment_rows=segment_rows,
                mean_capacity=mean_capacity,
                slope=slope,
            )
        )

    return {
        "target": "visible_delta_percent",
        "models": {
            "global_no_intercept_credit_slope": credit_to_delta_fit(rows),
            "global_ceiling_no_intercept_credit_slope": {
                "description": (
                    "Fits one global no-intercept credit slope, then rounds each "
                    "positive prediction up to the next visible 1% tick."
                ),
                "metrics": _regression_metrics(
                    actual,
                    predictions["global_slope_ceiling"],
                ),
            },
            "piecewise_mean_capacity_denominator": {
                "description": (
                    "Predicts visible delta as credits divided by the detected "
                    "segment mean credits per visible percent."
                ),
                "metrics": _regression_metrics(actual, predictions["mean_capacity"]),
            },
            "piecewise_ceiling_mean_capacity_denominator": {
                "description": (
                    "Predicts visible delta as credits divided by the detected "
                    "segment mean, then rounds positive predictions up to the "
                    "next visible 1% tick."
                ),
                "metrics": _regression_metrics(
                    actual,
                    predictions["mean_capacity_ceiling"],
                ),
            },
            "piecewise_leave_one_out_capacity_denominator": {
                "description": (
                    "Predicts visible delta as credits divided by the detected "
                    "segment mean after excluding the current row from that mean."
                ),
                "metrics": _regression_metrics(
                    actual,
                    predictions["leave_one_out_capacity"],
                ),
            },
            "piecewise_no_intercept_credit_slope": {
                "description": (
                    "Fits a no-intercept credit-to-delta slope separately inside "
                    "each detected segment."
                ),
                "metrics": _regression_metrics(actual, predictions["slope"]),
            },
            "piecewise_ceiling_no_intercept_credit_slope": {
                "description": (
                    "Fits a no-intercept credit-to-delta slope inside each "
                    "detected segment, then rounds positive predictions up to "
                    "the next visible 1% tick."
                ),
                "metrics": _regression_metrics(actual, predictions["slope_ceiling"]),
            },
        },
        "segment_models": segment_models,
        "notes": [
            "These fits test whether a capacity-adjusted credit metric explains visible drain after detected breakpoints.",
            "They are explanatory, not causal, because breakpoint detection uses the full observed series.",
        ],
    }

def allowance_online_capacity_credit_to_delta_fit(
    rows: list[dict[str, Any]],
    segments: list[tuple[int, int]],
) -> dict[str, Any]:
    if len(rows) < 2:
        return {
            "target": "visible_delta_percent",
            "prediction_rows": 0,
            "skipped_initial_rows": len(rows),
            "models": {},
            "notes": [
                "No online capacity fit is available without at least two positive usage-delta spans.",
            ],
        }

    model_descriptions = {
        "previous_capacity_denominator": (
            "Predicts visible delta as current credits divided by the immediately previous observed credits per visible percent."
        ),
        "rolling3_mean_capacity_denominator": (
            "Predicts visible delta as current credits divided by the mean observed capacity over the previous three spans."
        ),
        "rolling10_mean_capacity_denominator": (
            "Predicts visible delta as current credits divided by the mean observed capacity over the previous ten spans."
        ),
        "rolling10_median_capacity_denominator": (
            "Predicts visible delta as current credits divided by the median observed capacity over the previous ten spans."
        ),
        "ewma_capacity_denominator": (
            "Predicts visible delta as current credits divided by an EWMA of prior observed capacity, alpha 0.30."
        ),
    }
    predictions: dict[str, list[float]] = {
        name: [] for name in model_descriptions
    }
    ceiling_predictions: dict[str, list[float]] = {
        f"{name}_ceiling": [] for name in model_descriptions
    }
    actual: list[float] = []
    row_indexes: list[int] = []
    capacity_history: list[float] = []
    ewma_capacity: float | None = None
    for row_index, row in enumerate(rows):
        if capacity_history:
            credit = _number(row.get("standard_usage_credits"))
            estimates = {
                "previous_capacity_denominator": capacity_history[-1],
                "rolling3_mean_capacity_denominator": sum(capacity_history[-3:])
                / len(capacity_history[-3:]),
                "rolling10_mean_capacity_denominator": sum(capacity_history[-10:])
                / len(capacity_history[-10:]),
                "rolling10_median_capacity_denominator": float(
                    median(capacity_history[-10:])
                ),
                "ewma_capacity_denominator": ewma_capacity
                if ewma_capacity is not None
                else capacity_history[-1],
            }
            actual.append(_number(row.get("delta_usage_percent")))
            row_indexes.append(row_index)
            for model_name, capacity in estimates.items():
                prediction = credit / capacity if capacity and capacity > 0 else 0.0
                predictions[model_name].append(prediction)
                ceiling_predictions[f"{model_name}_ceiling"].append(
                    _ceil_to_visible_tick(prediction)
                )

        current_capacity = _number(row.get("credits_per_visible_percent"))
        if ewma_capacity is None:
            ewma_capacity = current_capacity
        else:
            ewma_capacity = (0.3 * current_capacity) + (0.7 * ewma_capacity)
        capacity_history.append(current_capacity)

    segment_start_indexes = {start for start, _end in segments if start > 0}
    models: dict[str, dict[str, Any]] = {}
    for model_name, values in predictions.items():
        models[model_name] = _allowance_online_capacity_model_record(
            rows,
            row_indexes,
            actual,
            values,
            description=model_descriptions[model_name],
            segment_start_indexes=segment_start_indexes,
        )
    for model_name, values in ceiling_predictions.items():
        base_name = model_name.removesuffix("_ceiling")
        models[model_name] = _allowance_online_capacity_model_record(
            rows,
            row_indexes,
            actual,
            values,
            description=(
                model_descriptions[base_name]
                + " Positive predictions are rounded up to the next visible 1% tick."
            ),
            segment_start_indexes=segment_start_indexes,
        )

    return {
        "target": "visible_delta_percent",
        "prediction_rows": len(actual),
        "skipped_initial_rows": len(rows) - len(actual),
        "models": models,
        "notes": [
            "Online capacity fits use current same-span credits but only prior spans for the capacity denominator.",
            "These are explanatory diagnostics for allowance-denominator drift; they are not advance predictions before current-span tokens are known.",
            "Known-breakpoint diagnostics use detected piecewise segment starts only to explain residual concentration.",
        ],
    }


def _allowance_online_capacity_model_record(
    rows: list[dict[str, Any]],
    row_indexes: list[int],
    actual: list[float],
    predicted: list[float],
    *,
    description: str,
    segment_start_indexes: set[int],
) -> dict[str, Any]:
    return {
        "description": description,
        "metrics": _regression_metrics(actual, predicted),
        "known_breakpoint_diagnostics": (
            _allowance_online_capacity_error_diagnostics(
                rows,
                row_indexes,
                actual,
                predicted,
                segment_start_indexes=segment_start_indexes,
            )
        ),
    }


def _allowance_online_capacity_error_diagnostics(
    rows: list[dict[str, Any]],
    row_indexes: list[int],
    actual: list[float],
    predicted: list[float],
    *,
    segment_start_indexes: set[int],
) -> dict[str, Any]:
    errors = [
        {
            "row_index": row_index,
            "actual": actual_value,
            "predicted": predicted_value,
            "abs_error": abs(predicted_value - actual_value),
            "is_known_breakpoint": row_index in segment_start_indexes,
        }
        for row_index, actual_value, predicted_value in zip(
            row_indexes,
            actual,
            predicted,
            strict=True,
        )
    ]
    breakpoint_errors = [
        row["abs_error"] for row in errors if row["is_known_breakpoint"]
    ]
    non_breakpoint_errors = [
        row["abs_error"] for row in errors if not row["is_known_breakpoint"]
    ]
    total_abs_error = sum(row["abs_error"] for row in errors)
    largest = sorted(
        errors,
        key=lambda row: (-_number(row.get("abs_error")), int(row["row_index"])),
    )[:8]
    return {
        "known_breakpoint_row_count": len(breakpoint_errors),
        "non_breakpoint_row_count": len(non_breakpoint_errors),
        "known_breakpoint_abs_error_share": _rounded(
            sum(breakpoint_errors) / total_abs_error if total_abs_error > 0 else 0.0
        ),
        "known_breakpoint_mae": _rounded(
            sum(breakpoint_errors) / len(breakpoint_errors)
            if breakpoint_errors
            else None
        ),
        "non_breakpoint_mae": _rounded(
            sum(non_breakpoint_errors) / len(non_breakpoint_errors)
            if non_breakpoint_errors
            else None
        ),
        "largest_errors": [
            {
                "row_index": int(item["row_index"]),
                "span_index": int(rows[int(item["row_index"])]["span_index"]),
                "is_known_breakpoint": bool(item["is_known_breakpoint"]),
                "actual_delta_percent": _rounded(_number(item["actual"])),
                "predicted_delta_percent": _rounded(_number(item["predicted"])),
                "abs_error": _rounded(_number(item["abs_error"])),
                "credits_per_visible_percent": _rounded(
                    _number(
                        rows[int(item["row_index"])].get(
                            "credits_per_visible_percent"
                        )
                    )
                ),
                "standard_usage_credits": _rounded(
                    _number(
                        rows[int(item["row_index"])].get("standard_usage_credits")
                    )
                ),
                "start_event_timestamp": rows[int(item["row_index"])].get(
                    "start_event_timestamp"
                ),
                "end_event_timestamp": rows[int(item["row_index"])].get(
                    "end_event_timestamp"
                ),
            }
            for item in largest
        ],
    }

def credit_to_delta_fit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 2:
        return {
            "n": len(rows),
            "slope_delta_percent_per_credit": None,
            "implied_credits_per_percent": None,
            "metrics": _regression_metrics([], []),
        }
    x_rows = [[_number(row.get("standard_usage_credits"))] for row in rows]
    actual = [_number(row.get("delta_usage_percent")) for row in rows]
    coefficients = _fit_linear_regression_coefficients(
        x_rows,
        actual,
        intercept=False,
    )
    predictions = _linear_regression_predictions(
        x_rows,
        coefficients,
        intercept=False,
    )
    slope = coefficients[0] if coefficients else 0.0
    return {
        "n": len(rows),
        "slope_delta_percent_per_credit": _rounded(slope),
        "implied_credits_per_percent": _rounded(1 / slope if slope > 0 else None),
        "metrics": _regression_metrics(actual, predictions),
    }
