"""Shared summary metrics for usage-drain analysis."""

from __future__ import annotations

import math
from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain.regression import pearson, spearman
from codex_usage_tracker.usage_drain.types import TOKEN_TOTAL_FIELDS, UsageDeltaSpan
from codex_usage_tracker.usage_drain.utils import (
    number,
    rounded,
    span_wall_time_seconds,
    value_stddev,
)

SPAN_RAW_CORRELATION_FEATURES = (
    "row_count",
    "standard_usage_credits",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "call_duration_seconds",
    "previous_call_delta_seconds",
    "span_wall_time_seconds",
    "baseline_used_percent",
)


SPAN_CAPACITY_CORRELATION_FEATURES = (
    "row_count",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "call_duration_seconds",
    "previous_call_delta_seconds",
    "span_wall_time_seconds",
    "baseline_used_percent",
)


def visible_delta_family_sequences() -> dict[str, list[tuple[str, str]]]:
    return {
        "cost_and_time_controls": [
            ("train mean", "baseline_train_mean"),
            ("credits", "credits_only"),
            ("token shape", "token_shape"),
            ("turn batching", "turn_batching"),
            ("fast proxy", "fast_proxy"),
            ("effort", "effort_controls"),
            ("online capacity", "online_capacity_controls"),
            ("usage state", "usage_state"),
            ("cyclic time", "time_controls"),
            ("date/day/hour categories", "date_day_hour_controls"),
            ("duration and wall time", "full_controls"),
        ],
        "history_regime_controls": [
            ("usage state", "usage_state"),
            ("history/regime", "lag_regime"),
            ("history plus cyclic time", "lag_time_controls"),
            ("history plus date and wall time", "adaptive_full_controls"),
        ],
    }


def capacity_family_sequences() -> dict[str, list[tuple[str, str]]]:
    return {
        "causal_capacity_controls": [
            ("train mean", "capacity_train_mean"),
            ("start context", "capacity_start_context"),
            ("date/hour context", "capacity_date_hour_context"),
            ("state buckets", "capacity_state_bucket_context"),
            ("history", "capacity_history_context"),
            ("history plus buckets", "capacity_history_state_buckets"),
            ("history plus interactions", "capacity_history_state_interactions"),
            ("regularized interactions", "capacity_history_state_interactions_ridge100"),
        ],
        "same_span_capacity_controls": [
            ("train mean", "capacity_train_mean"),
            ("same-span shape", "capacity_same_span_shape"),
            ("shape buckets", "capacity_same_span_shape_buckets"),
            ("shape interactions", "capacity_same_span_shape_interactions"),
            (
                "regularized shape interactions",
                "capacity_same_span_shape_interactions_ridge30",
            ),
            ("same-span tokens", "capacity_same_span_tokens"),
        ],
    }


def model_family_attribution(
    models: list[dict[str, Any]],
    sequences: dict[str, list[tuple[str, str]]],
) -> dict[str, Any]:
    by_key, validations = _model_family_lookup(models)
    return {
        "metric_notes": [
            "mae_improvement_vs_previous is positive when the later family reduces holdout MAE.",
            "Sequences are diagnostic comparisons between named model families, not causal proof that one field caused gain.",
        ],
        "sequences": _model_family_sequence_results(
            sequences=sequences,
            validations=validations,
            by_key=by_key,
        ),
    }


def _model_family_lookup(
    models: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], dict[str, Any]], list[str]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    validations: list[str] = []
    for model in models:
        validation = str(model.get("validation") or "missing")
        if validation not in validations:
            validations.append(validation)
        base_name = model_base_name(model, validation)
        by_key[(validation, base_name)] = model
    return by_key, validations


def _model_family_sequence_results(
    *,
    sequences: dict[str, list[tuple[str, str]]],
    validations: list[str],
    by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    return {
        sequence_name: _model_family_validation_rows(
            steps=steps,
            validations=validations,
            by_key=by_key,
        )
        for sequence_name, steps in sequences.items()
    }


def _model_family_validation_rows(
    *,
    steps: list[tuple[str, str]],
    validations: list[str],
    by_key: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        validation: _model_family_rows_for_validation(
            steps=steps,
            validation=validation,
            by_key=by_key,
        )
        for validation in validations
    }


def _model_family_rows_for_validation(
    *,
    steps: list[tuple[str, str]],
    validation: str,
    by_key: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_mae: float | None = None
    previous_r2: float | None = None
    for family, base_name in steps:
        matched_model = by_key.get((validation, base_name))
        if matched_model is None:
            continue
        mae = holdout_metric(matched_model, "mae")
        r2 = holdout_metric(matched_model, "r2")
        rows.append(_model_family_row(family, matched_model, mae, r2, previous_mae, previous_r2))
        previous_mae = mae
        previous_r2 = r2
    return rows


def _model_family_row(
    family: str,
    matched_model: dict[str, Any],
    mae: float | None,
    r2: float | None,
    previous_mae: float | None,
    previous_r2: float | None,
) -> dict[str, Any]:
    return {
        "family": family,
        "model": matched_model.get("name"),
        "holdout_mae": rounded(mae),
        "holdout_r2": rounded(r2),
        "mae_improvement_vs_previous": _model_metric_improvement(previous_mae, mae),
        "r2_delta_vs_previous": _model_metric_delta(previous_r2, r2),
    }


def _model_metric_delta(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None:
        return None
    return rounded(current - previous)


def _model_metric_improvement(previous: float | None, current: float | None) -> float | None:
    if previous is None or current is None:
        return None
    return rounded(previous - current)


def model_base_name(model: dict[str, Any], validation: str) -> str:
    name = str(model.get("name") or "")
    suffix = f"__{validation}"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return name.rsplit("__", 1)[0]


def holdout_metric(model: dict[str, Any], metric: str) -> float | None:
    holdout = model.get("holdout")
    if not isinstance(holdout, dict):
        return None
    value = holdout.get(metric)
    if value is None:
        return None
    return number(value)


def best_holdout_model(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    return min(
        models,
        key=lambda result: (
            number(result.get("holdout", {}).get("mae"))
            if result.get("holdout", {}).get("mae") is not None
            else math.inf
        ),
        default=None,
    )


def span_correlation_row(span: UsageDeltaSpan) -> dict[str, float]:
    row = {
        "delta_usage_percent": span.delta_usage_percent,
        "row_count": float(span.row_count),
        "standard_usage_credits": span.standard_usage_credits,
        "call_duration_seconds": span.timing_totals.get("call_duration_seconds", 0.0),
        "previous_call_delta_seconds": span.timing_totals.get("previous_call_delta_seconds", 0.0),
        "span_wall_time_seconds": span_wall_time_seconds(span),
        "baseline_used_percent": span.baseline_used_percent,
    }
    for field_name in TOKEN_TOTAL_FIELDS:
        row[field_name] = span.token_totals.get(field_name, 0.0)
    return row


def correlation_report(
    rows: list[dict[str, float]], *, target: str, feature_names: tuple[str, ...]
) -> dict[str, Any]:
    if not rows:
        return {
            "n": 0,
            "target": target,
            "target_mean": None,
            "target_stddev": None,
            "top_abs_pearson": [],
            "top_abs_spearman": [],
        }
    target_values = [row[target] for row in rows]
    correlations = [
        {
            "feature": feature_name,
            "pearson": rounded(pearson([row[feature_name] for row in rows], target_values)),
            "spearman": rounded(spearman([row[feature_name] for row in rows], target_values)),
        }
        for feature_name in feature_names
        if feature_name != target
    ]
    return {
        "n": len(rows),
        "target": target,
        "target_mean": rounded(sum(target_values) / len(target_values)),
        "target_stddev": rounded(value_stddev(target_values)),
        "top_abs_pearson": sorted(
            correlations,
            key=lambda row: abs(number(row["pearson"])),
            reverse=True,
        )[:10],
        "top_abs_spearman": sorted(
            correlations,
            key=lambda row: abs(number(row["spearman"])),
            reverse=True,
        )[:10],
    }


def delta_distribution(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    values = [span.delta_usage_percent for span in spans]
    if not values:
        return {
            "spans": 0,
            "mean_delta_percent": None,
            "median_delta_percent": None,
            "std_delta_percent": None,
            "min_delta_percent": None,
            "max_delta_percent": None,
            "one_percent_share": None,
            "top_delta_values": [],
        }
    mean_value = sum(values) / len(values)
    counts: dict[float, int] = {}
    for value in values:
        rounded_value = round(value, 6)
        counts[rounded_value] = counts.get(rounded_value, 0) + 1
    top_values = [
        {
            "delta_percent": value,
            "count": count,
            "share": rounded(count / len(values)),
        }
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    return {
        "spans": len(values),
        "mean_delta_percent": rounded(mean_value),
        "median_delta_percent": rounded(median(values)),
        "std_delta_percent": rounded(
            math.sqrt(sum((value - mean_value) ** 2 for value in values) / len(values))
        ),
        "min_delta_percent": rounded(min(values)),
        "max_delta_percent": rounded(max(values)),
        "one_percent_share": rounded(
            sum(1 for value in values if round(value, 6) == 1.0) / len(values)
        ),
        "top_delta_values": top_values,
    }
