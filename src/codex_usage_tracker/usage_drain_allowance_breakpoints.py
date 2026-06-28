"""Allowance breakpoint diagnostics for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker import usage_drain_allowance_fits as allowance_fits
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_feature_history import (
    is_one_percent_delta as _is_one_percent_delta,
)
from codex_usage_tracker.usage_drain_regression import count_values as _count_values
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import number as _number
from codex_usage_tracker.usage_drain_utils import rounded as _rounded

ALLOWANCE_BREAKPOINT_MIN_SEGMENT_SIZE = 20
ALLOWANCE_BREAKPOINT_MAX_SEGMENTS = 6
ALLOWANCE_BREAKPOINT_MIN_REDUCTION_SHARE = 0.12


def allowance_breakpoint_analysis(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
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
            "global_credit_to_delta_fit": allowance_fits.credit_to_delta_fit(rows),
            "best_single_break": None,
            "segments": [],
            "piecewise_credit_to_delta_fit": allowance_fits.allowance_piecewise_credit_to_delta_fit(
                rows,
                [],
            ),
            "online_capacity_credit_to_delta_fit": (
                allowance_fits.allowance_online_capacity_credit_to_delta_fit(rows, [])
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
        "global_credit_to_delta_fit": allowance_fits.credit_to_delta_fit(rows),
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
        "piecewise_credit_to_delta_fit": allowance_fits.allowance_piecewise_credit_to_delta_fit(
            rows,
            segments,
        ),
        "online_capacity_credit_to_delta_fit": (
            allowance_fits.allowance_online_capacity_credit_to_delta_fit(rows, segments)
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
        "credit_to_delta_fit": allowance_fits.credit_to_delta_fit(segment_rows),
    }


def _mean_field(rows: list[dict[str, Any]], field_name: str) -> float | None:
    if not rows:
        return None
    return sum(_number(row.get(field_name)) for row in rows) / len(rows)
