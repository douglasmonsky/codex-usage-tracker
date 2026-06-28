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
from codex_usage_tracker import usage_drain_boundary_summary as boundary_summary
from codex_usage_tracker import usage_drain_regime_labels as regime_labels
from codex_usage_tracker import usage_drain_token_components as token_components
from codex_usage_tracker import usage_drain_walk_forward as walk_forward
from codex_usage_tracker.usage_drain_capacity_specs import (
    capacity_model_specs as _capacity_model_specs,
)
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_feature_history import (
    date_label as _date_label,
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
    delta_distribution as _delta_distribution,
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
from codex_usage_tracker.usage_drain_utils import (
    rounded as _rounded,
)

ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE = 20
ALLOWANCE_BREAKPOINT_MAX_SEGMENTS = 6
ALLOWANCE_BREAKPOINT_MIN_REDUCTION_SHARE = 0.12

USAGE_DRAIN_MODEL_SCHEMA = "codex-usage-tracker-usage-drain-model-v1"
SEGMENT_PREDICTION_MODELS = (
    "constant_one_percent",
    "previous_delta",
    "one_percent_regime_grace",
    "empirical_reset_state_mode",
)
SEGMENT_POSITION_BUCKETS = (
    "first_span",
    "second_span",
    "third_span",
    "fourth_fifth_span",
    "sixth_plus_span",
)
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
        "delta_regimes": _delta_regime_summary(spans),
        "regime_streaks": _regime_streak_summary(spans),
        "piecewise_regime_segments": _piecewise_regime_segment_summary(spans),
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


def _delta_regime_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    train_size = max(1, min(len(spans) - 1, int(len(spans) * 0.8))) if spans else 0
    return {
        "all_spans": _delta_distribution(spans),
        "time_ordered_train_80": _delta_distribution(spans[:train_size]),
        "time_ordered_holdout_20": _delta_distribution(spans[train_size:]),
        "latest_100": _delta_distribution(spans[-100:]),
        "latest_25": _delta_distribution(spans[-25:]),
    }


def _regime_streak_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    one_percent_runs = _one_percent_runs(spans)
    top_runs = sorted(one_percent_runs, key=lambda run: -run["span_count"])[:10]
    breaks = [
        _run_break_record(spans, run)
        for run in one_percent_runs
        if run["span_count"] >= 3 and run["end_index"] + 1 < len(spans)
    ]
    breaks.sort(key=lambda item: (-int(item["preceding_span_count"]), item["break_index"]))
    latest_run = one_percent_runs[-1] if one_percent_runs else None
    current_run = one_percent_runs[-1] if one_percent_runs and spans else None
    if current_run and current_run["end_index"] != len(spans) - 1:
        current_run = None
    return {
        "one_percent_runs": {
            "count": len(one_percent_runs),
            "long_run_min_length": 3,
            "long_run_count": sum(1 for run in one_percent_runs if run["span_count"] >= 3),
            "max_span_count": max(
                (int(run["span_count"]) for run in one_percent_runs), default=0
            ),
            "current_streak": int(current_run["span_count"]) if current_run else 0,
            "latest_run": latest_run,
            "top_runs": top_runs,
        },
        "breaks_after_long_one_percent_runs": breaks[:10],
    }


def _piecewise_regime_segment_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    if not spans:
        return {
            "segment_count": 0,
            "segment_label_counts": {},
            "segments": [],
            "latest_segment": None,
            "adaptation_by_position": {},
            "boundary_diagnostics": {},
            "by_label": {},
        }
    prediction_rows = {
        int(row["index"]): row for row in walk_forward.walk_forward_prediction_rows(spans)
    }
    segments = _piecewise_regime_segments(spans)
    segment_records = [
        _piecewise_segment_record(spans, prediction_rows, segment)
        for segment in segments
    ]
    label_rows: dict[str, list[dict[str, Any]]] = {}
    for row in prediction_rows.values():
        label = regime_labels.delta_regime_label(_number(row.get("actual")))
        label_rows.setdefault(label, []).append(row)
    return {
        "segment_count": len(segment_records),
        "segment_label_counts": _count_segment_labels(segment_records),
        "latest_segment": segment_records[-1] if segment_records else None,
        "longest_segments": sorted(
            segment_records, key=lambda row: -int(row["span_count"])
        )[:10],
        "largest_mean_delta_segments": sorted(
            segment_records,
            key=lambda row: _number(
                (row.get("distribution") or {}).get("mean_delta_percent")
            ),
            reverse=True,
        )[:10],
        "adaptation_by_position": _piecewise_adaptation_by_position(
            prediction_rows, segments
        ),
        "boundary_diagnostics": boundary_summary.piecewise_boundary_diagnostics(
            spans, prediction_rows
        ),
        "by_label": {
            label: _piecewise_label_record(rows)
            for label, rows in sorted(label_rows.items())
        },
    }


def _piecewise_regime_segments(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current_label: str | None = None
    start_index = 0
    for index, span in enumerate(spans):
        label = regime_labels.delta_regime_label(span.delta_usage_percent)
        if current_label is None:
            current_label = label
            start_index = index
            continue
        if label == current_label:
            continue
        segments.append(
            {
                "label": current_label,
                "start_index": start_index,
                "end_index": index - 1,
            }
        )
        current_label = label
        start_index = index
    if current_label is not None:
        segments.append(
            {
                "label": current_label,
                "start_index": start_index,
                "end_index": len(spans) - 1,
            }
        )
    return segments


def _piecewise_segment_record(
    spans: list[UsageDeltaSpan],
    prediction_rows: dict[int, dict[str, Any]],
    segment: dict[str, Any],
) -> dict[str, Any]:
    start_index = int(segment["start_index"])
    end_index = int(segment["end_index"])
    segment_spans = spans[start_index : end_index + 1]
    rows = [
        prediction_rows[index]
        for index in range(start_index, end_index + 1)
        if index in prediction_rows
    ]
    return {
        "label": segment["label"],
        "start_index": start_index,
        "end_index": end_index,
        "span_count": end_index - start_index + 1,
        "start_timestamp": segment_spans[0].start_event_timestamp,
        "end_timestamp": segment_spans[-1].start_event_timestamp,
        "start_date": _date_label(segment_spans[0].start_event_timestamp),
        "end_date": _date_label(segment_spans[-1].start_event_timestamp),
        "distribution": _delta_distribution(segment_spans),
        "prediction_metrics": _segment_prediction_metrics(rows),
        "best_by_mae": _best_segment_prediction(rows),
    }


def _piecewise_label_record(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "prediction_rows": len(rows),
        "actual": _value_distribution([_number(row.get("actual")) for row in rows]),
        "prediction_metrics": _segment_prediction_metrics(rows),
        "best_by_mae": _best_segment_prediction(rows),
    }


def _piecewise_adaptation_by_position(
    prediction_rows: dict[int, dict[str, Any]],
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    all_rows_by_position: dict[str, list[dict[str, Any]]] = {
        bucket: [] for bucket in SEGMENT_POSITION_BUCKETS
    }
    label_rows_by_position: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for segment in segments:
        label = str(segment.get("label") or "missing")
        start_index = int(segment["start_index"])
        end_index = int(segment["end_index"])
        for index in range(start_index, end_index + 1):
            row = prediction_rows.get(index)
            if row is None:
                continue
            position = index - start_index + 1
            bucket = regime_labels.segment_position_bucket(position)
            all_rows_by_position[bucket].append(row)
            label_rows = label_rows_by_position.setdefault(
                label, {item: [] for item in SEGMENT_POSITION_BUCKETS}
            )
            label_rows[bucket].append(row)
    return {
        "position_buckets": list(SEGMENT_POSITION_BUCKETS),
        "all_segments": {
            bucket: _piecewise_position_record(rows)
            for bucket, rows in all_rows_by_position.items()
            if rows
        },
        "by_label": {
            label: {
                bucket: _piecewise_position_record(rows)
                for bucket, rows in rows_by_position.items()
                if rows
            }
            for label, rows_by_position in sorted(label_rows_by_position.items())
        },
    }


def _piecewise_position_record(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "prediction_rows": len(rows),
        "actual": _value_distribution([_number(row.get("actual")) for row in rows]),
        "prediction_metrics": _segment_prediction_metrics(rows),
        "best_by_mae": _best_segment_prediction(rows),
    }




def _segment_prediction_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual = [_number(row.get("actual")) for row in rows]
    return {
        model_name: _regression_metrics(
            actual,
            [
                _number((row.get("predictions") or {}).get(model_name))
                for row in rows
            ],
        )
        for model_name in SEGMENT_PREDICTION_MODELS
    }


def _best_segment_prediction(rows: list[dict[str, Any]]) -> str | None:
    metrics = _segment_prediction_metrics(rows)
    candidates: list[tuple[str, float]] = []
    for name, values in metrics.items():
        if not isinstance(values, dict):
            continue
        mae = values.get("mae")
        if mae is not None:
            candidates.append((name, _number(mae)))
    if not candidates:
        return None
    name, value = min(candidates, key=lambda item: item[1])
    return f"{name}:{value}"


def _count_segment_labels(segment_records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for segment in segment_records:
        label = str(segment.get("label") or "missing")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))




def _one_percent_runs(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    run_start: int | None = None
    for index, span in enumerate(spans):
        if _is_one_percent_delta(span.delta_usage_percent):
            if run_start is None:
                run_start = index
            continue
        if run_start is not None:
            runs.append(_run_record(spans, run_start, index - 1))
            run_start = None
    if run_start is not None:
        runs.append(_run_record(spans, run_start, len(spans) - 1))
    return runs


def _run_record(
    spans: list[UsageDeltaSpan], start_index: int, end_index: int
) -> dict[str, Any]:
    start_span = spans[start_index]
    end_span = spans[end_index]
    return {
        "start_index": start_index,
        "end_index": end_index,
        "span_count": end_index - start_index + 1,
        "start_timestamp": start_span.start_event_timestamp,
        "end_timestamp": end_span.start_event_timestamp,
        "start_date": _date_label(start_span.start_event_timestamp),
        "end_date": _date_label(end_span.start_event_timestamp),
    }


def _run_break_record(
    spans: list[UsageDeltaSpan], run: dict[str, Any]
) -> dict[str, Any]:
    break_index = int(run["end_index"]) + 1
    break_span = spans[break_index]
    return {
        "preceding_start_index": run["start_index"],
        "preceding_end_index": run["end_index"],
        "preceding_span_count": run["span_count"],
        "break_index": break_index,
        "break_delta_percent": _rounded(break_span.delta_usage_percent),
        "break_timestamp": break_span.start_event_timestamp,
        "break_date": _date_label(break_span.start_event_timestamp),
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
    _add_days_since_first_span(rows)
    _add_capacity_history_features(rows)
    models: list[dict[str, Any]] = []
    for split_name, train_rows, holdout_rows in _split_feature_rows(
        rows, train_fraction=0.8
    ):
        models.extend(_fit_capacity_baseline_models(train_rows, holdout_rows, split_name))
        for spec, kind in _capacity_model_specs():
            fitted = _fit_predictive_model(
                train_rows,
                holdout_rows,
                spec,
                include_capacity_residual_diagnostics=True,
            )
            if fitted is None:
                continue
            fitted["validation"] = split_name
            fitted["kind"] = kind
            fitted["name"] = f"{spec.name}__{split_name}"
            models.append(fitted)
    best_model = _best_holdout_model(models)
    best_causal = _best_holdout_model(
        [model for model in models if model.get("kind") != "explanatory_same_span"]
    )
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
        "notes": [
            "Causal/history models use prior closed spans plus start-time context.",
            "Explanatory same-span models use work observed inside the span and should not be treated as advance predictions.",
        ],
    }


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
