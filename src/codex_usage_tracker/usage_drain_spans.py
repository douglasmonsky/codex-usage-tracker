"""Build visible usage-drain spans from annotated dashboard rows."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from codex_usage_tracker.usage_drain_types import (
    DEFAULT_PROXY_NAMES,
    EFFORT_LEVELS,
    TIMING_TOTAL_FIELDS,
    TOKEN_COMPONENT_FIELDS,
    TOKEN_TOTAL_FIELDS,
    FastProxyAnnotation,
    UsageDeltaSpan,
    documented_fast_credit_multiplier,
)

FIVE_HOUR_WINDOW_MINUTES = 300


def _span_number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip():
        return float(value)
    return 0.0


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
            score=_span_optional_number(row.get("fast_proxy_score")),
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
        "alternate_codex_limit_rows_ignored_for_boundaries": 0,
        "censored_or_reset_pending_segments": 0,
        "positive_usage_spans": 0,
        "five_hour_usage_window_rows": 0,
        "fallback_usage_window_rows": 0,
    }

    baseline_percent: float | None = None
    baseline_bucket: tuple[Any, ...] | None = None
    pending_rows: list[dict[str, Any]] = []

    for row in sorted_rows:
        if _ignored_codex_limit(row.get("rate_limit_limit_id")):
            stats["alternate_codex_limit_rows_ignored_for_boundaries"] += 1
        usage_observation = _preferred_span_usage_observation(row)
        if usage_observation["used_percent"] is None:
            stats["rows_without_usage_snapshot"] += 1
            if baseline_percent is None:
                stats["rows_without_initial_baseline"] += 1
            else:
                pending_rows.append(row)
            continue
        used_percent = float(usage_observation["used_percent"])
        bucket = _span_usage_bucket(row)
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


def _span_row_token_components(row: dict[str, Any]) -> dict[str, float]:
    cached_input = _span_number(row.get("cached_input_tokens"))
    uncached_input = _span_number(row.get("uncached_input_tokens"))
    if uncached_input <= 0:
        uncached_input = max(_span_number(row.get("input_tokens")) - cached_input, 0.0)
    reasoning_output = _span_number(row.get("reasoning_output_tokens"))
    output_tokens = _span_number(row.get("output_tokens"))
    return {
        "uncached_input_tokens": uncached_input,
        "cached_input_tokens": cached_input,
        "reasoning_output_tokens": reasoning_output,
        "nonreasoning_output_tokens": max(output_tokens - reasoning_output, 0.0),
    }


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
    effort_counts: dict[str, int] = {}
    turn_counts: dict[tuple[str, str], int] = {}
    token_totals = dict.fromkeys(TOKEN_TOTAL_FIELDS, 0.0)
    timing_totals = dict.fromkeys(TIMING_TOTAL_FIELDS, 0.0)
    for row in rows:
        credits = max(_span_number(row.get("usage_credits")), 0.0)
        standard += credits
        model = str(row.get("model") or "unknown")
        model_counts[model] = model_counts.get(model, 0) + 1
        effort = _span_normalized_effort(row.get("effort"))
        effort_counts[effort] = effort_counts.get(effort, 0) + 1
        turn_key = _span_turn_key(row)
        turn_counts[turn_key] = turn_counts.get(turn_key, 0) + 1
        for field_name in TOKEN_TOTAL_FIELDS:
            token_totals[field_name] += _span_number(row.get(field_name))
        for field_name in TIMING_TOTAL_FIELDS:
            timing_totals[field_name] += _span_number(row.get(field_name))
        annotation = proxies.get(str(row.get("record_id") or ""), FastProxyAnnotation())
        token_components = _span_row_token_components(row)
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
    usage_observation = _preferred_span_usage_observation(rows[-1])

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
        effort_counts=effort_counts,
        turn_count=len(turn_counts),
        multi_call_turn_count=sum(1 for count in turn_counts.values() if count > 1),
        max_calls_in_turn=max(turn_counts.values(), default=0),
        token_totals=token_totals,
        timing_totals=timing_totals,
        rate_limit_plan_type=_span_optional_text(rows[-1].get("rate_limit_plan_type")),
        rate_limit_limit_id=_span_optional_text(rows[-1].get("rate_limit_limit_id")),
        usage_window_source=str(usage_observation["source"] or "missing"),
        usage_window_minutes=_span_optional_number(usage_observation["window_minutes"]),
        usage_window_resets_at=_span_optional_number(usage_observation["resets_at"]),
        rate_limit_primary_window_minutes=_span_optional_number(
            rows[-1].get("rate_limit_primary_window_minutes")
        ),
        rate_limit_primary_resets_at=_span_optional_number(
            rows[-1].get("rate_limit_primary_resets_at")
        ),
    )


def _span_usage_bucket(row: dict[str, Any]) -> tuple[Any, ...]:
    observation = _preferred_span_usage_observation(row)
    return (
        row.get("rate_limit_plan_type"),
        row.get("rate_limit_limit_id"),
        observation["source"],
        observation["window_minutes"],
        observation["resets_at"],
    )


def _preferred_span_usage_observation(row: dict[str, Any]) -> dict[str, Any]:
    """Prefer the 5-hour usage window and fall back only when it is unavailable."""

    if _ignored_codex_limit(row.get("rate_limit_limit_id")):
        return {
            "source": "alternate_codex_limit_ignored",
            "used_percent": None,
            "window_minutes": None,
            "resets_at": None,
        }

    candidates = [
        {
            "source": "primary",
            "used_percent": _span_optional_number(row.get("rate_limit_primary_used_percent")),
            "window_minutes": _span_optional_number(
                row.get("rate_limit_primary_window_minutes")
            ),
            "resets_at": _span_optional_number(row.get("rate_limit_primary_resets_at")),
        },
        {
            "source": "secondary",
            "used_percent": _span_optional_number(
                row.get("rate_limit_secondary_used_percent")
            ),
            "window_minutes": _span_optional_number(
                row.get("rate_limit_secondary_window_minutes")
            ),
            "resets_at": _span_optional_number(row.get("rate_limit_secondary_resets_at")),
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


def _ignored_codex_limit(limit_id: object) -> bool:
    if not isinstance(limit_id, str):
        return False
    return limit_id.startswith("codex_") and limit_id != "codex"


def _span_turn_key(row: dict[str, Any]) -> tuple[str, str]:
    session_id = str(row.get("session_id") or "missing")
    turn_id = str(row.get("turn_id") or row.get("record_id") or "missing")
    return session_id, turn_id


def _span_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _span_normalized_effort(value: object) -> str:
    text = _span_optional_text(value)
    if text is None:
        return "missing"
    normalized = text.lower().replace("-", "_")
    return normalized if normalized in EFFORT_LEVELS else "other"


def _span_optional_number(value: object) -> float | None:
    if value is None or value == "":
        return None
    return _span_number(value)
