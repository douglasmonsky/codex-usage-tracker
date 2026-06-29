"""Predictive usage-drain model orchestration."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.feature_history import add_causal_history_features
from codex_usage_tracker.usage_drain.features import (
    add_days_since_first_span,
    span_feature_row,
)
from codex_usage_tracker.usage_drain.predictive_specs import predictive_model_specs
from codex_usage_tracker.usage_drain.regression import (
    design_matrix,
    fit_ridge,
    predict,
    prepare_design,
    regression_metrics,
)
from codex_usage_tracker.usage_drain.types import PredictiveModelSpec, UsageDeltaSpan
from codex_usage_tracker.usage_drain.utils import number, rounded

CAPACITY_RESIDUAL_GROUP_FIELDS = (
    "date",
    "day_of_week",
    "hour_bucket",
    "baseline_used_bucket",
    "window_elapsed_bucket",
    "reset_remaining_bucket",
    "row_count_bucket",
    "call_duration_bucket",
    "span_wall_time_bucket",
    "rate_limit_plan_type",
    "rate_limit_limit_id",
    "usage_window_source",
)


def capacity_residual_diagnostics(
    rows: list[dict[str, Any]], actual: list[float], predicted: list[float]
) -> dict[str, Any]:
    errors = capacity_residual_error_rows(rows, actual, predicted)
    if not errors:
        return empty_capacity_residual_diagnostics()
    return capacity_residual_summary(errors)


def capacity_residual_error_rows(
    rows: list[dict[str, Any]], actual: list[float], predicted: list[float]
) -> list[dict[str, Any]]:
    return [
        {
            "actual": actual_value,
            "predicted": predicted_value,
            "error": predicted_value - actual_value,
            "abs_error": abs(predicted_value - actual_value),
            "metadata": capacity_residual_metadata(row),
        }
        for row, actual_value, predicted_value in zip(rows, actual, predicted, strict=True)
    ]


def empty_capacity_residual_diagnostics() -> dict[str, Any]:
    return {
        "n": 0,
        "mean_error": None,
        "within_5_credits_share": None,
        "within_10_credits_share": None,
        "large_error_share": None,
        "top_error_groups": {},
        "largest_errors": [],
    }


def capacity_residual_summary(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(errors),
        "mean_error": rounded(
            sum(item["error"] for item in errors) / len(errors)
        ),
        "within_5_credits_share": capacity_error_share(errors, max_error=5.0),
        "within_10_credits_share": capacity_error_share(errors, max_error=10.0),
        "large_error_share": capacity_error_share(errors, min_error=25.0),
        "top_error_groups": capacity_residual_top_error_groups(errors),
        "largest_errors": largest_capacity_residual_errors(errors),
    }


def capacity_error_share(
    errors: list[dict[str, Any]],
    *,
    min_error: float | None = None,
    max_error: float | None = None,
) -> float | None:
    if not errors:
        return None
    matching = 0
    for item in errors:
        abs_error = item["abs_error"]
        above_min = min_error is None or abs_error >= min_error
        below_max = max_error is None or abs_error <= max_error
        if above_min and below_max:
            matching += 1
    return rounded(matching / len(errors))


def capacity_residual_top_error_groups(
    errors: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    return {
        field_name: capacity_top_error_groups(errors, field_name)
        for field_name in CAPACITY_RESIDUAL_GROUP_FIELDS
    }


def capacity_residual_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        field_name: row.get(field_name, "missing")
        for field_name in CAPACITY_RESIDUAL_GROUP_FIELDS
    }


def capacity_top_error_groups(
    errors: list[dict[str, Any]], field_name: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in errors:
        metadata = item.get("metadata", {})
        key = str(metadata.get(field_name) or "missing")
        grouped.setdefault(key, []).append(item)
    rows = [
        {
            field_name: key,
            "count": len(items),
            "mean_abs_error": rounded(
                sum(item["abs_error"] for item in items) / len(items)
            ),
            "mean_error": rounded(sum(item["error"] for item in items) / len(items)),
            "max_abs_error": rounded(max(item["abs_error"] for item in items)),
            "mean_actual": rounded(sum(item["actual"] for item in items) / len(items)),
            "meanpredicted": rounded(
                sum(item["predicted"] for item in items) / len(items)
            ),
        }
        for key, items in grouped.items()
    ]
    rows.sort(
        key=lambda row: (
            -number(row["mean_abs_error"]),
            -int(number(row.get("count"))),
        )
    )
    return rows[:10]


def largest_capacity_residual_errors(
    errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = sorted(errors, key=lambda item: item["abs_error"], reverse=True)[:10]
    return [
        {
            "actual_credits": rounded(item["actual"]),
            "predicted_credits": rounded(item["predicted"]),
            "error_credits": rounded(item["error"]),
            "abs_error_credits": rounded(item["abs_error"]),
            **item["metadata"],
        }
        for item in rows
    ]


def fit_predictive_usage_drain_models(
    spans: list[UsageDeltaSpan],
    *,
    proxy: str = "all_candidates",
    train_fraction: float = 0.8,
) -> list[dict[str, Any]]:
    """Fit exploratory train/holdout models for richer control variables."""

    feature_rows = [span_feature_row(span, proxy=proxy) for span in spans]
    if len(feature_rows) < 10:
        return []
    add_days_since_first_span(feature_rows)
    add_causal_history_features(feature_rows)
    results: list[dict[str, Any]] = []
    for split_name, train_rows, holdout_rows in split_feature_rows(
        feature_rows, train_fraction=train_fraction
    ):
        results.extend(fit_causal_baseline_models(train_rows, holdout_rows, split_name))
        for spec in predictive_model_specs():
            fitted = fit_predictive_model(train_rows, holdout_rows, spec)
            if fitted is not None:
                fitted["validation"] = split_name
                fitted["name"] = f"{spec.name}__{split_name}"
                results.append(fitted)
    return results


def split_feature_rows(
    rows: list[dict[str, Any]], *, train_fraction: float
) -> list[tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    train_size = max(1, min(len(rows) - 1, int(len(rows) * train_fraction)))
    time_train = rows[:train_size]
    time_holdout = rows[train_size:]
    interleaved_holdout = [row for index, row in enumerate(rows) if index % 5 == 4]
    interleaved_train = [row for index, row in enumerate(rows) if index % 5 != 4]
    return [
        ("time_ordered_80_20", time_train, time_holdout),
        ("interleaved_every_5th", interleaved_train, interleaved_holdout),
    ]


def fit_causal_baseline_models(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    split_name: str,
) -> list[dict[str, Any]]:
    baselines: list[tuple[str, str | None, float | None]] = [
        ("constant_one_percent", None, 1.0),
        ("persistence_previous_delta", "previous_delta_percent", None),
        ("rolling3_delta", "rolling3_delta_percent", None),
        ("rolling10_delta", "rolling10_delta_percent", None),
        ("rolling50_delta", "rolling50_delta_percent", None),
        ("rolling10_median_delta", "rolling10_median_delta_percent", None),
        ("rolling10_mode_delta", "rolling10_mode_delta_percent", None),
        ("hybrid_streak_regime", "hybrid_streak_delta_percent", None),
        ("same_bucket_rolling10_delta", "same_bucket_rolling10_delta_percent", None),
        (
            "same_bucket_rolling10_mode_delta",
            "same_bucket_rolling10_mode_delta_percent",
            None,
        ),
        ("same_date_rolling10_delta", "same_date_rolling10_delta_percent", None),
        (
            "same_date_rolling10_mode_delta",
            "same_date_rolling10_mode_delta_percent",
            None,
        ),
        ("same_hour_rolling10_delta", "same_hour_rolling10_delta_percent", None),
        (
            "same_hour_rolling10_mode_delta",
            "same_hour_rolling10_mode_delta_percent",
            None,
        ),
        (
            "same_day_of_week_rolling10_delta",
            "same_day_of_week_rolling10_delta_percent",
            None,
        ),
        (
            "same_day_of_week_rolling10_mode_delta",
            "same_day_of_week_rolling10_mode_delta_percent",
            None,
        ),
        ("ewma_delta", "ewma_delta_percent", None),
    ]
    results: list[dict[str, Any]] = []
    for name, feature_field, constant in baselines:
        train_y = [number(row.get("target")) for row in train_rows]
        holdout_y = [number(row.get("target")) for row in holdout_rows]
        train_predictions = baseline_predictions(
            train_rows, field=feature_field, constant=constant
        )
        holdout_predictions = baseline_predictions(
            holdout_rows, field=feature_field, constant=constant
        )
        results.append(
            {
                "name": f"{name}__{split_name}",
                "validation": split_name,
                "kind": "causal_baseline",
                "feature_count": 1 if feature_field or constant is not None else 0,
                "numeric_features": [feature_field] if feature_field else [],
                "categorical_features": [],
                "train": regression_metrics(train_y, train_predictions),
                "holdout": regression_metrics(holdout_y, holdout_predictions),
                "top_coefficients": [],
            }
        )
    return results


def baseline_predictions(
    rows: list[dict[str, Any]], *, field: str | None, constant: float | None
) -> list[float]:
    if constant is not None:
        return [constant for _row in rows]
    if field is None:
        return [0.0 for _row in rows]
    return [number(row.get(field)) for row in rows]


def fit_predictive_model(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    spec: PredictiveModelSpec,
    *,
    include_capacity_residual_diagnostics: bool = False,
) -> dict[str, Any] | None:
    prepared = prepare_design(train_rows, spec)
    if prepared is None:
        return None
    feature_names, means, stddevs, category_levels = prepared
    train_x = design_matrix(
        train_rows,
        spec,
        feature_names=feature_names,
        means=means,
        stddevs=stddevs,
        category_levels=category_levels,
    )
    train_y = [number(row.get("target")) for row in train_rows]
    coefficients = fit_ridge(train_x, train_y, alpha=spec.ridge_alpha)
    if coefficients is None:
        return None
    holdout_x = design_matrix(
        holdout_rows,
        spec,
        feature_names=feature_names,
        means=means,
        stddevs=stddevs,
        category_levels=category_levels,
    )
    holdout_y = [number(row.get("target")) for row in holdout_rows]
    train_predictions = predict(train_x, coefficients)
    holdout_predictions = predict(holdout_x, coefficients)
    coefficient_rows = [
        {"feature": feature, "coefficient": rounded(value)}
        for feature, value in zip(feature_names, coefficients[1:], strict=True)
    ]
    coefficient_rows.sort(key=lambda row: abs(number(row["coefficient"])), reverse=True)
    result = {
        "name": spec.name,
        "feature_count": len(feature_names),
        "ridge_alpha": rounded(spec.ridge_alpha),
        "numeric_features": list(spec.numeric_features),
        "categorical_features": list(spec.categorical_features),
        "train": regression_metrics(train_y, train_predictions),
        "holdout": regression_metrics(holdout_y, holdout_predictions),
        "top_coefficients": coefficient_rows[:12],
    }
    if include_capacity_residual_diagnostics:
        result["holdout_error_diagnostics"] = capacity_residual_diagnostics(
            holdout_rows, holdout_y, holdout_predictions
        )
    return result
