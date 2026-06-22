"""Aggregate-only helpers for modeling observed Codex usage drain.

This module compares local aggregate token-credit estimates with visible
rate-limit usage percentage deltas. It intentionally treats usage drain as a
coarse observed signal, not as billing truth.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

DOCUMENTED_FAST_CREDIT_MULTIPLIERS = {
    "gpt-5.5": 2.5,
    "gpt-5.4": 2.0,
}
FIVE_HOUR_WINDOW_MINUTES = 300

USAGE_DRAIN_MODEL_SCHEMA = "codex-usage-tracker-usage-drain-model-v1"
DEFAULT_PROXY_NAMES = (
    "all_candidates",
    "strong_only",
    "high_medium_candidates",
    "high_confidence_only",
)
TOKEN_TOTAL_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
TOKEN_COMPONENT_FIELDS = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "reasoning_output_tokens",
    "nonreasoning_output_tokens",
)
TIMING_TOTAL_FIELDS = (
    "call_duration_seconds",
    "previous_call_delta_seconds",
)
REGIME_GRACE_STREAK_THRESHOLD = 10
REGIME_GRACE_SPANS = 1
REGIME_GRACE_MAX_BREAK_DELTA = 2.0
REGIME_GRACE_THRESHOLD_GRID = (3, 5, 10, 25, 50, 100, 200)
REGIME_GRACE_SPAN_GRID = (1, 2, 3)
STATE_BUCKET_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "empirical_history_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "same_delta_streak_bucket",
            "low_delta_streak_bucket",
        ),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
    "empirical_calendar_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "day_of_week",
            "hour_bucket",
        ),
        ("previous_delta_bucket", "day_of_week", "hour_bucket"),
        ("day_of_week", "hour_bucket"),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
    "empirical_reset_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "baseline_used_bucket",
            "window_elapsed_bucket",
            "reset_remaining_bucket",
        ),
        ("previous_delta_bucket", "window_elapsed_bucket", "reset_remaining_bucket"),
        ("previous_delta_bucket", "baseline_used_bucket"),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
    "empirical_previous_work_state_mode": (
        (
            "previous_delta_bucket",
            "one_percent_streak_bucket",
            "previous_span_wall_time_bucket",
            "previous_call_duration_bucket",
        ),
        ("previous_delta_bucket", "previous_span_wall_time_bucket"),
        ("previous_delta_bucket", "previous_call_duration_bucket"),
        ("previous_delta_bucket", "one_percent_streak_bucket"),
        ("previous_delta_bucket",),
    ),
}
STATE_BUCKET_MIN_SUPPORT = 2
TRANSITION_RISK_MODEL_SIGNATURES: dict[str, tuple[tuple[str, ...], ...]] = {
    "history_state_risk": STATE_BUCKET_MODEL_SIGNATURES[
        "empirical_history_state_mode"
    ],
    "calendar_state_risk": STATE_BUCKET_MODEL_SIGNATURES[
        "empirical_calendar_state_mode"
    ],
    "reset_state_risk": STATE_BUCKET_MODEL_SIGNATURES["empirical_reset_state_mode"],
    "previous_work_state_risk": STATE_BUCKET_MODEL_SIGNATURES[
        "empirical_previous_work_state_mode"
    ],
}
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


@dataclass(frozen=True)
class FastProxyAnnotation:
    """One aggregate fast-mode proxy label keyed by usage record id."""

    label: str = "not_fast_proxy"
    timing_confidence: str = "unknown"
    score: float | None = None

    @property
    def is_candidate(self) -> bool:
        return self.label in {"strong_proxy", "possible_proxy"}

    @property
    def is_strong(self) -> bool:
        return self.label == "strong_proxy"

    @property
    def is_high_or_medium(self) -> bool:
        return self.is_candidate and self.timing_confidence in {"high", "medium"}

    @property
    def is_high(self) -> bool:
        return self.is_candidate and self.timing_confidence == "high"


@dataclass
class UsageDeltaSpan:
    """A closed positive visible-usage delta and its aggregate call mix."""

    start_event_timestamp: str
    end_event_timestamp: str
    baseline_used_percent: float
    end_used_percent: float
    delta_usage_percent: float
    row_count: int
    standard_usage_credits: float
    non_candidate_standard_credits: dict[str, float]
    candidate_standard_credits: dict[str, float]
    documented_fast_weighted_credits: dict[str, float]
    candidate_row_counts: dict[str, int]
    documented_fast_weighted_token_totals: dict[str, dict[str, float]] = field(
        default_factory=dict
    )
    models: dict[str, int] = field(default_factory=dict)
    token_totals: dict[str, float] = field(default_factory=dict)
    timing_totals: dict[str, float] = field(default_factory=dict)
    rate_limit_plan_type: str | None = None
    rate_limit_limit_id: str | None = None
    usage_window_source: str | None = None
    usage_window_minutes: float | None = None
    usage_window_resets_at: float | None = None
    rate_limit_primary_window_minutes: float | None = None
    rate_limit_primary_resets_at: float | None = None

    def to_row(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "start_event_timestamp": self.start_event_timestamp,
            "end_event_timestamp": self.end_event_timestamp,
            "baseline_used_percent": round(self.baseline_used_percent, 6),
            "end_used_percent": round(self.end_used_percent, 6),
            "delta_usage_percent": round(self.delta_usage_percent, 6),
            "row_count": self.row_count,
            "standard_usage_credits": round(self.standard_usage_credits, 6),
            "models": "|".join(f"{model}:{count}" for model, count in sorted(self.models.items())),
            "rate_limit_plan_type": self.rate_limit_plan_type,
            "rate_limit_limit_id": self.rate_limit_limit_id,
            "usage_window_source": self.usage_window_source,
            "usage_window_minutes": _rounded(self.usage_window_minutes),
            "usage_window_resets_at": _rounded(self.usage_window_resets_at),
            "rate_limit_primary_window_minutes": _rounded(
                self.rate_limit_primary_window_minutes
            ),
            "rate_limit_primary_resets_at": _rounded(self.rate_limit_primary_resets_at),
        }
        for field_name in TOKEN_TOTAL_FIELDS:
            row[field_name] = round(self.token_totals.get(field_name, 0.0), 6)
        for field_name in TIMING_TOTAL_FIELDS:
            row[field_name] = round(self.timing_totals.get(field_name, 0.0), 6)
        for proxy in DEFAULT_PROXY_NAMES:
            candidate = self.candidate_standard_credits.get(proxy, 0.0)
            documented = self.documented_fast_weighted_credits.get(proxy, 0.0)
            row[f"{proxy}_candidate_rows"] = self.candidate_row_counts.get(proxy, 0)
            row[f"{proxy}_candidate_standard_credits"] = round(candidate, 6)
            row[f"{proxy}_non_candidate_standard_credits"] = round(
                self.non_candidate_standard_credits.get(proxy, 0.0), 6
            )
            row[f"{proxy}_documented_fast_weighted_credits"] = round(documented, 6)
        return row


@dataclass(frozen=True)
class UsageDrainModelResult:
    """Fit result for one candidate proxy definition."""

    proxy: str
    spans: int
    candidate_spans: int
    candidate_span_share: float
    coef_non_candidate_usage_pct_per_credit: float | None
    coef_candidate_usage_pct_per_credit: float | None
    implied_candidate_multiplier: float | None
    documented_weighted_candidate_multiplier: float | None
    two_feature_r2: float | None
    grid: list[dict[str, float | None]]
    best_grid_multiplier_by_r2: float | None
    corr_candidate_credit_share_vs_drain_per_standard_credit: float | None
    spans_with_candidates: dict[str, float | int | None]
    spans_without_candidates: dict[str, float | int | None]
    with_vs_without_median_drain_ratio: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredictiveModelSpec:
    """One exploratory usage-drain prediction feature family."""

    name: str
    numeric_features: tuple[str, ...]
    categorical_features: tuple[str, ...] = ()
    ridge_alpha: float = 1.0


def documented_fast_credit_multiplier(model: object) -> float | None:
    """Return the documented fast-mode credit multiplier for a model label."""

    normalized = str(model or "").strip().lower()
    return DOCUMENTED_FAST_CREDIT_MULTIPLIERS.get(normalized)


def load_fast_proxy_annotations(path: Path | None) -> dict[str, FastProxyAnnotation]:
    """Load optional fast-mode proxy labels from a CSV produced by local analysis."""

    if path is None:
        return {}
    annotations: dict[str, FastProxyAnnotation] = {}
    with path.expanduser().open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            record_id = str(row.get("record_id") or "").strip()
            if not record_id:
                continue
            annotations[record_id] = FastProxyAnnotation(
                label=str(row.get("fast_proxy_label") or "not_fast_proxy").strip(),
                timing_confidence=str(row.get("timing_confidence") or "unknown")
                .strip()
                .lower(),
                score=_optional_number(row.get("fast_proxy_score")),
            )
    return annotations


def build_usage_delta_spans(
    rows: list[dict[str, Any]],
    *,
    fast_proxy_annotations: dict[str, FastProxyAnnotation] | None = None,
) -> tuple[list[UsageDeltaSpan], dict[str, int]]:
    """Group chronological rows into closed positive visible-usage delta spans.

    Calls with unchanged visible usage percent are held in the pending span and
    included when a later row shows a positive usage increase. Decreases, bucket
    changes, or missing initial baselines are censored rather than treated as
    zero-cost periods.
    """

    proxies = fast_proxy_annotations or {}
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            str(row.get("event_timestamp") or ""),
            str(row.get("record_id") or ""),
        ),
    )
    spans: list[UsageDeltaSpan] = []
    stats = {
        "input_rows": len(rows),
        "rows_without_usage_snapshot": 0,
        "rows_without_initial_baseline": 0,
        "censored_or_reset_pending_segments": 0,
        "positive_usage_spans": 0,
        "five_hour_usage_window_rows": 0,
        "fallback_usage_window_rows": 0,
    }

    baseline_percent: float | None = None
    baseline_bucket: tuple[Any, ...] | None = None
    pending_rows: list[dict[str, Any]] = []

    for row in sorted_rows:
        usage_observation = _preferred_usage_observation(row)
        if usage_observation["used_percent"] is None:
            stats["rows_without_usage_snapshot"] += 1
            if baseline_percent is None:
                stats["rows_without_initial_baseline"] += 1
            else:
                pending_rows.append(row)
            continue
        used_percent = float(usage_observation["used_percent"])
        bucket = _usage_bucket(row)
        if usage_observation["window_minutes"] == FIVE_HOUR_WINDOW_MINUTES:
            stats["five_hour_usage_window_rows"] += 1
        else:
            stats["fallback_usage_window_rows"] += 1

        if baseline_percent is None:
            baseline_percent = used_percent
            baseline_bucket = bucket
            pending_rows = []
            continue

        if bucket != baseline_bucket:
            if pending_rows:
                stats["censored_or_reset_pending_segments"] += 1
            baseline_percent = used_percent
            baseline_bucket = bucket
            pending_rows = []
            continue

        if used_percent < baseline_percent:
            if pending_rows:
                stats["censored_or_reset_pending_segments"] += 1
            baseline_percent = used_percent
            pending_rows = []
            continue

        pending_rows.append(row)
        if used_percent <= baseline_percent:
            continue

        spans.append(
            _span_from_rows(
                pending_rows,
                baseline_percent=baseline_percent,
                end_used_percent=used_percent,
                proxies=proxies,
            )
        )
        stats["positive_usage_spans"] += 1
        baseline_percent = used_percent
        pending_rows = []

    if pending_rows:
        stats["censored_or_reset_pending_segments"] += 1
    return spans, stats


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
    candidates = [
        (name, values.get("mae"))
        for name, values in metrics.items()
        if isinstance(values, dict) and values.get("mae") is not None
    ]
    if not candidates:
        return None
    name, value = min(candidates, key=lambda item: float(item[1]))
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


def _row_token_components(row: dict[str, Any]) -> dict[str, float]:
    cached_input = _number(row.get("cached_input_tokens"))
    uncached_input = _number(row.get("uncached_input_tokens"))
    if uncached_input <= 0:
        uncached_input = max(_number(row.get("input_tokens")) - cached_input, 0.0)
    reasoning_output = _number(row.get("reasoning_output_tokens"))
    output_tokens = _number(row.get("output_tokens"))
    return {
        "uncached_input_tokens": uncached_input,
        "cached_input_tokens": cached_input,
        "reasoning_output_tokens": reasoning_output,
        "nonreasoning_output_tokens": max(output_tokens - reasoning_output, 0.0),
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


def _visible_delta_family_sequences() -> dict[str, list[tuple[str, str]]]:
    return {
        "cost_and_time_controls": [
            ("train mean", "baseline_train_mean"),
            ("credits", "credits_only"),
            ("token shape", "token_shape"),
            ("fast proxy", "fast_proxy"),
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


def _capacity_family_sequences() -> dict[str, list[tuple[str, str]]]:
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


def _model_family_attribution(
    models: list[dict[str, Any]],
    sequences: dict[str, list[tuple[str, str]]],
) -> dict[str, Any]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    validations: list[str] = []
    for model in models:
        validation = str(model.get("validation") or "missing")
        if validation not in validations:
            validations.append(validation)
        base_name = _model_base_name(model, validation)
        by_key[(validation, base_name)] = model

    sequence_results: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for sequence_name, steps in sequences.items():
        validation_rows: dict[str, list[dict[str, Any]]] = {}
        for validation in validations:
            rows: list[dict[str, Any]] = []
            previous_mae: float | None = None
            previous_r2: float | None = None
            for family, base_name in steps:
                model = by_key.get((validation, base_name))
                if model is None:
                    continue
                mae = _holdout_metric(model, "mae")
                r2 = _holdout_metric(model, "r2")
                rows.append(
                    {
                        "family": family,
                        "model": model.get("name"),
                        "holdout_mae": _rounded(mae),
                        "holdout_r2": _rounded(r2),
                        "mae_improvement_vs_previous": _rounded(
                            previous_mae - mae
                            if previous_mae is not None and mae is not None
                            else None
                        ),
                        "r2_delta_vs_previous": _rounded(
                            r2 - previous_r2
                            if previous_r2 is not None and r2 is not None
                            else None
                        ),
                    }
                )
                previous_mae = mae
                previous_r2 = r2
            validation_rows[validation] = rows
        sequence_results[sequence_name] = validation_rows

    return {
        "metric_notes": [
            "mae_improvement_vs_previous is positive when the later family reduces holdout MAE.",
            "Sequences are diagnostic comparisons between named model families, not causal proof that one field caused the gain.",
        ],
        "sequences": sequence_results,
    }


def _model_base_name(model: dict[str, Any], validation: str) -> str:
    name = str(model.get("name") or "")
    suffix = f"__{validation}"
    if name.endswith(suffix):
        return name[: -len(suffix)]
    return name.rsplit("__", 1)[0]


def _holdout_metric(model: dict[str, Any], metric: str) -> float | None:
    holdout = model.get("holdout")
    if not isinstance(holdout, dict):
        return None
    value = holdout.get(metric)
    if value is None:
        return None
    return _number(value)


def _best_holdout_model(models: list[dict[str, Any]]) -> dict[str, Any] | None:
    return min(
        models,
        key=lambda result: _number(result.get("holdout", {}).get("mae"))
        if result.get("holdout", {}).get("mae") is not None
        else math.inf,
        default=None,
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


def _span_correlation_row(span: UsageDeltaSpan) -> dict[str, float]:
    row = {
        "delta_usage_percent": span.delta_usage_percent,
        "row_count": float(span.row_count),
        "standard_usage_credits": span.standard_usage_credits,
        "call_duration_seconds": span.timing_totals.get("call_duration_seconds", 0.0),
        "previous_call_delta_seconds": span.timing_totals.get(
            "previous_call_delta_seconds", 0.0
        ),
        "span_wall_time_seconds": _span_wall_time_seconds(span),
        "baseline_used_percent": span.baseline_used_percent,
    }
    for field_name in TOKEN_TOTAL_FIELDS:
        row[field_name] = span.token_totals.get(field_name, 0.0)
    return row


def _span_wall_time_seconds(span: UsageDeltaSpan) -> float:
    start_dt = _parse_timestamp(span.start_event_timestamp)
    end_dt = _parse_timestamp(span.end_event_timestamp)
    if start_dt is None or end_dt is None:
        return 0.0
    return max((end_dt - start_dt).total_seconds(), 0.0)


def _correlation_report(
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
            "pearson": _rounded(
                _pearson([row[feature_name] for row in rows], target_values)
            ),
            "spearman": _rounded(
                _spearman([row[feature_name] for row in rows], target_values)
            ),
        }
        for feature_name in feature_names
        if feature_name != target
    ]
    return {
        "n": len(rows),
        "target": target,
        "target_mean": _rounded(sum(target_values) / len(target_values)),
        "target_stddev": _rounded(_value_stddev(target_values)),
        "top_abs_pearson": sorted(
            correlations,
            key=lambda row: abs(_number(row["pearson"])),
            reverse=True,
        )[:10],
        "top_abs_spearman": sorted(
            correlations,
            key=lambda row: abs(_number(row["spearman"])),
            reverse=True,
        )[:10],
    }


def _delta_distribution(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
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
            "share": _rounded(count / len(values)),
        }
        for value, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )[:8]
    ]
    return {
        "spans": len(values),
        "mean_delta_percent": _rounded(mean_value),
        "median_delta_percent": _rounded(median(values)),
        "std_delta_percent": _rounded(
            math.sqrt(sum((value - mean_value) ** 2 for value in values) / len(values))
        ),
        "min_delta_percent": _rounded(min(values)),
        "max_delta_percent": _rounded(max(values)),
        "one_percent_share": _rounded(
            sum(1 for value in values if round(value, 6) == 1.0) / len(values)
        ),
        "top_delta_values": top_values,
    }


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
        },
        "scopes": {
            name: _walk_forward_scope_metrics(rows, start_index=start_index)
            for name, start_index in scopes.items()
        },
        "one_percent_grace_calibration": _one_percent_grace_calibration(spans, scopes),
        "transition_risk": _transition_risk_summary(rows, scopes),
    }


def _walk_forward_prediction_rows(spans: list[UsageDeltaSpan]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous_deltas: list[float] = []
    previous_state_rows: list[dict[str, Any]] = []
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
            rows.append(
                {
                    "index": index,
                    "actual": actual,
                    "previous_actual": previous_deltas[-1],
                    "metadata": state,
                    "predictions": predictions,
                    "prediction_details": state_prediction_details,
                    "transition_risks": transition_risks,
                    "transition_risk_details": transition_risk_details,
                }
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
            )
            if model_name in model_names
        },
        "state_bucket_diagnostics": {
            model_name: _state_bucket_model_diagnostics(scope_rows, model_name)
            for model_name in STATE_BUCKET_MODEL_SIGNATURES
            if model_name in model_names
        },
    }


def _history_state_for_span(
    spans: list[UsageDeltaSpan],
    index: int,
    metadata: dict[str, Any],
    previous_deltas: list[float],
) -> dict[str, Any]:
    if previous_deltas:
        one_percent_streak = _tail_streak(
            previous_deltas, predicate=_is_one_percent_delta
        )
        low_delta_streak = _tail_streak(
            previous_deltas, predicate=lambda value: value <= 1.0
        )
        same_delta_streak = _same_value_tail_streak(previous_deltas)
        previous_delta_value = previous_deltas[-1]
        previous_delta_bucket = _delta_bucket(previous_deltas[-1])
    else:
        one_percent_streak = 0
        low_delta_streak = 0
        same_delta_streak = 0
        previous_delta_value = 0.0
        previous_delta_bucket = "missing"
    return {
        **metadata,
        "previous_delta_value": previous_delta_value,
        "previous_delta_bucket": previous_delta_bucket,
        "one_percent_streak_count": one_percent_streak,
        "one_percent_streak_bucket": _streak_bucket(one_percent_streak),
        "low_delta_streak_count": low_delta_streak,
        "low_delta_streak_bucket": _streak_bucket(low_delta_streak),
        "same_delta_streak_count": same_delta_streak,
        "same_delta_streak_bucket": _streak_bucket(same_delta_streak),
        "previous_span_wall_time_bucket": _previous_span_wall_time_bucket(
            spans, index
        ),
        "previous_call_duration_bucket": _previous_call_duration_bucket(spans, index),
    }


def _state_bucket_predictions(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    fallback_prediction: float,
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    predictions: dict[str, float] = {}
    details: dict[str, dict[str, Any]] = {}
    for model_name, signatures in STATE_BUCKET_MODEL_SIGNATURES.items():
        prediction, detail = _state_bucket_prediction(
            previous_state_rows,
            state,
            signatures=signatures,
            fallback_prediction=fallback_prediction,
        )
        predictions[model_name] = prediction
        details[model_name] = detail
    return predictions, details


def _transition_risk_predictions(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
) -> tuple[dict[str, float], dict[str, dict[str, Any]]]:
    prior_rate = _transition_rate(previous_state_rows)
    risks = {
        "overall_prior_rate": prior_rate,
        "stable_one_percent_rule": (
            0.0
            if int(state.get("one_percent_streak_count") or 0)
            >= REGIME_GRACE_STREAK_THRESHOLD
            else prior_rate
        ),
    }
    details = {
        "overall_prior_rate": {
            "source": "all_prior_spans",
            "support": len(previous_state_rows),
        },
        "stable_one_percent_rule": {
            "source": "long_one_percent_streak"
            if int(state.get("one_percent_streak_count") or 0)
            >= REGIME_GRACE_STREAK_THRESHOLD
            else "fallback_prior_rate",
            "support": len(previous_state_rows),
        },
    }
    for model_name, signatures in TRANSITION_RISK_MODEL_SIGNATURES.items():
        risk, detail = _state_bucket_transition_risk(
            previous_state_rows,
            state,
            signatures=signatures,
            fallback_rate=prior_rate,
        )
        risks[model_name] = risk
        details[model_name] = detail
    return risks, details


def _state_bucket_transition_risk(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    signatures: tuple[tuple[str, ...], ...],
    fallback_rate: float,
) -> tuple[float, dict[str, Any]]:
    for signature in signatures:
        matches = [
            row
            for row in previous_state_rows
            if _state_signature(row.get("state", {}), signature)
            == _state_signature(state, signature)
        ]
        if len(matches) < STATE_BUCKET_MIN_SUPPORT:
            continue
        risk = _transition_rate(matches)
        return risk, {
            "source": "matched_state",
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


def _transition_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if not _is_one_percent_delta(_number(row.get("actual")))) / len(rows)


def _state_bucket_prediction(
    previous_state_rows: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    signatures: tuple[tuple[str, ...], ...],
    fallback_prediction: float,
) -> tuple[float, dict[str, Any]]:
    for signature in signatures:
        matches = [
            row
            for row in previous_state_rows
            if _state_signature(row.get("state", {}), signature)
            == _state_signature(state, signature)
        ]
        if len(matches) < STATE_BUCKET_MIN_SUPPORT:
            continue
        actual_values = [_number(row.get("actual")) for row in matches]
        prediction = _value_mode(actual_values)
        return prediction, {
            "source": "matched_state",
            "signature": list(signature),
            "support": len(matches),
            "matched_mode": _rounded(prediction),
        }
    return fallback_prediction, {
        "source": "fallback_previous_delta",
        "signature": [],
        "support": 0,
        "matched_mode": None,
    }


def _state_signature(state: dict[str, Any], signature: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(state.get(field) or "missing") for field in signature)


def _state_bucket_model_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("prediction_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "n": 0,
            "matched_state_share": None,
            "mean_support": None,
            "top_signatures": [],
        }
    matched = [detail for detail in details if detail.get("source") == "matched_state"]
    signature_counts: dict[str, int] = {}
    for detail in matched:
        label = ",".join(str(item) for item in detail.get("signature") or [])
        signature_counts[label or "missing"] = signature_counts.get(label or "missing", 0) + 1
    top_signatures = [
        {"signature": signature, "count": count, "share": _rounded(count / len(details))}
        for signature, count in sorted(
            signature_counts.items(), key=lambda item: (-item[1], item[0])
        )[:8]
    ]
    return {
        "n": len(details),
        "matched_state_share": _rounded(len(matched) / len(details)),
        "mean_support": _rounded(
            sum(int(detail.get("support") or 0) for detail in matched) / len(matched)
            if matched
            else None
        ),
        "fallback_share": _rounded((len(details) - len(matched)) / len(details)),
        "top_signatures": top_signatures,
    }


def _transition_risk_summary(
    rows: list[dict[str, Any]], scopes: dict[str, int]
) -> dict[str, Any]:
    target_definitions = {
        "non_one_percent_delta": (
            "Next visible positive delta is not exactly 1%, across all scoped spans."
        ),
        "break_after_long_one_percent_run": (
            "Scoped to rows whose prior state has at least the configured long "
            "1% streak; target is whether the next delta breaks away from 1%."
        ),
    }
    return {
        "risk_models": {
            "overall_prior_rate": "Historical non-1% rate before the current span.",
            "stable_one_percent_rule": (
                "Predicts zero break risk after the configured long 1% streak; "
                "otherwise uses the historical prior rate."
            ),
            "history_state_risk": "Empirical non-1% rate for matching history/streak buckets.",
            "calendar_state_risk": "Empirical non-1% rate for matching calendar buckets.",
            "reset_state_risk": "Empirical non-1% rate for matching reset/window buckets.",
            "previous_work_state_risk": (
                "Empirical non-1% rate for matching previous-span work-duration buckets."
            ),
        },
        "target_definitions": target_definitions,
        "scopes": {
            scope_name: _transition_risk_scope(rows, start_index=start_index)
            for scope_name, start_index in scopes.items()
        },
    }


def _transition_risk_scope(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    long_run_rows = [
        row
        for row in scope_rows
        if int((row.get("metadata") or {}).get("one_percent_streak_count") or 0)
        >= REGIME_GRACE_STREAK_THRESHOLD
    ]
    return {
        "non_one_percent_delta": _transition_target_metrics(scope_rows),
        "break_after_long_one_percent_run": _transition_target_metrics(
            long_run_rows
        ),
    }


def _transition_target_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual = [
        0 if _is_one_percent_delta(_number(row.get("actual"))) else 1
        for row in rows
    ]
    risk_models = _transition_risk_model_names(rows)
    return {
        "n": len(rows),
        "positive_count": sum(actual),
        "positive_rate": _rounded(sum(actual) / len(actual) if actual else None),
        "models": {
            model_name: _binary_risk_metrics(
                actual,
                [
                    _number((row.get("transition_risks") or {}).get(model_name))
                    for row in rows
                ],
            )
            for model_name in risk_models
        },
        "risk_detail_diagnostics": {
            model_name: _transition_risk_detail_diagnostics(rows, model_name)
            for model_name in risk_models
            if model_name not in {"overall_prior_rate", "stable_one_percent_rule"}
        },
    }


def _transition_risk_model_names(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []
    names: list[str] = []
    for row in rows:
        for name in (row.get("transition_risks") or {}):
            if name not in names:
                names.append(str(name))
    return names


def _binary_risk_metrics(actual: list[int], scores: list[float]) -> dict[str, Any]:
    if not actual or len(actual) != len(scores):
        return {
            "n": len(actual),
            "brier": None,
            "auc": None,
            "average_precision": None,
            "precision_at_top_10pct": None,
            "recall_at_top_10pct": None,
            "top_10pct_positive_rate": None,
            "mean_score_positive": None,
            "mean_score_negative": None,
        }
    clipped_scores = [min(max(score, 0.0), 1.0) for score in scores]
    positives = [score for value, score in zip(actual, clipped_scores, strict=True) if value]
    negatives = [
        score for value, score in zip(actual, clipped_scores, strict=True) if not value
    ]
    top_count = max(1, math.ceil(len(actual) * 0.1))
    ranked = sorted(
        zip(actual, clipped_scores, strict=True),
        key=lambda item: item[1],
        reverse=True,
    )
    top = ranked[:top_count]
    positive_count = sum(actual)
    top_positive_count = sum(value for value, _score in top)
    return {
        "n": len(actual),
        "brier": _rounded(
            sum((score - value) ** 2 for value, score in zip(actual, clipped_scores, strict=True))
            / len(actual)
        ),
        "auc": _rounded(_binary_auc(actual, clipped_scores)),
        "average_precision": _rounded(_average_precision(actual, clipped_scores)),
        "precision_at_top_10pct": _rounded(top_positive_count / len(top)),
        "recall_at_top_10pct": _rounded(
            top_positive_count / positive_count if positive_count else None
        ),
        "top_10pct_positive_rate": _rounded(top_positive_count / len(top)),
        "mean_score_positive": _rounded(
            sum(positives) / len(positives) if positives else None
        ),
        "mean_score_negative": _rounded(
            sum(negatives) / len(negatives) if negatives else None
        ),
    }


def _binary_auc(actual: list[int], scores: list[float]) -> float | None:
    positive_count = sum(actual)
    negative_count = len(actual) - positive_count
    if positive_count == 0 or negative_count == 0:
        return None
    ranked = sorted(zip(scores, actual, strict=True), key=lambda item: item[0])
    rank_sum = 0.0
    index = 0
    while index < len(ranked):
        end = index
        while end + 1 < len(ranked) and ranked[end + 1][0] == ranked[index][0]:
            end += 1
        average_rank = ((index + 1) + (end + 1)) / 2.0
        positives_in_tie = sum(value for _score, value in ranked[index : end + 1])
        rank_sum += positives_in_tie * average_rank
        index = end + 1
    return (rank_sum - (positive_count * (positive_count + 1) / 2.0)) / (
        positive_count * negative_count
    )


def _average_precision(actual: list[int], scores: list[float]) -> float | None:
    positive_count = sum(actual)
    if positive_count == 0:
        return None
    ranked = sorted(
        zip(actual, scores, strict=True), key=lambda item: item[1], reverse=True
    )
    seen_positive = 0
    precision_sum = 0.0
    for rank, (value, _score) in enumerate(ranked, start=1):
        if not value:
            continue
        seen_positive += 1
        precision_sum += seen_positive / rank
    return precision_sum / positive_count


def _transition_risk_detail_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    details = [
        (row.get("transition_risk_details") or {}).get(model_name) or {}
        for row in rows
    ]
    if not details:
        return {
            "matched_state_share": None,
            "mean_support": None,
            "top_signatures": [],
        }
    matched = [detail for detail in details if detail.get("source") == "matched_state"]
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


def _previous_span_wall_time_bucket(spans: list[UsageDeltaSpan], index: int) -> str:
    if index <= 0:
        return "missing"
    return _second_bucket(_span_wall_time_seconds(spans[index - 1]))


def _previous_call_duration_bucket(spans: list[UsageDeltaSpan], index: int) -> str:
    if index <= 0:
        return "missing"
    return _second_bucket(
        spans[index - 1].timing_totals.get("call_duration_seconds", 0.0)
    )


def _delta_bucket(value: float) -> str:
    rounded = round(value, 6)
    if rounded == 1.0:
        return "1_pct"
    if rounded == 2.0:
        return "2_pct"
    if rounded == 3.0:
        return "3_pct"
    if rounded <= 0:
        return "0_pct"
    if rounded < 1.0:
        return "0_1_pct"
    if rounded < 5.0:
        return "3_5_pct"
    if rounded < 10.0:
        return "5_10_pct"
    if rounded < 25.0:
        return "10_25_pct"
    return "25_plus_pct"


def _one_percent_grace_calibration(
    spans: list[UsageDeltaSpan], scopes: dict[str, int]
) -> dict[str, Any]:
    values = [span.delta_usage_percent for span in spans]
    if len(values) < 2:
        return {
            "default_config": _one_percent_grace_config(
                REGIME_GRACE_STREAK_THRESHOLD, REGIME_GRACE_SPANS
            ),
            "scopes": {},
        }
    scope_results: dict[str, Any] = {}
    for scope_name, start_index in scopes.items():
        rows = []
        for threshold in REGIME_GRACE_THRESHOLD_GRID:
            for grace_spans in REGIME_GRACE_SPAN_GRID:
                rows.append(
                    _one_percent_grace_calibration_row(
                        values,
                        start_index=max(1, start_index),
                        streak_threshold=threshold,
                        grace_spans=grace_spans,
                    )
                )
        rows.sort(
            key=lambda row: (
                _number(row["mae"]),
                _number(row["rmse"]),
                int(row["streak_threshold"]),
                int(row["grace_spans"]),
            )
        )
        default_row = _one_percent_grace_calibration_row(
            values,
            start_index=max(1, start_index),
            streak_threshold=REGIME_GRACE_STREAK_THRESHOLD,
            grace_spans=REGIME_GRACE_SPANS,
        )
        by_rmse = sorted(
            rows,
            key=lambda row: (
                _number(row["rmse"]),
                _number(row["mae"]),
                int(row["streak_threshold"]),
                int(row["grace_spans"]),
            ),
        )
        scope_results[scope_name] = {
            "default": default_row,
            "best_by_mae": rows[0] if rows else None,
            "best_by_rmse": by_rmse[0] if by_rmse else None,
            "top_by_mae": rows[:5],
        }
    return {
        "default_config": _one_percent_grace_config(
            REGIME_GRACE_STREAK_THRESHOLD, REGIME_GRACE_SPANS
        ),
        "scopes": scope_results,
    }


def _one_percent_grace_calibration_row(
    values: list[float],
    *,
    start_index: int,
    streak_threshold: int,
    grace_spans: int,
) -> dict[str, Any]:
    actual: list[float] = []
    predictions: list[float] = []
    for index in range(max(1, start_index), len(values)):
        previous = values[:index]
        actual.append(values[index])
        predictions.append(
            _one_percent_regime_grace_prediction(
                previous,
                streak_threshold=streak_threshold,
                grace_spans=grace_spans,
                max_break_delta=REGIME_GRACE_MAX_BREAK_DELTA,
            )
        )
    metrics = _regression_metrics(actual, predictions)
    return {
        **_one_percent_grace_config(streak_threshold, grace_spans),
        "n": len(actual),
        "mae": metrics["mae"],
        "rmse": metrics["rmse"],
        "r2": metrics["r2"],
        "exact_match_share": _rounded(
            sum(
                1
                for actual_value, predicted_value in zip(
                    actual, predictions, strict=True
                )
                if round(actual_value, 6) == round(predicted_value, 6)
            )
            / len(actual)
            if actual
            else None
        ),
    }


def _one_percent_grace_config(
    streak_threshold: int, grace_spans: int
) -> dict[str, Any]:
    return {
        "streak_threshold": streak_threshold,
        "grace_spans": grace_spans,
        "max_break_delta_percent": REGIME_GRACE_MAX_BREAK_DELTA,
    }


def _one_percent_regime_grace_prediction(
    previous_deltas: list[float],
    *,
    streak_threshold: int,
    grace_spans: int,
    max_break_delta: float,
) -> float:
    if not previous_deltas:
        return 0.0
    one_percent_streak = _tail_streak(
        previous_deltas, predicate=_is_one_percent_delta
    )
    if one_percent_streak >= streak_threshold:
        return 1.0
    break_age = _small_break_age_after_one_percent_run(
        previous_deltas,
        streak_threshold=streak_threshold,
        max_break_delta=max_break_delta,
    )
    if break_age is not None and break_age <= grace_spans:
        return 1.0
    return previous_deltas[-1]


def _small_break_age_after_one_percent_run(
    values: list[float], *, streak_threshold: int, max_break_delta: float
) -> int | None:
    if not values or _is_one_percent_delta(values[-1]):
        return None
    index = len(values) - 1
    break_age = 0
    while (
        index >= 0
        and not _is_one_percent_delta(values[index])
        and values[index] <= max_break_delta
    ):
        break_age += 1
        index -= 1
    if break_age == 0:
        return None
    preceding_streak = 0
    while index >= 0 and _is_one_percent_delta(values[index]):
        preceding_streak += 1
        index -= 1
    if preceding_streak >= streak_threshold:
        return break_age
    return None


def _span_error_metadata(span: UsageDeltaSpan) -> dict[str, Any]:
    start_dt = _parse_timestamp(span.start_event_timestamp)
    reset_timestamp = (
        span.usage_window_resets_at
        if span.usage_window_resets_at is not None
        else span.rate_limit_primary_resets_at
    )
    reset_remaining_minutes = _reset_remaining_minutes(start_dt, reset_timestamp)
    window_minutes = (
        span.usage_window_minutes
        if span.usage_window_minutes is not None
        else span.rate_limit_primary_window_minutes or 0.0
    )
    reset_minutes = reset_remaining_minutes or 0.0
    elapsed_fraction = (
        min(max((window_minutes - reset_minutes) / window_minutes, 0.0), 1.0)
        if window_minutes > 0
        else 0.0
    )
    return {
        "date": start_dt.date().isoformat() if start_dt else "missing",
        "day_of_week": str(start_dt.weekday()) if start_dt else "missing",
        "hour_bucket": f"{start_dt.hour:02d}" if start_dt else "missing",
        "reset_phase": _reset_phase_bucket(elapsed_fraction),
        "baseline_used_bucket": _numeric_bucket(
            span.baseline_used_percent, width=5.0, max_value=100.0, suffix="pct"
        ),
        "window_elapsed_bucket": _reset_phase_bucket(elapsed_fraction),
        "reset_remaining_bucket": _minute_bucket(reset_minutes),
        "rate_limit_plan_type": span.rate_limit_plan_type or "missing",
        "rate_limit_limit_id": span.rate_limit_limit_id or "missing",
        "usage_window_source": span.usage_window_source or "missing",
    }


def _reset_phase_bucket(elapsed_fraction: float) -> str:
    if elapsed_fraction <= 0:
        return "missing"
    if elapsed_fraction < 0.25:
        return "first_quarter"
    if elapsed_fraction < 0.5:
        return "second_quarter"
    if elapsed_fraction < 0.75:
        return "third_quarter"
    return "fourth_quarter"


def _numeric_bucket(
    value: float, *, width: float, max_value: float, suffix: str
) -> str:
    if value <= 0 or width <= 0:
        return f"0_{suffix}"
    if value >= max_value:
        return f"{_format_bucket_number(max_value)}_plus_{suffix}"
    lower = math.floor(value / width) * width
    upper = lower + width
    return (
        f"{_format_bucket_number(lower)}_"
        f"{_format_bucket_number(upper)}_{suffix}"
    )


def _minute_bucket(minutes: float) -> str:
    if minutes <= 0:
        return "0_min"
    if minutes <= 15:
        return "0_15_min"
    if minutes <= 30:
        return "15_30_min"
    if minutes <= 60:
        return "30_60_min"
    if minutes <= 120:
        return "60_120_min"
    if minutes <= 240:
        return "120_240_min"
    if minutes <= 360:
        return "240_360_min"
    return "360_plus_min"


def _second_bucket(seconds: float) -> str:
    if seconds <= 0:
        return "0_sec"
    if seconds <= 30:
        return "0_30_sec"
    if seconds <= 60:
        return "30_60_sec"
    if seconds <= 120:
        return "60_120_sec"
    if seconds <= 300:
        return "120_300_sec"
    if seconds <= 900:
        return "300_900_sec"
    if seconds <= 1800:
        return "900_1800_sec"
    return "1800_plus_sec"


def _format_bucket_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "_")


def _prediction_error_diagnostics(
    rows: list[dict[str, Any]], model_name: str
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for row in rows:
        predictions = row.get("predictions", {})
        predicted = _number(predictions.get(model_name))
        actual = _number(row.get("actual"))
        previous_actual = _number(row.get("previous_actual"))
        error = predicted - actual
        errors.append(
            {
                "index": int(row["index"]),
                "actual": actual,
                "predicted": predicted,
                "previous_actual": previous_actual,
                "error": error,
                "abs_error": abs(error),
                "metadata": row.get("metadata", {}),
            }
        )
    if not errors:
        return {
            "n": 0,
            "exact_match_share": None,
            "within_quarter_point_share": None,
            "within_one_point_share": None,
            "large_error_share": None,
            "top_transition_errors": [],
            "top_error_dates": [],
            "error_by_day_of_week": [],
            "error_by_hour": [],
            "error_by_reset_phase": [],
            "error_by_one_percent_streak": [],
            "error_by_same_delta_streak": [],
            "largest_errors": [],
        }
    return {
        "n": len(errors),
        "exact_match_share": _rounded(
            sum(1 for item in errors if item["abs_error"] == 0) / len(errors)
        ),
        "within_quarter_point_share": _rounded(
            sum(1 for item in errors if item["abs_error"] <= 0.25) / len(errors)
        ),
        "within_one_point_share": _rounded(
            sum(1 for item in errors if item["abs_error"] <= 1.0) / len(errors)
        ),
        "large_error_share": _rounded(
            sum(1 for item in errors if item["abs_error"] >= 5.0) / len(errors)
        ),
        "top_transition_errors": _top_transition_errors(errors),
        "top_error_dates": _top_error_groups(errors, "date"),
        "error_by_day_of_week": _top_error_groups(errors, "day_of_week"),
        "error_by_hour": _top_error_groups(errors, "hour_bucket"),
        "error_by_reset_phase": _top_error_groups(errors, "reset_phase"),
        "error_by_one_percent_streak": _top_error_groups(
            errors, "one_percent_streak_bucket"
        ),
        "error_by_same_delta_streak": _top_error_groups(
            errors, "same_delta_streak_bucket"
        ),
        "largest_errors": _largest_prediction_errors(errors),
    }


def _top_transition_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for item in errors:
        key = (round(item["previous_actual"], 6), round(item["actual"], 6))
        grouped.setdefault(key, []).append(item)
    rows = [
        {
            "previous_delta_percent": previous,
            "actual_delta_percent": actual,
            "count": len(items),
            "mean_abs_error": _rounded(
                sum(item["abs_error"] for item in items) / len(items)
            ),
            "max_abs_error": _rounded(max(item["abs_error"] for item in items)),
        }
        for (previous, actual), items in grouped.items()
    ]
    rows.sort(key=lambda row: (-_number(row["mean_abs_error"]), -int(row["count"])))
    return rows[:10]


def _top_error_groups(errors: list[dict[str, Any]], field_name: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in errors:
        metadata = item.get("metadata", {})
        key = str(metadata.get(field_name) or "missing")
        grouped.setdefault(key, []).append(item)
    rows = [
        {
            field_name: key,
            "count": len(items),
            "mean_abs_error": _rounded(
                sum(item["abs_error"] for item in items) / len(items)
            ),
            "max_abs_error": _rounded(max(item["abs_error"] for item in items)),
        }
        for key, items in grouped.items()
    ]
    rows.sort(key=lambda row: (-_number(row["mean_abs_error"]), -int(row["count"])))
    return rows[:10]


def _largest_prediction_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(errors, key=lambda item: item["abs_error"], reverse=True)[:10]
    return [
        {
            "index": item["index"],
            "date": item["metadata"].get("date"),
            "hour_bucket": item["metadata"].get("hour_bucket"),
            "day_of_week": item["metadata"].get("day_of_week"),
            "reset_phase": item["metadata"].get("reset_phase"),
            "previous_delta_percent": _rounded(item["previous_actual"]),
            "actual_delta_percent": _rounded(item["actual"]),
            "predicted_delta_percent": _rounded(item["predicted"]),
            "abs_error": _rounded(item["abs_error"]),
        }
        for item in rows
    ]


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


def _capacity_residual_diagnostics(
    rows: list[dict[str, Any]], actual: list[float], predicted: list[float]
) -> dict[str, Any]:
    errors = [
        {
            "actual": actual_value,
            "predicted": predicted_value,
            "error": predicted_value - actual_value,
            "abs_error": abs(predicted_value - actual_value),
            "metadata": _capacity_residual_metadata(row),
        }
        for row, actual_value, predicted_value in zip(rows, actual, predicted, strict=True)
    ]
    if not errors:
        return {
            "n": 0,
            "mean_error": None,
            "within_5_credits_share": None,
            "within_10_credits_share": None,
            "large_error_share": None,
            "top_error_groups": {},
            "largest_errors": [],
        }
    return {
        "n": len(errors),
        "mean_error": _rounded(
            sum(item["error"] for item in errors) / len(errors)
        ),
        "within_5_credits_share": _rounded(
            sum(1 for item in errors if item["abs_error"] <= 5.0) / len(errors)
        ),
        "within_10_credits_share": _rounded(
            sum(1 for item in errors if item["abs_error"] <= 10.0) / len(errors)
        ),
        "large_error_share": _rounded(
            sum(1 for item in errors if item["abs_error"] >= 25.0) / len(errors)
        ),
        "top_error_groups": {
            field_name: _capacity_top_error_groups(errors, field_name)
            for field_name in CAPACITY_RESIDUAL_GROUP_FIELDS
        },
        "largest_errors": _largest_capacity_residual_errors(errors),
    }


def _capacity_residual_metadata(row: dict[str, Any]) -> dict[str, Any]:
    return {
        field_name: row.get(field_name, "missing")
        for field_name in CAPACITY_RESIDUAL_GROUP_FIELDS
    }


def _capacity_top_error_groups(
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
            "mean_abs_error": _rounded(
                sum(item["abs_error"] for item in items) / len(items)
            ),
            "mean_error": _rounded(sum(item["error"] for item in items) / len(items)),
            "max_abs_error": _rounded(max(item["abs_error"] for item in items)),
            "mean_actual": _rounded(sum(item["actual"] for item in items) / len(items)),
            "mean_predicted": _rounded(
                sum(item["predicted"] for item in items) / len(items)
            ),
        }
        for key, items in grouped.items()
    ]
    rows.sort(key=lambda row: (-_number(row["mean_abs_error"]), -int(row["count"])))
    return rows[:10]


def _largest_capacity_residual_errors(
    errors: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows = sorted(errors, key=lambda item: item["abs_error"], reverse=True)[:10]
    return [
        {
            "actual_credits": _rounded(item["actual"]),
            "predicted_credits": _rounded(item["predicted"]),
            "error_credits": _rounded(item["error"]),
            "abs_error_credits": _rounded(item["abs_error"]),
            **item["metadata"],
        }
        for item in rows
    ]


def _value_distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "stddev": None,
            "min": None,
            "max": None,
        }
    mean = sum(values) / len(values)
    return {
        "n": len(values),
        "mean": _rounded(mean),
        "stddev": _rounded(_value_stddev(values)),
        "min": _rounded(min(values)),
        "max": _rounded(max(values)),
    }


def _value_mode(values: list[float]) -> float:
    if not values:
        return 0.0
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    max_count = max(counts.values())
    candidates = {value for value, count in counts.items() if count == max_count}
    for value in reversed(values):
        if value in candidates:
            return value
    return values[-1]


def _value_stddev(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


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
    best_grid = max(
        (item for item in grid if item.get("r2_slope") is not None),
        key=lambda item: float(item["r2_slope"]),
        default=None,
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
        best_grid_multiplier_by_r2=(
            float(best_grid["multiplier"]) if best_grid is not None else None
        ),
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


def fit_predictive_usage_drain_models(
    spans: list[UsageDeltaSpan],
    *,
    proxy: str = "all_candidates",
    train_fraction: float = 0.8,
) -> list[dict[str, Any]]:
    """Fit exploratory train/holdout models for richer control variables."""

    feature_rows = [_span_feature_row(span, proxy=proxy) for span in spans]
    if len(feature_rows) < 10:
        return []
    _add_days_since_first_span(feature_rows)
    _add_causal_history_features(feature_rows)
    results: list[dict[str, Any]] = []
    for split_name, train_rows, holdout_rows in _split_feature_rows(
        feature_rows, train_fraction=train_fraction
    ):
        results.extend(_fit_causal_baseline_models(train_rows, holdout_rows, split_name))
        for spec in _predictive_model_specs():
            fitted = _fit_predictive_model(train_rows, holdout_rows, spec)
            if fitted is not None:
                fitted["validation"] = split_name
                fitted["name"] = f"{spec.name}__{split_name}"
                results.append(fitted)
    return results


def _split_feature_rows(
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


def _fit_causal_baseline_models(
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
        train_y = [_number(row.get("target")) for row in train_rows]
        holdout_y = [_number(row.get("target")) for row in holdout_rows]
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
                "kind": "causal_baseline",
                "feature_count": 1 if feature_field or constant is not None else 0,
                "numeric_features": [feature_field] if feature_field else [],
                "categorical_features": [],
                "train": _regression_metrics(train_y, train_predictions),
                "holdout": _regression_metrics(holdout_y, holdout_predictions),
                "top_coefficients": [],
            }
        )
    return results


def _baseline_predictions(
    rows: list[dict[str, Any]], *, field: str | None, constant: float | None
) -> list[float]:
    if constant is not None:
        return [constant for _row in rows]
    if field is None:
        return [0.0 for _row in rows]
    return [_number(row.get(field)) for row in rows]


def _span_from_rows(
    rows: list[dict[str, Any]],
    *,
    baseline_percent: float,
    end_used_percent: float,
    proxies: dict[str, FastProxyAnnotation],
) -> UsageDeltaSpan:
    standard = 0.0
    candidate = dict.fromkeys(DEFAULT_PROXY_NAMES, 0.0)
    non_candidate = dict.fromkeys(DEFAULT_PROXY_NAMES, 0.0)
    documented_weighted = dict.fromkeys(DEFAULT_PROXY_NAMES, 0.0)
    candidate_counts = dict.fromkeys(DEFAULT_PROXY_NAMES, 0)
    documented_weighted_token_totals = {
        proxy: dict.fromkeys(TOKEN_COMPONENT_FIELDS, 0.0)
        for proxy in DEFAULT_PROXY_NAMES
    }
    model_counts: dict[str, int] = {}
    token_totals = dict.fromkeys(TOKEN_TOTAL_FIELDS, 0.0)
    timing_totals = dict.fromkeys(TIMING_TOTAL_FIELDS, 0.0)
    for row in rows:
        credits = max(_number(row.get("usage_credits")), 0.0)
        standard += credits
        model = str(row.get("model") or "unknown")
        model_counts[model] = model_counts.get(model, 0) + 1
        for field_name in TOKEN_TOTAL_FIELDS:
            token_totals[field_name] += _number(row.get(field_name))
        for field_name in TIMING_TOTAL_FIELDS:
            timing_totals[field_name] += _number(row.get(field_name))
        annotation = proxies.get(str(row.get("record_id") or ""), FastProxyAnnotation())
        token_components = _row_token_components(row)
        proxy_flags = {
            "all_candidates": annotation.is_candidate,
            "strong_only": annotation.is_strong,
            "high_medium_candidates": annotation.is_high_or_medium,
            "high_confidence_only": annotation.is_high,
        }
        multiplier = documented_fast_credit_multiplier(model) or 1.0
        for proxy_name, is_candidate in proxy_flags.items():
            token_multiplier = multiplier if is_candidate else 1.0
            for field_name, value in token_components.items():
                documented_weighted_token_totals[proxy_name][
                    field_name
                ] += value * token_multiplier
            if is_candidate:
                candidate[proxy_name] += credits
                documented_weighted[proxy_name] += credits * multiplier
                candidate_counts[proxy_name] += 1
            else:
                non_candidate[proxy_name] += credits
                documented_weighted[proxy_name] += credits
    usage_observation = _preferred_usage_observation(rows[-1])

    return UsageDeltaSpan(
        start_event_timestamp=str(rows[0].get("event_timestamp") or ""),
        end_event_timestamp=str(rows[-1].get("event_timestamp") or ""),
        baseline_used_percent=baseline_percent,
        end_used_percent=end_used_percent,
        delta_usage_percent=end_used_percent - baseline_percent,
        row_count=len(rows),
        standard_usage_credits=standard,
        non_candidate_standard_credits=non_candidate,
        candidate_standard_credits=candidate,
        documented_fast_weighted_credits=documented_weighted,
        candidate_row_counts=candidate_counts,
        documented_fast_weighted_token_totals=documented_weighted_token_totals,
        models=model_counts,
        token_totals=token_totals,
        timing_totals=timing_totals,
        rate_limit_plan_type=_optional_text(rows[-1].get("rate_limit_plan_type")),
        rate_limit_limit_id=_optional_text(rows[-1].get("rate_limit_limit_id")),
        usage_window_source=str(usage_observation["source"] or "missing"),
        usage_window_minutes=_optional_number(usage_observation["window_minutes"]),
        usage_window_resets_at=_optional_number(usage_observation["resets_at"]),
        rate_limit_primary_window_minutes=_optional_number(
            rows[-1].get("rate_limit_primary_window_minutes")
        ),
        rate_limit_primary_resets_at=_optional_number(
            rows[-1].get("rate_limit_primary_resets_at")
        ),
    )


def _predictive_model_specs() -> list[PredictiveModelSpec]:
    base = (
        "standard_usage_credits",
        "log_standard_usage_credits",
    )
    token_shape = (
        *base,
        "row_count",
        "input_tokens",
        "cached_input_tokens",
        "uncached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "cache_ratio",
        "output_token_share",
        "reasoning_output_share",
        "mean_usage_credits_per_call",
    )
    fast_proxy = (
        *token_shape,
        "candidate_standard_credits",
        "non_candidate_standard_credits",
        "candidate_credit_share",
        "documented_fast_weighted_credits",
        "documented_fast_extra_credits",
    )
    usage_state = (
        *fast_proxy,
        "baseline_used_percent",
        "usage_window_minutes",
        "rate_limit_primary_window_minutes",
        "reset_remaining_minutes",
        "window_elapsed_minutes",
        "window_elapsed_fraction",
    )
    time_controls = (
        *usage_state,
        "days_since_first_span",
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
        "is_weekend",
    )
    duration_controls = (
        *time_controls,
        "call_duration_seconds",
        "mean_call_duration_seconds",
        "previous_call_delta_seconds",
        "span_wall_time_seconds",
        "span_wall_time_minutes",
        "mean_span_wall_time_seconds_per_call",
    )
    lag_regime = (
        *usage_state,
        "previous_delta_percent",
        "previous_drain_per_credit",
        "rolling3_delta_percent",
        "rolling10_delta_percent",
        "rolling50_delta_percent",
        "rolling10_median_delta_percent",
        "rolling10_mode_delta_percent",
        "rolling10_delta_stddev",
        "rolling50_delta_stddev",
        "one_percent_streak",
        "low_delta_streak",
        "same_delta_streak",
        "high_delta_streak",
        "hybrid_streak_delta_percent",
        "rolling3_drain_per_credit",
        "rolling10_drain_per_credit",
        "rolling50_drain_per_credit",
        "rolling10_low_delta_share",
        "rolling3_to_50_delta_ratio",
        "same_bucket_rolling10_delta_percent",
        "same_bucket_rolling10_mode_delta_percent",
        "same_bucket_rolling10_drain_per_credit",
        "same_bucket_seen_count",
        "same_date_rolling10_delta_percent",
        "same_date_rolling10_mode_delta_percent",
        "same_date_seen_count",
        "same_hour_rolling10_delta_percent",
        "same_hour_rolling10_mode_delta_percent",
        "same_hour_seen_count",
        "same_day_of_week_rolling10_delta_percent",
        "same_day_of_week_rolling10_mode_delta_percent",
        "same_day_of_week_seen_count",
        "ewma_delta_percent",
        "ewma_drain_per_credit",
    )
    lag_time = (
        *lag_regime,
        "days_since_first_span",
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
        "is_weekend",
    )
    adaptive_full = (
        *lag_time,
        "call_duration_seconds",
        "mean_call_duration_seconds",
        "previous_call_delta_seconds",
        "span_wall_time_seconds",
        "span_wall_time_minutes",
        "mean_span_wall_time_seconds_per_call",
    )
    return [
        PredictiveModelSpec("baseline_train_mean", ()),
        PredictiveModelSpec("credits_only", base),
        PredictiveModelSpec("token_shape", token_shape),
        PredictiveModelSpec("fast_proxy", fast_proxy),
        PredictiveModelSpec(
            "usage_state",
            usage_state,
            ("rate_limit_plan_type", "rate_limit_limit_id", "usage_window_source"),
        ),
        PredictiveModelSpec(
            "time_controls",
            time_controls,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "usage_window_source",
                "day_of_week",
            ),
        ),
        PredictiveModelSpec(
            "date_day_hour_controls",
            time_controls,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "usage_window_source",
                "date",
                "day_of_week",
                "hour_bucket",
            ),
        ),
        PredictiveModelSpec(
            "full_controls",
            duration_controls,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "usage_window_source",
                "date",
                "day_of_week",
                "hour_bucket",
            ),
        ),
        PredictiveModelSpec(
            "lag_regime",
            lag_regime,
            ("rate_limit_plan_type", "rate_limit_limit_id", "usage_window_source"),
        ),
        PredictiveModelSpec(
            "lag_time_controls",
            lag_time,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "usage_window_source",
                "day_of_week",
            ),
        ),
        PredictiveModelSpec(
            "adaptive_full_controls",
            adaptive_full,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "usage_window_source",
                "date",
                "day_of_week",
                "hour_bucket",
            ),
        ),
    ]


def _span_feature_row(span: UsageDeltaSpan, *, proxy: str) -> dict[str, Any]:
    start_dt = _parse_timestamp(span.start_event_timestamp)
    date_label = start_dt.date().isoformat() if start_dt else "missing"
    day_index = start_dt.weekday() if start_dt else -1
    hour_value = (
        start_dt.hour + (start_dt.minute / 60.0) + (start_dt.second / 3600.0)
        if start_dt
        else 0.0
    )
    hour_bucket = f"{start_dt.hour:02d}" if start_dt else "missing"
    standard = span.standard_usage_credits
    candidate = span.candidate_standard_credits.get(proxy, 0.0)
    non_candidate = span.non_candidate_standard_credits.get(proxy, 0.0)
    documented = span.documented_fast_weighted_credits.get(proxy, standard)
    input_tokens = span.token_totals.get("input_tokens", 0.0)
    cached_tokens = span.token_totals.get("cached_input_tokens", 0.0)
    output_tokens = span.token_totals.get("output_tokens", 0.0)
    reasoning_tokens = span.token_totals.get("reasoning_output_tokens", 0.0)
    total_tokens = span.token_totals.get("total_tokens", 0.0)
    duration = span.timing_totals.get("call_duration_seconds", 0.0)
    span_wall_time_seconds = _span_wall_time_seconds(span)
    window_minutes = (
        span.usage_window_minutes
        if span.usage_window_minutes is not None
        else span.rate_limit_primary_window_minutes or 0.0
    )
    reset_timestamp = (
        span.usage_window_resets_at
        if span.usage_window_resets_at is not None
        else span.rate_limit_primary_resets_at
    )
    reset_remaining_minutes = _reset_remaining_minutes(start_dt, reset_timestamp)
    reset_minutes = reset_remaining_minutes or 0.0
    window_elapsed_minutes = (
        max(window_minutes - reset_minutes, 0.0) if window_minutes > 0 else 0.0
    )
    window_elapsed_fraction = (
        min(max(window_elapsed_minutes / window_minutes, 0.0), 1.0)
        if window_minutes > 0
        else 0.0
    )
    day_of_week = str(day_index) if day_index >= 0 else "missing"
    baseline_used_bucket = _numeric_bucket(
        span.baseline_used_percent, width=5.0, max_value=100.0, suffix="pct"
    )
    window_elapsed_bucket = _reset_phase_bucket(window_elapsed_fraction)
    reset_remaining_bucket = _minute_bucket(reset_minutes)
    row_count_bucket = _numeric_bucket(
        float(span.row_count), width=5.0, max_value=50.0, suffix="calls"
    )
    call_duration_bucket = _second_bucket(duration)
    span_wall_time_bucket = _second_bucket(span_wall_time_seconds)
    return {
        "target": span.delta_usage_percent,
        "start_event_timestamp": span.start_event_timestamp,
        "standard_usage_credits": standard,
        "log_standard_usage_credits": math.log1p(max(standard, 0.0)),
        "row_count": float(span.row_count),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "uncached_input_tokens": span.token_totals.get("uncached_input_tokens", 0.0),
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "cache_ratio": cached_tokens / input_tokens if input_tokens else 0.0,
        "output_token_share": output_tokens / total_tokens if total_tokens else 0.0,
        "reasoning_output_share": reasoning_tokens / output_tokens if output_tokens else 0.0,
        "mean_usage_credits_per_call": standard / span.row_count if span.row_count else 0.0,
        "candidate_standard_credits": candidate,
        "non_candidate_standard_credits": non_candidate,
        "candidate_credit_share": candidate / standard if standard else 0.0,
        "documented_fast_weighted_credits": documented,
        "documented_fast_extra_credits": max(documented - standard, 0.0),
        "baseline_used_percent": span.baseline_used_percent,
        "rate_limit_primary_window_minutes": span.rate_limit_primary_window_minutes or 0.0,
        "usage_window_minutes": window_minutes,
        "usage_window_source": span.usage_window_source or "missing",
        "reset_remaining_minutes": reset_minutes,
        "window_elapsed_minutes": window_elapsed_minutes,
        "window_elapsed_fraction": window_elapsed_fraction,
        "baseline_used_bucket": baseline_used_bucket,
        "window_elapsed_bucket": window_elapsed_bucket,
        "reset_remaining_bucket": reset_remaining_bucket,
        "baseline_used_x_window_elapsed_bucket": (
            f"{baseline_used_bucket}__{window_elapsed_bucket}"
        ),
        "hour_x_window_elapsed_bucket": f"{hour_bucket}__{window_elapsed_bucket}",
        "day_x_hour_bucket": f"{day_of_week}__{hour_bucket}",
        "days_since_first_span": 0.0,
        "hour_sin": math.sin(2 * math.pi * hour_value / 24.0),
        "hour_cos": math.cos(2 * math.pi * hour_value / 24.0),
        "day_of_week_sin": math.sin(2 * math.pi * day_index / 7.0) if day_index >= 0 else 0.0,
        "day_of_week_cos": math.cos(2 * math.pi * day_index / 7.0) if day_index >= 0 else 0.0,
        "is_weekend": 1.0 if day_index in {5, 6} else 0.0,
        "call_duration_seconds": duration,
        "mean_call_duration_seconds": duration / span.row_count if span.row_count else 0.0,
        "previous_call_delta_seconds": span.timing_totals.get("previous_call_delta_seconds", 0.0),
        "span_wall_time_seconds": span_wall_time_seconds,
        "span_wall_time_minutes": span_wall_time_seconds / 60.0,
        "mean_span_wall_time_seconds_per_call": (
            span_wall_time_seconds / span.row_count if span.row_count else 0.0
        ),
        "row_count_bucket": row_count_bucket,
        "call_duration_bucket": call_duration_bucket,
        "span_wall_time_bucket": span_wall_time_bucket,
        "row_count_x_call_duration_bucket": (
            f"{row_count_bucket}__{call_duration_bucket}"
        ),
        "row_count_x_span_wall_time_bucket": (
            f"{row_count_bucket}__{span_wall_time_bucket}"
        ),
        "call_duration_x_span_wall_time_bucket": (
            f"{call_duration_bucket}__{span_wall_time_bucket}"
        ),
        "hour_x_row_count_bucket": f"{hour_bucket}__{row_count_bucket}",
        "baseline_used_x_row_count_bucket": (
            f"{baseline_used_bucket}__{row_count_bucket}"
        ),
        "date": date_label,
        "day_of_week": day_of_week,
        "hour_bucket": hour_bucket,
        "rate_limit_plan_type": span.rate_limit_plan_type or "missing",
        "rate_limit_limit_id": span.rate_limit_limit_id or "missing",
    }


def _add_days_since_first_span(rows: list[dict[str, Any]]) -> None:
    first_date: datetime | None = None
    for row in rows:
        parsed = _parse_timestamp(str(row.get("date") or ""))
        if parsed is None:
            parsed = _parse_timestamp(str(row.get("start_event_timestamp") or ""))
        if parsed is not None and first_date is None:
            first_date = parsed
        if parsed is None or first_date is None:
            row["days_since_first_span"] = 0.0
        else:
            row["days_since_first_span"] = max(
                (parsed.date() - first_date.date()).days, 0
            )


def _add_causal_history_features(rows: list[dict[str, Any]]) -> None:
    """Attach walk-forward features that only use previous closed spans."""

    previous_rows: list[dict[str, Any]] = []
    bucket_rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    date_rows: dict[str, list[dict[str, Any]]] = {}
    hour_rows: dict[str, list[dict[str, Any]]] = {}
    day_of_week_rows: dict[str, list[dict[str, Any]]] = {}
    ewma_delta: float | None = None
    ewma_drain: float | None = None
    alpha = 0.2
    for row in rows:
        bucket_key = (
            str(row.get("rate_limit_plan_type") or "missing"),
            str(row.get("rate_limit_limit_id") or "missing"),
        )
        date_key = str(row.get("date") or "missing")
        hour_key = str(row.get("hour_bucket") or "missing")
        day_of_week_key = str(row.get("day_of_week") or "missing")
        recent_bucket_rows = bucket_rows.get(bucket_key, [])
        recent_date_rows = date_rows.get(date_key, [])
        recent_hour_rows = hour_rows.get(hour_key, [])
        recent_day_of_week_rows = day_of_week_rows.get(day_of_week_key, [])
        row["previous_delta_percent"] = _previous_value(previous_rows, "target")
        row["previous_drain_per_credit"] = _previous_drain_per_credit(previous_rows)
        row["rolling3_delta_percent"] = _rolling_mean(previous_rows, "target", 3)
        row["rolling10_delta_percent"] = _rolling_mean(previous_rows, "target", 10)
        row["rolling50_delta_percent"] = _rolling_mean(previous_rows, "target", 50)
        row["rolling10_median_delta_percent"] = _rolling_median(
            previous_rows, "target", 10
        )
        row["rolling10_mode_delta_percent"] = _rolling_mode(previous_rows, "target", 10)
        row["rolling10_delta_stddev"] = _rolling_stddev(previous_rows, "target", 10)
        row["rolling50_delta_stddev"] = _rolling_stddev(previous_rows, "target", 50)
        one_percent_streak = _row_tail_streak(
            previous_rows,
            predicate=lambda previous: _is_one_percent_delta(
                _number(previous.get("target"))
            ),
        )
        low_delta_streak = _row_tail_streak(
            previous_rows,
            predicate=lambda previous: _number(previous.get("target")) <= 1.0,
        )
        same_delta_streak = _same_target_tail_streak(previous_rows)
        high_delta_streak = _row_tail_streak(
            previous_rows,
            predicate=lambda previous: _number(previous.get("target")) > 1.0,
        )
        row["one_percent_streak"] = float(one_percent_streak)
        row["low_delta_streak"] = float(low_delta_streak)
        row["same_delta_streak"] = float(same_delta_streak)
        row["high_delta_streak"] = float(high_delta_streak)
        row["hybrid_streak_delta_percent"] = (
            1.0
            if one_percent_streak >= 3
            else _number(row["previous_delta_percent"])
            if same_delta_streak >= 2
            else _number(row["rolling3_delta_percent"])
        )
        row["rolling3_drain_per_credit"] = _rolling_drain_per_credit(previous_rows, 3)
        row["rolling10_drain_per_credit"] = _rolling_drain_per_credit(previous_rows, 10)
        row["rolling50_drain_per_credit"] = _rolling_drain_per_credit(previous_rows, 50)
        row["rolling10_low_delta_share"] = _rolling_low_delta_share(previous_rows, 10)
        rolling50 = _number(row["rolling50_delta_percent"])
        row["rolling3_to_50_delta_ratio"] = (
            _number(row["rolling3_delta_percent"]) / rolling50 if rolling50 > 0 else 0.0
        )
        row["same_bucket_rolling10_delta_percent"] = _rolling_mean(
            recent_bucket_rows, "target", 10
        )
        row["same_bucket_rolling10_mode_delta_percent"] = _rolling_mode(
            recent_bucket_rows, "target", 10
        )
        row["same_bucket_rolling10_drain_per_credit"] = _rolling_drain_per_credit(
            recent_bucket_rows, 10
        )
        row["same_bucket_seen_count"] = float(len(recent_bucket_rows))
        row["same_date_rolling10_delta_percent"] = _rolling_mean(
            recent_date_rows, "target", 10
        )
        row["same_date_rolling10_mode_delta_percent"] = _rolling_mode(
            recent_date_rows, "target", 10
        )
        row["same_date_seen_count"] = float(len(recent_date_rows))
        row["same_hour_rolling10_delta_percent"] = _rolling_mean(
            recent_hour_rows, "target", 10
        )
        row["same_hour_rolling10_mode_delta_percent"] = _rolling_mode(
            recent_hour_rows, "target", 10
        )
        row["same_hour_seen_count"] = float(len(recent_hour_rows))
        row["same_day_of_week_rolling10_delta_percent"] = _rolling_mean(
            recent_day_of_week_rows, "target", 10
        )
        row["same_day_of_week_rolling10_mode_delta_percent"] = _rolling_mode(
            recent_day_of_week_rows, "target", 10
        )
        row["same_day_of_week_seen_count"] = float(len(recent_day_of_week_rows))
        row["ewma_delta_percent"] = ewma_delta or 0.0
        row["ewma_drain_per_credit"] = ewma_drain or 0.0

        current_delta = _number(row.get("target"))
        current_drain = _drain_per_credit(row)
        ewma_delta = (
            current_delta
            if ewma_delta is None
            else (alpha * current_delta) + ((1 - alpha) * ewma_delta)
        )
        ewma_drain = (
            current_drain
            if ewma_drain is None
            else (alpha * current_drain) + ((1 - alpha) * ewma_drain)
        )
        previous_rows.append(row)
        bucket_rows.setdefault(bucket_key, []).append(row)
        date_rows.setdefault(date_key, []).append(row)
        hour_rows.setdefault(hour_key, []).append(row)
        day_of_week_rows.setdefault(day_of_week_key, []).append(row)


def _previous_value(rows: list[dict[str, Any]], field: str) -> float:
    if not rows:
        return 0.0
    return _number(rows[-1].get(field))


def _previous_drain_per_credit(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return _drain_per_credit(rows[-1])


def _rolling_mean(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return sum(_number(row.get(field)) for row in selected) / len(selected)


def _rolling_median(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return float(median(_number(row.get(field)) for row in selected))


def _rolling_mode(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return _value_mode([_number(row.get(field)) for row in selected])


def _rolling_stddev(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return _value_stddev([_number(row.get(field)) for row in selected])


def _rolling_drain_per_credit(rows: list[dict[str, Any]], window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    return sum(_drain_per_credit(row) for row in selected) / len(selected)


def _rolling_low_delta_share(rows: list[dict[str, Any]], window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    low_count = sum(1 for row in selected if _number(row.get("target")) <= 1.0)
    return low_count / len(selected)


def _row_tail_streak(
    rows: list[dict[str, Any]], *, predicate: Any
) -> int:
    count = 0
    for row in reversed(rows):
        if not predicate(row):
            break
        count += 1
    return count


def _tail_streak(values: list[float], *, predicate: Any) -> int:
    count = 0
    for value in reversed(values):
        if not predicate(value):
            break
        count += 1
    return count


def _same_target_tail_streak(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    return _tail_streak(
        [_number(row.get("target")) for row in rows],
        predicate=lambda value: round(value, 6) == round(_number(rows[-1].get("target")), 6),
    )


def _same_value_tail_streak(values: list[float]) -> int:
    if not values:
        return 0
    target = round(values[-1], 6)
    return _tail_streak(values, predicate=lambda value: round(value, 6) == target)


def _is_one_percent_delta(value: float) -> bool:
    return round(value, 6) == 1.0


def _streak_bucket(value: int) -> str:
    if value <= 0:
        return "0"
    if value <= 2:
        return str(value)
    if value <= 9:
        return "3_9"
    if value <= 49:
        return "10_49"
    if value <= 199:
        return "50_199"
    return "200_plus"


def _date_label(timestamp: str) -> str:
    parsed = _parse_timestamp(timestamp)
    return parsed.date().isoformat() if parsed else "missing"


def _drain_per_credit(row: dict[str, Any]) -> float:
    credits = _number(row.get("standard_usage_credits"))
    if credits <= 0:
        return 0.0
    return _number(row.get("target")) / credits


def _fit_predictive_model(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    spec: PredictiveModelSpec,
    *,
    include_capacity_residual_diagnostics: bool = False,
) -> dict[str, Any] | None:
    prepared = _prepare_design(train_rows, spec)
    if prepared is None:
        return None
    feature_names, means, stddevs, category_levels = prepared
    train_x = _design_matrix(
        train_rows,
        spec,
        feature_names=feature_names,
        means=means,
        stddevs=stddevs,
        category_levels=category_levels,
    )
    train_y = [_number(row.get("target")) for row in train_rows]
    coefficients = _fit_ridge(train_x, train_y, alpha=spec.ridge_alpha)
    if coefficients is None:
        return None
    holdout_x = _design_matrix(
        holdout_rows,
        spec,
        feature_names=feature_names,
        means=means,
        stddevs=stddevs,
        category_levels=category_levels,
    )
    holdout_y = [_number(row.get("target")) for row in holdout_rows]
    train_predictions = _predict(train_x, coefficients)
    holdout_predictions = _predict(holdout_x, coefficients)
    coefficient_rows = [
        {"feature": feature, "coefficient": _rounded(value)}
        for feature, value in zip(feature_names, coefficients[1:], strict=True)
    ]
    coefficient_rows.sort(key=lambda row: abs(_number(row["coefficient"])), reverse=True)
    result = {
        "name": spec.name,
        "feature_count": len(feature_names),
        "ridge_alpha": _rounded(spec.ridge_alpha),
        "numeric_features": list(spec.numeric_features),
        "categorical_features": list(spec.categorical_features),
        "train": _regression_metrics(train_y, train_predictions),
        "holdout": _regression_metrics(holdout_y, holdout_predictions),
        "top_coefficients": coefficient_rows[:12],
    }
    if include_capacity_residual_diagnostics:
        result["holdout_error_diagnostics"] = _capacity_residual_diagnostics(
            holdout_rows, holdout_y, holdout_predictions
        )
    return result


def _prepare_design(
    rows: list[dict[str, Any]], spec: PredictiveModelSpec
) -> tuple[list[str], dict[str, float], dict[str, float], dict[str, list[str]]] | None:
    if not rows:
        return None
    means: dict[str, float] = {}
    stddevs: dict[str, float] = {}
    feature_names: list[str] = []
    for feature in spec.numeric_features:
        values = [_number(row.get(feature)) for row in rows]
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


def _design_matrix(
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
            values[index] = (_number(row.get(feature)) - means[feature]) / stddevs[feature]
        for feature in spec.categorical_features:
            value = str(row.get(feature) or "missing")
            encoded_name = f"{feature}={value}"
            if encoded_name in feature_index:
                values[feature_index[encoded_name]] = 1.0
        matrix.append(values)
    return matrix


def _fit_ridge(
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
    return _solve_linear_system(lhs, rhs)


def _solve_linear_system(lhs: list[list[float]], rhs: list[float]) -> list[float] | None:
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


def _predict(x_rows: list[list[float]], coefficients: list[float]) -> list[float]:
    return [
        coefficients[0]
        + sum(value * coefficient for value, coefficient in zip(row, coefficients[1:], strict=True))
        for row in x_rows
    ]


def _regression_metrics(
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
        "r2": _rounded(_r2(actual, predicted)),
        "mae": _rounded(sum(abs(error) for error in errors) / len(errors)),
        "rmse": _rounded(math.sqrt(sum(error * error for error in errors) / len(errors))),
        "pearson": _rounded(_pearson(actual, predicted)),
        "mean_actual": _rounded(mean_actual),
        "mean_predicted": _rounded(sum(predicted) / len(predicted)),
        "std_actual": _rounded(math.sqrt(actual_variance)),
        "min_actual": _rounded(min(actual)),
        "max_actual": _rounded(max(actual)),
    }


def _fit_two_feature_no_intercept(
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


def _fit_grid_multiplier(
    spans: list[UsageDeltaSpan], *, proxy: str, multiplier: float
) -> dict[str, float | None]:
    y_values = [span.delta_usage_percent for span in spans]
    x_values = [
        span.non_candidate_standard_credits.get(proxy, 0.0)
        + multiplier * span.candidate_standard_credits.get(proxy, 0.0)
        for span in spans
    ]
    slope = _fit_one_feature_no_intercept(x_values, y_values)
    y_hat = [slope * value for value in x_values] if slope is not None else None
    return {
        "multiplier": multiplier,
        "pearson": _rounded(_pearson(x_values, y_values)),
        "r2_slope": _rounded(_r2(y_values, y_hat) if y_hat is not None else None),
        "slope_usage_pct_per_weighted_credit": _rounded(slope),
    }


def _fit_one_feature_no_intercept(x_values: list[float], y_values: list[float]) -> float | None:
    denominator = sum(x * x for x in x_values)
    if denominator <= 0:
        return None
    return sum(x * y for x, y in zip(x_values, y_values, strict=True)) / denominator


def _documented_weighted_multiplier(
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


def _candidate_share_correlation(spans: list[UsageDeltaSpan], proxy: str) -> float | None:
    shares: list[float] = []
    drain_per_credit: list[float] = []
    for span in spans:
        total = span.standard_usage_credits
        if total <= 0:
            continue
        candidate = span.candidate_standard_credits.get(proxy, 0.0)
        shares.append(candidate / total)
        drain_per_credit.append(span.delta_usage_percent / total)
    return _pearson(shares, drain_per_credit)


def _drain_stats(spans: list[UsageDeltaSpan]) -> dict[str, float | int | None]:
    drains = [
        span.delta_usage_percent / span.standard_usage_credits
        for span in spans
        if span.standard_usage_credits > 0
    ]
    deltas = [span.delta_usage_percent for span in spans]
    return {
        "spans": len(spans),
        "median_delta_percent": _rounded(median(deltas) if deltas else None),
        "median_drain_per_standard_credit": _rounded(median(drains) if drains else None),
        "mean_drain_per_standard_credit": _rounded(
            sum(drains) / len(drains) if drains else None
        ),
    }


def _r2(y_values: list[float], y_hat: list[float] | None) -> float | None:
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


def _pearson(x_values: list[float], y_values: list[float]) -> float | None:
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


def _spearman(x_values: list[float], y_values: list[float]) -> float | None:
    if len(x_values) < 2 or len(x_values) != len(y_values):
        return None
    return _pearson(_rank_values(x_values), _rank_values(y_values))


def _rank_values(values: list[float]) -> list[float]:
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


def _usage_bucket(row: dict[str, Any]) -> tuple[Any, ...]:
    observation = _preferred_usage_observation(row)
    return (
        row.get("rate_limit_plan_type"),
        row.get("rate_limit_limit_id"),
        observation["source"],
        observation["window_minutes"],
        observation["resets_at"],
    )


def _preferred_usage_observation(row: dict[str, Any]) -> dict[str, Any]:
    """Prefer the 5-hour usage window and fall back only when it is unavailable."""

    candidates = [
        {
            "source": "primary",
            "used_percent": _optional_number(row.get("rate_limit_primary_used_percent")),
            "window_minutes": _optional_number(
                row.get("rate_limit_primary_window_minutes")
            ),
            "resets_at": _optional_number(row.get("rate_limit_primary_resets_at")),
        },
        {
            "source": "secondary",
            "used_percent": _optional_number(
                row.get("rate_limit_secondary_used_percent")
            ),
            "window_minutes": _optional_number(
                row.get("rate_limit_secondary_window_minutes")
            ),
            "resets_at": _optional_number(row.get("rate_limit_secondary_resets_at")),
        },
    ]
    for candidate in candidates:
        if (
            candidate["used_percent"] is not None
            and candidate["window_minutes"] == FIVE_HOUR_WINDOW_MINUTES
        ):
            return candidate
    for candidate in candidates:
        if candidate["used_percent"] is not None:
            return candidate
    return {
        "source": "missing",
        "used_percent": None,
        "window_minutes": None,
        "resets_at": None,
    }


def _parse_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        text = f"{text}T00:00:00+00:00"
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _reset_remaining_minutes(
    event_timestamp: datetime | None, reset_at: float | None
) -> float | None:
    if event_timestamp is None or reset_at is None:
        return None
    return max((reset_at - event_timestamp.timestamp()) / 60.0, 0.0)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        label = str(row.get(key) or "missing")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _optional_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    return _number(value)


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0


def _rounded(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 6)
