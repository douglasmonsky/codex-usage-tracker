from codex_usage_tracker.usage_drain_regression import (
    fit_linear_coefficients,
    predict_linear,
    prepare_design,
)
from codex_usage_tracker.usage_drain_types import PredictiveModelSpec


def test_prepare_design_returns_none_for_empty_rows() -> None:
    spec = PredictiveModelSpec("fixture", ("tokens",), ("mode",))

    assert prepare_design([], spec) is None


def test_prepare_design_standardizes_numeric_and_filters_sparse_categories() -> None:
    spec = PredictiveModelSpec("fixture", ("tokens", "duration"), ("mode",))
    rows = [
        {"tokens": 2.0, "duration": 1.0, "mode": "A"},
        {"tokens": 4.0, "duration": 3.0, "mode": "A"},
        {"tokens": 6.0, "duration": 5.0, "mode": "B"},
    ]

    feature_names, means, stddevs, category_levels = prepare_design(rows, spec)

    assert feature_names == ["tokens", "duration", "mode=A"]
    assert means == {"tokens": 4.0, "duration": 3.0}
    assert round(stddevs["tokens"], 6) == 1.632993
    assert round(stddevs["duration"], 6) == 1.632993
    assert category_levels == {"mode": ["A"]}


def test_fit_linear_coefficients_with_intercept() -> None:
    x_rows = [[1.0], [2.0], [3.0]]
    y_values = [3.0, 5.0, 7.0]

    coefficients = fit_linear_coefficients(x_rows, y_values, intercept=True)

    assert coefficients == [1.0, 2.0]
    assert predict_linear(x_rows, coefficients, intercept=True) == y_values


def test_fit_linear_coefficients_without_intercept() -> None:
    x_rows = [[1.0], [2.0], [3.0]]
    y_values = [2.0, 4.0, 6.0]

    coefficients = fit_linear_coefficients(x_rows, y_values, intercept=False)

    assert coefficients == [2.0]
    assert predict_linear(x_rows, coefficients, intercept=False) == y_values


def test_fit_linear_coefficients_uses_ridge_fallback_for_singular_design() -> None:
    x_rows = [[1.0, 2.0], [1.0, 2.0]]
    y_values = [3.0, 3.0]

    coefficients = fit_linear_coefficients(x_rows, y_values, intercept=True)

    assert coefficients == [3.0, 0.0, -0.0]
    assert predict_linear(x_rows, coefficients, intercept=True) == y_values


def test_fit_linear_coefficients_returns_zeroes_when_unsolvable() -> None:
    x_rows = [[0.0], [0.0]]
    y_values = [1.0, 2.0]

    coefficients = fit_linear_coefficients(x_rows, y_values, intercept=False)

    assert coefficients == [0.0]
