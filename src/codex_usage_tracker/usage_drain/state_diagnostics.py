"""State ambiguity diagnostics for usage-drain modeling."""

from __future__ import annotations

from typing import Any

from codex_usage_tracker.usage_drain.regression import regression_metrics
from codex_usage_tracker.usage_drain.utils import number, rounded, value_mode

STATE_AMBIGUITY_SIGNATURES: dict[str, tuple[str, ...]] = {
    "previous_delta": ("previous_delta_bucket",),
    "history_state": (
        "previous_delta_bucket",
        "one_percent_streak_bucket",
        "same_delta_streak_bucket",
        "low_delta_streak_bucket",
    ),
    "calendar_state": (
        "previous_delta_bucket",
        "one_percent_streak_bucket",
        "day_of_week",
        "hour_bucket",
    ),
    "reset_state": (
        "previous_delta_bucket",
        "one_percent_streak_bucket",
        "baseline_used_bucket",
        "window_elapsed_bucket",
        "reset_remaining_bucket",
    ),
    "previous_work_state": (
        "previous_delta_bucket",
        "one_percent_streak_bucket",
        "previous_span_wall_time_bucket",
        "previous_call_duration_bucket",
    ),
    "full_bucket_state": (
        "previous_delta_bucket",
        "one_percent_streak_bucket",
        "same_delta_streak_bucket",
        "low_delta_streak_bucket",
        "baseline_used_bucket",
        "window_elapsed_bucket",
        "reset_remaining_bucket",
        "day_of_week",
        "hour_bucket",
        "previous_span_wall_time_bucket",
        "previous_call_duration_bucket",
        "rate_limit_plan_type",
        "rate_limit_limit_id",
    ),
}

def state_ambiguity_summary(
    rows: list[dict[str, Any]], scopes: dict[str, int]
) -> dict[str, Any]:
    return {
        "target": "next_visible_usage_delta_percent",
        "definition": (
            "Groups walk-forward rows by aggregate state signatures and reports "
            "whether identical-looking prior states produce different next "
            "visible deltas."
        ),
        "interpretation": [
            "Oracle mode metrics use all rows in the scope and are lower-bound diagnostics, not causal predictions.",
            "Repeated ambiguous states indicate missing variables, overly coarse buckets, or true counter nondeterminism from the available logs.",
            "Unique states can look perfect by construction, so repeated-state metrics are the stricter signal.",
        ],
        "signatures": {
            name: list(signature)
            for name, signature in STATE_AMBIGUITY_SIGNATURES.items()
        },
        "scopes": {
            scope_name: state_ambiguity_scope(rows, start_index=start_index)
            for scope_name, start_index in scopes.items()
        },
    }

def state_ambiguity_scope(
    rows: list[dict[str, Any]], *, start_index: int
) -> dict[str, Any]:
    scope_rows = [row for row in rows if int(row["index"]) >= start_index]
    return {
        "start_index": start_index,
        "n": len(scope_rows),
        "signatures": {
            name: state_signature_ambiguity(scope_rows, name, signature)
            for name, signature in STATE_AMBIGUITY_SIGNATURES.items()
        },
    }

def state_signature_ambiguity(
    rows: list[dict[str, Any]],
    signature_name: str,
    signature: tuple[str, ...],
) -> dict[str, Any]:
    groups = _state_signature_groups(rows, signature)
    analyses = [
        _state_ambiguity_group_analysis(key, items, signature=signature)
        for key, items in groups.items()
    ]
    return _state_signature_ambiguity_result(
        rows=rows,
        groups=groups,
        analyses=analyses,
        signature_name=signature_name,
        signature=signature,
    )


def _state_signature_groups(
    rows: list[dict[str, Any]], signature: tuple[str, ...]
) -> dict[tuple[str, ...], list[dict[str, Any]]]:
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = state_signature(row.get("metadata") or {}, signature)
        groups.setdefault(key, []).append(row)
    return groups


def _state_ambiguity_group_analysis(
    key: tuple[str, ...],
    items: list[dict[str, Any]],
    *,
    signature: tuple[str, ...],
) -> dict[str, Any]:
    values = [number(item.get("actual")) for item in items]
    mode_value = value_mode(values)
    is_ambiguous = _state_group_is_ambiguous(values)
    return {
        "values": values,
        "predicted": [mode_value] * len(values),
        "repeated": len(items) > 1,
        "ambiguous": is_ambiguous,
        "ambiguous_record": (
            state_ambiguous_group_record(
                key,
                items,
                signature=signature,
                mode_value=mode_value,
            )
            if is_ambiguous
            else None
        ),
    }


def _state_group_is_ambiguous(values: list[float]) -> bool:
    return len({round(value, 6) for value in values}) > 1


def _state_signature_ambiguity_result(
    *,
    rows: list[dict[str, Any]],
    groups: dict[tuple[str, ...], list[dict[str, Any]]],
    analyses: list[dict[str, Any]],
    signature_name: str,
    signature: tuple[str, ...],
) -> dict[str, Any]:
    repeated = [analysis for analysis in analyses if analysis["repeated"]]
    ambiguous = [analysis for analysis in analyses if analysis["ambiguous"]]
    actual = _state_analysis_values(analyses, "values")
    predicted = _state_analysis_values(analyses, "predicted")
    repeated_actual = _state_analysis_values(repeated, "values")
    repeated_predicted = _state_analysis_values(repeated, "predicted")
    ambiguous_groups = _state_ambiguous_records(ambiguous)
    return {
        "signature": signature_name,
        "fields": list(signature),
        "n": len(rows),
        "group_count": len(groups),
        "repeated_group_count": len(repeated),
        "repeated_row_count": _state_analysis_row_count(repeated),
        "repeated_row_share": rounded(
            _state_analysis_row_count(repeated) / len(rows) if rows else None
        ),
        "ambiguous_group_count": len(ambiguous),
        "ambiguous_row_count": _state_analysis_row_count(ambiguous),
        "ambiguous_row_share": rounded(
            _state_analysis_row_count(ambiguous) / len(rows) if rows else None
        ),
        "oracle_mode_metrics": regression_metrics(actual, predicted),
        "repeated_oracle_mode_metrics": regression_metrics(
            repeated_actual,
            repeated_predicted,
        ),
        "top_ambiguous_states": ambiguous_groups[:8],
    }


def _state_analysis_values(
    analyses: list[dict[str, Any]], field: str
) -> list[float]:
    values: list[float] = []
    for analysis in analyses:
        values.extend(analysis[field])
    return values


def _state_analysis_row_count(analyses: list[dict[str, Any]]) -> int:
    return sum(len(analysis["values"]) for analysis in analyses)


def _state_ambiguous_records(
    analyses: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records = [
        analysis["ambiguous_record"]
        for analysis in analyses
        if analysis["ambiguous_record"] is not None
    ]
    return sorted(records, key=_state_ambiguous_record_sort_key)


def _state_ambiguous_record_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
    return (
        -number(row.get("total_abs_error")),
        -int(row.get("n") or 0),
        str(row.get("state") or ""),
    )

def state_ambiguous_group_record(
    key: tuple[str, ...],
    rows: list[dict[str, Any]],
    *,
    signature: tuple[str, ...],
    mode_value: float,
) -> dict[str, Any]:
    values = _ambiguous_actual_values(rows)
    value_counts = _rounded_value_counts(values)
    errors = _mode_errors(values, mode_value)
    dates = _row_dates(rows)
    return {
        "state": _signature_state(key, signature),
        "n": len(rows),
        "actual_values": _actual_value_rows(value_counts, row_count=len(rows)),
        "mode_delta_percent": rounded(mode_value),
        "mode_share": _mode_share(value_counts, mode_value, row_count=len(rows)),
        "oracle_mae": _mean_error(errors),
        "total_abs_error": rounded(sum(errors)),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
    }


def _ambiguous_actual_values(rows: list[dict[str, Any]]) -> list[float]:
    return [number(row.get("actual")) for row in rows]


def _rounded_value_counts(values: list[float]) -> dict[float, int]:
    value_counts: dict[float, int] = {}
    for value in values:
        rounded_value = round(value, 6)
        value_counts[rounded_value] = value_counts.get(rounded_value, 0) + 1
    return value_counts


def _mode_errors(values: list[float], mode_value: float) -> list[float]:
    return [abs(value - mode_value) for value in values]


def _row_dates(rows: list[dict[str, Any]]) -> list[str]:
    return [
        str((row.get("metadata") or {}).get("date") or "missing") for row in rows
    ]


def _signature_state(key: tuple[str, ...], signature: tuple[str, ...]) -> dict[str, str]:
    return {
        field_name: key[index] if index < len(key) else "missing"
        for index, field_name in enumerate(signature)
    }


def _actual_value_rows(
    value_counts: dict[float, int], *, row_count: int
) -> list[dict[str, Any]]:
    return [
        {
            "delta_percent": value,
            "count": count,
            "share": rounded(count / row_count),
        }
        for value, count in sorted(
            value_counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]


def _mode_share(
    value_counts: dict[float, int], mode_value: float, *, row_count: int
) -> float | None:
    return rounded(value_counts.get(round(mode_value, 6), 0) / row_count)


def _mean_error(errors: list[float]) -> float | None:
    if not errors:
        return None
    return rounded(sum(errors) / len(errors))

def state_signature(state: dict[str, Any], signature: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(state.get(field) or "missing") for field in signature)
