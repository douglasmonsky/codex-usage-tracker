"""Compact dashboard reports for visible usage-drain research."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sqrt
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import annotate_rows_with_allowance, load_allowance_config
from codex_usage_tracker.call_origin import ensure_call_origin
from codex_usage_tracker.paths import (
    DEFAULT_ALLOWANCE_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_PRICING_PATH,
    DEFAULT_RATE_CARD_PATH,
)
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.store import query_dashboard_events
from codex_usage_tracker.threads import annotate_thread_attachments
from codex_usage_tracker.usage_drain_model import (
    DOCUMENTED_FAST_CREDIT_MULTIPLIERS,
    UsageDeltaSpan,
    build_usage_delta_spans,
)

MAX_THREAD_CURVES = 12
MAX_CURVE_POINTS_PER_THREAD = 120
MAX_VISIBLE_USAGE_POINTS = 240


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
    curves = _thread_cost_curves(
        rows,
        max_threads=max_threads,
        max_curve_points=max_curve_points,
    )
    return {
        "summary": _report_summary(rows, spans, span_stats, curves),
        "thread_cost_curves": curves,
        "time_series": _usage_time_series(rows, spans),
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


def _usage_time_series(
    rows: list[dict[str, Any]],
    spans: list[UsageDeltaSpan],
) -> dict[str, Any]:
    weekly_projection = _weekly_credit_projection(rows)
    return {
        "visible_usage": _visible_usage_time_series(rows),
        "usage_drain_spans": _usage_drain_span_series(spans),
        "weekly_credit_projection": weekly_projection,
        "notes": [
            "Visible usage lines use sampled indexed rows and may include flat stretches where the visible percentage did not change.",
            "Weekly credit projection uses the secondary 10,080-minute usage counter when present.",
            "Projection intervals are descriptive 95% intervals from within-window span dispersion, not official allowance guarantees.",
        ],
    }


def _visible_usage_time_series(rows: list[dict[str, Any]]) -> dict[str, Any]:
    points = []
    for index, row in enumerate(sorted(rows, key=_chronological_key), start=1):
        if _is_alternate_codex_limit(row.get("rate_limit_limit_id")):
            continue
        five_hour = _number_or_none(row.get("rate_limit_primary_used_percent"))
        weekly = _number_or_none(row.get("rate_limit_secondary_used_percent"))
        if five_hour is None and weekly is None:
            continue
        points.append(
            {
                "call_index": index,
                "timestamp": row.get("event_timestamp"),
                "five_hour_used_percent": _rounded(five_hour),
                "weekly_used_percent": _rounded(weekly),
            }
        )
    return {
        "unit": "visible_used_percent",
        "series": ["five_hour_used_percent", "weekly_used_percent"],
        "points": _sample_curve_points(points, max_points=MAX_VISIBLE_USAGE_POINTS),
        "source_fields": {
            "five_hour_used_percent": "rate_limit_primary_used_percent",
            "weekly_used_percent": "rate_limit_secondary_used_percent",
        },
    }


def _usage_drain_span_series(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    points = [
        {
            "span_index": index,
            "timestamp": span.end_event_timestamp,
            "delta_usage_percent": _rounded(span.delta_usage_percent),
            "standard_usage_credits": _rounded(span.standard_usage_credits),
            "credits_per_visible_percent": _rounded(
                span.standard_usage_credits / span.delta_usage_percent
                if span.delta_usage_percent > 0
                else None
            ),
        }
        for index, span in enumerate(spans, start=1)
        if span.delta_usage_percent > 0
    ]
    return {
        "unit": "positive_visible_delta_percent",
        "points": _sample_curve_points(points, max_points=MAX_VISIBLE_USAGE_POINTS),
    }


def _weekly_credit_projection(rows: list[dict[str, Any]]) -> dict[str, Any]:
    spans = _weekly_usage_delta_spans(rows)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        key = str(span.get("week_key") or span.get("reset_key") or "unknown")
        grouped.setdefault(key, []).append(span)
    points = [
        _weekly_projection_point(key, grouped[key])
        for key in sorted(grouped, key=lambda item: _weekly_group_sort_key(grouped[item]))
    ]
    points = [point for point in points if point is not None]
    trend = _weekly_projection_trend(points)
    return {
        "unit": "projected_standard_usage_credits_per_full_week",
        "window_minutes": 10080,
        "span_count": len(spans),
        "point_count": len(points),
        "points": points,
        "trend": trend,
        "confidence_method": (
            "For each weekly reset window, estimate full-week credits as "
            "observed standard credits divided by observed weekly visible percent "
            "and multiplied by 100. Confidence bars use 1.96 times the standard "
            "error of per-span full-week estimates inside that reset window."
        ),
    }


def _weekly_usage_delta_spans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=_chronological_key)
    spans: list[dict[str, Any]] = []
    baseline_percent: float | None = None
    baseline_bucket: tuple[Any, ...] | None = None
    pending_rows: list[dict[str, Any]] = []
    for row in sorted_rows:
        if _is_alternate_codex_limit(row.get("rate_limit_limit_id")):
            continue
        used_percent = _number_or_none(row.get("rate_limit_secondary_used_percent"))
        window_minutes = _number_or_none(row.get("rate_limit_secondary_window_minutes"))
        resets_at = _number_or_none(row.get("rate_limit_secondary_resets_at"))
        if used_percent is None or window_minutes != 10080:
            continue
        if not _row_in_usage_window(row, resets_at, window_minutes):
            continue
        bucket = (
            row.get("rate_limit_plan_type"),
            row.get("rate_limit_limit_id"),
            _weekly_window_key(
                resets_at,
                row.get("rate_limit_plan_type"),
                row.get("rate_limit_limit_id"),
            ),
        )
        if baseline_percent is None:
            baseline_percent = used_percent
            baseline_bucket = bucket
            pending_rows = []
            continue
        if bucket != baseline_bucket:
            baseline_percent = used_percent
            baseline_bucket = bucket
            pending_rows = []
            continue
        pending_rows.append(row)
        if used_percent <= baseline_percent:
            continue
        credits = sum(max(_number(item.get("usage_credits")), 0.0) for item in pending_rows)
        delta = used_percent - baseline_percent
        spans.append(
            {
                "start_event_timestamp": pending_rows[0].get("event_timestamp"),
                "end_event_timestamp": pending_rows[-1].get("event_timestamp"),
                "baseline_used_percent": baseline_percent,
                "end_used_percent": used_percent,
                "delta_usage_percent": delta,
                "standard_usage_credits": credits,
                "row_count": len(pending_rows),
                "week_key": _weekly_window_key(
                    resets_at,
                    row.get("rate_limit_plan_type"),
                    row.get("rate_limit_limit_id"),
                ),
                "reset_key": _reset_key(resets_at),
                "reset_timestamp": _timestamp_from_epoch(resets_at),
                "rate_limit_plan_type": row.get("rate_limit_plan_type"),
                "rate_limit_limit_id": row.get("rate_limit_limit_id"),
            }
        )
        baseline_percent = used_percent
        pending_rows = []
    return spans


def _weekly_projection_point(
    key: str,
    spans: list[dict[str, Any]],
) -> dict[str, Any] | None:
    usable = [span for span in spans if _number(span.get("delta_usage_percent")) > 0]
    if not usable:
        return None
    observed_delta = sum(_number(span.get("delta_usage_percent")) for span in usable)
    observed_credits = sum(_number(span.get("standard_usage_credits")) for span in usable)
    if observed_delta <= 0:
        return None
    estimates = [
        _number(span.get("standard_usage_credits"))
        / _number(span.get("delta_usage_percent"))
        * 100.0
        for span in usable
        if _number(span.get("delta_usage_percent")) > 0
    ]
    projection = observed_credits / observed_delta * 100.0
    stddev = _sample_stddev(estimates)
    standard_error = stddev / sqrt(len(estimates)) if len(estimates) > 1 else None
    ci_half_width = 1.96 * standard_error if standard_error is not None else None
    start = min(str(span.get("start_event_timestamp") or "") for span in usable)
    end = max(str(span.get("end_event_timestamp") or "") for span in usable)
    return {
        "week_key": key,
        "label": _week_label(usable[0], key),
        "start_event_timestamp": start,
        "end_event_timestamp": end,
        "span_count": len(usable),
        "call_count": int(sum(_number(span.get("row_count")) for span in usable)),
        "observed_usage_delta_percent": _rounded(observed_delta),
        "observed_standard_usage_credits": _rounded(observed_credits),
        "projected_weekly_credits": _rounded(projection),
        "ci_low": _rounded(max(projection - ci_half_width, 0.0) if ci_half_width is not None else None),
        "ci_high": _rounded(projection + ci_half_width if ci_half_width is not None else None),
        "confidence": _projection_confidence(len(usable), observed_delta),
        "rate_limit_plan_type": usable[-1].get("rate_limit_plan_type"),
    }


def _weekly_projection_trend(points: list[dict[str, Any]]) -> dict[str, Any]:
    trend_points = [
        point for point in points if point.get("confidence") in {"medium", "high"}
    ]
    if len(trend_points) < 2:
        trend_points = points
    values = [_number(point.get("projected_weekly_credits")) for point in trend_points]
    if len(values) < 2:
        return {
            "point_count": len(values),
            "basis": "all_points",
            "slope_credits_per_week": None,
            "direction": "insufficient_data",
            "first_projected_weekly_credits": _rounded(values[0]) if values else None,
            "latest_projected_weekly_credits": _rounded(values[-1]) if values else None,
            "change_from_first_credits": None,
            "change_from_first_pct": None,
        }
    xs = list(range(len(values)))
    x_mean = _mean([float(value) for value in xs])
    y_mean = _mean(values)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=False))
        / denominator
        if denominator
        else 0.0
    )
    change = values[-1] - values[0]
    return {
        "point_count": len(values),
        "basis": "medium_high_confidence" if trend_points is not points else "all_points",
        "slope_credits_per_week": _rounded(slope),
        "direction": "up" if slope > 0 else "down" if slope < 0 else "flat",
        "first_projected_weekly_credits": _rounded(values[0]),
        "latest_projected_weekly_credits": _rounded(values[-1]),
        "change_from_first_credits": _rounded(change),
        "change_from_first_pct": _rounded(change / values[0] if values[0] else None),
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
        "rows_without_usage_snapshot": _int_from_mapping(
            span_stats, "rows_without_usage_snapshot"
        ),
        "estimated_cost_usd": round(estimated_cost, 6),
        "usage_credits": round(usage_credits, 6),
        "top_thread_cost_share": curves.get("top_thread_share"),
        "best_predictive_model": best.get("name") if isinstance(best, dict) else None,
        "raw_context_included": False,
    }


def _thread_cost_curves(
    rows: list[dict[str, Any]],
    *,
    max_threads: int,
    max_curve_points: int,
) -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=_chronological_key):
        key = str(row.get("thread_key") or row.get("session_id") or "unknown")
        bucket = buckets.setdefault(
            key,
            {
                "thread_key": key,
                "thread": _thread_label(row),
                "calls": [],
            },
        )
        bucket["calls"].append(row)
        if bucket["thread"] == "Unknown thread":
            bucket["thread"] = _thread_label(row)

    thread_rows = [
        _thread_curve_record(bucket, max_curve_points=max_curve_points)
        for bucket in buckets.values()
    ]
    thread_rows.sort(
        key=lambda row: (
            -_number(row.get("estimated_cost_usd")),
            -int(row.get("call_count") or 0),
            str(row.get("thread") or ""),
        )
    )
    total_cost = sum(_number(row.get("estimated_cost_usd")) for row in thread_rows)
    top_cost = _number(thread_rows[0].get("estimated_cost_usd")) if thread_rows else 0.0
    return {
        "total_threads": len(thread_rows),
        "shown_threads": min(len(thread_rows), max_threads),
        "max_points_per_thread": max_curve_points,
        "estimated_cost_usd": round(total_cost, 6),
        "top_thread_share": round(top_cost / total_cost, 6) if total_cost else 0.0,
        "threads": thread_rows[:max_threads],
    }


def _thread_curve_record(
    bucket: dict[str, Any],
    *,
    max_curve_points: int,
) -> dict[str, Any]:
    calls = list(bucket["calls"])
    cumulative = 0.0
    points: list[dict[str, Any]] = []
    call_costs: list[float] = []
    first_half_cutoff = max(len(calls) // 2, 1)
    first_half_cost = 0.0
    for index, row in enumerate(calls, start=1):
        call_cost = _number(row.get("estimated_cost_usd"))
        call_costs.append(call_cost)
        cumulative += call_cost
        if index <= first_half_cutoff:
            first_half_cost += call_cost
        points.append(
            {
                "call_index": index,
                "cumulative_cost_usd": round(cumulative, 6),
            }
        )
    largest_call_cost = max(call_costs, default=0.0)
    first_half_share = first_half_cost / cumulative if cumulative else 0.0
    largest_share = largest_call_cost / cumulative if cumulative else 0.0
    return {
        "thread_key": bucket["thread_key"],
        "thread": bucket["thread"],
        "call_count": len(calls),
        "estimated_cost_usd": round(cumulative, 6),
        "avg_cost_usd": round(cumulative / len(calls), 6) if calls else 0.0,
        "first_half_cost_share": round(first_half_share, 6),
        "largest_call_cost_share": round(largest_share, 6),
        "shape": _curve_shape(first_half_share, largest_share),
        "points": _sample_curve_points(points, max_points=max_curve_points),
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
    errors = [abs(left - right) for left, right in zip(actual, predicted, strict=False)]
    return {
        "name": name,
        "kind": "compact_dashboard_baseline",
        "validation": "same_series_compact",
        "mae": _rounded(sum(errors) / len(errors) if errors else None),
        "rmse": _rounded(
            (sum((left - right) ** 2 for left, right in zip(actual, predicted, strict=False)) / len(actual))
            ** 0.5
            if actual
            else None
        ),
        "r2": _rounded(_r2(actual, predicted)),
        "pearson": _rounded(_pearson(actual, predicted)),
        "within_1pt": _rounded(
            sum(1 for error in errors if error <= 1.0) / len(errors) if errors else None
        ),
        "within_5pts": _rounded(
            sum(1 for error in errors if error <= 5.0) / len(errors) if errors else None
        ),
    }


def _token_accounting_highlights(
    rows: list[dict[str, Any]],
    spans: list[UsageDeltaSpan],
) -> dict[str, Any]:
    totals = {
        "input_tokens": sum(_number(row.get("input_tokens")) for row in rows),
        "cached_input_tokens": sum(_number(row.get("cached_input_tokens")) for row in rows),
        "uncached_input_tokens": sum(_number(row.get("uncached_input_tokens")) for row in rows),
        "output_tokens": sum(_number(row.get("output_tokens")) for row in rows),
        "reasoning_output_tokens": sum(
            _number(row.get("reasoning_output_tokens")) for row in rows
        ),
        "total_tokens": sum(_number(row.get("total_tokens")) for row in rows),
        "usage_credits": sum(_number(row.get("usage_credits")) for row in rows),
    }
    span_credits = [span.standard_usage_credits for span in spans]
    span_delta = [span.delta_usage_percent for span in spans]
    return {
        "feature_units": "tokens",
        "features": [
            "uncached_input_tokens",
            "cached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ],
        "totals": {key: _rounded(value) for key, value in totals.items()},
        "credits_to_visible_delta": {
            "span_count": len(spans),
            "r2": _rounded(_r2(span_delta, _credit_slope_predictions(spans))),
            "pearson": _rounded(_pearson(span_credits, span_delta)),
        },
        "unweighted": {},
        "high_medium_fast_weighted": {},
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
        "segments": [_allowance_segment_record(rows, start, end, index) for index, (start, end) in enumerate(segments, start=1)],
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
        if best is None or reduction > _number(best["sse_reduction"]):
            left = rows[:split]
            right = rows[split:]
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
        mean_capacity = _mean(
            [_number(row["credits_per_visible_percent"]) for row in segment]
        )
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


def _sample_curve_points(
    points: list[dict[str, Any]],
    *,
    max_points: int,
) -> list[dict[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    last_index = len(points) - 1
    selected_indexes = {
        round(index * last_index / (max_points - 1)) for index in range(max_points)
    }
    return [points[index] for index in sorted(selected_indexes)]


def _curve_shape(first_half_share: float, largest_call_share: float) -> str:
    if largest_call_share >= 0.2:
        return "spiky"
    if first_half_share < 0.4:
        return "back-loaded"
    if first_half_share > 0.6:
        return "front-loaded"
    return "near-linear"


def _thread_label(row: dict[str, Any]) -> str:
    return str(
        row.get("thread_attachment_label")
        or row.get("thread_name")
        or row.get("resolved_parent_thread_name")
        or row.get("parent_thread_name")
        or row.get("session_id")
        or "Unknown thread"
    )


def _chronological_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row.get("event_timestamp") or ""),
        int(_number(row.get("cumulative_total_tokens"))),
        str(row.get("record_id") or ""),
    )


def _count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "missing")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_rows(values: object) -> list[dict[str, Any]]:
    if not isinstance(values, dict):
        return []
    rows = [{"value": str(key), "count": int(value)} for key, value in values.items()]
    rows.sort(key=lambda row: (-row["count"], row["value"]))
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


def _sample_stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean_value = _mean(values)
    variance = sum((value - mean_value) ** 2 for value in values) / (len(values) - 1)
    return variance**0.5


def _projection_confidence(span_count: int, observed_delta_percent: float) -> str:
    if span_count >= 20 and observed_delta_percent >= 30:
        return "high"
    if span_count >= 8 and observed_delta_percent >= 10:
        return "medium"
    return "low"


def _weekly_group_sort_key(spans: list[dict[str, Any]]) -> str:
    if not spans:
        return ""
    return str(spans[0].get("start_event_timestamp") or "")


def _week_label(span: dict[str, Any], fallback: str) -> str:
    timestamp = str(span.get("reset_timestamp") or span.get("end_event_timestamp") or "")
    dt = _parse_datetime(timestamp)
    if dt is None:
        return fallback
    return dt.strftime("Reset %b %d")


def _weekly_window_key(
    resets_at: float | None,
    plan_type: object,
    limit_id: object,
) -> str:
    reset_day = "unknown"
    timestamp = _timestamp_from_epoch(resets_at)
    dt = _parse_datetime(timestamp)
    if dt is not None:
        reset_day = dt.date().isoformat()
    elif resets_at is not None:
        reset_day = str(int(resets_at))
    return f"{plan_type or 'unknown'}:{limit_id or 'unknown'}:{reset_day}"


def _row_in_usage_window(
    row: dict[str, Any],
    resets_at: float | None,
    window_minutes: float | None,
) -> bool:
    """Reject repaired/stale allowance snapshots outside their reset window."""

    if resets_at is None or window_minutes is None:
        return False
    event_dt = _parse_datetime(row.get("event_timestamp"))
    if event_dt is None:
        return False
    reset_dt = datetime.fromtimestamp(resets_at, tz=timezone.utc)
    window = timedelta(minutes=window_minutes)
    tolerance = timedelta(minutes=30)
    return reset_dt - window - tolerance <= event_dt <= reset_dt + tolerance


def _reset_key(value: float | None) -> str:
    if value is None:
        return "unknown"
    return str(int(value))


def _timestamp_from_epoch(value: float | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


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
    residual = sum(
        (left - right) ** 2 for left, right in zip(actual, predicted, strict=False)
    )
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
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
