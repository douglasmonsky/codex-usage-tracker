from codex_usage_tracker.usage_drain_regression import (
    fit_linear_coefficients,
    predict_linear,
)


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
