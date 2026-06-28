"""Regime-boundary diagnostics for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker import usage_drain_boundary_delta as boundary_delta
from codex_usage_tracker import usage_drain_boundary_delta_summary as boundary_delta_summary
from codex_usage_tracker import usage_drain_boundary_scopes as boundary_scopes
from codex_usage_tracker import usage_drain_regime_labels as regime_labels
from codex_usage_tracker.usage_drain_error_diagnostics import (
    span_error_metadata as _span_error_metadata,
)
from codex_usage_tracker.usage_drain_grace import REGIME_GRACE_STREAK_THRESHOLD
from codex_usage_tracker.usage_drain_transition_metrics import (
    binary_risk_metrics as _binary_risk_metrics,
)
from codex_usage_tracker.usage_drain_types import UsageDeltaSpan
from codex_usage_tracker.usage_drain_utils import (
    bounded_wall_time_seconds as _bounded_wall_time_seconds,
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

def piecewise_boundary_diagnostics(
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
        "walk_forward_delta_prediction": boundary_delta_summary.boundary_walk_forward_delta_prediction_summary(
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
        current_label = regime_labels.delta_regime_label(span.delta_usage_percent)
        previous_label = regime_labels.delta_regime_label(previous_span.delta_usage_percent)
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
            "previous_segment_position_bucket": regime_labels.segment_position_bucket(
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
                start_index=boundary_scopes.boundary_scope_start_index(rows, start),
            )
            for scope_name, start in boundary_scopes.BOUNDARY_RISK_SCOPE_STARTS.items()
        },
    }




def _boundary_walk_forward_risk_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_rows: list[dict[str, Any]] = []
    for row in rows:
        prior_rate = boundary_delta.boundary_rate(previous_rows)
        risks = {"overall_prior_rate": prior_rate}
        details = {
            "overall_prior_rate": {
                "source": "all_prior_boundaries",
                "support": len(previous_rows),
                "risk": _rounded(prior_rate),
            }
        }
        for model_name, signatures in boundary_delta.BOUNDARY_RISK_MODEL_SIGNATURES.items():
            risk, detail = boundary_delta.state_bucket_boundary_risk(
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
