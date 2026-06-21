"""Aggregate-only helpers for modeling observed Codex usage drain.

This module compares local aggregate token-credit estimates with visible
rate-limit usage percentage deltas. It intentionally treats usage drain as a
coarse observed signal, not as billing truth.
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass, field
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
        }
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
    return {
        "schema": USAGE_DRAIN_MODEL_SCHEMA,
        "source_rows": len(rows),
        "span_stats": span_stats,
        "model_mix": _count_values(rows, "model"),
        "rate_limit_plan_type_mix": _count_values(rows, "rate_limit_plan_type"),
        "rate_limit_limit_id_mix": _count_values(rows, "rate_limit_limit_id"),
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
            "controls": ["model", "effort", "thread_key", "session_id", "cwd"],
        },
        "limitations": [
            "Visible usage percentages are coarse snapshots, not exact per-call credit debits.",
            "Rows with unchanged usage are assigned to the next positive delta span.",
            "Bucket changes and usage percentage decreases are censored.",
            "The public aggregate logs do not expose a direct fast-mode flag.",
            "Local logs can omit usage from other agentic surfaces sharing the same allowance.",
        ],
        "results": results,
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
    for row in rows:
        credits = max(_number(row.get("usage_credits")), 0.0)
        standard += credits
        model = str(row.get("model") or "unknown")
        model_counts[model] = model_counts.get(model, 0) + 1
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
    )


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
