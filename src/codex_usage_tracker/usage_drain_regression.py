"""Regression and correlation helpers for usage-drain modeling."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain_types import PredictiveModelSpec, UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import number, rounded


def prepare_design(
    rows: list[dict[str, Any]], spec: PredictiveModelSpec
) -> tuple[list[str], dict[str, float], dict[str, float], dict[str, list[str]]] | None:
    if not rows:
        return None
    means: dict[str, float] = {}
    stddevs: dict[str, float] = {}
    feature_names: list[str] = []
    for feature in spec.numeric_features:
        values = [number(row.get(feature)) for row in rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        stddev = math.sqrt(variance) or 1.0
        means[feature] = mean
        stddevs[feature] = stddev
        feature_names.append(feature)
    category_levels: dict[str, list[str]] = {}
    for feature in spec.categorical_features:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(row.get(feature) or "missing")
            counts[value] = counts.get(value, 0) + 1
        levels = [value for value, count in sorted(counts.items()) if count >= 2]
        category_levels[feature] = levels
        feature_names.extend(f"{feature}={value}" for value in levels)
    return feature_names, means, stddevs, category_levels


def design_matrix(
    rows: list[dict[str, Any]],
    spec: PredictiveModelSpec,
    *,
    feature_names: list[str],
    means: dict[str, float],
    stddevs: dict[str, float],
    category_levels: dict[str, list[str]],
) -> list[list[float]]:
    matrix: list[list[float]] = []
    feature_index = {feature: index for index, feature in enumerate(feature_names)}
    for row in rows:
        values = [0.0] * len(feature_names)
        for feature in spec.numeric_features:
            index = feature_index[feature]
            values[index] = (number(row.get(feature)) - means[feature]) / stddevs[feature]
        for feature in spec.categorical_features:
            value = str(row.get(feature) or "missing")
            encoded_name = f"{feature}={value}"
            if encoded_name in feature_index:
                values[feature_index[encoded_name]] = 1.0
        matrix.append(values)
    return matrix


def fit_ridge(
    x_rows: list[list[float]], y_values: list[float], *, alpha: float
) -> list[float] | None:
    if not x_rows or not y_values:
        return None
    width = len(x_rows[0]) + 1
    lhs = [[0.0 for _ in range(width)] for _ in range(width)]
    rhs = [0.0 for _ in range(width)]
    for row, y_value in zip(x_rows, y_values, strict=True):
        expanded = [1.0, *row]
        for i, x_i in enumerate(expanded):
            rhs[i] += x_i * y_value
            for j, x_j in enumerate(expanded):
                lhs[i][j] += x_i * x_j
    for index in range(1, width):
        lhs[index][index] += alpha
    return solve_linear_system(lhs, rhs)


def solve_linear_system(lhs: list[list[float]], rhs: list[float]) -> list[float] | None:
    size = len(rhs)
    matrix = [row[:] + [rhs_value] for row, rhs_value in zip(lhs, rhs, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12:
            return None
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        pivot_value = matrix[column][column]
        matrix[column] = [value / pivot_value for value in matrix[column]]
        for row_index in range(size):
            if row_index == column:
                continue
            factor = matrix[row_index][column]
            if factor == 0:
                continue
            matrix[row_index] = [
                value - factor * pivot_component
                for value, pivot_component in zip(
                    matrix[row_index], matrix[column], strict=True
                )
            ]
    return [matrix[row][size] for row in range(size)]


def predict(x_rows: list[list[float]], coefficients: list[float]) -> list[float]:
    return [
        coefficients[0]
        + sum(value * coefficient for value, coefficient in zip(row, coefficients[1:], strict=True))
        for row in x_rows
    ]



def fit_linear_coefficients(
    x_rows: list[list[float]],
    y_values: list[float],
    *,
    intercept: bool,
) -> list[float]:
    """Fit ordinary least-squares coefficients with a tiny ridge fallback."""

    width = len(x_rows[0]) + (1 if intercept else 0)
    lhs = [[0.0 for _ in range(width)] for _ in range(width)]
    rhs = [0.0 for _ in range(width)]
    for row, y_value in zip(x_rows, y_values, strict=True):
        expanded = ([1.0] if intercept else []) + row
        for i, x_i in enumerate(expanded):
            rhs[i] += x_i * y_value
            for j, x_j in enumerate(expanded):
                lhs[i][j] += x_i * x_j
    coefficients = solve_linear_system(lhs, rhs)
    if coefficients is not None:
        return coefficients
    for index in range(1 if intercept else 0, width):
        lhs[index][index] += 1e-9
    coefficients = solve_linear_system(lhs, rhs)
    if coefficients is None:
        return [0.0 for _index in range(width)]
    return coefficients


def predict_linear(
    x_rows: list[list[float]],
    coefficients: list[float],
    *,
    intercept: bool,
) -> list[float]:
    predictions: list[float] = []
    for row in x_rows:
        expanded = ([1.0] if intercept else []) + row
        predictions.append(
            sum(
                coefficient * value
                for coefficient, value in zip(coefficients, expanded, strict=True)
            )
        )
    return predictions


def regression_metrics(
    actual: list[float], predicted: list[float]
) -> dict[str, float | int | None]:
    if not actual or len(actual) != len(predicted):
        return {
            "n": len(actual),
            "r2": None,
            "mae": None,
            "rmse": None,
            "pearson": None,
            "mean_actual": None,
            "mean_predicted": None,
            "std_actual": None,
            "min_actual": None,
            "max_actual": None,
        }
    errors = [prediction - value for value, prediction in zip(actual, predicted, strict=True)]
    mean_actual = sum(actual) / len(actual)
    actual_variance = sum((value - mean_actual) ** 2 for value in actual) / len(actual)
    return {
        "n": len(actual),
        "r2": rounded(r2(actual, predicted)),
        "mae": rounded(sum(abs(error) for error in errors) / len(errors)),
        "rmse": rounded(math.sqrt(sum(error * error for error in errors) / len(errors))),
        "pearson": rounded(pearson(actual, predicted)),
        "mean_actual": rounded(mean_actual),
        "mean_predicted": rounded(sum(predicted) / len(predicted)),
        "std_actual": rounded(math.sqrt(actual_variance)),
        "min_actual": rounded(min(actual)),
        "max_actual": rounded(max(actual)),
    }


def fit_two_feature_no_intercept(
    x0_values: list[float], x1_values: list[float], y_values: list[float]
) -> tuple[float | None, float | None]:
    if not y_values:
        return None, None
    s00 = sum(x0 * x0 for x0 in x0_values)
    s01 = sum(x0 * x1 for x0, x1 in zip(x0_values, x1_values, strict=True))
    s11 = sum(x1 * x1 for x1 in x1_values)
    t0 = sum(x0 * y for x0, y in zip(x0_values, y_values, strict=True))
    t1 = sum(x1 * y for x1, y in zip(x1_values, y_values, strict=True))
    determinant = s00 * s11 - s01 * s01
    if abs(determinant) < 1e-12:
        return None, None
    return (t0 * s11 - t1 * s01) / determinant, (s00 * t1 - s01 * t0) / determinant


def fit_grid_multiplier(
    spans: list[UsageDeltaSpan], *, proxy: str, multiplier: float
) -> dict[str, float | None]:
    y_values = [span.delta_usage_percent for span in spans]
    x_values = [
        span.non_candidate_standard_credits.get(proxy, 0.0)
        + multiplier * span.candidate_standard_credits.get(proxy, 0.0)
        for span in spans
    ]
    slope = fit_one_feature_no_intercept(x_values, y_values)
    y_hat = [slope * value for value in x_values] if slope is not None else None
    return {
        "multiplier": multiplier,
        "pearson": rounded(pearson(x_values, y_values)),
        "r2_slope": rounded(r2(y_values, y_hat) if y_hat is not None else None),
        "slope_usage_pct_per_weighted_credit": rounded(slope),
    }


def fit_one_feature_no_intercept(x_values: list[float], y_values: list[float]) -> float | None:
    denominator = sum(x * x for x in x_values)
    if denominator <= 0:
        return None
    return sum(x * y for x, y in zip(x_values, y_values, strict=True)) / denominator


def documented_weighted_multiplier(
    spans: list[UsageDeltaSpan], proxy: str
) -> float | None:
    candidate = sum(span.candidate_standard_credits.get(proxy, 0.0) for span in spans)
    if candidate <= 0:
        return None
    documented_extra = sum(
        span.documented_fast_weighted_credits.get(proxy, 0.0)
        - span.non_candidate_standard_credits.get(proxy, 0.0)
        for span in spans
    )
    return documented_extra / candidate


def candidate_share_correlation(spans: list[UsageDeltaSpan], proxy: str) -> float | None:
    shares: list[float] = []
    drain_per_credit: list[float] = []
    for span in spans:
        total = span.standard_usage_credits
        if total <= 0:
            continue
        candidate = span.candidate_standard_credits.get(proxy, 0.0)
        shares.append(candidate / total)
        drain_per_credit.append(span.delta_usage_percent / total)
    return pearson(shares, drain_per_credit)


def drain_stats(spans: list[UsageDeltaSpan]) -> dict[str, float | int | None]:
    drains = [
        span.delta_usage_percent / span.standard_usage_credits
        for span in spans
        if span.standard_usage_credits > 0
    ]
    deltas = [span.delta_usage_percent for span in spans]
    return {
        "spans": len(spans),
        "median_delta_percent": rounded(median(deltas) if deltas else None),
        "median_drain_per_standard_credit": rounded(median(drains) if drains else None),
        "mean_drain_per_standard_credit": rounded(
            sum(drains) / len(drains) if drains else None
        ),
    }


def r2(y_values: list[float], y_hat: list[float] | None) -> float | None:
    if not y_values or y_hat is None or len(y_values) != len(y_hat):
        return None
    mean_y = sum(y_values) / len(y_values)
    sst = sum((value - mean_y) ** 2 for value in y_values)
    if sst <= 0:
        return None
    sse = sum(
        (actual - predicted) ** 2
        for actual, predicted in zip(y_values, y_hat, strict=True)
    )
    return 1.0 - (sse / sst)


def pearson(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) < 2 or len(x_values) != len(y_values):
        return None
    mean_x = sum(x_values) / len(x_values)
    mean_y = sum(y_values) / len(y_values)
    covariance = sum(
        (x - mean_x) * (y - mean_y)
        for x, y in zip(x_values, y_values, strict=True)
    )
    x_var = sum((x - mean_x) ** 2 for x in x_values)
    y_var = sum((y - mean_y) ** 2 for y in y_values)
    denominator = math.sqrt(x_var * y_var)
    if denominator <= 0:
        return None
    return covariance / denominator


def spearman(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) < 2 or len(x_values) != len(y_values):
        return None
    return pearson(rank_values(x_values), rank_values(y_values))


def rank_values(values: list[float]) -> list[float]:
    ordered = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0 for _value in values]
    index = 0
    while index < len(ordered):
        end_index = index
        while (
            end_index + 1 < len(ordered)
            and ordered[end_index + 1][0] == ordered[index][0]
        ):
            end_index += 1
        rank = ((index + 1) + (end_index + 1)) / 2.0
        for rank_index in range(index, end_index + 1):
            ranks[ordered[rank_index][1]] = rank
        index = end_index + 1
    return ranks


def count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "missing")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
