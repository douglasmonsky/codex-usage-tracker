"""Estimated usage-impact allocation from observed Codex usage snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

WindowKey = Literal["primary", "secondary"]
Basis = Literal["credits", "cost"]
SortKey = tuple[str, int, str]


_MIN_CALIBRATION_SAMPLES = 5
_PRIMARY_RESET_ROLLBACK_TOLERANCE_SECONDS = 120
_MAX_OBSERVED_TO_CALIBRATED_RATIO = 3.0
_MIN_OBSERVED_CALIBRATED_EXCESS_PERCENT = 0.2
_MAX_UNCALIBRATED_SINGLE_CALL_OBSERVED_PERCENT = 0.5


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
    weight: float
    delta: float
    lower_delta: float
    upper_delta: float
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
            sample = _calibration_sample(
                rows=pending,
                previous=previous,
                current=snapshot,
                observed_after_key=_sort_key(row),
                delta=0.0,
                include_rounding_margin=False,
            )
            if sample is not None:
                calibration_samples.append(sample)
            previous = snapshot
            pending.clear()
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
    sample = _calibration_sample(
        rows=rows,
        previous=previous,
        current=current,
        observed_after_key=observed_after_key,
        delta=delta,
        include_rounding_margin=True,
    )
    if sample is None:
        return None
    weighted_rows, basis = _weighted_rows(rows)
    total_weight = sample.weight
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
    return sample


def _calibration_sample(
    *,
    rows: list[dict[str, Any]],
    previous: _Snapshot,
    current: _Snapshot,
    observed_after_key: SortKey,
    delta: float,
    include_rounding_margin: bool,
) -> _CalibrationSample | None:
    weighted_rows, basis = _weighted_rows(rows)
    if not weighted_rows:
        return None
    total_weight = sum(weight for _row, weight in weighted_rows)
    if total_weight <= 0:
        return None
    margin = _rounding_margin(previous.used_percent, current.used_percent) if include_rounding_margin else 0.0
    lower_delta = max(0.0, delta - margin)
    upper_delta = max(delta, delta + margin)
    return _CalibrationSample(
        basis=basis,
        window_minutes=current.window_minutes,
        plan_type=current.plan_type,
        limit_id=current.limit_id,
        observed_after_key=observed_after_key,
        weight=total_weight,
        delta=delta,
        lower_delta=lower_delta,
        upper_delta=upper_delta,
        rate=delta / total_weight,
        lower_rate=lower_delta / total_weight,
        upper_rate=upper_delta / total_weight,
    )


def _apply_calibrated_estimates(
    rows: list[dict[str, Any]],
    window_key: WindowKey,
    samples: list[_CalibrationSample],
) -> None:
    calibration_cache: dict[tuple[int, str | None, str | None], _Calibration | None] = {}
    for row in rows:
        impact = row.setdefault("usage_impact", {"primary": None, "secondary": None})
        window_minutes = _window_minutes(row, window_key)
        plan_type = _optional_str(row.get("rate_limit_plan_type"))
        limit_id = _optional_str(row.get("rate_limit_limit_id"))
        cache_key = (window_minutes, plan_type, limit_id)
        if cache_key not in calibration_cache:
            calibration_cache[cache_key] = _calibration(
                samples,
                window_minutes=window_minutes,
                plan_type=plan_type,
                limit_id=limit_id,
            )
        calibration = calibration_cache[cache_key]
        if calibration is None:
            existing = impact.get(window_key)
            if isinstance(existing, dict) and _observed_interval_should_be_suppressed(existing):
                impact[window_key] = _suppressed_observed_interval(
                    existing,
                    row=row,
                    window_key=window_key,
                    window_minutes=window_minutes,
                )
            continue
        weight = _row_weight(row, calibration.basis)
        if weight <= 0:
            continue
        existing = impact.get(window_key)
        if isinstance(existing, dict) and (
            _observed_interval_should_be_suppressed(existing)
            or _observed_estimate_is_noisy(
                existing,
                row=row,
                calibration=calibration,
            )
        ):
            impact[window_key] = _calibrated_impact(
                row=row,
                window_key=window_key,
                calibration=calibration,
                window_minutes=window_minutes,
                observed_impact=existing,
            )
            continue
        if existing is not None:
            continue
        impact[window_key] = _calibrated_impact(
            row=row,
            window_key=window_key,
            calibration=calibration,
            window_minutes=window_minutes,
        )


def _calibrated_impact(
    *,
    row: dict[str, Any],
    window_key: WindowKey,
    calibration: _Calibration,
    window_minutes: int,
    observed_impact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weight = _row_weight(row, calibration.basis)
    estimate = calibration.rate * weight
    impact: dict[str, Any] = {
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
    if observed_impact is not None:
        impact["observed_delta_percent"] = observed_impact.get("observed_delta_percent")
        impact["observed_interval_call_count"] = observed_impact.get("interval_call_count")
        impact["observed_interval_estimate_percent"] = observed_impact.get("estimate_percent")
        impact["previous_used_percent"] = observed_impact.get("previous_used_percent")
        impact["current_used_percent"] = observed_impact.get("current_used_percent")
        impact["source_note"] = "calibrated_after_noisy_observed_interval"
    return impact


def _observed_interval_should_be_suppressed(impact: dict[str, Any]) -> bool:
    if impact.get("source") != "observed_interval":
        return False
    if int(impact.get("interval_call_count") or 0) != 1:
        return False
    return _number(impact.get("estimate_percent")) > _MAX_UNCALIBRATED_SINGLE_CALL_OBSERVED_PERCENT


def _suppressed_observed_interval(
    observed_impact: dict[str, Any],
    *,
    row: dict[str, Any],
    window_key: WindowKey,
    window_minutes: int,
) -> dict[str, Any]:
    return {
        "schema": "codex-usage-tracker-usage-impact-estimate-v1",
        "label": _window_label(window_minutes),
        "window_minutes": window_minutes,
        "estimate_percent": None,
        "lower_percent": None,
        "upper_percent": None,
        "observed_delta_percent": observed_impact.get("observed_delta_percent"),
        "observed_interval_call_count": observed_impact.get("interval_call_count"),
        "observed_interval_estimate_percent": observed_impact.get("estimate_percent"),
        "basis": observed_impact.get("basis"),
        "source": "observed_interval",
        "source_note": "suppressed_unvalidated_single_call_observed_jump",
        "plan_type": _optional_str(row.get("rate_limit_plan_type")),
        "limit_id": _optional_str(row.get("rate_limit_limit_id")),
        "resets_at": _optional_int(row.get(f"rate_limit_{window_key}_resets_at")),
    }


def _observed_estimate_is_noisy(
    impact: dict[str, Any],
    *,
    row: dict[str, Any],
    calibration: _Calibration,
) -> bool:
    if impact.get("source") != "observed_interval":
        return False
    observed = _number(impact.get("estimate_percent"))
    if observed <= 0:
        return False
    calibrated = calibration.rate * _row_weight(row, calibration.basis)
    if calibrated <= 0:
        return False
    return observed > max(
        calibrated * _MAX_OBSERVED_TO_CALIBRATED_RATIO,
        calibrated + _MIN_OBSERVED_CALIBRATED_EXCESS_PERCENT,
    )


def _calibration(
    samples: list[_CalibrationSample],
    *,
    window_minutes: int,
    plan_type: str | None,
    limit_id: str | None,
) -> _Calibration | None:
    matching = [
        sample
        for sample in samples
        if sample.window_minutes == window_minutes
        and _scope_matches(sample.plan_type, plan_type)
        and _scope_matches(sample.limit_id, limit_id)
    ]
    if not matching:
        return None

    preferred_basis: Basis = "credits" if any(sample.basis == "credits" for sample in matching) else "cost"
    basis_samples = [sample for sample in matching if sample.basis == preferred_basis]
    if len(basis_samples) < _MIN_CALIBRATION_SAMPLES:
        return None
    total_weight = sum(sample.weight for sample in basis_samples)
    if total_weight <= 0:
        return None
    total_delta = sum(sample.delta for sample in basis_samples)
    if total_delta <= 0:
        return None
    total_lower_delta = sum(sample.lower_delta for sample in basis_samples)
    total_upper_delta = sum(sample.upper_delta for sample in basis_samples)
    return _Calibration(
        basis=preferred_basis,
        rate=total_delta / total_weight,
        lower_rate=total_lower_delta / total_weight,
        upper_rate=max(total_upper_delta, total_delta) / total_weight,
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
        return not (
            previous.resets_at is not None
            and current.resets_at is not None
            and current.resets_at
            < previous.resets_at - _PRIMARY_RESET_ROLLBACK_TOLERANCE_SECONDS
        )
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
    return previous != current


def _scope_matches(sample_value: str | None, row_value: str | None) -> bool:
    return sample_value == row_value


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
