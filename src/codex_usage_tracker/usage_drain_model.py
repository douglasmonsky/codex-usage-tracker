"""Aggregate-only helpers for modeling observed Codex usage drain.

This module compares local aggregate token-credit estimates with visible
rate-limit usage percentage deltas. It intentionally treats usage drain as a
coarse observed signal, not as billing truth.
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import median
from typing import Any

from codex_usage_tracker.usage_drain_error_diagnostics import (
    prediction_error_diagnostics as _prediction_error_diagnostics,
)
from codex_usage_tracker.usage_drain_error_diagnostics import (
    span_error_metadata as _span_error_metadata,
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
from codex_usage_tracker.usage_drain_feature_history import (
    same_value_tail_streak as _same_value_tail_streak,
)
from codex_usage_tracker.usage_drain_feature_history import (
    streak_bucket as _streak_bucket,
)
from codex_usage_tracker.usage_drain_feature_history import (
    tail_streak as _tail_streak,
)
from codex_usage_tracker.usage_drain_features import (
    add_days_since_first_span as _add_days_since_first_span,
)
from codex_usage_tracker.usage_drain_features import (
    span_feature_row as _span_feature_row,
)
from codex_usage_tracker.usage_drain_grace import (
    REGIME_GRACE_MAX_BREAK_DELTA,
    REGIME_GRACE_SPANS,
    REGIME_GRACE_STREAK_THRESHOLD,
)
from codex_usage_tracker.usage_drain_grace import (
    one_percent_grace_calibration as _one_percent_grace_calibration,
)
from codex_usage_tracker.usage_drain_grace import (
    one_percent_regime_grace_prediction as _one_percent_regime_grace_prediction,
)
from codex_usage_tracker.usage_drain_history_state import (
    delta_bucket as _delta_bucket,
)
from codex_usage_tracker.usage_drain_history_state import (
    history_state_for_span as _history_state_for_span,
)
from codex_usage_tracker.usage_drain_history_state import (
    previous_call_duration_bucket as _previous_call_duration_bucket,
)
from codex_usage_tracker.usage_drain_history_state import (
    previous_span_wall_time_bucket as _previous_span_wall_time_bucket,
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
from codex_usage_tracker.usage_drain_regression import (
    candidate_share_correlation as _candidate_share_correlation,
)
from codex_usage_tracker.usage_drain_regression import (
    count_values as _count_values,
)
from codex_usage_tracker.usage_drain_regression import (
    documented_weighted_multiplier as _documented_weighted_multiplier,
)
from codex_usage_tracker.usage_drain_regression import (
    drain_stats as _drain_stats,
)
from codex_usage_tracker.usage_drain_regression import (
    fit_grid_multiplier as _fit_grid_multiplier,
)
from codex_usage_tracker.usage_drain_regression import (
    fit_two_feature_no_intercept as _fit_two_feature_no_intercept,
)
from codex_usage_tracker.usage_drain_regression import (
    r2 as _r2,
)
from codex_usage_tracker.usage_drain_regression import (
    regression_metrics as _regression_metrics,
)
from codex_usage_tracker.usage_drain_regression import (
    solve_linear_system as _solve_linear_system,
)
from codex_usage_tracker.usage_drain_spans import (
    build_usage_delta_spans,
    load_fast_proxy_annotations,  # noqa: F401
)
from codex_usage_tracker.usage_drain_state_buckets import (
    STATE_BUCKET_MIN_SUPPORT,
    STATE_BUCKET_MODEL_SIGNATURES,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_model_diagnostics as _state_bucket_model_diagnostics,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_prediction as _state_bucket_prediction,
)
from codex_usage_tracker.usage_drain_state_buckets import (
    state_bucket_predictions as _state_bucket_predictions,
)
from codex_usage_tracker.usage_drain_state_diagnostics import (
    state_ambiguity_summary as _state_ambiguity_summary,
)
from codex_usage_tracker.usage_drain_state_diagnostics import (
    state_signature as _state_signature,
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
from codex_usage_tracker.usage_drain_transition_gates import (
    RISK_GATE_THRESHOLDS,
    TRANSITION_DELTA_RISK_GATE_THRESHOLD,
    TRANSITION_DELTA_RISK_GATE_THRESHOLDS,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    best_transition_delta_gate_threshold_from_sums as _best_transition_delta_gate_threshold_from_sums,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    risk_gated_transition_delta_prediction as _risk_gated_transition_delta_prediction,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    transition_delta_gate_diagnostics as _transition_delta_gate_diagnostics,
)
from codex_usage_tracker.usage_drain_transition_gates import (
    update_transition_delta_gate_threshold_sums as _update_transition_delta_gate_threshold_sums,
)
from codex_usage_tracker.usage_drain_transition_metrics import (
    binary_risk_metrics as _binary_risk_metrics,
)
from codex_usage_tracker.usage_drain_transition_metrics import (
    transition_risk_predictions as _transition_risk_predictions,
)
from codex_usage_tracker.usage_drain_transition_metrics import (
    transition_risk_summary as _transition_risk_summary,
)
from codex_usage_tracker.usage_drain_types import (
    DEFAULT_PROXY_NAMES,
    DOCUMENTED_FAST_CREDIT_MULTIPLIERS,
    TIMING_TOTAL_FIELDS,  # noqa: F401
    TOKEN_COMPONENT_FIELDS,
    FastProxyAnnotation,
    PredictiveModelSpec,
    UsageDeltaSpan,
    UsageDrainModelResult,
    documented_fast_credit_multiplier,  # noqa: F401
)
from codex_usage_tracker.usage_drain_utils import (
    bounded_wall_time_seconds as _bounded_wall_time_seconds,
)
from codex_usage_tracker.usage_drain_utils import (
    ceil_to_visible_tick as _ceil_to_visible_tick,
)
from codex_usage_tracker.usage_drain_utils import (
    format_bucket_number as _format_bucket_number,
)
from codex_usage_tracker.usage_drain_utils import (
    number as _number,
)
from codex_usage_tracker.usage_drain_utils import (
    rounded as _rounded,
)
from codex_usage_tracker.usage_drain_utils import (
    second_bucket as _second_bucket,
)
from codex_usage_tracker.usage_drain_utils import (
    value_mode as _value_mode,
)
from codex_usage_tracker.usage_drain_utils import (
    value_stddev as _value_stddev,
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
BOUNDARY_CONTEXT_FIELDS = (
    "previous_label",
    "previous_delta_bucket",
    "previous_segment_position_bucket",
    "previous_segment_wall_time_bucket",
    "one_percent_streak_bucket",
    "same_delta_streak_bucket",
    "low_delta_streak_bucket",
    "baseline_used_bucket",
    "window_elapsed_bucket",
    "reset_remaining_bucket",
    "date",
    "day_of_week",
    "hour_bucket",
    "previous_span_wall_time_bucket",
    "previous_call_duration_bucket",
    "rate_limit_plan_type",
    "rate_limit_limit_id",
)
BOUNDARY_RISK_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "previous_label_risk": (
        ("previous_label",),
    ),
    "segment_age_risk": (
        ("previous_segment_position_bucket",),
        ("previous_segment_wall_time_bucket",),
    ),
    "label_segment_age_risk": (
        ("previous_label", "previous_segment_position_bucket"),
        ("previous_label",),
    ),
    "reset_segment_age_risk": (
        ("previous_label", "previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket",),
    ),
    "calendar_segment_age_risk": (
        ("previous_label", "previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket",),
    ),
}
BOUNDARY_DELTA_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "segment_age_mode": (
        ("previous_segment_position_bucket",),
        ("previous_segment_wall_time_bucket",),
    ),
    "label_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket"),
        ("previous_label",),
    ),
    "reset_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket", "window_elapsed_bucket"),
        ("previous_segment_position_bucket",),
    ),
    "calendar_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket", "day_of_week", "hour_bucket"),
        ("previous_segment_position_bucket",),
    ),
}
BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "boundary_conditioned_label_segment_age_mode": (
        ("previous_label", "previous_segment_position_bucket"),
        ("previous_label",),
        ("previous_segment_position_bucket",),
    ),
}
BOUNDARY_DELTA_RISK_GATE_THRESHOLD = 0.5
BOUNDARY_DELTA_RISK_GATE_THRESHOLDS = RISK_GATE_THRESHOLDS
BOUNDARY_DELTA_RESIDUAL_MODELS = (
    "previous_delta",
    "risk_weighted_label_segment_age_mode",
    "risk_weighted_boundary_conditioned_mode",
    "adaptive_mae_gate_label_segment_age_mode",
)
BOUNDARY_DELTA_ERROR_CONTEXT_FIELDS = (
    "boundary_state",
    "transition",
    "previous_label",
    "current_label",
    "previous_segment_position_bucket",
    "previous_segment_wall_time_bucket",
    "window_elapsed_bucket",
    "reset_remaining_bucket",
    "day_of_week",
    "hour_bucket",
    "previous_span_wall_time_bucket",
    "previous_call_duration_bucket",
    "one_percent_streak_bucket",
    "same_delta_streak_bucket",
    "low_delta_streak_bucket",
)
BOUNDARY_RISK_SCOPE_STARTS = {
    "all_after_first": 1,
    "all_after_10": 10,
    "time_ordered_holdout_20": 0.8,
    "latest_500": -500,
    "latest_100": -100,
}
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
        "token_component_regression": _token_component_regression_summary(spans),
        "one_percent_capacity_modeling": _one_percent_capacity_modeling(spans),
        "allowance_breakpoint_analysis": _allowance_breakpoint_analysis(spans),
        "walk_forward_prediction": _walk_forward_prediction_summary(spans),
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
        int(row["index"]): row for row in _walk_forward_prediction_rows(spans)
    }
    segments = _piecewise_regime_segments(spans)
    segment_records = [
        _piecewise_segment_record(spans, prediction_rows, segment)
        for segment in segments
    ]
    label_rows: dict[str, list[dict[str, Any]]] = {}
    for row in prediction_rows.values():
        label = _delta_regime_label(_number(row.get("actual")))
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
        "boundary_diagnostics": _piecewise_boundary_diagnostics(
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
        label = _delta_regime_label(span.delta_usage_percent)
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
            bucket = _segment_position_bucket(position)
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


def _segment_position_bucket(position: int) -> str:
    if position <= 1:
        return "first_span"
    if position == 2:
        return "second_span"
    if position == 3:
        return "third_span"
    if position <= 5:
        return "fourth_fifth_span"
    return "sixth_plus_span"


def _piecewise_boundary_diagnostics(
    spans: list[UsageDeltaSpan],
    prediction_rows: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    rows = _piecewise_boundary_rows(spans, prediction_rows)
    long_one_percent_rows = [
        row
        for row in rows
        if row["previous_label"] == "stable_one_percent"
        and int(row.get("one_percent_streak_count") or 0)
        >= REGIME_GRACE_STREAK_THRESHOLD
    ]
    return {
        "target": "next_span_regime_label_changes",
        "definition": (
            "A boundary means the current span's visible-delta regime label differs "
            "from the previous span's label."
        ),
        "context_fields": list(BOUNDARY_CONTEXT_FIELDS),
        **_boundary_basic_metrics(rows),
        "after_long_one_percent_run": _boundary_basic_metrics(long_one_percent_rows),
        "transition_counts": _piecewise_boundary_transition_counts(rows),
        "by_previous_label": _boundary_context_rates(rows, "previous_label"),
        "by_context": {
            field_name: _boundary_context_rates(rows, field_name)
            for field_name in BOUNDARY_CONTEXT_FIELDS
        },
        "walk_forward_risk": _boundary_walk_forward_risk_summary(rows),
        "walk_forward_delta_prediction": _boundary_walk_forward_delta_prediction_summary(
            rows
        ),
        "latest_boundaries": _latest_piecewise_boundaries(rows),
    }


def _piecewise_boundary_rows(
    spans: list[UsageDeltaSpan],
    prediction_rows: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    segment_start_index = 0
    for index in range(1, len(spans)):
        span = spans[index]
        previous_span = spans[index - 1]
        current_label = _delta_regime_label(span.delta_usage_percent)
        previous_label = _delta_regime_label(previous_span.delta_usage_percent)
        previous_segment_position = index - segment_start_index
        previous_segment_wall_time_seconds = _bounded_wall_time_seconds(
            spans[segment_start_index].start_event_timestamp,
            previous_span.start_event_timestamp,
        )
        prediction_row = prediction_rows.get(index) or {}
        metadata = prediction_row.get("metadata") or _span_error_metadata(span)
        row = {
            "index": index,
            "is_boundary": current_label != previous_label,
            "previous_label": previous_label,
            "current_label": current_label,
            "transition": f"{previous_label}->{current_label}",
            "delta_percent": _rounded(span.delta_usage_percent),
            "previous_delta_percent": _rounded(previous_span.delta_usage_percent),
            "previous_segment_position": previous_segment_position,
            "previous_segment_position_bucket": _segment_position_bucket(
                previous_segment_position
            ),
            "previous_segment_wall_time_seconds": _rounded(
                previous_segment_wall_time_seconds
            ),
            "previous_segment_wall_time_bucket": _second_bucket(
                previous_segment_wall_time_seconds
            ),
            "timestamp": span.start_event_timestamp,
        }
        for field_name in BOUNDARY_CONTEXT_FIELDS:
            if field_name in row:
                continue
            row[field_name] = metadata.get(field_name, "missing")
        row["one_percent_streak_count"] = int(
            metadata.get("one_percent_streak_count") or 0
        )
        rows.append(row)
        if current_label != previous_label:
            segment_start_index = index
    return rows


def _boundary_basic_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    boundary_count = sum(1 for row in rows if row.get("is_boundary"))
    return {
        "n": len(rows),
        "boundary_count": boundary_count,
        "non_boundary_count": len(rows) - boundary_count,
        "boundary_rate": _rounded(boundary_count / len(rows) if rows else None),
    }


def _piecewise_boundary_transition_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        if not row.get("is_boundary"):
            continue
        transition = str(row.get("transition") or "missing")
        counts[transition] = counts.get(transition, 0) + 1
    total = sum(counts.values())
    return [
        {
            "transition": transition,
            "count": count,
            "share": _rounded(count / total if total else None),
        }
        for transition, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[:10]
    ]


def _boundary_context_rates(
    rows: list[dict[str, Any]],
    field_name: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(field_name) or "missing")
        grouped.setdefault(key, []).append(row)
    output_rows = [
        {
            field_name: key,
            **_boundary_basic_metrics(items),
        }
        for key, items in grouped.items()
    ]
    output_rows.sort(
        key=lambda row: (
            -int(row["boundary_count"]),
            -_number(row["boundary_rate"]),
            -int(row["n"]),
            str(row.get(field_name) or ""),
        )
    )
    return output_rows[:10]


def _latest_piecewise_boundaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundary_rows = [row for row in rows if row.get("is_boundary")]
    return [
        {
            "index": row["index"],
            "transition": row["transition"],
            "date": row.get("date"),
            "hour_bucket": row.get("hour_bucket"),
            "window_elapsed_bucket": row.get("window_elapsed_bucket"),
            "previous_delta_percent": row.get("previous_delta_percent"),
            "previous_segment_position": row.get("previous_segment_position"),
            "previous_segment_position_bucket": row.get(
                "previous_segment_position_bucket"
            ),
            "delta_percent": row.get("delta_percent"),
            "one_percent_streak_count": row.get("one_percent_streak_count"),
        }
        for row in reversed(boundary_rows[-10:])
    ]


def _boundary_walk_forward_risk_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    risk_rows = _boundary_walk_forward_risk_rows(rows)
    return {
        "target": "next_span_regime_label_changes",
        "risk_models": {
            "overall_prior_rate": "Historical boundary rate before the current opportunity.",
            "previous_label_risk": "Empirical boundary rate for the previous regime label.",
            "segment_age_risk": "Empirical boundary rate for segment-position or wall-time age.",
            "label_segment_age_risk": (
                "Empirical boundary rate for previous label plus segment-position age."
            ),
            "reset_segment_age_risk": (
                "Empirical boundary rate for segment age with reset-window context."
            ),
            "calendar_segment_age_risk": (
                "Empirical boundary rate for segment age with day/hour context."
            ),
        },
        "scopes": {
            scope_name: _boundary_risk_scope(
                risk_rows,
                start_index=_boundary_scope_start_index(rows, start),
            )
            for scope_name, start in BOUNDARY_RISK_SCOPE_STARTS.items()
        },
    }


def _boundary_scope_start_index(rows: list[dict[str, Any]], start: int | float) -> int:
    if not rows:
        return 0
    if isinstance(start, float):
        return max(1, min(len(rows) - 1, int(len(rows) * start)))
    if start < 0:
        return max(len(rows) + start, 1)
    return start


def _boundary_walk_forward_risk_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_rows: list[dict[str, Any]] = []
    for row in rows:
        prior_rate = _boundary_rate(previous_rows)
        risks = {"overall_prior_rate": prior_rate}
        details = {
            "overall_prior_rate": {
                "source": "all_prior_boundaries",
                "support": len(previous_rows),
                "risk": _rounded(prior_rate),
            }
        }
        for model_name, signatures in BOUNDARY_RISK_MODEL_SIGNATURES.items():
            risk, detail = _state_bucket_boundary_risk(
                previous_rows,
                row,
                signatures=signatures,
                fallback_rate=prior_rate,
            )
            risks[model_name] = risk
            details[model_name] = detail
        output.append(
            {
                **row,
                "boundary_risks": risks,
                "boundary_risk_details": details,
            }
        )
        previous_rows.append(row)
    return output


def _state_bucket_boundary_risk(
    previous_rows: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    signatures: tuple[tuple[str, ...], ...],
    fallback_rate: float,
) -> tuple[float, dict[str, Any]]:
    for signature in signatures:
        matches = [
            previous
            for previous in previous_rows
            if _state_signature(previous, signature) == _state_signature(row, signature)
        ]
        if len(matches) < STATE_BUCKET_MIN_SUPPORT:
            continue
        risk = _boundary_rate(matches)
        return risk, {
            "source": "matched_boundary_state",
            "signature": list(signature),
            "support": len(matches),
            "risk": _rounded(risk),
        }
    return fallback_rate, {
        "source": "fallback_prior_rate",
        "signature": [],
        "support": 0,
        "risk": _rounded(fallback_rate),
    }


def _boundary_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.get("is_boundary")) / len(rows)


def _boundary_risk_scope(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    actual = [1 if row.get("is_boundary") else 0 for row in scope_rows]
    model_names = _boundary_risk_model_names(scope_rows)
    return {
        "start_index": start_index,
        "n": len(scope_rows),
        "boundary_count": sum(actual),
        "boundary_rate": _rounded(sum(actual) / len(actual) if actual else None),
        "models": {
            model_name: _binary_risk_metrics(
                actual,
                [
                    _number((row.get("boundary_risks") or {}).get(model_name))
                    for row in scope_rows
                ],
            )
            for model_name in model_names
        },
        "risk_detail_diagnostics": {
            model_name: _boundary_risk_detail_diagnostics(scope_rows, model_name)
            for model_name in model_names
            if model_name != "overall_prior_rate"
        },
    }


def _boundary_risk_model_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for name in row.get("boundary_risks") or {}:
            if name not in names:
                names.append(str(name))
    return names


def _boundary_risk_detail_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("boundary_risk_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "matched_state_share": None,
            "mean_support": None,
            "top_signatures": [],
        }
    matched = [
        detail for detail in details if detail.get("source") == "matched_boundary_state"
    ]
    signature_counts: dict[str, int] = {}
    for detail in matched:
        label = ",".join(str(item) for item in detail.get("signature") or [])
        signature_counts[label or "missing"] = (
            signature_counts.get(label or "missing", 0) + 1
        )
    return {
        "matched_state_share": _rounded(len(matched) / len(details)),
        "mean_support": _rounded(
            sum(int(detail.get("support") or 0) for detail in matched) / len(matched)
            if matched
            else None
        ),
        "top_signatures": [
            {
                "signature": signature,
                "count": count,
                "share": _rounded(count / len(details)),
            }
            for signature, count in sorted(
                signature_counts.items(), key=lambda item: (-item[1], item[0])
            )[:8]
        ],
    }


def _boundary_walk_forward_delta_prediction_summary(
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    prediction_rows = _boundary_walk_forward_delta_prediction_rows(rows)
    return {
        "target": "next_visible_usage_delta_percent",
        "prediction_models": {
            "previous_delta": "Predicts the previous visible usage delta.",
            "prior_mode_delta": "Predicts the modal prior next-span delta.",
            "segment_age_mode": (
                "Uses the modal prior next-span delta from matching segment age."
            ),
            "label_segment_age_mode": (
                "Uses the modal prior next-span delta from matching previous label "
                "plus segment-position age."
            ),
            "reset_segment_age_mode": (
                "Uses the modal prior next-span delta from matching segment age "
                "plus reset-window context."
            ),
            "calendar_segment_age_mode": (
                "Uses the modal prior next-span delta from matching segment age "
                "plus day/hour context."
            ),
            "risk_gated_label_segment_age_mode": (
                "Uses previous delta unless previous-label plus segment-age boundary "
                "risk is at least 50%, then uses the matched label/segment-age mode."
            ),
            "risk_weighted_label_segment_age_mode": (
                "Blends previous delta with matched label/segment-age mode according "
                "to the prior boundary-risk estimate."
            ),
            "adaptive_mae_gate_label_segment_age_mode": (
                "Selects the prior-best boundary-risk threshold by MAE, then gates "
                "between previous delta and matched label/segment-age mode."
            ),
            "adaptive_rmse_gate_label_segment_age_mode": (
                "Selects the prior-best boundary-risk threshold by RMSE, then gates "
                "between previous delta and matched label/segment-age mode."
            ),
            "boundary_conditioned_label_segment_age_mode": (
                "Uses the modal prior next-span delta from matching prior boundary "
                "rows only."
            ),
            "risk_weighted_boundary_conditioned_mode": (
                "Blends previous delta with the boundary-conditioned mode according "
                "to the prior boundary-risk estimate."
            ),
        },
        "scopes": {
            scope_name: _boundary_delta_prediction_scope(
                prediction_rows,
                start_index=_boundary_scope_start_index(rows, start),
            )
            for scope_name, start in BOUNDARY_RISK_SCOPE_STARTS.items()
        },
    }


def _boundary_walk_forward_delta_prediction_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_rows: list[dict[str, Any]] = []
    previous_state_rows: list[dict[str, Any]] = []
    previous_boundary_state_rows: list[dict[str, Any]] = []
    threshold_absolute_error_sums = {
        threshold: 0.0 for threshold in BOUNDARY_DELTA_RISK_GATE_THRESHOLDS
    }
    threshold_squared_error_sums = {
        threshold: 0.0 for threshold in BOUNDARY_DELTA_RISK_GATE_THRESHOLDS
    }
    for threshold_training_count, row in enumerate(rows):
        previous_delta = _number(row.get("previous_delta_percent"))
        prior_boundary_rate = _boundary_rate(previous_rows)
        if previous_state_rows:
            prior_values = [
                _number(previous.get("actual")) for previous in previous_state_rows
            ]
            prior_mode = _value_mode(prior_values)
            prior_mode_detail = {
                "source": "all_prior_delta_mode",
                "signature": [],
                "support": len(previous_state_rows),
                "matched_mode": _rounded(prior_mode),
            }
        else:
            prior_mode = previous_delta
            prior_mode_detail = {
                "source": "fallback_previous_delta",
                "signature": [],
                "support": 0,
                "matched_mode": None,
            }
        predictions = {
            "previous_delta": previous_delta,
            "prior_mode_delta": prior_mode,
        }
        details = {
            "previous_delta": {
                "source": "previous_delta",
                "signature": [],
                "support": 1,
                "matched_mode": _rounded(previous_delta),
            },
            "prior_mode_delta": prior_mode_detail,
        }
        for model_name, signatures in BOUNDARY_DELTA_MODEL_SIGNATURES.items():
            prediction, detail = _state_bucket_prediction(
                previous_state_rows,
                row,
                signatures=signatures,
                fallback_prediction=previous_delta,
            )
            predictions[model_name] = prediction
            details[model_name] = detail
        for model_name, signatures in BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES.items():
            prediction, detail = _state_bucket_prediction(
                previous_boundary_state_rows,
                row,
                signatures=signatures,
                fallback_prediction=previous_delta,
            )
            predictions[model_name] = prediction
            details[model_name] = {
                **detail,
                "conditioned_on": "prior_boundary_rows",
            }
        label_segment_age_prediction = _number(predictions.get("label_segment_age_mode"))
        boundary_conditioned_prediction = _number(
            predictions.get("boundary_conditioned_label_segment_age_mode")
        )
        label_segment_age_risk, label_segment_age_risk_detail = (
            _state_bucket_boundary_risk(
                previous_rows,
                row,
                signatures=BOUNDARY_RISK_MODEL_SIGNATURES["label_segment_age_risk"],
                fallback_rate=prior_boundary_rate,
            )
        )
        risk_gated_prediction = (
            label_segment_age_prediction
            if label_segment_age_risk >= BOUNDARY_DELTA_RISK_GATE_THRESHOLD
            else previous_delta
        )
        risk_weighted_prediction = previous_delta + (
            label_segment_age_risk * (label_segment_age_prediction - previous_delta)
        )
        risk_weighted_boundary_conditioned_prediction = previous_delta + (
            label_segment_age_risk * (boundary_conditioned_prediction - previous_delta)
        )
        adaptive_mae_threshold, adaptive_mae_threshold_detail = (
            _best_boundary_delta_gate_threshold_from_sums(
                threshold_absolute_error_sums,
                training_count=threshold_training_count,
                metric="mae",
            )
        )
        adaptive_rmse_threshold, adaptive_rmse_threshold_detail = (
            _best_boundary_delta_gate_threshold_from_sums(
                threshold_squared_error_sums,
                training_count=threshold_training_count,
                metric="rmse",
            )
        )
        adaptive_mae_prediction = _risk_gated_boundary_delta_prediction(
            previous_delta=previous_delta,
            alternate_prediction=label_segment_age_prediction,
            risk=label_segment_age_risk,
            threshold=adaptive_mae_threshold,
        )
        adaptive_rmse_prediction = _risk_gated_boundary_delta_prediction(
            previous_delta=previous_delta,
            alternate_prediction=label_segment_age_prediction,
            risk=label_segment_age_risk,
            threshold=adaptive_rmse_threshold,
        )
        predictions["risk_gated_label_segment_age_mode"] = risk_gated_prediction
        predictions["risk_weighted_label_segment_age_mode"] = risk_weighted_prediction
        predictions["risk_weighted_boundary_conditioned_mode"] = (
            risk_weighted_boundary_conditioned_prediction
        )
        predictions["adaptive_mae_gate_label_segment_age_mode"] = (
            adaptive_mae_prediction
        )
        predictions["adaptive_rmse_gate_label_segment_age_mode"] = (
            adaptive_rmse_prediction
        )
        details["risk_gated_label_segment_age_mode"] = {
            "source": "risk_gate_override"
            if label_segment_age_risk >= BOUNDARY_DELTA_RISK_GATE_THRESHOLD
            else "risk_gate_previous_delta",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        details["risk_weighted_label_segment_age_mode"] = {
            "source": "risk_weighted_blend",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        details["risk_weighted_boundary_conditioned_mode"] = {
            "source": "risk_weighted_boundary_conditioned_blend",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": BOUNDARY_DELTA_RISK_GATE_THRESHOLD,
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(boundary_conditioned_prediction),
        }
        details["adaptive_mae_gate_label_segment_age_mode"] = {
            "source": "adaptive_risk_gate_override"
            if label_segment_age_risk >= adaptive_mae_threshold
            else "adaptive_risk_gate_previous_delta",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": adaptive_mae_threshold,
            "training_metric": adaptive_mae_threshold_detail.get("metric"),
            "training_error": adaptive_mae_threshold_detail.get("error"),
            "training_support": adaptive_mae_threshold_detail.get("support"),
            "threshold_source": adaptive_mae_threshold_detail.get("source"),
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        details["adaptive_rmse_gate_label_segment_age_mode"] = {
            "source": "adaptive_risk_gate_override"
            if label_segment_age_risk >= adaptive_rmse_threshold
            else "adaptive_risk_gate_previous_delta",
            "risk_model": "label_segment_age_risk",
            "risk": _rounded(label_segment_age_risk),
            "risk_threshold": adaptive_rmse_threshold,
            "training_metric": adaptive_rmse_threshold_detail.get("metric"),
            "training_error": adaptive_rmse_threshold_detail.get("error"),
            "training_support": adaptive_rmse_threshold_detail.get("support"),
            "threshold_source": adaptive_rmse_threshold_detail.get("source"),
            "risk_detail": label_segment_age_risk_detail,
            "support": int(label_segment_age_risk_detail.get("support") or 0),
            "matched_mode": _rounded(label_segment_age_prediction),
        }
        output_row = {
            **row,
            "boundary_delta_predictions": predictions,
            "boundary_delta_prediction_details": details,
            "prediction_details": details,
        }
        output.append(output_row)
        _update_boundary_delta_gate_threshold_sums(
            threshold_absolute_error_sums,
            threshold_squared_error_sums,
            row=output_row,
        )
        previous_state_rows.append(
            {
                "actual": _number(row.get("delta_percent")),
                "state": row,
            }
        )
        if row.get("is_boundary"):
            previous_boundary_state_rows.append(
                {
                    "actual": _number(row.get("delta_percent")),
                    "state": row,
                }
            )
        previous_rows.append(row)
    return output


def _boundary_delta_prediction_scope(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    actual = [_number(row.get("delta_percent")) for row in scope_rows]
    model_names = _boundary_delta_model_names(scope_rows)
    return {
        "start_index": start_index,
        "n": len(scope_rows),
        "actual": _value_distribution(actual),
        "models": {
            model_name: _regression_metrics(
                actual,
                [
                    _number(
                        (row.get("boundary_delta_predictions") or {}).get(model_name)
                    )
                    for row in scope_rows
                ],
            )
            for model_name in model_names
        },
        "prediction_detail_diagnostics": {
            model_name: _state_bucket_model_diagnostics(scope_rows, model_name)
            for model_name in model_names
            if model_name in BOUNDARY_DELTA_MODEL_SIGNATURES
            or model_name in BOUNDARY_CONDITIONED_DELTA_MODEL_SIGNATURES
        },
        "risk_gate_diagnostics": {
            model_name: _boundary_delta_risk_gate_diagnostics(scope_rows, model_name)
            for model_name in (
                "risk_gated_label_segment_age_mode",
                "risk_weighted_label_segment_age_mode",
                "risk_weighted_boundary_conditioned_mode",
                "adaptive_mae_gate_label_segment_age_mode",
                "adaptive_rmse_gate_label_segment_age_mode",
            )
            if model_name in model_names
        },
        "residual_diagnostics": {
            model_name: _boundary_delta_residual_diagnostics(scope_rows, model_name)
            for model_name in BOUNDARY_DELTA_RESIDUAL_MODELS
            if model_name in model_names
        },
    }


def _boundary_delta_model_names(rows: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for row in rows:
        for name in row.get("boundary_delta_predictions") or {}:
            if name not in names:
                names.append(str(name))
    return names


def _risk_gated_boundary_delta_prediction(
    *,
    previous_delta: float,
    alternate_prediction: float,
    risk: float,
    threshold: float,
) -> float:
    if risk >= threshold:
        return alternate_prediction
    return previous_delta


def _best_boundary_delta_gate_threshold_from_sums(
    error_sums: dict[float, float],
    *,
    training_count: int,
    metric: str,
) -> tuple[float, dict[str, Any]]:
    if training_count < STATE_BUCKET_MIN_SUPPORT:
        return BOUNDARY_DELTA_RISK_GATE_THRESHOLD, {
            "source": "fallback_fixed_threshold",
            "metric": metric,
            "support": training_count,
            "error": None,
        }
    candidates: list[tuple[float, float]] = []
    for threshold, error_sum in error_sums.items():
        if metric == "rmse":
            error_value = math.sqrt(error_sum / training_count)
        else:
            error_value = error_sum / training_count
        candidates.append((threshold, error_value))
    threshold, error_value = min(
        candidates,
        key=lambda item: (
            item[1],
            abs(item[0] - BOUNDARY_DELTA_RISK_GATE_THRESHOLD),
            item[0],
        ),
    )
    return threshold, {
        "source": "prior_best_threshold",
        "metric": metric,
        "support": training_count,
        "error": _rounded(error_value),
    }


def _update_boundary_delta_gate_threshold_sums(
    absolute_error_sums: dict[float, float],
    squared_error_sums: dict[float, float],
    *,
    row: dict[str, Any],
) -> None:
    actual = _number(row.get("delta_percent"))
    previous_delta = _number(row.get("previous_delta_percent"))
    alternate_prediction = _number(
        (row.get("boundary_delta_predictions") or {}).get("label_segment_age_mode")
    )
    detail = (row.get("boundary_delta_prediction_details") or {}).get(
        "risk_gated_label_segment_age_mode"
    ) or {}
    risk = _number(detail.get("risk"))
    for threshold in BOUNDARY_DELTA_RISK_GATE_THRESHOLDS:
        prediction = _risk_gated_boundary_delta_prediction(
            previous_delta=previous_delta,
            alternate_prediction=alternate_prediction,
            risk=risk,
            threshold=threshold,
        )
        error = prediction - actual
        absolute_error_sums[threshold] += abs(error)
        squared_error_sums[threshold] += error * error


def _boundary_delta_risk_gate_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("boundary_delta_prediction_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "n": 0,
            "override_share": None,
            "mean_risk": None,
            "mean_support": None,
            "mean_threshold": None,
            "source_counts": [],
        }
    source_counts: dict[str, int] = {}
    risks: list[float] = []
    supports: list[int] = []
    thresholds: list[float] = []
    for detail in details:
        source = str(detail.get("source") or "missing")
        source_counts[source] = source_counts.get(source, 0) + 1
        risks.append(_number(detail.get("risk")))
        supports.append(int(detail.get("support") or 0))
        thresholds.append(_number(detail.get("risk_threshold")))
    override_count = sum(
        count for source, count in source_counts.items() if source.endswith("_override")
    )
    return {
        "n": len(details),
        "override_share": _rounded(override_count / len(details)),
        "mean_risk": _rounded(sum(risks) / len(risks)),
        "mean_support": _rounded(sum(supports) / len(supports)),
        "mean_threshold": _rounded(sum(thresholds) / len(thresholds)),
        "source_counts": [
            {
                "source": source,
                "count": count,
                "share": _rounded(count / len(details)),
            }
            for source, count in sorted(
                source_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ],
    }


def _boundary_delta_residual_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for row in rows:
        predicted = _number((row.get("boundary_delta_predictions") or {}).get(model_name))
        actual = _number(row.get("delta_percent"))
        error = predicted - actual
        errors.append(
            {
                "index": int(row["index"]),
                "actual": actual,
                "predicted": predicted,
                "previous_delta_percent": _number(row.get("previous_delta_percent")),
                "error": error,
                "abs_error": abs(error),
                "metadata": row,
            }
        )
    if not errors:
        return {
            "n": 0,
            "total_abs_error": None,
            "exact_match_share": None,
            "within_one_point_share": None,
            "large_error_share": None,
            "top_error_groups": {},
            "largest_errors": [],
        }
    total_abs_error = sum(item["abs_error"] for item in errors)
    return {
        "n": len(errors),
        "total_abs_error": _rounded(total_abs_error),
        "exact_match_share": _rounded(
            sum(1 for item in errors if item["abs_error"] == 0) / len(errors)
        ),
        "within_one_point_share": _rounded(
            sum(1 for item in errors if item["abs_error"] <= 1.0) / len(errors)
        ),
        "large_error_share": _rounded(
            sum(1 for item in errors if item["abs_error"] >= 5.0) / len(errors)
        ),
        "top_error_groups": {
            field_name: _boundary_delta_top_error_groups(errors, field_name)
            for field_name in BOUNDARY_DELTA_ERROR_CONTEXT_FIELDS
        },
        "largest_errors": _largest_boundary_delta_errors(errors),
    }


def _boundary_delta_top_error_groups(
    errors: list[dict[str, Any]], field_name: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in errors:
        metadata = item.get("metadata", {})
        if field_name == "boundary_state":
            key = "boundary" if metadata.get("is_boundary") else "same_label"
        else:
            key = str(metadata.get(field_name) or "missing")
        grouped.setdefault(key, []).append(item)
    total_abs_error = sum(item["abs_error"] for item in errors)
    rows = [
        {
            field_name: key,
            "count": len(items),
            "count_share": _rounded(len(items) / len(errors)),
            "share_abs_error": _rounded(
                sum(item["abs_error"] for item in items) / total_abs_error
                if total_abs_error
                else None
            ),
            "mean_abs_error": _rounded(
                sum(item["abs_error"] for item in items) / len(items)
            ),
            "rmse": _rounded(
                math.sqrt(sum(item["error"] * item["error"] for item in items) / len(items))
            ),
            "max_abs_error": _rounded(max(item["abs_error"] for item in items)),
            "mean_actual": _rounded(sum(item["actual"] for item in items) / len(items)),
            "mean_predicted": _rounded(
                sum(item["predicted"] for item in items) / len(items)
            ),
        }
        for key, items in grouped.items()
    ]
    rows.sort(
        key=lambda row: (
            -_number(row["share_abs_error"]),
            -_number(row["mean_abs_error"]),
            -int(_number(row.get("count"))),
            str(row.get(field_name) or ""),
        )
    )
    return rows[:10]


def _largest_boundary_delta_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(errors, key=lambda item: item["abs_error"], reverse=True)[:10]
    return [
        {
            "index": item["index"],
            "date": item["metadata"].get("date"),
            "day_of_week": item["metadata"].get("day_of_week"),
            "hour_bucket": item["metadata"].get("hour_bucket"),
            "transition": item["metadata"].get("transition"),
            "previous_segment_position_bucket": item["metadata"].get(
                "previous_segment_position_bucket"
            ),
            "boundary_state": "boundary"
            if item["metadata"].get("is_boundary")
            else "same_label",
            "previous_delta_percent": _rounded(item["previous_delta_percent"]),
            "actual_delta_percent": _rounded(item["actual"]),
            "predicted_delta_percent": _rounded(item["predicted"]),
            "abs_error": _rounded(item["abs_error"]),
        }
        for item in rows
    ]


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


def _delta_regime_label(value: float) -> str:
    if _is_one_percent_delta(value):
        return "stable_one_percent"
    if value <= 2.0:
        return "small_blip"
    if value <= 5.0:
        return "moderate_delta"
    if value <= 10.0:
        return "high_delta"
    return "very_high_delta"


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


def _token_component_regression_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
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


def _fit_linear_regression_coefficients(
    x_rows: list[list[float]], y_values: list[float], *, intercept: bool
) -> list[float]:
    width = len(x_rows[0]) + (1 if intercept else 0)
    lhs = [[0.0 for _ in range(width)] for _ in range(width)]
    rhs = [0.0 for _ in range(width)]
    for row, y_value in zip(x_rows, y_values, strict=True):
        expanded = ([1.0] if intercept else []) + row
        for i, x_i in enumerate(expanded):
            rhs[i] += x_i * y_value
            for j, x_j in enumerate(expanded):
                lhs[i][j] += x_i * x_j
    coefficients = _solve_linear_system(lhs, rhs)
    if coefficients is not None:
        return coefficients
    for index in range(1 if intercept else 0, width):
        lhs[index][index] += 1e-9
    coefficients = _solve_linear_system(lhs, rhs)
    if coefficients is None:
        return [0.0 for _index in range(width)]
    return coefficients


def _linear_regression_predictions(
    x_rows: list[list[float]], coefficients: list[float], *, intercept: bool
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


def _component_coefficient_rows(
    coefficients: list[float], *, intercept: bool
) -> list[dict[str, Any]]:
    names = (["intercept"] if intercept else []) + list(TOKEN_COMPONENT_FIELDS)
    return [
        {"feature": name, "coefficient": _rounded(coefficient)}
        for name, coefficient in zip(names, coefficients, strict=True)
    ]


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
            "token_component_regression": _one_percent_capacity_component_regression(
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
        "token_component_regression": _one_percent_capacity_component_regression(
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


def _one_percent_capacity_component_regression(
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


def _allowance_breakpoint_analysis(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    rows = _allowance_breakpoint_rows(spans)
    if len(rows) < ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE * 2:
        return {
            "target": "standard_usage_credits_per_visible_percent",
            "target_description": (
                "Estimated hidden allowance capacity for one visible usage-percent point."
            ),
            "span_count": len(rows),
            "min_segment_size": ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE,
            "max_segments": ALLOWANCE_BREAKPOINT_MAX_SEGMENTS,
            "global": _allowance_capacity_distribution(rows),
            "global_credit_to_delta_fit": _credit_to_delta_fit(rows),
            "best_single_break": None,
            "segments": [],
            "piecewise_credit_to_delta_fit": _allowance_piecewise_credit_to_delta_fit(
                rows,
                [],
            ),
            "online_capacity_credit_to_delta_fit": (
                _allowance_online_capacity_credit_to_delta_fit(rows, [])
            ),
            "piecewise_sse_reduction_share": None,
            "notes": _allowance_breakpoint_notes(),
        }

    global_sse = _allowance_capacity_sse(rows, 0, len(rows))
    segments = _allowance_capacity_segments(rows)
    piecewise_sse = sum(
        _allowance_capacity_sse(rows, start, end) for start, end in segments
    )
    return {
        "target": "standard_usage_credits_per_visible_percent",
        "target_description": (
            "Estimated hidden allowance capacity for one visible usage-percent point."
        ),
        "span_count": len(rows),
        "min_segment_size": ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE,
        "max_segments": ALLOWANCE_BREAKPOINT_MAX_SEGMENTS,
        "global": _allowance_capacity_distribution(rows),
        "global_credit_to_delta_fit": _credit_to_delta_fit(rows),
        "best_single_break": _allowance_split_record(
            rows,
            _best_allowance_capacity_split(
                rows,
                0,
                len(rows),
                min_segment_size=ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE,
            ),
        ),
        "segments": [
            _allowance_segment_record(rows, start, end, segment_index=index)
            for index, (start, end) in enumerate(segments, start=1)
        ],
        "piecewise_credit_to_delta_fit": _allowance_piecewise_credit_to_delta_fit(
            rows,
            segments,
        ),
        "online_capacity_credit_to_delta_fit": (
            _allowance_online_capacity_credit_to_delta_fit(rows, segments)
        ),
        "piecewise_sse_reduction_share": _rounded(
            (global_sse - piecewise_sse) / global_sse if global_sse > 0 else 0.0
        ),
        "notes": _allowance_breakpoint_notes(),
    }


def _allowance_breakpoint_notes() -> list[str]:
    return [
        "This tests whether the apparent credits-per-visible-percent denominator changes over time.",
        "A strong breakpoint result means token/credit correlation should be checked within each segment, not only globally.",
        "Piecewise credit-to-delta fits are explanatory diagnostics because the breakpoint detector sees the full series.",
        "Segments are chronological diagnostics over closed positive usage-delta spans; they are not proof of an official allowance change.",
    ]


def _allowance_breakpoint_rows(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, span in enumerate(spans):
        if span.delta_usage_percent <= 0:
            continue
        rows.append(
            {
                "span_index": index,
                "start_event_timestamp": span.start_event_timestamp,
                "end_event_timestamp": span.end_event_timestamp,
                "delta_usage_percent": span.delta_usage_percent,
                "standard_usage_credits": span.standard_usage_credits,
                "credits_per_visible_percent": (
                    span.standard_usage_credits / span.delta_usage_percent
                ),
                "is_one_percent": _is_one_percent_delta(span.delta_usage_percent),
                "row_count": span.row_count,
                "rate_limit_plan_type": span.rate_limit_plan_type or "missing",
                "rate_limit_limit_id": span.rate_limit_limit_id or "missing",
                "usage_window_minutes": span.usage_window_minutes or 0,
                "usage_window_source": span.usage_window_source or "missing",
            }
        )
    return rows


def _allowance_capacity_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return _value_distribution(
        [_number(row.get("credits_per_visible_percent")) for row in rows]
    )


def _allowance_capacity_segments(rows: list[dict[str, Any]]) -> list[tuple[int, int]]:
    segments = [(0, len(rows))]
    while len(segments) < ALLOWANCE_BREAKPOINT_MAX_SEGMENTS:
        candidates = [
            (index, split)
            for index, (start, end) in enumerate(segments)
            for split in [
                _best_allowance_capacity_split(
                    rows,
                    start,
                    end,
                    min_segment_size=ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE,
                )
            ]
            if split is not None
        ]
        if not candidates:
            break
        segment_index, split = max(
            candidates,
            key=lambda item: _number(item[1].get("sse_reduction")),
        )
        if (
            _number(split.get("sse_reduction_share"))
            < ALLOWANCE_BREAKPOINT_MIN_REDUCTION_SHARE
        ):
            break
        start, end = segments[segment_index]
        split_index = int(split["split_index"])
        segments[segment_index : segment_index + 1] = [
            (start, split_index),
            (split_index, end),
        ]
    return segments


def _best_allowance_capacity_split(
    rows: list[dict[str, Any]],
    start: int,
    end: int,
    *,
    min_segment_size: int,
) -> dict[str, Any] | None:
    if end - start < min_segment_size * 2:
        return None
    parent_sse = _allowance_capacity_sse(rows, start, end)
    if parent_sse <= 0:
        return None
    best_split: dict[str, Any] | None = None
    for split_index in range(start + min_segment_size, end - min_segment_size + 1):
        left_sse = _allowance_capacity_sse(rows, start, split_index)
        right_sse = _allowance_capacity_sse(rows, split_index, end)
        combined_sse = left_sse + right_sse
        reduction = parent_sse - combined_sse
        if best_split is None or reduction > _number(best_split["sse_reduction"]):
            best_split = {
                "start": start,
                "end": end,
                "split_index": split_index,
                "parent_sse": parent_sse,
                "piecewise_sse": combined_sse,
                "sse_reduction": reduction,
                "sse_reduction_share": reduction / parent_sse,
            }
    return best_split


def _allowance_capacity_sse(rows: list[dict[str, Any]], start: int, end: int) -> float:
    values = [
        _number(row.get("credits_per_visible_percent")) for row in rows[start:end]
    ]
    if not values:
        return 0.0
    mean_value = sum(values) / len(values)
    return sum((value - mean_value) ** 2 for value in values)


def _allowance_split_record(
    rows: list[dict[str, Any]], split: dict[str, Any] | None
) -> dict[str, Any] | None:
    if split is None:
        return None
    start = int(split["start"])
    end = int(split["end"])
    split_index = int(split["split_index"])
    left = rows[start:split_index]
    right = rows[split_index:end]
    return {
        "split_index": split_index,
        "left_n": len(left),
        "right_n": len(right),
        "left_start_event_timestamp": left[0]["start_event_timestamp"] if left else None,
        "left_end_event_timestamp": left[-1]["end_event_timestamp"] if left else None,
        "right_start_event_timestamp": right[0]["start_event_timestamp"] if right else None,
        "right_end_event_timestamp": right[-1]["end_event_timestamp"] if right else None,
        "left_mean_credits_per_percent": _rounded(
            _mean_field(left, "credits_per_visible_percent")
        ),
        "right_mean_credits_per_percent": _rounded(
            _mean_field(right, "credits_per_visible_percent")
        ),
        "sse_reduction_share": _rounded(_number(split.get("sse_reduction_share"))),
    }


def _allowance_segment_record(
    rows: list[dict[str, Any]],
    start: int,
    end: int,
    *,
    segment_index: int,
) -> dict[str, Any]:
    segment_rows = rows[start:end]
    one_percent_rows = [row for row in segment_rows if row.get("is_one_percent")]
    return {
        "segment_index": segment_index,
        "start_index": start,
        "end_index": end - 1,
        "span_start_index": int(segment_rows[0]["span_index"]) if segment_rows else None,
        "span_end_index": int(segment_rows[-1]["span_index"]) if segment_rows else None,
        "start_event_timestamp": segment_rows[0]["start_event_timestamp"]
        if segment_rows
        else None,
        "end_event_timestamp": segment_rows[-1]["end_event_timestamp"]
        if segment_rows
        else None,
        "n": len(segment_rows),
        "credits_per_visible_percent": _allowance_capacity_distribution(segment_rows),
        "mean_delta_usage_percent": _rounded(
            _mean_field(segment_rows, "delta_usage_percent")
        ),
        "mean_standard_usage_credits": _rounded(
            _mean_field(segment_rows, "standard_usage_credits")
        ),
        "one_percent_span_count": len(one_percent_rows),
        "one_percent_mean_standard_usage_credits": _rounded(
            _mean_field(one_percent_rows, "standard_usage_credits")
        ),
        "rate_limit_plan_type_mix": _count_values(
            segment_rows,
            "rate_limit_plan_type",
        ),
        "rate_limit_limit_id_mix": _count_values(
            segment_rows,
            "rate_limit_limit_id",
        ),
        "usage_window_minutes_mix": _count_values(
            segment_rows,
            "usage_window_minutes",
        ),
        "credit_to_delta_fit": _credit_to_delta_fit(segment_rows),
    }


def _allowance_piecewise_credit_to_delta_fit(
    rows: list[dict[str, Any]],
    segments: list[tuple[int, int]],
) -> dict[str, Any]:
    actual = [_number(row.get("delta_usage_percent")) for row in rows]
    if not rows or not segments:
        return {
            "target": "visible_delta_percent",
            "models": {},
            "notes": [
                "No piecewise fit is available without breakpoint segments.",
            ],
        }

    mean_capacity_predictions: list[float] = []
    mean_capacity_ceiling_predictions: list[float] = []
    leave_one_out_predictions: list[float] = []
    slope_predictions: list[float] = []
    slope_ceiling_predictions: list[float] = []
    global_slope_ceiling_predictions: list[float] = []
    segment_models: list[dict[str, Any]] = []
    global_coefficients = _fit_linear_regression_coefficients(
        [[_number(row.get("standard_usage_credits"))] for row in rows],
        actual,
        intercept=False,
    )
    global_slope = global_coefficients[0] if global_coefficients else 0.0
    for segment_index, (start, end) in enumerate(segments, start=1):
        segment_rows = rows[start:end]
        capacities = [
            _number(row.get("credits_per_visible_percent")) for row in segment_rows
        ]
        credits = [_number(row.get("standard_usage_credits")) for row in segment_rows]
        delta = [_number(row.get("delta_usage_percent")) for row in segment_rows]
        mean_capacity = sum(capacities) / len(capacities) if capacities else 0.0
        segment_coefficients = _fit_linear_regression_coefficients(
            [[credit] for credit in credits],
            delta,
            intercept=False,
        )
        slope = segment_coefficients[0] if segment_coefficients else 0.0
        capacity_sum = sum(capacities)
        for offset, credit in enumerate(credits):
            global_prediction = global_slope * credit
            mean_prediction = credit / mean_capacity if mean_capacity > 0 else 0.0
            slope_prediction = slope * credit
            global_slope_ceiling_predictions.append(
                _ceil_to_visible_tick(global_prediction)
            )
            mean_capacity_predictions.append(mean_prediction)
            mean_capacity_ceiling_predictions.append(
                _ceil_to_visible_tick(mean_prediction)
            )
            slope_predictions.append(slope_prediction)
            slope_ceiling_predictions.append(_ceil_to_visible_tick(slope_prediction))
            if len(capacities) > 1:
                loo_capacity = (capacity_sum - capacities[offset]) / (
                    len(capacities) - 1
                )
            else:
                loo_capacity = mean_capacity
            leave_one_out_predictions.append(
                credit / loo_capacity if loo_capacity > 0 else 0.0
            )
        segment_models.append(
            {
                "segment_index": segment_index,
                "n": len(segment_rows),
                "mean_credits_per_visible_percent": _rounded(mean_capacity),
                "no_intercept_slope_delta_percent_per_credit": _rounded(slope),
                "no_intercept_implied_credits_per_percent": _rounded(
                    1 / slope if slope > 0 else None
                ),
            }
        )

    return {
        "target": "visible_delta_percent",
        "models": {
            "global_no_intercept_credit_slope": _credit_to_delta_fit(rows),
            "global_ceiling_no_intercept_credit_slope": {
                "description": (
                    "Fits one global no-intercept credit slope, then rounds each "
                    "positive prediction up to the next visible 1% tick."
                ),
                "metrics": _regression_metrics(
                    actual,
                    global_slope_ceiling_predictions,
                ),
            },
            "piecewise_mean_capacity_denominator": {
                "description": (
                    "Predicts visible delta as credits divided by the detected "
                    "segment mean credits per visible percent."
                ),
                "metrics": _regression_metrics(actual, mean_capacity_predictions),
            },
            "piecewise_ceiling_mean_capacity_denominator": {
                "description": (
                    "Predicts visible delta as credits divided by the detected "
                    "segment mean, then rounds positive predictions up to the "
                    "next visible 1% tick."
                ),
                "metrics": _regression_metrics(
                    actual,
                    mean_capacity_ceiling_predictions,
                ),
            },
            "piecewise_leave_one_out_capacity_denominator": {
                "description": (
                    "Predicts visible delta as credits divided by the detected "
                    "segment mean after excluding the current row from that mean."
                ),
                "metrics": _regression_metrics(actual, leave_one_out_predictions),
            },
            "piecewise_no_intercept_credit_slope": {
                "description": (
                    "Fits a no-intercept credit-to-delta slope separately inside "
                    "each detected segment."
                ),
                "metrics": _regression_metrics(actual, slope_predictions),
            },
            "piecewise_ceiling_no_intercept_credit_slope": {
                "description": (
                    "Fits a no-intercept credit-to-delta slope inside each "
                    "detected segment, then rounds positive predictions up to "
                    "the next visible 1% tick."
                ),
                "metrics": _regression_metrics(actual, slope_ceiling_predictions),
            },
        },
        "segment_models": segment_models,
        "notes": [
            "These fits test whether a capacity-adjusted credit metric explains visible drain after detected breakpoints.",
            "They are explanatory, not causal, because breakpoint detection uses the full observed series.",
        ],
    }


def _allowance_online_capacity_credit_to_delta_fit(
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

    model_descriptions = {
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
    predictions: dict[str, list[float]] = {
        name: [] for name in model_descriptions
    }
    ceiling_predictions: dict[str, list[float]] = {
        f"{name}_ceiling": [] for name in model_descriptions
    }
    actual: list[float] = []
    row_indexes: list[int] = []
    capacity_history: list[float] = []
    ewma_capacity: float | None = None
    for row_index, row in enumerate(rows):
        if capacity_history:
            credit = _number(row.get("standard_usage_credits"))
            estimates = {
                "previous_capacity_denominator": capacity_history[-1],
                "rolling3_mean_capacity_denominator": sum(capacity_history[-3:])
                / len(capacity_history[-3:]),
                "rolling10_mean_capacity_denominator": sum(capacity_history[-10:])
                / len(capacity_history[-10:]),
                "rolling10_median_capacity_denominator": float(
                    median(capacity_history[-10:])
                ),
                "ewma_capacity_denominator": ewma_capacity
                if ewma_capacity is not None
                else capacity_history[-1],
            }
            actual.append(_number(row.get("delta_usage_percent")))
            row_indexes.append(row_index)
            for model_name, capacity in estimates.items():
                prediction = credit / capacity if capacity and capacity > 0 else 0.0
                predictions[model_name].append(prediction)
                ceiling_predictions[f"{model_name}_ceiling"].append(
                    _ceil_to_visible_tick(prediction)
                )

        current_capacity = _number(row.get("credits_per_visible_percent"))
        if ewma_capacity is None:
            ewma_capacity = current_capacity
        else:
            ewma_capacity = (0.3 * current_capacity) + (0.7 * ewma_capacity)
        capacity_history.append(current_capacity)

    segment_start_indexes = {start for start, _end in segments if start > 0}
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
                model_descriptions[base_name]
                + " Positive predictions are rounded up to the next visible 1% tick."
            ),
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
    errors = [
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
    breakpoint_errors = [
        row["abs_error"] for row in errors if row["is_known_breakpoint"]
    ]
    non_breakpoint_errors = [
        row["abs_error"] for row in errors if not row["is_known_breakpoint"]
    ]
    total_abs_error = sum(row["abs_error"] for row in errors)
    largest = sorted(
        errors,
        key=lambda row: (-_number(row.get("abs_error")), int(row["row_index"])),
    )[:8]
    return {
        "known_breakpoint_row_count": len(breakpoint_errors),
        "non_breakpoint_row_count": len(non_breakpoint_errors),
        "known_breakpoint_abs_error_share": _rounded(
            sum(breakpoint_errors) / total_abs_error if total_abs_error > 0 else 0.0
        ),
        "known_breakpoint_mae": _rounded(
            sum(breakpoint_errors) / len(breakpoint_errors)
            if breakpoint_errors
            else None
        ),
        "non_breakpoint_mae": _rounded(
            sum(non_breakpoint_errors) / len(non_breakpoint_errors)
            if non_breakpoint_errors
            else None
        ),
        "largest_errors": [
            {
                "row_index": int(item["row_index"]),
                "span_index": int(rows[int(item["row_index"])]["span_index"]),
                "is_known_breakpoint": bool(item["is_known_breakpoint"]),
                "actual_delta_percent": _rounded(_number(item["actual"])),
                "predicted_delta_percent": _rounded(_number(item["predicted"])),
                "abs_error": _rounded(_number(item["abs_error"])),
                "credits_per_visible_percent": _rounded(
                    _number(
                        rows[int(item["row_index"])].get(
                            "credits_per_visible_percent"
                        )
                    )
                ),
                "standard_usage_credits": _rounded(
                    _number(
                        rows[int(item["row_index"])].get("standard_usage_credits")
                    )
                ),
                "start_event_timestamp": rows[int(item["row_index"])].get(
                    "start_event_timestamp"
                ),
                "end_event_timestamp": rows[int(item["row_index"])].get(
                    "end_event_timestamp"
                ),
            }
            for item in largest
        ],
    }


def _mean_field(rows: list[dict[str, Any]], field_name: str) -> float | None:
    if not rows:
        return None
    return sum(_number(row.get(field_name)) for row in rows) / len(rows)


def _credit_to_delta_fit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < 2:
        return {
            "n": len(rows),
            "slope_delta_percent_per_credit": None,
            "implied_credits_per_percent": None,
            "metrics": _regression_metrics([], []),
        }
    x_rows = [[_number(row.get("standard_usage_credits"))] for row in rows]
    actual = [_number(row.get("delta_usage_percent")) for row in rows]
    coefficients = _fit_linear_regression_coefficients(
        x_rows,
        actual,
        intercept=False,
    )
    predictions = _linear_regression_predictions(
        x_rows,
        coefficients,
        intercept=False,
    )
    slope = coefficients[0] if coefficients else 0.0
    return {
        "n": len(rows),
        "slope_delta_percent_per_credit": _rounded(slope),
        "implied_credits_per_percent": _rounded(1 / slope if slope > 0 else None),
        "metrics": _regression_metrics(actual, predictions),
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


def _capacity_model_specs() -> list[tuple[PredictiveModelSpec, str]]:
    start_context = (
        "baseline_used_percent",
        "usage_window_minutes",
        "reset_remaining_minutes",
        "window_elapsed_minutes",
        "window_elapsed_fraction",
        "days_since_first_span",
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
        "is_weekend",
    )
    history_context = (
        *start_context,
        "previous_capacity_credits",
        "rolling3_capacity_credits",
        "rolling10_capacity_credits",
        "rolling10_capacity_median",
        "rolling10_capacity_stddev",
        "same_hour_rolling10_capacity_credits",
        "same_hour_seen_count",
        "same_day_of_week_rolling10_capacity_credits",
        "same_day_of_week_seen_count",
        "ewma_capacity_credits",
    )
    time_categories = (
        "rate_limit_plan_type",
        "rate_limit_limit_id",
        "usage_window_source",
        "day_of_week",
    )
    date_categories = (*time_categories, "date", "hour_bucket")
    state_bucket_categories = (
        *time_categories,
        "hour_bucket",
        "baseline_used_bucket",
        "window_elapsed_bucket",
        "reset_remaining_bucket",
    )
    state_interaction_categories = (
        *state_bucket_categories,
        "baseline_used_x_window_elapsed_bucket",
        "hour_x_window_elapsed_bucket",
        "day_x_hour_bucket",
    )
    same_span_shape = (
        *history_context,
        "row_count",
        "call_duration_seconds",
        "mean_call_duration_seconds",
        "previous_call_delta_seconds",
        "span_wall_time_seconds",
        "span_wall_time_minutes",
        "mean_span_wall_time_seconds_per_call",
    )
    same_span_shape_categories = (
        *state_bucket_categories,
        "row_count_bucket",
        "call_duration_bucket",
        "span_wall_time_bucket",
    )
    same_span_shape_interaction_categories = (
        *same_span_shape_categories,
        "row_count_x_call_duration_bucket",
        "row_count_x_span_wall_time_bucket",
        "call_duration_x_span_wall_time_bucket",
        "hour_x_row_count_bucket",
        "baseline_used_x_row_count_bucket",
    )
    same_span_tokens = (
        *same_span_shape,
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "cache_ratio",
        "output_token_share",
        "reasoning_output_share",
    )
    specs: list[tuple[PredictiveModelSpec, str]] = [
        (
            PredictiveModelSpec(
                "capacity_start_context",
                start_context,
                time_categories,
            ),
            "causal_start_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_date_hour_context",
                start_context,
                date_categories,
            ),
            "causal_start_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_state_bucket_context",
                start_context,
                state_bucket_categories,
            ),
            "causal_start_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_history_context",
                history_context,
                time_categories,
            ),
            "causal_history_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_history_state_buckets",
                history_context,
                state_bucket_categories,
            ),
            "causal_history_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_history_state_interactions",
                history_context,
                state_interaction_categories,
            ),
            "causal_history_context",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_shape",
                same_span_shape,
                time_categories,
            ),
            "explanatory_same_span",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_shape_buckets",
                same_span_shape,
                same_span_shape_categories,
            ),
            "explanatory_same_span",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_shape_interactions",
                same_span_shape,
                same_span_shape_interaction_categories,
            ),
            "explanatory_same_span",
        ),
        (
            PredictiveModelSpec(
                "capacity_same_span_tokens",
                same_span_tokens,
                time_categories,
            ),
            "explanatory_same_span",
        ),
    ]
    for alpha in (10.0, 30.0, 100.0):
        alpha_label = _format_bucket_number(alpha)
        specs.extend(
            [
                (
                    PredictiveModelSpec(
                        f"capacity_history_state_interactions_ridge{alpha_label}",
                        history_context,
                        state_interaction_categories,
                        ridge_alpha=alpha,
                    ),
                    "causal_history_context",
                ),
                (
                    PredictiveModelSpec(
                        f"capacity_same_span_shape_interactions_ridge{alpha_label}",
                        same_span_shape,
                        same_span_shape_interaction_categories,
                        ridge_alpha=alpha,
                    ),
                    "explanatory_same_span",
                ),
            ]
        )
    return specs


def _walk_forward_prediction_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    rows = _walk_forward_prediction_rows(spans)
    scopes = {
        "all_after_first": 1,
        "all_after_10": 10,
        "all_after_50": 50,
        "time_ordered_holdout_20": max(1, min(len(spans) - 1, int(len(spans) * 0.8)))
        if spans
        else 0,
        "latest_500": max(len(spans) - 500, 1),
        "latest_100": max(len(spans) - 100, 1),
    }
    return {
        "model_descriptions": {
            "constant_one_percent": "Always predicts a 1% visible counter increase.",
            "previous_delta": "Predicts the previous closed positive usage delta.",
            "rolling3_mean_delta": "Predicts the mean of the previous 3 deltas.",
            "rolling10_mean_delta": "Predicts the mean of the previous 10 deltas.",
            "rolling10_median_delta": "Predicts the median of the previous 10 deltas.",
            "rolling10_mode_delta": "Predicts the most common previous 10-delta value.",
            "hybrid_streak_regime": (
                "Predicts 1% after at least three prior 1% deltas; otherwise "
                "uses previous delta after a repeated same-delta streak; "
                "otherwise uses rolling3 mean."
            ),
            "one_percent_regime_grace": (
                "Predicts 1% during a long 1% regime and for one small break "
                "after the regime; otherwise uses previous delta."
            ),
            "adaptive_low_delta_mode": (
                "Uses rolling10 mode when at least 80% of the previous 10 deltas "
                "are <=1%; otherwise uses previous delta."
            ),
            "adaptive_stable_mode": (
                "Uses rolling10 mode when rolling10 standard deviation is <=1%; "
                "otherwise uses previous delta."
            ),
            "empirical_history_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta "
                "and streak buckets, falling back to simpler history buckets."
            ),
            "empirical_calendar_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta, "
                "day-of-week, and hour buckets, with history fallbacks."
            ),
            "empirical_reset_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta, "
                "baseline, reset-phase, and reset-remaining buckets."
            ),
            "empirical_previous_work_state_mode": (
                "Uses the modal prior actual delta from matching previous-delta "
                "plus the prior span's wall-time and call-duration buckets."
            ),
            "transition_gated_history_state_mode": (
                "Uses the 1% continuation grace rule unless matched history-state "
                "transition risk is at least 50%, then uses matched history-state mode."
            ),
            "transition_weighted_history_state_mode": (
                "Blends the 1% continuation grace rule with matched history-state "
                "mode according to matched history-state transition risk."
            ),
            "adaptive_mae_transition_gate_history_state_mode": (
                "Learns the prior-best transition-risk threshold by MAE, then gates "
                "between the 1% continuation grace rule and matched history-state mode."
            ),
        },
        "scopes": {
            name: _walk_forward_scope_metrics(rows, start_index=start_index)
            for name, start_index in scopes.items()
        },
        "one_percent_grace_calibration": _one_percent_grace_calibration(spans, scopes),
        "transition_risk": _transition_risk_summary(rows, scopes),
        "state_ambiguity": _state_ambiguity_summary(rows, scopes),
    }


def _walk_forward_prediction_rows(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_deltas: list[float] = []
    previous_state_rows: list[dict[str, Any]] = []
    transition_gate_absolute_error_sums = {
        threshold: 0.0 for threshold in TRANSITION_DELTA_RISK_GATE_THRESHOLDS
    }
    for index, span in enumerate(spans):
        actual = span.delta_usage_percent
        metadata = _span_error_metadata(span)
        if previous_deltas:
            recent3 = previous_deltas[-3:]
            recent10 = previous_deltas[-10:]
            rolling10_mode = _value_mode(recent10)
            rolling10_stddev = _value_stddev(recent10)
            rolling10_low_share = sum(1 for value in recent10 if value <= 1.0) / len(
                recent10
            )
            one_percent_streak = _tail_streak(
                previous_deltas, predicate=_is_one_percent_delta
            )
            low_delta_streak = _tail_streak(
                previous_deltas, predicate=lambda value: value <= 1.0
            )
            same_delta_streak = _same_value_tail_streak(previous_deltas)
            hybrid_streak = (
                1.0
                if one_percent_streak >= 3
                else previous_deltas[-1]
                if same_delta_streak >= 2
                else sum(recent3) / len(recent3)
            )
            one_percent_grace = _one_percent_regime_grace_prediction(
                previous_deltas,
                streak_threshold=REGIME_GRACE_STREAK_THRESHOLD,
                grace_spans=REGIME_GRACE_SPANS,
                max_break_delta=REGIME_GRACE_MAX_BREAK_DELTA,
            )
            state = {
                **metadata,
                "previous_delta_value": previous_deltas[-1],
                "previous_delta_bucket": _delta_bucket(previous_deltas[-1]),
                "one_percent_streak_count": one_percent_streak,
                "one_percent_streak_bucket": _streak_bucket(one_percent_streak),
                "low_delta_streak_count": low_delta_streak,
                "low_delta_streak_bucket": _streak_bucket(low_delta_streak),
                "same_delta_streak_count": same_delta_streak,
                "same_delta_streak_bucket": _streak_bucket(same_delta_streak),
                "previous_span_wall_time_bucket": _previous_span_wall_time_bucket(
                    spans, index
                ),
                "previous_call_duration_bucket": _previous_call_duration_bucket(
                    spans, index
                ),
            }
            predictions = {
                "constant_one_percent": 1.0,
                "previous_delta": previous_deltas[-1],
                "rolling3_mean_delta": sum(recent3) / len(recent3),
                "rolling10_mean_delta": sum(recent10) / len(recent10),
                "rolling10_median_delta": float(median(recent10)),
                "rolling10_mode_delta": rolling10_mode,
                "hybrid_streak_regime": hybrid_streak,
                "one_percent_regime_grace": one_percent_grace,
                "adaptive_low_delta_mode": rolling10_mode
                if rolling10_low_share >= 0.8
                else previous_deltas[-1],
                "adaptive_stable_mode": rolling10_mode
                if rolling10_stddev <= 1.0
                else previous_deltas[-1],
            }
            state_predictions, state_prediction_details = _state_bucket_predictions(
                previous_state_rows,
                state,
                fallback_prediction=previous_deltas[-1],
            )
            predictions.update(state_predictions)
            transition_risks, transition_risk_details = _transition_risk_predictions(
                previous_state_rows,
                state,
            )
            history_state_prediction = _number(
                predictions.get("empirical_history_state_mode")
            )
            continuation_prediction = _number(predictions.get("one_percent_regime_grace"))
            history_state_risk = _number(transition_risks.get("history_state_risk"))
            adaptive_threshold, adaptive_threshold_detail = (
                _best_transition_delta_gate_threshold_from_sums(
                    transition_gate_absolute_error_sums,
                    training_count=len(rows),
                )
            )
            transition_gate_prediction = _risk_gated_transition_delta_prediction(
                continuation_prediction=continuation_prediction,
                alternate_prediction=history_state_prediction,
                risk=history_state_risk,
                threshold=TRANSITION_DELTA_RISK_GATE_THRESHOLD,
            )
            transition_weighted_prediction = continuation_prediction + (
                history_state_risk
                * (history_state_prediction - continuation_prediction)
            )
            adaptive_gate_prediction = _risk_gated_transition_delta_prediction(
                continuation_prediction=continuation_prediction,
                alternate_prediction=history_state_prediction,
                risk=history_state_risk,
                threshold=adaptive_threshold,
            )
            predictions["transition_gated_history_state_mode"] = (
                transition_gate_prediction
            )
            predictions["transition_weighted_history_state_mode"] = (
                transition_weighted_prediction
            )
            predictions["adaptive_mae_transition_gate_history_state_mode"] = (
                adaptive_gate_prediction
            )
            history_state_risk_detail = (
                transition_risk_details.get("history_state_risk") or {}
            )
            prediction_details = {
                **state_prediction_details,
                "transition_gated_history_state_mode": {
                    "source": "transition_gate_history_state_mode"
                    if history_state_risk >= TRANSITION_DELTA_RISK_GATE_THRESHOLD
                    else "transition_gate_continuation",
                    "risk_model": "history_state_risk",
                    "risk": _rounded(history_state_risk),
                    "risk_threshold": TRANSITION_DELTA_RISK_GATE_THRESHOLD,
                    "risk_detail": history_state_risk_detail,
                    "continuation_model": "one_percent_regime_grace",
                    "alternate_model": "empirical_history_state_mode",
                },
                "transition_weighted_history_state_mode": {
                    "source": "transition_weighted_blend",
                    "risk_model": "history_state_risk",
                    "risk": _rounded(history_state_risk),
                    "risk_detail": history_state_risk_detail,
                    "continuation_model": "one_percent_regime_grace",
                    "alternate_model": "empirical_history_state_mode",
                },
                "adaptive_mae_transition_gate_history_state_mode": {
                    "source": "adaptive_transition_gate_history_state_mode"
                    if history_state_risk >= adaptive_threshold
                    else "adaptive_transition_gate_continuation",
                    "risk_model": "history_state_risk",
                    "risk": _rounded(history_state_risk),
                    "risk_threshold": adaptive_threshold,
                    "training_metric": adaptive_threshold_detail.get("metric"),
                    "training_error": adaptive_threshold_detail.get("error"),
                    "training_support": adaptive_threshold_detail.get("support"),
                    "threshold_source": adaptive_threshold_detail.get("source"),
                    "risk_detail": history_state_risk_detail,
                    "continuation_model": "one_percent_regime_grace",
                    "alternate_model": "empirical_history_state_mode",
                },
            }
            row = {
                "index": index,
                "actual": actual,
                "previous_actual": previous_deltas[-1],
                "metadata": state,
                "predictions": predictions,
                "prediction_details": prediction_details,
                "transition_risks": transition_risks,
                "transition_risk_details": transition_risk_details,
            }
            rows.append(row)
            _update_transition_delta_gate_threshold_sums(
                transition_gate_absolute_error_sums,
                row=row,
            )
        previous_state_rows.append(
            {
                "actual": actual,
                "state": _history_state_for_span(spans, index, metadata, previous_deltas),
            }
        )
        previous_deltas.append(actual)
    return rows








def _walk_forward_scope_metrics(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    actual = [_number(row.get("actual")) for row in scope_rows]
    model_names = list(scope_rows[0]["predictions"].keys()) if scope_rows else []
    return {
        "start_index": start_index,
        "actual": _value_distribution(actual),
        "models": {
            model_name: _regression_metrics(
                actual,
                [
                    _number(row.get("predictions", {}).get(model_name))
                    for row in scope_rows
                ],
            )
            for model_name in model_names
        },
        "error_diagnostics": {
            model_name: _prediction_error_diagnostics(scope_rows, model_name)
            for model_name in (
                "constant_one_percent",
                "previous_delta",
                "rolling3_mean_delta",
                "rolling10_mode_delta",
                "hybrid_streak_regime",
                "one_percent_regime_grace",
                "adaptive_low_delta_mode",
                "empirical_history_state_mode",
                "empirical_calendar_state_mode",
                "empirical_reset_state_mode",
                "empirical_previous_work_state_mode",
                "transition_gated_history_state_mode",
                "transition_weighted_history_state_mode",
                "adaptive_mae_transition_gate_history_state_mode",
            )
            if model_name in model_names
        },
        "transition_gate_diagnostics": {
            model_name: _transition_delta_gate_diagnostics(scope_rows, model_name)
            for model_name in (
                "transition_gated_history_state_mode",
                "transition_weighted_history_state_mode",
                "adaptive_mae_transition_gate_history_state_mode",
            )
            if model_name in model_names
        },
        "state_bucket_diagnostics": {
            model_name: _state_bucket_model_diagnostics(scope_rows, model_name)
            for model_name in STATE_BUCKET_MODEL_SIGNATURES
            if model_name in model_names
        },
    }








































































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
