"""Token-component regression diagnostics for usage-drain modeling."""

from __future__ import annotations

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
from codex_usage_tracker.usage_drain_types import TOKEN_COMPONENT_FIELDS, UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import rounded as _rounded


def token_component_regression_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    return {
        "feature_units": "tokens_per_million",
        "features": list(TOKEN_COMPONENT_FIELDS),
        "variants": {
            "unweighted": _token_component_regression_variant(
                spans,
                weighted_proxy=None,
                credit_target_label="standard_usage_credits",
            ),
            "high_medium_fast_weighted": _token_component_regression_variant(
                spans,
                weighted_proxy="high_medium_candidates",
                credit_target_label="high_medium_fast_weighted_credits",
            ),
        },
        "notes": [
            "visible_drain tests whether token components explain the selected 5-hour usage percentage delta.",
            "credit_accounting tests whether token components reconstruct the tracker rate-card credit estimate.",
            "The high_medium_fast_weighted variant multiplies medium/high fast-proxy token components by each row's documented model fast multiplier.",
        ],
    }


def _token_component_regression_variant(
    spans: list[UsageDeltaSpan],
    *,
    weighted_proxy: str | None,
    credit_target_label: str,
) -> dict[str, Any]:
    x_rows = [
        [
            value / 1_000_000.0
            for value in _span_token_components(
                span, weighted_proxy=weighted_proxy
            ).values()
        ]
        for span in spans
    ]
    visible_target = [span.delta_usage_percent for span in spans]
    credit_target = [
        span.documented_fast_weighted_credits.get(weighted_proxy, 0.0)
        if weighted_proxy
        else span.standard_usage_credits
        for span in spans
    ]
    candidate_rows = (
        sum(span.candidate_row_counts.get(weighted_proxy, 0) for span in spans)
        if weighted_proxy
        else 0
    )
    candidate_spans = (
        sum(1 for span in spans if span.candidate_row_counts.get(weighted_proxy, 0) > 0)
        if weighted_proxy
        else 0
    )
    return {
        "weighted_proxy": weighted_proxy,
        "candidate_rows": candidate_rows,
        "candidate_spans": candidate_spans,
        "visible_drain": _token_component_target_regression(
            x_rows, visible_target, target="delta_usage_percent"
        ),
        "credit_accounting": _token_component_target_regression(
            x_rows, credit_target, target=credit_target_label
        ),
    }


def _span_token_components(
    span: UsageDeltaSpan, *, weighted_proxy: str | None
) -> dict[str, float]:
    if weighted_proxy:
        weighted = span.documented_fast_weighted_token_totals.get(weighted_proxy)
        if weighted:
            return {
                field_name: weighted.get(field_name, 0.0)
                for field_name in TOKEN_COMPONENT_FIELDS
            }
    return {
        "uncached_input_tokens": span.token_totals.get("uncached_input_tokens", 0.0),
        "cached_input_tokens": span.token_totals.get("cached_input_tokens", 0.0),
        "reasoning_output_tokens": span.token_totals.get(
            "reasoning_output_tokens", 0.0
        ),
        "nonreasoning_output_tokens": max(
            span.token_totals.get("output_tokens", 0.0)
            - span.token_totals.get("reasoning_output_tokens", 0.0),
            0.0,
        ),
    }
def _token_component_target_regression(
    x_rows: list[list[float]], y_values: list[float], *, target: str
) -> dict[str, Any]:
    return {
        "target": target,
        "with_intercept": _token_component_fit_summary(
            x_rows, y_values, intercept=True
        ),
        "no_intercept": _token_component_fit_summary(
            x_rows, y_values, intercept=False
        ),
    }


def _token_component_fit_summary(
    x_rows: list[list[float]], y_values: list[float], *, intercept: bool
) -> dict[str, Any]:
    if len(x_rows) < 2 or len(x_rows) != len(y_values):
        return {
            "all": _regression_metrics([], []),
            "time_ordered_holdout_20": _regression_metrics([], []),
        }
    train_size = max(1, min(len(x_rows) - 1, int(len(x_rows) * 0.8)))
    all_coefficients = _fit_linear_regression_coefficients(
        x_rows, y_values, intercept=intercept
    )
    train_coefficients = _fit_linear_regression_coefficients(
        x_rows[:train_size], y_values[:train_size], intercept=intercept
    )
    all_predictions = _linear_regression_predictions(
        x_rows, all_coefficients, intercept=intercept
    )
    holdout_x = x_rows[train_size:]
    holdout_y = y_values[train_size:]
    holdout_predictions = _linear_regression_predictions(
        holdout_x, train_coefficients, intercept=intercept
    )
    return {
        "all": {
            **_regression_metrics(y_values, all_predictions),
            "coefficients": _component_coefficient_rows(
                all_coefficients, intercept=intercept
            ),
        },
        "time_ordered_holdout_20": {
            **_regression_metrics(holdout_y, holdout_predictions),
            "train_coefficients": _component_coefficient_rows(
                train_coefficients, intercept=intercept
            ),
        },
    }




def _component_coefficient_rows(
    coefficients: list[float], *, intercept: bool
) -> list[dict[str, Any]]:
    names = (["intercept"] if intercept else []) + list(TOKEN_COMPONENT_FIELDS)
    return [
        {"feature": name, "coefficient": _rounded(coefficient)}
        for name, coefficient in zip(names, coefficients, strict=True)
    ]

def one_percent_capacity_component_regression(
    spans: list[UsageDeltaSpan],
) -> dict[str, Any]:
    return {
        "feature_units": "tokens_per_million",
        "features": list(TOKEN_COMPONENT_FIELDS),
        "target": "usage_credits_inside_exact_one_percent_spans",
        "variants": {
            "unweighted": _one_percent_capacity_component_variant(
                spans,
                weighted_proxy=None,
                credit_target_label="standard_usage_credits",
            ),
            "high_medium_fast_weighted": _one_percent_capacity_component_variant(
                spans,
                weighted_proxy="high_medium_candidates",
                credit_target_label="high_medium_fast_weighted_credits",
            ),
        },
        "notes": [
            "This is an accounting check for work inside exact 1% ticks, not an advance prediction of when the tick will occur.",
            "A near-perfect fit is expected when the local credit target is computed from these same token components and rate-card coefficients.",
        ],
    }


def _one_percent_capacity_component_variant(
    spans: list[UsageDeltaSpan],
    *,
    weighted_proxy: str | None,
    credit_target_label: str,
) -> dict[str, Any]:
    x_rows = [
        [
            value / 1_000_000.0
            for value in _span_token_components(
                span, weighted_proxy=weighted_proxy
            ).values()
        ]
        for span in spans
    ]
    credit_target = [
        span.documented_fast_weighted_credits.get(weighted_proxy, 0.0)
        if weighted_proxy
        else span.standard_usage_credits
        for span in spans
    ]
    candidate_rows = (
        sum(span.candidate_row_counts.get(weighted_proxy, 0) for span in spans)
        if weighted_proxy
        else 0
    )
    candidate_spans = (
        sum(1 for span in spans if span.candidate_row_counts.get(weighted_proxy, 0) > 0)
        if weighted_proxy
        else 0
    )
    return {
        "weighted_proxy": weighted_proxy,
        "candidate_rows": candidate_rows,
        "candidate_spans": candidate_spans,
        "capacity_credits": _token_component_target_regression(
            x_rows, credit_target, target=credit_target_label
        ),
    }
