"""Online capacity fit diagnostics for allowance modeling."""

from __future__ import annotations

from statistics import median
from typing import Any

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

    model_descriptions = _online_capacity_model_descriptions()
    predictions, ceiling_predictions = _empty_online_capacity_predictions(model_descriptions)
    actual: list[float] = []
    row_indexes: list[int] = []
    capacity_history: list[float] = []
    ewma_capacity: float | None = None

    for row_index, row in enumerate(rows):
        if capacity_history:
            _append_online_capacity_predictions(
                row,
                capacity_history=capacity_history,
                ewma_capacity=ewma_capacity,
                predictions=predictions,
                ceiling_predictions=ceiling_predictions,
            )
            actual.append(_number(row.get("delta_usage_percent")))
            row_indexes.append(row_index)

        current_capacity = _number(row.get("credits_per_visible_percent"))
        ewma_capacity = (
            current_capacity
            if ewma_capacity is None
            else 0.30 * current_capacity + 0.70 * ewma_capacity
        )
        capacity_history.append(current_capacity)

    segment_start_indexes = {start for start, _end in segments if start > 0}
    models = _online_capacity_model_records(
        rows,
        row_indexes=row_indexes,
        actual=actual,
        predictions=predictions,
        ceiling_predictions=ceiling_predictions,
        model_descriptions=model_descriptions,
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


def _online_capacity_model_descriptions() -> dict[str, str]:
    return {
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


def _empty_online_capacity_predictions(
    model_descriptions: dict[str, str],
) -> tuple[dict[str, list[float]], dict[str, list[float]]]:
    predictions: dict[str, list[float]] = {name: [] for name in model_descriptions}
    ceiling_predictions: dict[str, list[float]] = {
        f"{name}_ceiling": [] for name in model_descriptions
    }
    return predictions, ceiling_predictions


def _append_online_capacity_predictions(
    row: dict[str, Any],
    *,
    capacity_history: list[float],
    ewma_capacity: float | None,
    predictions: dict[str, list[float]],
    ceiling_predictions: dict[str, list[float]],
) -> None:
    credit = _number(row.get("standard_usage_credits"))
    for model_name, capacity in _online_capacity_estimates(
        capacity_history,
        ewma_capacity=ewma_capacity,
    ).items():
        prediction = credit / capacity if capacity and capacity > 0 else 0.0
        predictions[model_name].append(prediction)
        ceiling_predictions[f"{model_name}_ceiling"].append(_ceil_to_visible_tick(prediction))


def _online_capacity_estimates(
    capacity_history: list[float], *, ewma_capacity: float | None
) -> dict[str, float]:
    return {
        "previous_capacity_denominator": capacity_history[-1],
        "rolling3_mean_capacity_denominator": sum(capacity_history[-3:])
        / len(capacity_history[-3:]),
        "rolling10_mean_capacity_denominator": sum(capacity_history[-10:])
        / len(capacity_history[-10:]),
        "rolling10_median_capacity_denominator": float(median(capacity_history[-10:])),
        "ewma_capacity_denominator": ewma_capacity
        if ewma_capacity is not None
        else capacity_history[-1],
    }


def _online_capacity_model_records(
    rows: list[dict[str, Any]],
    *,
    row_indexes: list[int],
    actual: list[float],
    predictions: dict[str, list[float]],
    ceiling_predictions: dict[str, list[float]],
    model_descriptions: dict[str, str],
    segment_start_indexes: set[int],
) -> dict[str, dict[str, Any]]:
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
                f"{model_descriptions[base_name]} Positive predictions are rounded up "
                "to the next visible 1% tick."
            ),
            segment_start_indexes=segment_start_indexes,
        )
    return models


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
    errors = _allowance_online_error_rows(
        row_indexes,
        actual,
        predicted,
        segment_start_indexes=segment_start_indexes,
    )
    breakpoint_errors = _allowance_online_abs_errors(
        errors, is_known_breakpoint=True
    )
    non_breakpoint_errors = _allowance_online_abs_errors(
        errors, is_known_breakpoint=False
    )
    return {
        "known_breakpoint_row_count": len(breakpoint_errors),
        "non_breakpoint_row_count": len(non_breakpoint_errors),
        "known_breakpoint_abs_error_share": _known_breakpoint_abs_error_share(
            errors, breakpoint_errors
        ),
        "known_breakpoint_mae": _mean_abs_error(breakpoint_errors),
        "non_breakpoint_mae": _mean_abs_error(non_breakpoint_errors),
        "largest_errors": _largest_allowance_online_errors(rows, errors),
    }


def _allowance_online_error_rows(
    row_indexes: list[int],
    actual: list[float],
    predicted: list[float],
    *,
    segment_start_indexes: set[int],
) -> list[dict[str, Any]]:
    return [
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


def _allowance_online_abs_errors(
    errors: list[dict[str, Any]], *, is_known_breakpoint: bool
) -> list[float]:
    return [
        row["abs_error"]
        for row in errors
        if row["is_known_breakpoint"] is is_known_breakpoint
    ]


def _known_breakpoint_abs_error_share(
    errors: list[dict[str, Any]], breakpoint_errors: list[float]
) -> float | None:
    total_abs_error = sum(row["abs_error"] for row in errors)
    return _rounded(sum(breakpoint_errors) / total_abs_error if total_abs_error > 0 else 0.0)


def _mean_abs_error(errors: list[float]) -> float | None:
    return _rounded(sum(errors) / len(errors) if errors else None)


def _largest_allowance_online_errors(
    rows: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    largest = sorted(
        errors,
        key=lambda row: (-_number(row.get("abs_error")), int(row["row_index"])),
    )[:8]
    return [_allowance_online_error_record(rows, item) for item in largest]


def _allowance_online_error_record(
    rows: list[dict[str, Any]], item: dict[str, Any]
) -> dict[str, Any]:
    row = rows[int(item["row_index"])]
    return {
        "row_index": int(item["row_index"]),
        "span_index": int(row["span_index"]),
        "is_known_breakpoint": bool(item["is_known_breakpoint"]),
        "actual_delta_percent": _rounded(_number(item["actual"])),
        "predicted_delta_percent": _rounded(_number(item["predicted"])),
        "abs_error": _rounded(_number(item["abs_error"])),
        "credits_per_visible_percent": _rounded(
            _number(row.get("credits_per_visible_percent"))
        ),
        "standard_usage_credits": _rounded(
            _number(row.get("standard_usage_credits"))
        ),
        "start_event_timestamp": row.get("start_event_timestamp"),
        "end_event_timestamp": row.get("end_event_timestamp"),
    }
