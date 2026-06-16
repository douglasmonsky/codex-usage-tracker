"""Estimated usage-impact allocation from observed Codex usage snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

WindowKey = Literal["primary", "secondary"]
Basis = Literal["credits", "cost"]
SortKey = tuple[str, int, str]


_MIN_CALIBRATION_SAMPLES = 5
_PRIMARY_RESET_ROLLBACK_TOLERANCE_SECONDS = 120


@dataclass(frozen=True)
class _Snapshot:
    used_percent: float
    window_minutes: int
    resets_at: int | None
    plan_type: str | None
    limit_id: str | None


@dataclass(frozen=True)
class _CalibrationSample:
    basis: Basis
    window_minutes: int
    plan_type: str | None
    limit_id: str | None
    observed_after_key: SortKey
    rate: float
    lower_rate: float
    upper_rate: float


@dataclass(frozen=True)
class _Calibration:
    basis: Basis
    rate: float
    lower_rate: float
    upper_rate: float
    sample_count: int


def annotate_rows_with_usage_impact(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return copied rows with estimated per-call usage impact.

    The estimates are derived only from persisted aggregate rows. Adjacent
    account-level observed usage percentages define movement, and that movement
    is allocated to local calls in the chronological interval by Codex credit
    estimate first, then cost estimate. Token-count proxy allocation is
    intentionally not used.
    """

    annotated = [dict(row) for row in rows]
    for row in annotated:
        row["usage_impact"] = {"primary": None, "secondary": None}

    chronological = sorted(
        annotated,
        key=_sort_key,
    )
    for window_key in ("primary", "secondary"):
        _annotate_window(chronological, window_key)
    return annotated


def copy_usage_impact_from_context(
    rows: list[dict[str, Any]],
    context_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Copy usage-impact estimates from an annotated full context onto rows."""

    annotated_context = annotate_rows_with_usage_impact(context_rows)
    impact_by_record_id = {
        str(row.get("record_id")): row.get("usage_impact")
        for row in annotated_context
        if row.get("record_id")
    }
    copied: list[dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        next_row["usage_impact"] = impact_by_record_id.get(
            str(row.get("record_id")),
            {"primary": None, "secondary": None},
        )
        copied.append(next_row)
    return copied


def usage_impact_estimate(row: dict[str, Any], window_key: WindowKey) -> float | None:
    """Return the estimated impact percent for a row/window, if present."""

    impact = row.get("usage_impact")
    if not isinstance(impact, dict):
        return None
    window = impact.get(window_key)
    if not isinstance(window, dict):
        return None
    value = window.get("estimate_percent")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _annotate_window(rows: list[dict[str, Any]], window_key: WindowKey) -> None:
    previous: _Snapshot | None = None
    pending: list[dict[str, Any]] = []
    calibration_samples: list[_CalibrationSample] = []
    for row in rows:
        pending.append(row)
        snapshot = _snapshot(row, window_key)
        if snapshot is None:
            continue
        if previous is None:
            previous = snapshot
            pending.clear()
            continue
        if not _same_window(previous, snapshot, window_key):
            previous = snapshot
            pending.clear()
            continue
        delta = snapshot.used_percent - previous.used_percent
        if delta < 0:
            if not _is_stale_decrease(previous, snapshot, window_key):
                previous = snapshot
            pending.clear()
            continue
        if delta == 0:
            continue
        sample = _allocate_interval(
            rows=pending,
            window_key=window_key,
            previous=previous,
            current=snapshot,
            observed_after_key=_sort_key(row),
            delta=delta,
        )
        if sample is not None:
            calibration_samples.append(sample)
        previous = snapshot
        pending.clear()
    _apply_calibrated_estimates(rows, window_key, calibration_samples)


def _allocate_interval(
    *,
    rows: list[dict[str, Any]],
    window_key: WindowKey,
    previous: _Snapshot,
    current: _Snapshot,
    observed_after_key: SortKey,
    delta: float,
) -> _CalibrationSample | None:
    weighted_rows, basis = _weighted_rows(rows)
    if not weighted_rows:
        return None
    total_weight = sum(weight for _row, weight in weighted_rows)
    if total_weight <= 0:
        return None
    margin = _rounding_margin(previous.used_percent, current.used_percent)
    lower_delta = max(0.0, delta - margin)
    upper_delta = max(delta, delta + margin)
    for row, weight in weighted_rows:
        share = weight / total_weight
        estimate = delta * share
        lower = lower_delta * share
        upper = upper_delta * share
        impact = row.setdefault("usage_impact", {"primary": None, "secondary": None})
        impact[window_key] = {
            "schema": "codex-usage-tracker-usage-impact-estimate-v1",
            "label": _window_label(current.window_minutes),
            "window_minutes": current.window_minutes,
            "estimate_percent": estimate,
            "lower_percent": lower,
            "upper_percent": upper,
            "observed_delta_percent": delta,
            "interval_call_count": len(rows),
            "basis": basis,
            "source": "observed_interval",
            "previous_used_percent": previous.used_percent,
            "current_used_percent": current.used_percent,
            "plan_type": current.plan_type,
            "limit_id": current.limit_id,
            "resets_at": current.resets_at,
        }
    return _CalibrationSample(
        basis=basis,
        window_minutes=current.window_minutes,
        plan_type=current.plan_type,
        limit_id=current.limit_id,
        observed_after_key=observed_after_key,
        rate=delta / total_weight,
        lower_rate=lower_delta / total_weight,
        upper_rate=upper_delta / total_weight,
    )


def _apply_calibrated_estimates(
    rows: list[dict[str, Any]],
    window_key: WindowKey,
    samples: list[_CalibrationSample],
) -> None:
    for row in rows:
        impact = row.setdefault("usage_impact", {"primary": None, "secondary": None})
        if impact.get(window_key) is not None:
            continue
        window_minutes = _window_minutes(row, window_key)
        calibration = _calibration(samples, row=row, window_key=window_key)
        if calibration is None:
            continue
        weight = _row_weight(row, calibration.basis)
        if weight <= 0:
            continue
        estimate = calibration.rate * weight
        impact[window_key] = {
            "schema": "codex-usage-tracker-usage-impact-estimate-v1",
            "label": _window_label(window_minutes),
            "window_minutes": window_minutes,
            "estimate_percent": estimate,
            "lower_percent": calibration.lower_rate * weight,
            "upper_percent": calibration.upper_rate * weight,
            "observed_delta_percent": None,
            "interval_call_count": None,
            "basis": calibration.basis,
            "source": "calibrated_history",
            "calibration_sample_count": calibration.sample_count,
            "plan_type": _optional_str(row.get("rate_limit_plan_type")),
            "limit_id": _optional_str(row.get("rate_limit_limit_id")),
            "resets_at": _optional_int(row.get(f"rate_limit_{window_key}_resets_at")),
        }


def _calibration(
    samples: list[_CalibrationSample],
    *,
    row: dict[str, Any],
    window_key: WindowKey,
) -> _Calibration | None:
    window_minutes = _window_minutes(row, window_key)
    plan_type = _optional_str(row.get("rate_limit_plan_type"))
    limit_id = _optional_str(row.get("rate_limit_limit_id"))
    row_key = _sort_key(row)
    row_has_snapshot = _snapshot(row, window_key) is not None
    matching = [
        sample
        for sample in samples
        if sample.window_minutes == window_minutes
        and (not row_has_snapshot or sample.observed_after_key <= row_key)
        and _scope_matches(sample.plan_type, plan_type)
        and _scope_matches(sample.limit_id, limit_id)
    ]
    if not matching:
        return None

    preferred_basis: Basis = "credits" if any(sample.basis == "credits" for sample in matching) else "cost"
    basis_samples = [sample for sample in matching if sample.basis == preferred_basis]
    if len(basis_samples) < _MIN_CALIBRATION_SAMPLES:
        return None
    rates = sorted(sample.rate for sample in basis_samples if sample.rate > 0)
    lower_rates = sorted(sample.lower_rate for sample in basis_samples if sample.lower_rate >= 0)
    upper_rates = sorted(sample.upper_rate for sample in basis_samples if sample.upper_rate > 0)
    if not rates:
        return None
    return _Calibration(
        basis=preferred_basis,
        rate=_median(rates),
        lower_rate=_median(lower_rates) if lower_rates else 0.0,
        upper_rate=_median(upper_rates) if upper_rates else _median(rates),
        sample_count=len(basis_samples),
    )


def _weighted_rows(rows: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], float]], Basis | None]:
    credit_rows = [
        (row, _number(row.get("usage_credits")))
        for row in rows
        if _number(row.get("usage_credits")) > 0
    ]
    if credit_rows:
        return credit_rows, "credits"
    cost_rows = [
        (row, _number(row.get("estimated_cost_usd")))
        for row in rows
        if _number(row.get("estimated_cost_usd")) > 0
    ]
    if cost_rows:
        return cost_rows, "cost"
    return [], None


def _row_weight(row: dict[str, Any], basis: Basis) -> float:
    if basis == "credits":
        return _number(row.get("usage_credits"))
    return _number(row.get("estimated_cost_usd"))


def _snapshot(row: dict[str, Any], window_key: WindowKey) -> _Snapshot | None:
    used = _optional_float(row.get(f"rate_limit_{window_key}_used_percent"))
    minutes = _optional_int(row.get(f"rate_limit_{window_key}_window_minutes"))
    if used is None or minutes is None:
        return None
    return _Snapshot(
        used_percent=used,
        window_minutes=minutes,
        resets_at=_optional_int(row.get(f"rate_limit_{window_key}_resets_at")),
        plan_type=_optional_str(row.get("rate_limit_plan_type")),
        limit_id=_optional_str(row.get("rate_limit_limit_id")),
    )


def _sort_key(row: dict[str, Any]) -> SortKey:
    return (
        str(row.get("event_timestamp") or ""),
        int(row.get("line_number") or 0),
        str(row.get("record_id") or ""),
    )


def _same_window(previous: _Snapshot, current: _Snapshot, window_key: WindowKey) -> bool:
    # The short Codex allowance window behaves like a rolling horizon in local
    # logs, so the advertised reset timestamp can drift between adjacent calls
    # even when the used percentage is moving within the same observed window.
    # Decreases are handled as reset/external-correction boundaries before this
    # check; same-sized windows with positive movement are still allocatable.
    if previous.window_minutes != current.window_minutes:
        return False
    if _scope_changed(previous.plan_type, current.plan_type):
        return False
    if _scope_changed(previous.limit_id, current.limit_id):
        return False
    if window_key == "primary":
        if (
            previous.resets_at is not None
            and current.resets_at is not None
            and current.resets_at
            < previous.resets_at - _PRIMARY_RESET_ROLLBACK_TOLERANCE_SECONDS
        ):
            return False
        return True
    return previous.resets_at == current.resets_at


def _is_stale_decrease(previous: _Snapshot, current: _Snapshot, window_key: WindowKey) -> bool:
    if window_key == "secondary":
        return previous.resets_at == current.resets_at
    if previous.resets_at is None or current.resets_at is None:
        return False
    return current.resets_at <= previous.resets_at


def _rounding_margin(previous: float, current: float) -> float:
    if _is_integerish(previous) and _is_integerish(current):
        return 1.0
    return 0.1


def _is_integerish(value: float) -> bool:
    return abs(value - round(value)) < 0.000001


def _window_label(window_minutes: int) -> str:
    if window_minutes == 300:
        return "5h"
    if window_minutes == 10080:
        return "Weekly"
    if window_minutes % 1440 == 0:
        return f"{window_minutes // 1440}d"
    if window_minutes % 60 == 0:
        return f"{window_minutes // 60}h"
    return f"{window_minutes}m"


def _window_minutes(row: dict[str, Any], window_key: WindowKey) -> int:
    minutes = _optional_int(row.get(f"rate_limit_{window_key}_window_minutes"))
    if minutes is not None:
        return minutes
    return 300 if window_key == "primary" else 10080


def _scope_changed(previous: str | None, current: str | None) -> bool:
    return previous is not None and current is not None and previous != current


def _scope_matches(sample_value: str | None, row_value: str | None) -> bool:
    return sample_value is None or row_value is None or sample_value == row_value


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    midpoint = len(values) // 2
    if len(values) % 2:
        return values[midpoint]
    return (values[midpoint - 1] + values[midpoint]) / 2


def _number(value: object) -> float:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return numeric if numeric > 0 else 0.0


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric >= 0 else None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
