"""Thread-level cost curve helpers for usage-drain dashboard reports."""

from __future__ import annotations

from typing import Any

MAX_THREAD_CURVES = 12
MAX_CURVE_POINTS_PER_THREAD = 120


def thread_cost_curves(
    rows: list[dict[str, Any]],
    *,
    max_threads: int,
    max_curve_points: int,
) -> dict[str, Any]:
    thread_rows = _sorted_thread_curve_records(rows, max_curve_points=max_curve_points)
    return _thread_curve_summary(
        thread_rows,
        max_threads=max_threads,
        max_curve_points=max_curve_points,
    )


def _sorted_thread_curve_records(
    rows: list[dict[str, Any]],
    *,
    max_curve_points: int,
) -> list[dict[str, Any]]:
    thread_rows = [
        _thread_curve_record(bucket, max_curve_points=max_curve_points)
        for bucket in _thread_buckets(rows).values()
    ]
    thread_rows.sort(key=_thread_sort_key)
    return thread_rows


def _thread_buckets(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=_thread_curve_chronological_key):
        key = str(row.get("thread_key") or row.get("session_id") or "unknown")
        bucket = buckets.setdefault(key, _new_thread_bucket(key, row))
        bucket["calls"].append(row)
        if bucket["thread"] == "Unknown thread":
            bucket["thread"] = _thread_label(row)
    return buckets


def _new_thread_bucket(key: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "thread_key": key,
        "thread": _thread_label(row),
        "calls": [],
    }


def _thread_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
    return (
        -number(row.get("estimated_cost_usd")),
        -int(row.get("call_count") or 0),
        str(row.get("thread") or ""),
    )


def _thread_curve_summary(
    thread_rows: list[dict[str, Any]],
    *,
    max_threads: int,
    max_curve_points: int,
) -> dict[str, Any]:
    total_cost = sum(number(row.get("estimated_cost_usd")) for row in thread_rows)
    top_cost = number(thread_rows[0].get("estimated_cost_usd")) if thread_rows else 0.0
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
    representative_call = _representative_call(calls)
    cumulative = 0.0
    points: list[dict[str, Any]] = []
    call_costs: list[float] = []
    first_half_cutoff = max(len(calls) // 2, 1)
    first_half_cost = 0.0
    for index, row in enumerate(calls, start=1):
        call_cost = number(row.get("estimated_cost_usd"))
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
        "largest_record_id": _record_id(representative_call),
        "representative_record_id": _record_id(representative_call),
        "largest_call_tokens": int(number(representative_call.get("total_tokens"))),
        "largest_call_cost_usd": round(
            number(representative_call.get("estimated_cost_usd")),
            6,
        ),
        "first_half_cost_share": round(first_half_share, 6),
        "largest_call_cost_share": round(largest_share, 6),
        "shape": _curve_shape(first_half_share, largest_share),
        "points": _sample_curve_points(points, max_points=max_curve_points),
    }


def _representative_call(calls: list[dict[str, Any]]) -> dict[str, Any]:
    if not calls:
        return {}
    return max(calls, key=_representative_call_key)


def _representative_call_key(row: dict[str, Any]) -> tuple[float, int, int, str, str]:
    return (
        number(row.get("estimated_cost_usd")),
        int(number(row.get("total_tokens"))),
        int(number(row.get("cumulative_total_tokens"))),
        str(row.get("event_timestamp") or ""),
        _record_id(row),
    )


def _record_id(row: dict[str, Any]) -> str:
    value = row.get("record_id")
    return str(value) if value else ""


def _sample_curve_points(
    points: list[dict[str, Any]],
    *,
    max_points: int,
) -> list[dict[str, Any]]:
    if max_points <= 0 or len(points) <= max_points:
        return points
    if max_points == 1:
        return [points[0]]
    last_index = len(points) - 1
    selected_indexes = {round(index * last_index / (max_points - 1)) for index in range(max_points)}
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


def _thread_curve_chronological_key(row: dict[str, Any]) -> tuple[str, int, str]:
    return (
        str(row.get("event_timestamp") or ""),
        int(number(row.get("cumulative_total_tokens"))),
        str(row.get("record_id") or ""),
    )


def number(value: object) -> float:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0
