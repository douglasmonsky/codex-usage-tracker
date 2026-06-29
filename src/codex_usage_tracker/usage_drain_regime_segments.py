"""Regime segment diagnostics for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker import usage_drain_boundary_summary as boundary_summary
from codex_usage_tracker import usage_drain_regime_labels as regime_labels
from codex_usage_tracker import usage_drain_walk_forward as walk_forward
from codex_usage_tracker.usage_drain_error_diagnostics import (
    value_distribution as _value_distribution,
)
from codex_usage_tracker.usage_drain_feature_history import (
    date_label as _date_label,
)
from codex_usage_tracker.usage_drain_feature_history import (
    is_one_percent_delta as _is_one_percent_delta,
)
from codex_usage_tracker.usage_drain_regression import regression_metrics as _regression_metrics
from codex_usage_tracker.usage_drain_summary_metrics import (
    delta_distribution as _delta_distribution,
)
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import number as _number
from codex_usage_tracker.usage_drain_utils import rounded as _rounded

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

def delta_regime_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    train_size = max(1, min(len(spans) - 1, int(len(spans) * 0.8))) if spans else 0
    return {
        "all_spans": _delta_distribution(spans),
        "time_ordered_train_80": _delta_distribution(spans[:train_size]),
        "time_ordered_holdout_20": _delta_distribution(spans[train_size:]),
        "latest_100": _delta_distribution(spans[-100:]),
        "latest_25": _delta_distribution(spans[-25:]),
    }


def regime_streak_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
    one_percent_runs = _one_percent_runs(spans)
    return {
        "one_percent_runs": _one_percent_run_summary(one_percent_runs, spans),
        "breaks_after_long_one_percent_runs": _breaks_after_long_one_percent_runs(
            spans, one_percent_runs
        ),
    }


def _one_percent_run_summary(
    one_percent_runs: list[dict[str, Any]], spans: list[UsageDeltaSpan]
) -> dict[str, Any]:
    current_run = _current_one_percent_run(one_percent_runs, span_count=len(spans))
    return {
        "count": len(one_percent_runs),
        "long_run_min_length": 3,
        "long_run_count": _long_one_percent_run_count(one_percent_runs),
        "max_span_count": _max_one_percent_run_length(one_percent_runs),
        "current_streak": int(current_run["span_count"]) if current_run else 0,
        "latest_run": one_percent_runs[-1] if one_percent_runs else None,
        "top_runs": _top_one_percent_runs(one_percent_runs),
    }


def _long_one_percent_run_count(one_percent_runs: list[dict[str, Any]]) -> int:
    return sum(1 for run in one_percent_runs if run["span_count"] >= 3)


def _max_one_percent_run_length(one_percent_runs: list[dict[str, Any]]) -> int:
    return max((int(run["span_count"]) for run in one_percent_runs), default=0)


def _current_one_percent_run(
    one_percent_runs: list[dict[str, Any]], *, span_count: int
) -> dict[str, Any] | None:
    if not one_percent_runs or not span_count:
        return None
    current_run = one_percent_runs[-1]
    if current_run["end_index"] != span_count - 1:
        return None
    return current_run


def _top_one_percent_runs(
    one_percent_runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return sorted(one_percent_runs, key=lambda run: -run["span_count"])[:10]


def _breaks_after_long_one_percent_runs(
    spans: list[UsageDeltaSpan], one_percent_runs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    breaks = [
        _run_break_record(spans, run)
        for run in one_percent_runs
        if run["span_count"] >= 3 and run["end_index"] + 1 < len(spans)
    ]
    breaks.sort(key=lambda item: (-int(item["preceding_span_count"]), item["break_index"]))
    return breaks[:10]


def piecewise_regime_segment_summary(spans: list[UsageDeltaSpan]) -> dict[str, Any]:
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
    all_rows_by_position = _empty_segment_position_rows()
    label_rows_by_position: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for segment in segments:
        _collect_piecewise_position_rows(
            segment,
            prediction_rows=prediction_rows,
            all_rows_by_position=all_rows_by_position,
            label_rows_by_position=label_rows_by_position,
        )
    return _piecewise_adaptation_position_report(
        all_rows_by_position, label_rows_by_position
    )


def _empty_segment_position_rows() -> dict[str, list[dict[str, Any]]]:
    return {bucket: [] for bucket in SEGMENT_POSITION_BUCKETS}


def _collect_piecewise_position_rows(
    segment: dict[str, Any],
    *,
    prediction_rows: dict[int, dict[str, Any]],
    all_rows_by_position: dict[str, list[dict[str, Any]]],
    label_rows_by_position: dict[str, dict[str, list[dict[str, Any]]]],
) -> None:
    label = str(segment.get("label") or "missing")
    start_index = int(segment["start_index"])
    end_index = int(segment["end_index"])
    label_rows = label_rows_by_position.setdefault(
        label, _empty_segment_position_rows()
    )
    for index in range(start_index, end_index + 1):
        row = prediction_rows.get(index)
        if row is not None:
            _append_piecewise_position_row(
                row,
                index=index,
                start_index=start_index,
                all_rows_by_position=all_rows_by_position,
                label_rows=label_rows,
            )


def _append_piecewise_position_row(
    row: dict[str, Any],
    *,
    index: int,
    start_index: int,
    all_rows_by_position: dict[str, list[dict[str, Any]]],
    label_rows: dict[str, list[dict[str, Any]]],
) -> None:
    position = index - start_index + 1
    bucket = regime_labels.segment_position_bucket(position)
    all_rows_by_position[bucket].append(row)
    label_rows[bucket].append(row)


def _piecewise_adaptation_position_report(
    all_rows_by_position: dict[str, list[dict[str, Any]]],
    label_rows_by_position: dict[str, dict[str, list[dict[str, Any]]]],
) -> dict[str, Any]:
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
