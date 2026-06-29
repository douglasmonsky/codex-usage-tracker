"""Aggregate-only helpers for modeling observed Codex usage drain.

This module compares local aggregate token-credit estimates with visible
rate-limit usage percentage deltas. It intentionally treats usage drain as a
coarse observed signal, not as billing truth.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

from codex_usage_tracker import usage_drain_allowance_breakpoints as allowance_breakpoints
from codex_usage_tracker import usage_drain_regime_segments as regime_segments
from codex_usage_tracker import usage_drain_token_components as token_components
from codex_usage_tracker import usage_drain_walk_forward as walk_forward
from codex_usage_tracker.usage_drain_capacity_specs import (
    capacity_model_specs as _capacity_model_specs,
)
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_feature_history import (
    is_one_percent_delta as _is_one_percent_delta,
)
from codex_usage_tracker.usage_drain_feature_history import (
    previous_value as _previous_value,
)
from codex_usage_tracker.usage_drain_feature_history import (
    rolling_mean as _rolling_mean,
)
from codex_usage_tracker.usage_drain_feature_history import (
    rolling_median as _rolling_median,
)
from codex_usage_tracker.usage_drain_feature_history import (
    rolling_stddev as _rolling_stddev,
)
from codex_usage_tracker.usage_drain_features import (
    add_days_since_first_span as _add_days_since_first_span,
)
from codex_usage_tracker.usage_drain_features import (
    span_feature_row as _span_feature_row,
)
from codex_usage_tracker.usage_drain_predictive import (
    baseline_predictions as _baseline_predictions,
)
from codex_usage_tracker.usage_drain_predictive import (
    capacity_residual_diagnostics as _capacity_residual_diagnostics,
)
from codex_usage_tracker.usage_drain_predictive import (
    fit_predictive_model as _fit_predictive_model,
)
from codex_usage_tracker.usage_drain_predictive import (
    fit_predictive_usage_drain_models,
)
from codex_usage_tracker.usage_drain_predictive import (
    split_feature_rows as _split_feature_rows,
)
from codex_usage_tracker.usage_drain_proxy_fit import fit_usage_drain_proxy
from codex_usage_tracker.usage_drain_regression import (
    count_values as _count_values,
)
from codex_usage_tracker.usage_drain_regression import (
    regression_metrics as _regression_metrics,
)
from codex_usage_tracker.usage_drain_spans import (
    build_usage_delta_spans,
    load_fast_proxy_annotations,  # noqa: F401
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    SPAN_CAPACITY_CORRELATION_FEATURES,
    SPAN_RAW_CORRELATION_FEATURES,
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    best_holdout_model as _best_holdout_model,
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    capacity_family_sequences as _capacity_family_sequences,
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    correlation_report as _correlation_report,
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    model_family_attribution as _model_family_attribution,
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    span_correlation_row as _span_correlation_row,
)
from codex_usage_tracker.usage_drain_summary_metrics import (
    visible_delta_family_sequences as _visible_delta_family_sequences,
)
from codex_usage_tracker.usage_drain_types import (
    DEFAULT_PROXY_NAMES,
    DOCUMENTED_FAST_CREDIT_MULTIPLIERS,
    TIMING_TOTAL_FIELDS,  # noqa: F401
    FastProxyAnnotation,
    UsageDeltaSpan,
    documented_fast_credit_multiplier,  # noqa: F401
)
from codex_usage_tracker.usage_drain_utils import (
    number as _number,
)

ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE = 20
ALLOWANCE_BREAKPOINT_MAX_SEGMENTS = 6
ALLOWANCE_BREAKPOINT_MIN_REDUCTION_SHARE = 0.12

USAGE_DRAIN_MODEL_SCHEMA = "codex-usage-tracker-usage-drain-model-v1"
def summarize_usage_drain_model(
    rows: list[dict[str, Any]],
    *,
    fast_proxy_annotations: dict[str, FastProxyAnnotation] | None = None,
) -> dict[str, Any]:
    """Return a schema-versioned usage-drain modeling payload."""

    spans, span_stats = build_usage_delta_spans(
        rows,
        fast_proxy_annotations=fast_proxy_annotations,
    )
    results = [fit_usage_drain_proxy(spans, proxy).to_dict() for proxy in DEFAULT_PROXY_NAMES]
    predictive_models = fit_predictive_usage_drain_models(spans, proxy="all_candidates")
    best_predictive_r2_model = max(
        predictive_models,
        key=lambda result: _number(result.get("holdout", {}).get("r2")),
        default=None,
    )
    best_predictive_mae_model = min(
        predictive_models,
        key=lambda result: _number(result.get("holdout", {}).get("mae"))
        if result.get("holdout", {}).get("mae") is not None
        else math.inf,
        default=None,
    )
    return {
        "schema": USAGE_DRAIN_MODEL_SCHEMA,
        "source_rows": len(rows),
        "span_stats": span_stats,
        "model_mix": _count_values(rows, "model"),
        "rate_limit_plan_type_mix": _count_values(rows, "rate_limit_plan_type"),
        "rate_limit_limit_id_mix": _count_values(rows, "rate_limit_limit_id"),
        "delta_regimes": regime_segments.delta_regime_summary(spans),
        "regime_streaks": regime_segments.regime_streak_summary(spans),
        "piecewise_regime_segments": regime_segments.piecewise_regime_segment_summary(spans),
        "span_correlations": _span_correlation_summary(spans),
        "token_component_regression": token_components.token_component_regression_summary(spans),
        "one_percent_capacity_modeling": _one_percent_capacity_modeling(spans),
        "allowance_breakpoint_analysis": allowance_breakpoints.allowance_breakpoint_analysis(spans),
        "walk_forward_prediction": walk_forward.walk_forward_prediction_summary(spans),
        "documented_fast_multipliers": dict(DOCUMENTED_FAST_CREDIT_MULTIPLIERS),
        "available_signals": {
            "direct_fast_mode_flag": False,
            "aggregate_tokens": [
                "input_tokens",
                "cached_input_tokens",
                "uncached_input_tokens",
                "output_tokens",
                "reasoning_output_tokens",
                "total_tokens",
            ],
            "observed_usage_snapshots": [
                "selected 5-hour usage window when present",
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "rate_limit_primary_used_percent",
                "rate_limit_primary_window_minutes",
                "rate_limit_primary_resets_at",
                "rate_limit_secondary_used_percent",
                "rate_limit_secondary_window_minutes",
                "rate_limit_secondary_resets_at",
            ],
            "timing": [
                "event_timestamp",
                "turn_timestamp",
                "call_started_at",
                "call_duration_seconds",
                "previous_call_delta_seconds",
                "span_wall_time_seconds",
            ],
            "controls": [
                "model",
                "effort",
                "thread_key",
                "session_id",
                "cwd",
                "date",
                "day_of_week",
                "hour_of_day",
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "rate_limit_primary_window_minutes",
                "rate_limit_primary_resets_at",
                "one_percent_streak",
                "low_delta_streak",
                "same_delta_streak",
                "one_percent_regime_grace",
            ],
        },
        "limitations": [
            "Visible usage percentages are coarse snapshots, not exact per-call credit debits.",
            "Rows with unchanged usage are assigned to the next positive delta span.",
            "Bucket changes and usage percentage decreases are censored.",
            "The public aggregate logs do not expose a direct fast-mode flag.",
            "Local logs can omit usage from other agentic surfaces sharing the same allowance.",
        ],
        "results": results,
        "predictive_modeling": {
            "proxy": "all_candidates",
            "splits": ["time_ordered_80_20", "interleaved_every_5th"],
            "best_by_holdout_r2": best_predictive_r2_model["name"]
            if best_predictive_r2_model
            else None,
            "best_by_holdout_mae": best_predictive_mae_model["name"]
            if best_predictive_mae_model
            else None,
            "feature_family_attribution": _model_family_attribution(
                predictive_models, _visible_delta_family_sequences()
            ),
            "models": predictive_models,
        },
    }


def _span_correlation_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    rows = [_span_correlation_row(span) for span in spans]
    one_percent_rows = [
        row for row in rows if _is_one_percent_delta(row["delta_usage_percent"])
    ]
    latest_rows = rows[-500:]
    return {
        "delta_usage_percent": _correlation_report(
            rows,
            target="delta_usage_percent",
            feature_names=SPAN_RAW_CORRELATION_FEATURES,
        ),
        "delta_usage_percent_latest_500": _correlation_report(
            latest_rows,
            target="delta_usage_percent",
            feature_names=SPAN_RAW_CORRELATION_FEATURES,
        ),
        "one_percent_span_capacity": {
            "note": (
                "For exact 1% spans, these describe how much aggregate work fits "
                "inside one visible counter tick."
            ),
            "standard_usage_credits": _correlation_report(
                one_percent_rows,
                target="standard_usage_credits",
                feature_names=SPAN_CAPACITY_CORRELATION_FEATURES,
            ),
            "total_tokens": _correlation_report(
                one_percent_rows,
                target="total_tokens",
                feature_names=SPAN_CAPACITY_CORRELATION_FEATURES,
            ),
            "row_count": _correlation_report(
                one_percent_rows,
                target="row_count",
                feature_names=SPAN_CAPACITY_CORRELATION_FEATURES,
            ),
        },
    }


def _one_percent_capacity_modeling(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    one_percent_spans = [
        span for span in spans if _is_one_percent_delta(span.delta_usage_percent)
    ]
    rows = [_one_percent_capacity_row(span) for span in one_percent_spans]
    if len(rows) < 10:
        return _empty_one_percent_capacity_modeling(one_percent_spans, rows)

    _prepare_one_percent_capacity_rows(rows)
    models = _fit_one_percent_capacity_models(rows)
    return _one_percent_capacity_modeling_report(one_percent_spans, rows, models)


def _empty_one_percent_capacity_modeling(
    one_percent_spans: list[UsageDeltaSpan], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "target": "standard_usage_credits",
        "target_description": (
            "Aggregate standard usage credits inside exact 1% visible-counter spans."
        ),
        "span_count": len(rows),
        "splits": ["time_ordered_80_20", "interleaved_every_5th"],
        "best_by_holdout_mae": None,
        "best_causal_by_holdout_mae": None,
        "token_component_regression": token_components.one_percent_capacity_component_regression(
            one_percent_spans
        ),
        "models": [],
    }


def _prepare_one_percent_capacity_rows(rows: list[dict[str, Any]]) -> None:
    _add_days_since_first_span(rows)
    _add_capacity_history_features(rows)


def _fit_one_percent_capacity_models(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for split_name, train_rows, holdout_rows in _split_feature_rows(
        rows, train_fraction=0.8
    ):
        models.extend(_fit_capacity_baseline_models(train_rows, holdout_rows, split_name))
        models.extend(
            _fit_one_percent_capacity_predictive_models(
                train_rows, holdout_rows, split_name
            )
        )
    return models


def _fit_one_percent_capacity_predictive_models(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    split_name: str,
) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for spec, kind in _capacity_model_specs():
        fitted = _fit_predictive_model(
            train_rows,
            holdout_rows,
            spec,
            include_capacity_residual_diagnostics=True,
        )
        if fitted is not None:
            _annotate_one_percent_capacity_model(fitted, spec.name, split_name, kind)
            models.append(fitted)
    return models


def _annotate_one_percent_capacity_model(
    fitted: dict[str, Any], spec_name: str, split_name: str, kind: str
) -> None:
    fitted["validation"] = split_name
    fitted["kind"] = kind
    fitted["name"] = f"{spec_name}__{split_name}"


def _one_percent_capacity_modeling_report(
    one_percent_spans: list[UsageDeltaSpan],
    rows: list[dict[str, Any]],
    models: list[dict[str, Any]],
) -> dict[str, Any]:
    best_model = _best_holdout_model(models)
    best_causal = _best_holdout_model(_causal_one_percent_capacity_models(models))
    return {
        "target": "standard_usage_credits",
        "target_description": (
            "Aggregate standard usage credits inside exact 1% visible-counter spans."
        ),
        "span_count": len(rows),
        "target_distribution": _value_distribution(
            [_number(row.get("target")) for row in rows]
        ),
        "splits": ["time_ordered_80_20", "interleaved_every_5th"],
        "best_by_holdout_mae": best_model["name"] if best_model else None,
        "best_causal_by_holdout_mae": best_causal["name"] if best_causal else None,
        "token_component_regression": token_components.one_percent_capacity_component_regression(
            one_percent_spans
        ),
        "feature_family_attribution": _model_family_attribution(
            models, _capacity_family_sequences()
        ),
        "models": models,
        "notes": _one_percent_capacity_modeling_notes(),
    }


def _causal_one_percent_capacity_models(
    models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [model for model in models if model.get("kind") != "explanatory_same_span"]


def _one_percent_capacity_modeling_notes() -> list[str]:
    return [
        "Causal/history models use prior closed spans plus start-time context.",
        "Explanatory same-span models use work observed inside span should not treated advance predictions.",
    ]


def _one_percent_capacity_row(span: UsageDeltaSpan) -> dict[str, Any]:
    row = _span_feature_row(span, proxy="all_candidates")
    row["target"] = span.standard_usage_credits
    row["log_target"] = math.log1p(max(span.standard_usage_credits, 0.0))
    return row


def _add_capacity_history_features(rows: list[dict[str, Any]]) -> None:
    previous_rows: list[dict[str, Any]] = []
    hour_rows: dict[str, list[dict[str, Any]]] = {}
    day_of_week_rows: dict[str, list[dict[str, Any]]] = {}
    ewma_target: float | None = None
    alpha = 0.2
    for row in rows:
        hour_key = str(row.get("hour_bucket") or "missing")
        day_of_week_key = str(row.get("day_of_week") or "missing")
        recent_hour_rows = hour_rows.get(hour_key, [])
        recent_day_of_week_rows = day_of_week_rows.get(day_of_week_key, [])
        row["previous_capacity_credits"] = _previous_value(previous_rows, "target")
        row["rolling3_capacity_credits"] = _rolling_mean(previous_rows, "target", 3)
        row["rolling10_capacity_credits"] = _rolling_mean(previous_rows, "target", 10)
        row["rolling10_capacity_median"] = _rolling_median(previous_rows, "target", 10)
        row["rolling10_capacity_stddev"] = _rolling_stddev(previous_rows, "target", 10)
        row["same_hour_rolling10_capacity_credits"] = _rolling_mean(
            recent_hour_rows, "target", 10
        )
        row["same_hour_seen_count"] = float(len(recent_hour_rows))
        row["same_day_of_week_rolling10_capacity_credits"] = _rolling_mean(
            recent_day_of_week_rows, "target", 10
        )
        row["same_day_of_week_seen_count"] = float(len(recent_day_of_week_rows))
        row["ewma_capacity_credits"] = ewma_target or 0.0

        current_target = _number(row.get("target"))
        ewma_target = (
            current_target
            if ewma_target is None
            else (alpha * current_target) + ((1 - alpha) * ewma_target)
        )
        previous_rows.append(row)
        hour_rows.setdefault(hour_key, []).append(row)
        day_of_week_rows.setdefault(day_of_week_key, []).append(row)


def _fit_capacity_baseline_models(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    split_name: str,
) -> list[dict[str, Any]]:
    train_y = [_number(row.get("target")) for row in train_rows]
    holdout_y = [_number(row.get("target")) for row in holdout_rows]
    train_mean = sum(train_y) / len(train_y) if train_y else 0.0
    baselines: list[tuple[str, str | None, float | None]] = [
        ("capacity_train_mean", None, train_mean),
        ("capacity_previous", "previous_capacity_credits", None),
        ("capacity_rolling3", "rolling3_capacity_credits", None),
        ("capacity_rolling10", "rolling10_capacity_credits", None),
        ("capacity_rolling10_median", "rolling10_capacity_median", None),
        ("capacity_ewma", "ewma_capacity_credits", None),
        (
            "capacity_same_hour_rolling10",
            "same_hour_rolling10_capacity_credits",
            None,
        ),
        (
            "capacity_same_day_of_week_rolling10",
            "same_day_of_week_rolling10_capacity_credits",
            None,
        ),
    ]
    results: list[dict[str, Any]] = []
    for name, feature_field, constant in baselines:
        train_predictions = _baseline_predictions(
            train_rows, field=feature_field, constant=constant
        )
        holdout_predictions = _baseline_predictions(
            holdout_rows, field=feature_field, constant=constant
        )
        results.append(
            {
                "name": f"{name}__{split_name}",
                "validation": split_name,
                "kind": "capacity_causal_baseline",
                "feature_count": 1 if feature_field or constant is not None else 0,
                "numeric_features": [feature_field] if feature_field else [],
                "categorical_features": [],
                "train": _regression_metrics(train_y, train_predictions),
                "holdout": _regression_metrics(holdout_y, holdout_predictions),
                "holdout_error_diagnostics": _capacity_residual_diagnostics(
                    holdout_rows, holdout_y, holdout_predictions
                ),
                "top_coefficients": [],
            }
        )
    return results




def write_usage_drain_spans_csv(spans: list[UsageDeltaSpan], path: Path) -> Path:
    """Write modeled spans to a local CSV artifact."""

    path.parent.mkdir(parents=True, exist_ok=True)
    empty_span = UsageDeltaSpan("", "", 0, 0, 0, 0, 0, {}, {}, {}, {})
    fieldnames = list(spans[0].to_row()) if spans else list(empty_span.to_row())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for span in spans:
            writer.writerow(span.to_row())
    return path
