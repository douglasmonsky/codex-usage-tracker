"""Shared row, pricing, and revision helpers for allowance materialization."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from codex_usage_tracker.allowance_intelligence.cycles import MODEL_VERSION
from codex_usage_tracker.pricing.allowance_usage import annotate_rows_with_allowance

INTERVAL_INSERT_SQL = """INSERT INTO allowance_intervals (interval_id,cycle_id,window_kind,window_key,cohort_key,is_archived,start_observation_id,end_observation_id,start_record_id,end_record_id,start_observed_at,end_observed_at,start_used_percent,end_used_percent,visible_percent_delta,percent_resolution,input_tokens,cached_input_tokens,uncached_input_tokens,output_tokens,reasoning_output_tokens,total_tokens,estimated_credits,price_coverage,confidence,confidence_mix,point_kind,interval_kind,censor_reason,simultaneous_conflict_count,explained_movement,unexplained_movement,eligible_for_interpolation,eligible_for_calibration,eligible_for_forecasting,eligible_for_change_detection,source_revision,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
_REVISION_FIELDS = (
    "observation_id",
    "record_id",
    "event_timestamp",
    "window_key",
    "window_kind",
    "used_percent",
    "resets_at",
    "limit_id",
    "is_archived",
    "model",
    "effort",
    "input_tokens",
    "cached_input_tokens",
    "uncached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
    "cumulative_total_tokens",
)
_REVISION_SEED = hashlib.sha256(
    b"codex-usage-tracker.allowance-source-revision.chain-v1"
).digest()


def interval_usage_rows(
    observations: tuple[dict[str, object], ...],
    start: dict[str, object],
    end: dict[str, object],
    *,
    positions: dict[object, int],
) -> tuple[dict[str, object], ...]:
    """Return canonical calls after the start anchor through the end anchor."""
    start_index = positions.get(start.get("observation_id"))
    end_index = positions.get(end.get("observation_id"))
    if start_index is None or end_index is None or end_index <= start_index:
        return (end,) if end else ()
    return observations[start_index + 1 : end_index + 1]


def observation_positions(
    observations: tuple[dict[str, object], ...],
) -> dict[object, int]:
    return {
        row.get("observation_id"): index
        for index, row in enumerate(observations)
        if row.get("observation_id") is not None
    }


def interval_storage_row(
    interval: Any,
    *,
    cycle: Any,
    usage_rows: tuple[dict[str, object], ...],
    pricing: dict[str, object],
    revision: str,
) -> tuple[object, ...]:
    start, end = interval.start or {}, interval.end or {}
    eligible = interval.eligible_for_interpolation
    supported = eligible and bool(pricing["supported"])
    return (
        interval.interval_id,
        interval.cycle_id,
        cycle.cohort.window_kind,
        cycle.cohort.window_key,
        cycle.cohort.key,
        int(cycle.cohort.is_archived),
        start.get("observation_id"),
        end.get("observation_id"),
        start.get("record_id"),
        end.get("record_id"),
        start.get("event_timestamp"),
        end.get("event_timestamp"),
        start.get("used_percent"),
        end.get("used_percent"),
        float_value(end.get("used_percent")) - float_value(start.get("used_percent")),
        None,
        sum(int_value(row.get("input_tokens")) for row in usage_rows),
        sum(int_value(row.get("cached_input_tokens")) for row in usage_rows),
        sum(int_value(row.get("uncached_input_tokens")) for row in usage_rows),
        sum(int_value(row.get("output_tokens")) for row in usage_rows),
        sum(int_value(row.get("reasoning_output_tokens")) for row in usage_rows),
        sum(int_value(row.get("total_tokens")) for row in usage_rows),
        pricing["estimated_credits"],
        pricing["price_coverage"],
        pricing["confidence"],
        pricing["confidence_mix"],
        interval.point_kind.value,
        "observed",
        interval.censor_reason,
        0,
        None,
        None,
        int(eligible),
        int(supported),
        int(supported),
        int(supported),
        revision,
        MODEL_VERSION,
    )


def interval_pricing(
    rows: tuple[dict[str, object], ...], allowance_config: Any
) -> dict[str, object]:
    annotated = annotate_rows_with_allowance(
        [dict(row) for row in rows],
        allowance_config,
    )
    total_tokens = sum(int_value(row.get("total_tokens")) for row in annotated)
    priced = [row for row in annotated if row.get("usage_credits") is not None]
    priced_tokens = sum(int_value(row.get("total_tokens")) for row in priced)
    coverage = priced_tokens / total_tokens if total_tokens > 0 else 0.0
    credits = sum(float_value(row.get("usage_credits")) for row in priced)
    mix: dict[str, int] = {}
    weighted_confidence = 0.0
    for row in annotated:
        label = str(row.get("usage_credit_confidence") or "unpriced")
        mix[label] = mix.get(label, 0) + 1
        tokens = int_value(row.get("total_tokens"))
        weighted_confidence += tokens * _pricing_confidence_score(label)
    confidence = weighted_confidence / total_tokens if total_tokens > 0 else 0.0
    return {
        "estimated_credits": credits if priced else None,
        "price_coverage": coverage,
        "confidence": confidence,
        "confidence_mix": json.dumps(mix, sort_keys=True, separators=(",", ":")),
        "supported": coverage >= 0.95 and confidence >= 0.5,
        "total_tokens": total_tokens,
        "priced_tokens": priced_tokens,
    }


def cycle_pricing(intervals: list[dict[str, object]]) -> dict[str, float | None]:
    total_tokens = sum(int_value(row["total_tokens"]) for row in intervals)
    priced_tokens = sum(int_value(row["priced_tokens"]) for row in intervals)
    coverage = priced_tokens / total_tokens if total_tokens > 0 else None
    priced_credits = sum(float_value(row["estimated_credits"]) for row in intervals)
    has_priced = any(row["estimated_credits"] is not None for row in intervals)
    fully_priced = coverage is not None and coverage >= 1.0
    return {
        "canonical_credits": priced_credits if fully_priced else None,
        "priced_credits": priced_credits if has_priced else None,
        "unpriced_credits": 0.0 if fully_priced else None,
        "price_coverage": coverage,
    }


def _pricing_confidence_score(label: str) -> float:
    return {
        "exact": 1.0,
        "user_override": 1.0,
        "inferred": 0.85,
        "alias": 0.85,
        "estimated": 0.65,
        "unpriced": 0.0,
    }.get(label, 0.5)


def int_value(value: object) -> int:
    return int(value) if isinstance(value, int | float) else 0


def float_value(value: object) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def revision(rows: list[dict[str, object]]) -> str:
    return _extend_revision(_REVISION_SEED, rows).hex()


def append_revision(
    source_revision: str,
    rows: list[dict[str, object]],
) -> str | None:
    try:
        seed = bytes.fromhex(source_revision)
    except ValueError:
        return None
    if len(seed) != hashlib.sha256().digest_size:
        return None
    return _extend_revision(seed, rows).hex()


def _extend_revision(
    seed: bytes,
    rows: list[dict[str, object]],
) -> bytes:
    revision_digest = seed
    for row in rows:
        payload = json.dumps(
            [row.get(field) for field in _REVISION_FIELDS],
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        revision_digest = hashlib.sha256(
            revision_digest + len(payload).to_bytes(8, "big") + payload
        ).digest()
    return revision_digest
