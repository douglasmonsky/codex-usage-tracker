"""Credit-to-delta fit helpers for allowance breakpoint diagnostics."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.allowance_online import (
    allowance_online_capacity_credit_to_delta_fit as allowance_online_capacity_credit_to_delta_fit,
)
from codex_usage_tracker.usage_drain.regression import (
    fit_linear_coefficients as _fit_linear_regression_coefficients,
)
from codex_usage_tracker.usage_drain.regression import (
    predict_linear as _linear_regression_predictions,
)
from codex_usage_tracker.usage_drain.regression import (
    regression_metrics as _regression_metrics,
)
from codex_usage_tracker.usage_drain.utils import (
    ceil_to_visible_tick as _ceil_to_visible_tick,
)
from codex_usage_tracker.usage_drain.utils import (
    number as _number,
)
from codex_usage_tracker.usage_drain.utils import (
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
    capacities = [_number(row.get("credits_per_visible_percent")) for row in segment_rows]
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
        predictions["global_slope_ceiling"].append(_ceil_to_visible_tick(global_prediction))
        predictions["mean_capacity"].append(mean_prediction)
        predictions["mean_capacity_ceiling"].append(_ceil_to_visible_tick(mean_prediction))
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
        "no_intercept_implied_credits_per_percent": _rounded(1 / slope if slope > 0 else None),
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
