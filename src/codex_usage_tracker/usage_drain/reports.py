"""Compact dashboard reports for visible usage-drain research."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.core.call_origin import ensure_call_origin
from codex_usage_tracker.core.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.core.threads import annotate_thread_attachments
from codex_usage_tracker.pricing.allowance import (
    annotate_rows_with_allowance,
    load_allowance_config,
)
from codex_usage_tracker.pricing.api import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.store.api import query_dashboard_events
from codex_usage_tracker.usage_drain.model import (
    DOCUMENTED_FAST_CREDIT_MULTIPLIERS,
    UsageDeltaSpan,
    build_usage_delta_spans,
)
from codex_usage_tracker.usage_drain.thread_curves import (
    MAX_CURVE_POINTS_PER_THREAD,
    MAX_THREAD_CURVES,
    thread_cost_curves,
)
from codex_usage_tracker.usage_drain.time_series import usage_time_series

TOKEN_ACCOUNTING_FEATURES = (
    "uncached_input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
TOKEN_ACCOUNTING_TOTAL_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "usage_credits",
)


def build_usage_drain_dashboard_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    pricing_path: Path = DEFAULT_PRICING_PATH,
    allowance_path: Path = DEFAULT_ALLOWANCE_PATH,
    rate_card_path: Path = DEFAULT_RATE_CARD_PATH,
    include_archived: bool = False,
    max_threads: int = MAX_THREAD_CURVES,
    max_curve_points: int = MAX_CURVE_POINTS_PER_THREAD,
) -> dict[str, Any]:
    """Build a bounded, aggregate-only usage-drain report for the dashboard."""

    rows = annotate_thread_attachments(
        [
            ensure_call_origin(row)
            for row in query_dashboard_events(
                db_path=db_path,
                limit=0,
                include_archived=include_archived,
            )
        ]
    )
    pricing = load_pricing_config(pricing_path)
    allowance = load_allowance_config(allowance_path, rate_card_path=rate_card_path)
    rows = annotate_rows_with_allowance(
        annotate_rows_with_efficiency(rows, pricing),
        allowance,
    )
    spans, span_stats = build_usage_delta_spans(rows) if rows else ([], _empty_span_stats())
    curves = thread_cost_curves(
        rows,
        max_threads=max_threads,
        max_curve_points=max_curve_points,
    )
    return {
        "summary": _report_summary(rows, spans, span_stats, curves),
        "thread_cost_curves": curves,
        "time_series": usage_time_series(rows, spans),
        "model_highlights": _model_highlights(rows, spans),
        "pricing": {
            "configured": bool(pricing.loaded and not pricing.error),
            "rate_card_loaded": bool(allowance.rate_card_loaded),
            "credit_source_name": allowance.source.get("name"),
            "credit_source_url": allowance.source.get("url"),
            "credit_source_fetched_at": allowance.source.get("fetched_at"),
        },
        "notes": [
            "Visible usage percentages are coarse snapshots, so calls with unchanged usage are grouped into the next positive span.",
            "Usage-drain reports are aggregate-only and do not include prompts, assistant text, tool output, command text, or patch text.",
            "Thread names are shown in the local dashboard because they are already indexed aggregate metadata.",
            "The logs do not expose a direct fast-mode flag; documented fast multipliers are listed only as model-rate context.",
        ],
    }


def _empty_span_stats() -> dict[str, int]:
    return {
        "input_rows": 0,
        "rows_without_usage_snapshot": 0,
        "rows_without_initial_baseline": 0,
        "alternate_codex_limit_rows_ignored_for_boundaries": 0,
        "censored_or_reset_pending_segments": 0,
        "positive_usage_spans": 0,
        "five_hour_usage_window_rows": 0,
        "fallback_usage_window_rows": 0,
    }


def _report_summary(
    rows: list[dict[str, Any]],
    spans: list[UsageDeltaSpan],
    span_stats: dict[str, int],
    curves: dict[str, Any],
) -> dict[str, Any]:
    usage_credits = sum(_number(row.get("usage_credits")) for row in rows)
    estimated_cost = sum(_number(row.get("estimated_cost_usd")) for row in rows)
    best = _simple_predictive_models(spans).get("best_mae_model")
    return {
        "usage_rows": len(rows),
        "thread_count": int(curves.get("total_threads") or 0),
        "positive_usage_spans": _int_from_mapping(span_stats, "positive_usage_spans"),
        "censored_or_reset_pending_segments": _int_from_mapping(
            span_stats, "censored_or_reset_pending_segments"
        ),
        "rows_without_usage_snapshot": _int_from_mapping(span_stats, "rows_without_usage_snapshot"),
        "estimated_cost_usd": round(estimated_cost, 6),
        "usage_credits": round(usage_credits, 6),
        "top_thread_cost_share": curves.get("top_thread_share"),
        "best_predictive_model": best.get("name") if isinstance(best, dict) else None,
        "raw_context_included": False,
    }


def _model_highlights(rows: list[dict[str, Any]], spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    return {
        "model_mix": _count_rows(_count_values(rows, "model")),
        "rate_limit_plan_type_mix": _count_rows(_count_values(rows, "rate_limit_plan_type")),
        "rate_limit_limit_id_mix": _count_rows(_count_values(rows, "rate_limit_limit_id")),
        "predictive_modeling": _simple_predictive_models(spans),
        "token_accounting": _token_accounting_highlights(rows, spans),
        "one_percent_capacity": _one_percent_capacity_highlights(spans),
        "allowance_breakpoints": _allowance_breakpoint_highlights(spans),
        "documented_fast_multipliers": _value_rows(DOCUMENTED_FAST_CREDIT_MULTIPLIERS),
        "limitations": [
            "Visible usage percentages are coarse snapshots, not exact per-call credit debits.",
            "Rows with unchanged usage are assigned to the next positive delta span.",
            "Bucket changes and usage percentage decreases are censored.",
            "The public aggregate logs do not expose a direct fast-mode flag.",
        ],
    }


def _simple_predictive_models(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    if not spans:
        return {
            "best_by_holdout_r2": None,
            "best_by_holdout_mae": None,
            "best_r2_model": None,
            "best_mae_model": None,
            "models": [],
        }
    actual = [span.delta_usage_percent for span in spans]
    credit_predictions = _credit_slope_predictions(spans)
    one_percent_predictions = [1.0 for _span in spans]
    train_mean = sum(actual) / len(actual)
    mean_predictions = [train_mean for _span in spans]
    previous_predictions = [actual[0], *actual[:-1]]
    models = [
        _prediction_model_record("credit_slope", actual, credit_predictions),
        _prediction_model_record("constant_one_percent", actual, one_percent_predictions),
        _prediction_model_record("span_mean", actual, mean_predictions),
        _prediction_model_record("previous_delta", actual, previous_predictions),
    ]
    best_mae = min(models, key=lambda model: _number(model.get("mae")), default=None)
    best_r2 = max(models, key=lambda model: _number(model.get("r2")), default=None)
    return {
        "best_by_holdout_r2": best_r2.get("name") if best_r2 else None,
        "best_by_holdout_mae": best_mae.get("name") if best_mae else None,
        "best_r2_model": best_r2,
        "best_mae_model": best_mae,
        "models": models,
    }


def _credit_slope_predictions(spans: list[UsageDeltaSpan]) -> list[float]:
    credits = [span.standard_usage_credits for span in spans]
    actual = [span.delta_usage_percent for span in spans]
    denominator = sum(credit * credit for credit in credits)
    slope = sum(credit * delta for credit, delta in zip(credits, actual, strict=False))
    slope = slope / denominator if denominator else 0.0
    return [credit * slope for credit in credits]


def _prediction_model_record(
    name: str,
    actual: list[float],
    predicted: list[float],
) -> dict[str, Any]:
    errors = _absolute_errors(actual, predicted)
    return {
        "name": name,
        "kind": "compact_dashboard_baseline",
        "validation": "same_series_compact",
        "mae": _rounded(_mean_absolute_error(errors)),
        "rmse": _rounded(_root_mean_square_error(actual, predicted)),
        "r2": _rounded(_r2(actual, predicted)),
        "pearson": _rounded(_pearson(actual, predicted)),
        "within_1pt": _rounded(_within_error_share(errors, threshold=1.0)),
        "within_5pts": _rounded(_within_error_share(errors, threshold=5.0)),
    }


def _absolute_errors(actual: list[float], predicted: list[float]) -> list[float]:
    return [abs(left - right) for left, right in zip(actual, predicted, strict=False)]


def _mean_absolute_error(errors: list[float]) -> float | None:
    if not errors:
        return None
    return sum(errors) / len(errors)


def _root_mean_square_error(actual: list[float], predicted: list[float]) -> float | None:
    if not actual:
        return None
    squared_error = sum((left - right) ** 2 for left, right in zip(actual, predicted, strict=False))
    return (squared_error / len(actual)) ** 0.5


def _within_error_share(errors: list[float], *, threshold: float) -> float | None:
    if not errors:
        return None
    return sum(1 for error in errors if error <= threshold) / len(errors)


def _token_accounting_highlights(
    rows: list[dict[str, Any]],
    spans: list[UsageDeltaSpan],
) -> dict[str, Any]:
    totals = _token_accounting_totals(rows)
    credits_to_visible_delta = _credits_to_visible_delta_fit(spans)
    return {
        "feature_units": "tokens",
        "features": list(TOKEN_ACCOUNTING_FEATURES),
        "totals": totals,
        "credits_to_visible_delta": credits_to_visible_delta,
        "unweighted": {},
        "high_medium_fast_weighted": {},
    }


def _token_accounting_totals(rows: list[dict[str, Any]]) -> dict[str, float | None]:
    return {
        field_name: _rounded(sum(_number(row.get(field_name)) for row in rows))
        for field_name in TOKEN_ACCOUNTING_TOTAL_FIELDS
    }


def _credits_to_visible_delta_fit(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    span_credits = [span.standard_usage_credits for span in spans]
    span_delta = [span.delta_usage_percent for span in spans]
    return {
        "span_count": len(spans),
        "r2": _rounded(_r2(span_delta, _credit_slope_predictions(spans))),
        "pearson": _rounded(_pearson(span_credits, span_delta)),
    }


def _one_percent_capacity_highlights(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    one_percent = [
        span.standard_usage_credits
        for span in spans
        if abs(span.delta_usage_percent - 1.0) <= 0.000001
    ]
    distribution = _value_distribution(one_percent)
    return {
        "span_count": len(one_percent),
        "target": "standard_usage_credits_inside_exact_one_percent_spans",
        "target_mean": _rounded(distribution.get("mean")),
        "target_min": _rounded(distribution.get("min")),
        "target_max": _rounded(distribution.get("max")),
        "best_by_holdout_mae": None,
        "best_causal_by_holdout_mae": None,
        "best_model": None,
        "best_causal_model": None,
        "notes": [
            "Compact dashboard capacity stats describe closed exact-1% spans only.",
            "Offline exports can run heavier same-span and causal model-family comparisons.",
        ],
    }


def _allowance_breakpoint_highlights(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    rows = [
        {
            "span_index": index,
            "start_event_timestamp": span.start_event_timestamp,
            "end_event_timestamp": span.end_event_timestamp,
            "delta_usage_percent": span.delta_usage_percent,
            "standard_usage_credits": span.standard_usage_credits,
            "credits_per_visible_percent": (
                span.standard_usage_credits / span.delta_usage_percent
                if span.delta_usage_percent > 0
                else 0.0
            ),
        }
        for index, span in enumerate(spans)
        if span.delta_usage_percent > 0
    ]
    values = [_number(row["credits_per_visible_percent"]) for row in rows]
    global_fit = _credit_to_delta_fit(rows)
    best_break = _best_allowance_split(rows)
    segments = _allowance_segments(rows, best_break)
    piecewise_predictions = _piecewise_mean_capacity_predictions(rows, segments)
    return {
        "span_count": len(rows),
        "global_mean_credits_per_percent": _rounded(_mean(values)),
        "global_median_credits_per_percent": _rounded(_median(values)),
        "piecewise_sse_reduction_share": _rounded(
            best_break.get("sse_reduction_share") if best_break else None
        ),
        "global_credit_to_delta_r2": _rounded(global_fit.get("r2")),
        "piecewise_credit_to_delta_r2": _rounded(
            _r2([_number(row["delta_usage_percent"]) for row in rows], piecewise_predictions)
        ),
        "best_single_break": best_break,
        "segments": [
            _allowance_segment_record(rows, start, end, index)
            for index, (start, end) in enumerate(segments, start=1)
        ],
        "notes": [
            "Compact dashboard breakpoints use one efficient single-break scan.",
            "Segments are chronological diagnostics over closed positive usage-delta spans, not proof of an official allowance change.",
        ],
    }


def _credit_to_delta_fit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actual = [_number(row.get("delta_usage_percent")) for row in rows]
    credits = [_number(row.get("standard_usage_credits")) for row in rows]
    denominator = sum(credit * credit for credit in credits)
    slope = sum(credit * delta for credit, delta in zip(credits, actual, strict=False))
    slope = slope / denominator if denominator else 0.0
    predicted = [credit * slope for credit in credits]
    return {"slope": _rounded(slope), "r2": _r2(actual, predicted)}


def _best_allowance_split(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    min_segment_size = 10
    if len(rows) < min_segment_size * 2:
        return None
    values = [_number(row["credits_per_visible_percent"]) for row in rows]
    prefix_sum = [0.0]
    prefix_square = [0.0]
    for value in values:
        prefix_sum.append(prefix_sum[-1] + value)
        prefix_square.append(prefix_square[-1] + value * value)
    parent_sse = _range_sse(prefix_sum, prefix_square, 0, len(values))
    if parent_sse <= 0:
        return None
    best: dict[str, Any] | None = None
    for split in range(min_segment_size, len(values) - min_segment_size + 1):
        left_sse = _range_sse(prefix_sum, prefix_square, 0, split)
        right_sse = _range_sse(prefix_sum, prefix_square, split, len(values))
        reduction = parent_sse - left_sse - right_sse
        if reduction <= (_number(best["sse_reduction"]) if best else float("-inf")):
            continue
        left, right = rows[:split], rows[split:]
        best = {
            "split_index": split,
            "left_n": len(left),
            "right_n": len(right),
            "left_start_event_timestamp": left[0]["start_event_timestamp"],
            "left_end_event_timestamp": left[-1]["end_event_timestamp"],
            "right_start_event_timestamp": right[0]["start_event_timestamp"],
            "right_end_event_timestamp": right[-1]["end_event_timestamp"],
            "left_mean_credits_per_percent": _rounded(
                _mean([_number(row["credits_per_visible_percent"]) for row in left])
            ),
            "right_mean_credits_per_percent": _rounded(
                _mean([_number(row["credits_per_visible_percent"]) for row in right])
            ),
            "sse_reduction_share": _rounded(reduction / parent_sse),
            "sse_reduction": reduction,
        }
    return best


def _allowance_segments(
    rows: list[dict[str, Any]],
    split: dict[str, Any] | None,
) -> list[tuple[int, int]]:
    if not rows:
        return []
    if not split:
        return [(0, len(rows))]
    split_index = int(split["split_index"])
    return [(0, split_index), (split_index, len(rows))]


def _piecewise_mean_capacity_predictions(
    rows: list[dict[str, Any]],
    segments: list[tuple[int, int]],
) -> list[float]:
    predictions = [0.0 for _row in rows]
    for start, end in segments:
        segment = rows[start:end]
        mean_capacity = _mean([_number(row["credits_per_visible_percent"]) for row in segment])
        if mean_capacity <= 0:
            continue
        for index in range(start, end):
            predictions[index] = _number(rows[index]["standard_usage_credits"]) / mean_capacity
    return predictions


def _allowance_segment_record(
    rows: list[dict[str, Any]],
    start: int,
    end: int,
    segment_index: int,
) -> dict[str, Any]:
    segment = rows[start:end]
    values = [_number(row["credits_per_visible_percent"]) for row in segment]
    fit = _credit_to_delta_fit(segment)
    return {
        "segment_index": segment_index,
        "n": len(segment),
        "start_event_timestamp": segment[0]["start_event_timestamp"] if segment else None,
        "end_event_timestamp": segment[-1]["end_event_timestamp"] if segment else None,
        "mean_credits_per_percent": _rounded(_mean(values)),
        "median_credits_per_percent": _rounded(_median(values)),
        "credit_to_delta_r2": _rounded(fit.get("r2")),
    }


def _range_sse(
    prefix_sum: list[float],
    prefix_square: list[float],
    start: int,
    end: int,
) -> float:
    n = end - start
    if n <= 0:
        return 0.0
    total = prefix_sum[end] - prefix_sum[start]
    square_total = prefix_square[end] - prefix_square[start]
    return square_total - (total * total / n)


def _count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "missing")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_rows(values: object) -> list[dict[str, Any]]:
    if not isinstance(values, dict):
        return []
    rows: list[dict[str, Any]] = [
        {"value": str(key), "count": int(_number(value))} for key, value in values.items()
    ]
    rows.sort(key=lambda row: (-int(_number(row["count"])), str(row["value"])))
    return rows


def _value_rows(values: object) -> list[dict[str, Any]]:
    if not isinstance(values, dict):
        return []
    rows = [{"value": str(key), "metric": value} for key, value in values.items()]
    rows.sort(key=lambda row: row["value"])
    return rows


def _int_from_mapping(mapping: object, key: str) -> int:
    if not isinstance(mapping, dict):
        return 0
    return int(_number(mapping.get(key)))


def _value_distribution(values: list[float]) -> dict[str, Any]:
    return {
        "n": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "mean": _mean(values),
        "median": _median(values),
    }


def _is_alternate_codex_limit(limit_id: object) -> bool:
    return isinstance(limit_id, str) and limit_id.startswith("codex_") and limit_id != "codex"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _r2(actual: list[float], predicted: list[float]) -> float | None:
    if len(actual) != len(predicted) or len(actual) < 2:
        return None
    mean_actual = _mean(actual)
    total = sum((value - mean_actual) ** 2 for value in actual)
    if total <= 0:
        return None
    residual = sum((left - right) ** 2 for left, right in zip(actual, predicted, strict=False))
    return 1.0 - (residual / total)


def _pearson(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_mean = _mean(left)
    right_mean = _mean(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=False)
    )
    left_denominator = sum((value - left_mean) ** 2 for value in left)
    right_denominator = sum((value - right_mean) ** 2 for value in right)
    denominator = (left_denominator * right_denominator) ** 0.5
    if denominator <= 0:
        return None
    return numerator / denominator


def _rounded(value: object) -> float | None:
    if value is None or value == "":
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _number_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    if not isinstance(value, int | float | str):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
