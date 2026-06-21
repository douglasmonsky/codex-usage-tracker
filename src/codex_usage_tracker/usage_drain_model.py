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
TIMING_TOTAL_FIELDS = (
    "call_duration_seconds",
    "previous_call_delta_seconds",
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
    models: dict[str, int] = field(default_factory=dict)
    token_totals: dict[str, float] = field(default_factory=dict)
    timing_totals: dict[str, float] = field(default_factory=dict)
    rate_limit_plan_type: str | None = None
    rate_limit_limit_id: str | None = None
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
    }

    baseline_percent: float | None = None
    baseline_bucket: tuple[Any, ...] | None = None
    pending_rows: list[dict[str, Any]] = []

    for row in sorted_rows:
        used_percent = _optional_number(row.get("rate_limit_primary_used_percent"))
        bucket = _usage_bucket(row)
        if used_percent is None:
            stats["rows_without_usage_snapshot"] += 1
            if baseline_percent is None:
                stats["rows_without_initial_baseline"] += 1
            else:
                pending_rows.append(row)
            continue

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
        proxy_flags = {
            "all_candidates": annotation.is_candidate,
            "strong_only": annotation.is_strong,
            "high_medium_candidates": annotation.is_high_or_medium,
            "high_confidence_only": annotation.is_high,
        }
        multiplier = documented_fast_credit_multiplier(model) or 1.0
        for proxy_name, is_candidate in proxy_flags.items():
            if is_candidate:
                candidate[proxy_name] += credits
                documented_weighted[proxy_name] += credits * multiplier
                candidate_counts[proxy_name] += 1
            else:
                non_candidate[proxy_name] += credits
                documented_weighted[proxy_name] += credits

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
        models=model_counts,
        token_totals=token_totals,
        timing_totals=timing_totals,
        rate_limit_plan_type=_optional_text(rows[-1].get("rate_limit_plan_type")),
        rate_limit_limit_id=_optional_text(rows[-1].get("rate_limit_limit_id")),
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
    )
    return [
        PredictiveModelSpec("baseline_train_mean", ()),
        PredictiveModelSpec("credits_only", base),
        PredictiveModelSpec("token_shape", token_shape),
        PredictiveModelSpec("fast_proxy", fast_proxy),
        PredictiveModelSpec(
            "usage_state",
            usage_state,
            ("rate_limit_plan_type", "rate_limit_limit_id"),
        ),
        PredictiveModelSpec(
            "time_controls",
            time_controls,
            ("rate_limit_plan_type", "rate_limit_limit_id", "day_of_week"),
        ),
        PredictiveModelSpec(
            "date_day_hour_controls",
            time_controls,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
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
                "date",
                "day_of_week",
                "hour_bucket",
            ),
        ),
        PredictiveModelSpec(
            "lag_regime",
            lag_regime,
            ("rate_limit_plan_type", "rate_limit_limit_id"),
        ),
        PredictiveModelSpec(
            "lag_time_controls",
            lag_time,
            ("rate_limit_plan_type", "rate_limit_limit_id", "day_of_week"),
        ),
        PredictiveModelSpec(
            "adaptive_full_controls",
            adaptive_full,
            (
                "rate_limit_plan_type",
                "rate_limit_limit_id",
                "date",
                "day_of_week",
                "hour_bucket",
            ),
        ),
    ]


def _span_feature_row(span: UsageDeltaSpan, *, proxy: str) -> dict[str, Any]:
    start_dt = _parse_timestamp(span.start_event_timestamp)
    reset_remaining_minutes = _reset_remaining_minutes(
        start_dt, span.rate_limit_primary_resets_at
    )
    window_minutes = span.rate_limit_primary_window_minutes or 0.0
    reset_minutes = reset_remaining_minutes or 0.0
    window_elapsed_minutes = (
        max(window_minutes - reset_minutes, 0.0) if window_minutes > 0 else 0.0
    )
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
        "rate_limit_primary_window_minutes": window_minutes,
        "reset_remaining_minutes": reset_minutes,
        "window_elapsed_minutes": window_elapsed_minutes,
        "window_elapsed_fraction": (
            min(max(window_elapsed_minutes / window_minutes, 0.0), 1.0)
            if window_minutes > 0
            else 0.0
        ),
        "days_since_first_span": 0.0,
        "hour_sin": math.sin(2 * math.pi * hour_value / 24.0),
        "hour_cos": math.cos(2 * math.pi * hour_value / 24.0),
        "day_of_week_sin": math.sin(2 * math.pi * day_index / 7.0) if day_index >= 0 else 0.0,
        "day_of_week_cos": math.cos(2 * math.pi * day_index / 7.0) if day_index >= 0 else 0.0,
        "is_weekend": 1.0 if day_index in {5, 6} else 0.0,
        "call_duration_seconds": duration,
        "mean_call_duration_seconds": duration / span.row_count if span.row_count else 0.0,
        "previous_call_delta_seconds": span.timing_totals.get("previous_call_delta_seconds", 0.0),
        "date": date_label,
        "day_of_week": str(day_index) if day_index >= 0 else "missing",
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
    counts: dict[float, int] = {}
    values = [_number(row.get(field)) for row in selected]
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    max_count = max(counts.values())
    candidates = {value for value, count in counts.items() if count == max_count}
    for value in reversed(values):
        if value in candidates:
            return value
    return values[-1]


def _rolling_stddev(rows: list[dict[str, Any]], field: str, window: int) -> float:
    selected = rows[-window:]
    if not selected:
        return 0.0
    values = [_number(row.get(field)) for row in selected]
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


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


def _drain_per_credit(row: dict[str, Any]) -> float:
    credits = _number(row.get("standard_usage_credits"))
    if credits <= 0:
        return 0.0
    return _number(row.get("target")) / credits


def _fit_predictive_model(
    train_rows: list[dict[str, Any]],
    holdout_rows: list[dict[str, Any]],
    spec: PredictiveModelSpec,
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
    coefficients = _fit_ridge(train_x, train_y, alpha=1.0)
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
    return {
        "name": spec.name,
        "feature_count": len(feature_names),
        "numeric_features": list(spec.numeric_features),
        "categorical_features": list(spec.categorical_features),
        "train": _regression_metrics(train_y, train_predictions),
        "holdout": _regression_metrics(holdout_y, holdout_predictions),
        "top_coefficients": coefficient_rows[:12],
    }


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


def _usage_bucket(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("rate_limit_plan_type"),
        row.get("rate_limit_limit_id"),
        row.get("rate_limit_primary_window_minutes"),
        row.get("rate_limit_primary_resets_at"),
    )


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
