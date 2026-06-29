"""Recommendation report aggregation helpers."""

from __future__ import annotations

from typing import Any


def recommendation_sort_key(row: dict[str, Any]) -> tuple[float, int, str, str]:
    """Sort highest-value recommendation rows first."""

    return (
        -float(row.get("recommendation_score") or 0),
        -int(row.get("total_tokens") or 0),
        str(row.get("event_timestamp") or ""),
        str(row.get("record_id") or ""),
    )


def thread_recommendation_rows(
    rows: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Aggregate recommendation rows by thread."""

    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        _add_thread_recommendation_row(buckets, row)
    summaries = [_thread_recommendation_summary(bucket) for bucket in buckets.values()]
    summaries.sort(
        key=lambda row: (
            -float(row["recommendation_score"]),
            -int(row["total_tokens"]),
            str(row["thread"]),
        )
    )
    return summaries[:limit]


def _add_thread_recommendation_row(
    buckets: dict[str, dict[str, Any]],
    row: dict[str, Any],
) -> None:
    bucket = buckets.setdefault(_recommendation_thread_label(row), _new_thread_bucket(row))
    _add_thread_totals(bucket, row)
    _update_primary_recommendation(bucket, row)
    _add_secondary_signals(bucket, row)


def _recommendation_thread_label(row: dict[str, Any]) -> str:
    return str(
        row.get("thread_attachment_label")
        or row.get("thread_name")
        or row.get("resolved_parent_thread_name")
        or row.get("parent_thread_name")
        or row.get("session_id")
        or "Unknown thread"
    )


def _new_thread_bucket(row: dict[str, Any]) -> dict[str, Any]:
    label = _recommendation_thread_label(row)
    return {
        "thread": label,
        "call_count": 0,
        "session_count": set(),
        "total_tokens": 0,
        "estimated_cost_usd": 0.0,
        "usage_credits": 0.0,
        "recommendation_score": 0.0,
        "max_recommendation_score": 0.0,
        "primary_recommendation": None,
        "secondary_signals": set(),
        "latest_event": "",
    }


def _add_thread_totals(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    bucket["call_count"] += 1
    bucket["session_count"].add(row.get("session_id"))
    bucket["total_tokens"] += int(row.get("total_tokens") or 0)
    bucket["estimated_cost_usd"] += float(row.get("estimated_cost_usd") or 0)
    bucket["usage_credits"] += float(row.get("usage_credits") or 0)
    bucket["recommendation_score"] += float(row.get("recommendation_score") or 0)
    bucket["latest_event"] = max(bucket["latest_event"], str(row.get("event_timestamp") or ""))


def _update_primary_recommendation(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    score = float(row.get("recommendation_score") or 0)
    if score <= float(bucket["max_recommendation_score"] or 0):
        return
    bucket["max_recommendation_score"] = score
    bucket["primary_recommendation"] = row.get("primary_recommendation")


def _add_secondary_signals(bucket: dict[str, Any], row: dict[str, Any]) -> None:
    for signal in row.get("secondary_signals") or []:
        bucket["secondary_signals"].add(signal)
    primary_signal = row.get("primary_signal")
    if primary_signal:
        bucket["secondary_signals"].add(primary_signal)


def _thread_recommendation_summary(bucket: dict[str, Any]) -> dict[str, Any]:
    primary = bucket.get("primary_recommendation")
    secondary = _secondary_signals(bucket["secondary_signals"], primary)
    return {
        "thread": bucket["thread"],
        "call_count": int(bucket["call_count"]),
        "session_count": len(bucket["session_count"]),
        "total_tokens": int(bucket["total_tokens"]),
        "estimated_cost_usd": round(float(bucket["estimated_cost_usd"]), 6),
        "usage_credits": round(float(bucket["usage_credits"]), 6),
        "recommendation_score": round(float(bucket["recommendation_score"]), 2),
        "max_recommendation_score": round(float(bucket["max_recommendation_score"]), 2),
        "primary_recommendation": primary,
        "secondary_signals": secondary,
        "latest_event": bucket["latest_event"],
    }


def _secondary_signals(signals: set[object], primary: object) -> list[str]:
    primary_key = primary.get("key") if isinstance(primary, dict) else None
    secondary = sorted(str(signal) for signal in signals if signal)
    if primary_key in secondary:
        secondary.remove(primary_key)
    return secondary
