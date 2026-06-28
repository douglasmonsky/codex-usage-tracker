"""Candidate proxy fit helpers for usage-drain modeling."""

from __future__ import annotations

from codex_usage_tracker.usage_drain_regression import (
    candidate_share_correlation as _candidate_share_correlation,
)
from codex_usage_tracker.usage_drain_regression import (
    documented_weighted_multiplier as _documented_weighted_multiplier,
)
from codex_usage_tracker.usage_drain_regression import drain_stats as _drain_stats
from codex_usage_tracker.usage_drain_regression import (
    fit_grid_multiplier as _fit_grid_multiplier,
)
from codex_usage_tracker.usage_drain_regression import (
    fit_two_feature_no_intercept as _fit_two_feature_no_intercept,
)
from codex_usage_tracker.usage_drain_regression import r2 as _r2
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan, UsageDrainModelResult
from codex_usage_tracker.usage_drain_utils import number as _number
from codex_usage_tracker.usage_drain_utils import rounded as _rounded


def fit_usage_drain_proxy(
    spans: list[UsageDeltaSpan],
    proxy: str,
    *,
    grid_multipliers: tuple[float, ...] = (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0),
) -> UsageDrainModelResult:
    """Fit usage-drain deltas against candidate and non-candidate credits."""

    y_values = [span.delta_usage_percent for span in spans]
    candidate_values = [span.candidate_standard_credits.get(proxy, 0.0) for span in spans]
    non_candidate_values = [
        span.non_candidate_standard_credits.get(proxy, 0.0) for span in spans
    ]
    candidate_spans = sum(1 for value in candidate_values if value > 0)
    beta_non, beta_candidate = _fit_two_feature_no_intercept(
        non_candidate_values, candidate_values, y_values
    )
    implied_multiplier = (
        beta_candidate / beta_non
        if beta_non is not None and beta_candidate is not None and beta_non > 0
        else None
    )
    y_hat = (
        [
            (beta_non or 0.0) * non_candidate
            + (beta_candidate or 0.0) * candidate
            for non_candidate, candidate in zip(
                non_candidate_values, candidate_values, strict=True
            )
        ]
        if beta_non is not None and beta_candidate is not None
        else None
    )
    grid = [
        _fit_grid_multiplier(spans, proxy=proxy, multiplier=multiplier)
        for multiplier in grid_multipliers
    ]
    valid_grid = [item for item in grid if item.get("r2_slope") is not None]
    best_grid = max(
        valid_grid,
        key=lambda item: _number(item.get("r2_slope")),
        default=None,
    )
    best_grid_multiplier = (
        _number(best_grid.get("multiplier")) if best_grid is not None else None
    )
    with_candidates = _drain_stats(
        [
            span
            for span, candidate in zip(spans, candidate_values, strict=True)
            if candidate > 0 and span.standard_usage_credits > 0
        ]
    )
    without_candidates = _drain_stats(
        [
            span
            for span, candidate in zip(spans, candidate_values, strict=True)
            if candidate <= 0 and span.standard_usage_credits > 0
        ]
    )
    median_ratio = (
        float(with_candidates["median_drain_per_standard_credit"])
        / float(without_candidates["median_drain_per_standard_credit"])
        if with_candidates["median_drain_per_standard_credit"]
        and without_candidates["median_drain_per_standard_credit"]
        else None
    )
    documented_multiplier = _documented_weighted_multiplier(spans, proxy)
    return UsageDrainModelResult(
        proxy=proxy,
        spans=len(spans),
        candidate_spans=candidate_spans,
        candidate_span_share=round(candidate_spans / len(spans), 6) if spans else 0.0,
        coef_non_candidate_usage_pct_per_credit=_rounded(beta_non),
        coef_candidate_usage_pct_per_credit=_rounded(beta_candidate),
        implied_candidate_multiplier=_rounded(implied_multiplier),
        documented_weighted_candidate_multiplier=_rounded(documented_multiplier),
        two_feature_r2=_rounded(_r2(y_values, y_hat) if y_hat is not None else None),
        grid=grid,
        best_grid_multiplier_by_r2=best_grid_multiplier,
        corr_candidate_credit_share_vs_drain_per_standard_credit=_rounded(
            _candidate_share_correlation(spans, proxy)
        ),
        spans_with_candidates=with_candidates,
        spans_without_candidates=without_candidates,
        with_vs_without_median_drain_ratio=_rounded(median_ratio),
    )
