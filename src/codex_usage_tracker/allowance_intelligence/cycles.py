"""Deterministic reset-aware allowance cohort, cycle, and interval derivation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime
from statistics import median
from typing import Any

from .contracts import AllowanceCohort, AllowanceCycle, AllowanceInterval, AllowancePointKind

MODEL_VERSION = "reset-aware-v4"
RESET_JITTER_SECONDS = 60
FRESH_SECONDS = 5 * 60
AGING_SECONDS = {"weekly": 6 * 60 * 60, "five_hour": 15 * 60}


def observed_plan_type(rows: Iterable[dict[str, Any]]) -> str:
    """Return one explicit normalized plan type, or a conservative sentinel."""
    values = set()
    for row in rows:
        value = str(row.get("plan_type") or "").strip().lower()
        if not value:
            continue
        normalized = value.replace("-", "_").replace(" ", "_")
        values.add("prolite" if normalized == "pro_lite" else normalized)
    if not values:
        return "unknown"
    if len(values) > 1:
        return "mixed"
    return values.pop()


def select_allowance_cohort(
    rows: Iterable[dict[str, Any]], *, now: datetime
) -> AllowanceCohort | None:
    """Select a normal cohort while fresh/aging, otherwise a proven alternate."""
    observations = list(rows)
    if not observations:
        return None
    groups: dict[tuple[str, str, str, bool], list[dict[str, Any]]] = {}
    for row in observations:
        group_key = (
            str(row.get("window_kind") or "unknown"),
            str(row.get("window_key") or "primary"),
            str(row.get("limit_id") or "codex"),
            bool(row.get("is_archived")),
        )
        groups.setdefault(group_key, []).append(row)
    candidates = []
    normal_stale = True
    for (kind, window_key, limit, archived), group in groups.items():
        newest = max(group, key=_sort_key)
        age = _age_seconds(newest, now)
        reset = newest.get("resets_at")
        stale = age > AGING_SECONDS.get(kind, 0) or (
            isinstance(reset, (int, float)) and reset < now.timestamp()
        )
        normal = limit == "codex"
        if normal:
            normal_stale = normal_stale and stale
        viable_alt = _alternate_has_cycle_evidence(group)
        candidates.append(
            (
                not stale,
                normal,
                viable_alt,
                _sort_key(newest),
                kind,
                window_key,
                limit,
                archived,
            )
        )
    # Prefer a non-stale normal codex group; ties deterministically retain primary.
    active_normal = [item for item in candidates if item[0] and item[1]]
    alternate = [item for item in candidates if item[0] and item[2]] if normal_stale else []
    available = active_normal or alternate
    if not available:
        return None
    selected = max(available, key=lambda item: (not item[7], item[0], item[1], item[2], item[3]))
    _, _, _, _, kind, window_key, limit, archived = selected
    return AllowanceCohort(limit, kind, window_key, archived, True)


def derive_allowance_cycles(
    rows: Iterable[dict[str, Any]],
    *,
    now: datetime,
    existing_reset_epochs: Any = (),
    cohort: AllowanceCohort | None = None,
) -> tuple[list[AllowanceCycle], list[AllowanceInterval]]:
    """Derive archive-safe cycles and positive/censored interval evidence."""
    selected = cohort or select_allowance_cohort(rows, now=now)
    if selected is None:
        return [], []
    selected_rows = [dict(row) for row in rows if _matches(row, selected)]
    selected_rows.sort(key=_sort_key)
    scope = (selected.is_archived, selected.window_kind, selected.window_key, selected.key)
    epochs = (
        existing_reset_epochs.get(scope, ())
        if isinstance(existing_reset_epochs, dict)
        else existing_reset_epochs
    )
    clustered = _cluster_resets(selected_rows, epochs)
    reset_buckets: dict[int, list[dict[str, Any]]] = {}
    unknown_buckets: list[list[dict[str, Any]]] = []
    current_unknown: list[dict[str, Any]] | None = None
    for row in selected_rows:
        reset = clustered.get(str(row.get("observation_id")))
        row["_cycle_reset"] = reset
        if reset is None:
            if current_unknown is None:
                current_unknown = []
                unknown_buckets.append(current_unknown)
            current_unknown.append(row)
            continue
        current_unknown = None
        reset_buckets.setdefault(reset, []).append(row)
    buckets = [*reset_buckets.values(), *unknown_buckets]
    buckets.sort(
        key=lambda bucket: (
            bucket[0].get("_cycle_reset") is None,
            int(bucket[0].get("_cycle_reset") or 0),
            _sort_key(bucket[0]),
        )
    )
    known_resets = set(reset_buckets)
    cycles: list[AllowanceCycle] = []
    intervals: list[AllowanceInterval] = []
    for index, bucket in enumerate(buckets):
        cycle_id = _id(
            "cycle",
            selected.key,
            selected.window_kind,
            selected.window_key,
            selected.is_archived,
            bucket[0].get("_cycle_reset"),
            index,
        )
        conflict = _has_conflict(bucket)
        reset_at = bucket[0].get("_cycle_reset")
        # A cycle is historical only once its advertised reset has passed, or
        # a later confirmed reset separates it from the currently open cycle.
        completed = bool(
            reset_at is not None
            and (
                int(reset_at) <= int(now.timestamp())
                or any(candidate > int(reset_at) for candidate in known_resets)
            )
        )
        cycle = AllowanceCycle(
            cycle_id,
            selected,
            reset_at,
            tuple(bucket),
            "ambiguous" if conflict or reset_at is None else ("completed" if completed else "open"),
        )
        cycles.append(cycle)
        intervals.extend(_intervals(cycle, conflict))
    return cycles, intervals


def _intervals(cycle: AllowanceCycle, conflict: bool) -> list[AllowanceInterval]:
    rows = cycle.observations
    if not rows:
        return []
    if cycle.reset_at is None:
        return [
            _interval(cycle, rows[0], row, AllowancePointKind.CENSORED, "missing_reset_metadata")
            for row in rows[1:]
        ]
    result: list[AllowanceInterval] = []
    anchor = rows[0]
    for row in rows[1:]:
        delta = _number(row.get("used_percent")) - _number(anchor.get("used_percent"))
        if conflict:
            result.append(_interval(cycle, anchor, row, AllowancePointKind.CONFLICT, "conflict"))
            anchor = row
            continue
        if delta > 0:
            eligible = (
                cycle.cohort.window_kind == "weekly"
                and cycle.status != "ambiguous"
                and _tokens_between(anchor, row) > 0
            )
            result.append(
                _interval(cycle, anchor, row, AllowancePointKind.POSITIVE, None, eligible)
            )
            anchor = row
        elif delta < 0 and cycle.cohort.window_kind == "weekly":
            result.append(
                _interval(cycle, anchor, row, AllowancePointKind.CENSORED, "weekly_reversal")
            )
            anchor = row
    return result


def _interval(
    cycle: AllowanceCycle,
    start: dict[str, Any],
    end: dict[str, Any],
    kind: AllowancePointKind,
    reason: str | None,
    eligible: bool = False,
) -> AllowanceInterval:
    return AllowanceInterval(
        _id("interval", cycle.cycle_id, start.get("observation_id"), end.get("observation_id")),
        cycle.cycle_id,
        start,
        end,
        kind,
        reason,
        eligible,
    )


def _cluster_resets(
    rows: list[dict[str, Any]], existing_epochs: Iterable[int]
) -> dict[str, int | None]:
    values = sorted(
        {int(row["resets_at"]) for row in rows if isinstance(row.get("resets_at"), (int, float))}
    )
    clusters: list[list[int]] = []
    for value in values:
        if clusters and value - clusters[-1][-1] <= RESET_JITTER_SECONDS:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    existing = tuple(int(epoch) for epoch in existing_epochs)
    mapping = {}
    for cluster in clusters:
        display = int(median(cluster))
        nearest = min(existing, key=lambda epoch: abs(epoch - display), default=None)
        identity = (
            nearest
            if nearest is not None and abs(nearest - display) <= RESET_JITTER_SECONDS
            else display
        )
        mapping.update({value: identity for value in cluster})
    return {
        str(row.get("observation_id")): mapping.get(int(row["resets_at"]))
        if isinstance(row.get("resets_at"), (int, float))
        else None
        for row in rows
    }


def _has_conflict(rows: tuple[dict[str, object], ...] | list[dict[str, Any]]) -> bool:
    seen: dict[str, object] = {}
    for row in rows:
        timestamp = str(row.get("event_timestamp"))
        used = row.get("used_percent")
        if timestamp in seen and seen[timestamp] != used:
            return True
        seen[timestamp] = used
    return False


def _alternate_has_cycle_evidence(rows: list[dict[str, Any]]) -> bool:
    by_reset: dict[int | None, list[dict[str, Any]]] = {}
    for row in rows:
        reset = int(row["resets_at"]) if isinstance(row.get("resets_at"), (int, float)) else None
        by_reset.setdefault(reset, []).append(row)
    return any(
        len(group) >= 3 and len({row.get("used_percent") for row in group}) > 1
        for group in by_reset.values()
    )


def _matches(row: dict[str, Any], cohort: AllowanceCohort) -> bool:
    return (
        str(row.get("window_kind") or "unknown"),
        str(row.get("window_key") or "primary"),
        str(row.get("limit_id") or "codex"),
        bool(row.get("is_archived")),
    ) == (cohort.window_kind, cohort.window_key, cohort.key, cohort.is_archived)


def _sort_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row.get("event_timestamp") or ""),
        int(row.get("cumulative_total_tokens") or 0),
        str(row.get("observation_id") or ""),
    )


def _number(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _tokens_between(start: dict[str, Any], end: dict[str, Any]) -> int:
    return max(
        0,
        int(end.get("cumulative_total_tokens") or 0)
        - int(start.get("cumulative_total_tokens") or 0),
    )


def _age_seconds(row: dict[str, Any], now: datetime) -> float:
    return (
        now - datetime.fromisoformat(str(row["event_timestamp"]).replace("Z", "+00:00"))
    ).total_seconds()


def _id(*parts: object) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]
