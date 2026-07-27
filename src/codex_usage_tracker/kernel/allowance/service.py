"""Bounded generation-consistent allowance reads for every public adapter."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from ..database import open_read_snapshot
from ..operational import load_cutover_control
from .efficiency import AllowanceObservation, LocalUsage, build_interval
from .rates import estimate_local_usage, load_rate_card

MAX_ALLOWANCE_LIMIT = 500
MAX_ALLOWANCE_OFFSET = 1_000_000
_SCHEMA = "codex-usage-tracker.allowance-efficiency.v1"

ALLOWANCE_BASE_SQL = """
(
WITH ordered AS (
    SELECT allowance_observations.*,
           LAG(allowance_observation_id) OVER observation_window
               AS previous_observation_id,
           LAG(observed_at) OVER observation_window AS previous_observed_at,
           LAG(used_percent) OVER observation_window AS previous_used_percent,
           LAG(duration_minutes) OVER observation_window
               AS previous_duration_minutes,
           LAG(resets_at) OVER observation_window AS previous_resets_at,
           LAG(model) OVER observation_window AS previous_model,
           LAG(service_tier) OVER observation_window
               AS previous_service_tier,
           LAG(provenance) OVER observation_window AS previous_provenance,
           LAG(validation_warnings) OVER observation_window
               AS previous_validation_warnings
    FROM allowance_observations
    WHERE generation <= ? AND duplicate_state = 'canonical'
    WINDOW observation_window AS (
        PARTITION BY
            window_kind,
            COALESCE(limit_id, ''),
            COALESCE(plan_type, '')
        ORDER BY observed_at, allowance_observation_id
    )
),
deltas AS (
    SELECT ordered.*,
           CASE
               WHEN previous_observation_id IS NOT NULL
                AND previous_resets_at IS resets_at
                AND previous_duration_minutes IS duration_minutes
                AND observed_at > previous_observed_at
                AND (
                    duration_minutes IS NULL
                    OR (
                        julianday(observed_at)
                        - julianday(previous_observed_at)
                    ) * 1440.0 <= duration_minutes
                )
                AND used_percent > previous_used_percent
               THEN used_percent - previous_used_percent
               ELSE NULL
           END AS delta_used_percent,
           CASE
               WHEN previous_observation_id IS NOT NULL
                AND previous_resets_at IS resets_at
                AND previous_duration_minutes IS duration_minutes
                AND observed_at > previous_observed_at
                AND (
                    duration_minutes IS NULL
                    OR (
                        julianday(observed_at)
                        - julianday(previous_observed_at)
                    ) * 1440.0 <= duration_minutes
                )
                AND used_percent > previous_used_percent
               THEN (
                   julianday(observed_at) - julianday(previous_observed_at)
               ) * 24.0
               ELSE NULL
           END AS elapsed_hours
    FROM ordered
),
fact_events AS (
    SELECT model_calls.event_at,
           0 AS event_rank,
           'call:' || model_calls.model_call_id AS event_id,
           NULL AS allowance_observation_id,
           model_calls.input_tokens - model_calls.cached_input_tokens
               AS uncached_input_tokens,
           model_calls.cached_input_tokens AS cached_input_tokens,
           model_calls.reasoning_tokens AS reasoning_tokens,
           model_calls.output_tokens AS output_tokens,
           model_calls.input_tokens + model_calls.output_tokens
               AS total_tokens,
           1 AS calls,
           0 AS turns
    FROM model_calls
    WHERE model_calls.generation <= ?
      AND model_calls.duplicate_state = 'canonical'
    UNION ALL
    SELECT MIN(model_calls.event_at),
           0,
           'turn:' || turns.turn_id,
           NULL,
           0, 0, 0, 0, 0, 0, 1
    FROM turns
    JOIN model_calls ON model_calls.turn_id = turns.turn_id
    WHERE model_calls.generation <= ?
      AND model_calls.duplicate_state = 'canonical'
    GROUP BY turns.turn_id
    UNION ALL
    SELECT ordered.observed_at,
           1,
           'allowance:' || ordered.allowance_observation_id,
           ordered.allowance_observation_id,
           0, 0, 0, 0, 0, 0, 0
    FROM ordered
),
running_facts AS (
    SELECT fact_events.*,
           SUM(uncached_input_tokens) OVER fact_window
               AS cumulative_uncached_input_tokens,
           SUM(cached_input_tokens) OVER fact_window
               AS cumulative_cached_input_tokens,
           SUM(reasoning_tokens) OVER fact_window
               AS cumulative_reasoning_tokens,
           SUM(output_tokens) OVER fact_window
               AS cumulative_output_tokens,
           SUM(total_tokens) OVER fact_window AS cumulative_total_tokens,
           SUM(calls) OVER fact_window AS cumulative_calls,
           SUM(turns) OVER fact_window AS cumulative_turns
    FROM fact_events
    WINDOW fact_window AS (
        ORDER BY event_at, event_rank, event_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
),
observation_facts AS (
    SELECT *
    FROM running_facts
    WHERE allowance_observation_id IS NOT NULL
),
local_facts AS (
    SELECT deltas.*,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_uncached_input_tokens
               - previous_facts.cumulative_uncached_input_tokens
           END AS local_uncached_input_tokens,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_cached_input_tokens
               - previous_facts.cumulative_cached_input_tokens
           END AS local_cached_input_tokens,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_reasoning_tokens
               - previous_facts.cumulative_reasoning_tokens
           END AS local_reasoning_tokens,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_output_tokens
               - previous_facts.cumulative_output_tokens
           END AS local_output_tokens,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_total_tokens
               - previous_facts.cumulative_total_tokens
           END AS local_total_tokens,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_calls
               - previous_facts.cumulative_calls
           END AS local_calls,
           CASE WHEN previous_observation_id IS NULL THEN 0 ELSE
               current_facts.cumulative_turns
               - previous_facts.cumulative_turns
           END AS local_turns
    FROM deltas
    JOIN observation_facts AS current_facts
      ON current_facts.allowance_observation_id
       = deltas.allowance_observation_id
    LEFT JOIN observation_facts AS previous_facts
      ON previous_facts.allowance_observation_id
       = deltas.previous_observation_id
)
SELECT local_facts.*,
       100.0 - used_percent AS remaining_percent,
       CASE
           WHEN delta_used_percent IS NULL THEN NULL
           ELSE delta_used_percent / elapsed_hours
       END AS percentage_points_per_hour,
       CASE
           WHEN delta_used_percent IS NULL THEN NULL
           ELSE 1.0 * local_total_tokens / delta_used_percent
       END AS local_tokens_per_percentage_point,
       CASE
           WHEN delta_used_percent IS NULL THEN NULL
           ELSE 1.0 * local_calls / delta_used_percent
       END AS local_calls_per_percentage_point,
       CASE
           WHEN delta_used_percent IS NULL THEN NULL
           ELSE 1.0 * local_turns / delta_used_percent
       END AS local_turns_per_percentage_point
FROM local_facts
) AS allowance_intervals
"""

_OBSERVATION_SQL = """
SELECT *
FROM """ + ALLOWANCE_BASE_SQL + """
ORDER BY observed_at DESC, allowance_observation_id DESC
LIMIT ? OFFSET ?
"""

_LOCAL_USAGE_SQL = """
SELECT model,
       SUM(input_tokens - cached_input_tokens) AS uncached_input_tokens,
       SUM(cached_input_tokens) AS cached_input_tokens,
       SUM(reasoning_tokens) AS reasoning_tokens,
       SUM(output_tokens) AS output_tokens,
       COUNT(*) AS calls,
       COUNT(DISTINCT turn_id) AS turns
FROM model_calls
WHERE generation <= ?
  AND duplicate_state = 'canonical'
                 AND event_at > ?
                 AND event_at <= ?
GROUP BY model
ORDER BY model
"""

class AllowanceService:
    """Return exact observations plus deterministic local-efficiency facts."""

    def __init__(self, operational_path: Path, rate_card_path: Path) -> None:
        self._operational_path = operational_path.resolve()
        self._rate_card_path = rate_card_path.resolve()

    def read(self, *, limit: int = 100, cursor: str | None = None) -> dict[str, Any]:
        if not 1 <= limit <= MAX_ALLOWANCE_LIMIT:
            raise ValueError(
                f"allowance limit must be between 1 and {MAX_ALLOWANCE_LIMIT}"
            )
        started = time.perf_counter()
        control = load_cutover_control(self._operational_path)
        path = control.active_kernel_path
        generation = control.active_generation
        if path is None or generation is None:
            raise ValueError("no active analytical generation")
        publication_id = control.integrity_digest
        if publication_id is None:
            raise ValueError("active analytical publication identity is missing")
        offset = _decode_cursor(
            cursor,
            generation=generation,
            publication_id=publication_id,
        )
        card = load_rate_card(self._rate_card_path)
        with open_read_snapshot(path) as connection:
            matched = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM allowance_observations
                    WHERE generation <= ? AND duplicate_state = 'canonical'
                    """,
                    (generation,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                _OBSERVATION_SQL,
                (generation, generation, generation, limit + 1, offset),
            ).fetchall()
            returned_rows = rows[:limit]
            intervals = [
                _interval_payload(
                    row,
                    connection=connection,
                    generation=generation,
                    card=card,
                )
                for row in returned_rows
            ]
        truncated = len(rows) > limit
        next_cursor = (
            _encode_cursor(
                generation=generation,
                publication_id=publication_id,
                offset=offset + limit,
            )
            if truncated
            else None
        )
        observed_through = (
            max(str(row["observed_at"]) for row in returned_rows)
            if returned_rows
            else None
        )
        grades = {str(item["grade"]) for item in intervals}
        grade = "deterministic" if "deterministic" in grades else "exact"
        return {
            "schema": _SCHEMA,
            "plan_id": "allowance.efficiency.v1",
            "plan_version": 1,
            "generation": generation,
            "source_generation": generation,
            "observed_through": observed_through,
            "rows": intervals,
            "intervals": intervals,
            "matched_count": matched,
            "returned_count": len(intervals),
            "scanned_count": matched,
            "truncated": truncated,
            "next_cursor": next_cursor,
            "elapsed_ms": (time.perf_counter() - started) * 1000,
            "grade": grade,
            "coverage": _coverage(intervals, card is not None),
            "evidence_selectors": [
                str(item["evidence_selector"]) for item in intervals
            ],
        }


def _interval_payload(
    row: sqlite3.Row,
    *,
    connection: sqlite3.Connection,
    generation: int,
    card: Any,
) -> dict[str, Any]:
    current = _observation(row)
    previous = _previous_observation(row, current)
    usage = LocalUsage(
        uncached_input_tokens=int(row["local_uncached_input_tokens"]),
        cached_input_tokens=int(row["local_cached_input_tokens"]),
        reasoning_tokens=int(row["local_reasoning_tokens"]),
        output_tokens=int(row["local_output_tokens"]),
        calls=int(row["local_calls"]),
        turns=int(row["local_turns"]),
    )
    usage_by_model = (
        _local_usage(
            connection,
            generation=generation,
            previous=previous,
            current=current,
        )
        if card is not None
        else {"unconfigured": usage}
    )
    interval = build_interval(previous, current, usage)
    estimate = estimate_local_usage(usage_by_model, card)
    limitations = list(interval.limitations)
    if estimate.coverage_percent < 100:
        limitations.append("incomplete_rate_card_coverage")
    payload = {
        "allowance_observation_id": current.allowance_observation_id,
        "previous_observation_id": (
            previous.allowance_observation_id if previous else None
        ),
        "evidence_selector": (
            f"allowance:{current.allowance_observation_id}"
        ),
        "observed_at": _timestamp_text(current.observed_at),
        "window_kind": current.window_kind,
        "limit_id": current.limit_id,
        "plan_type": current.plan_type,
        "used_percent": current.used_percent,
        "remaining_percent": current.remaining_percent,
        "fact_basis": {
            "used_percent": "upstream_observed",
            "remaining_percent": "deterministic_complement",
        },
        "duration_minutes": current.duration_minutes,
        "resets_at": current.resets_at,
        "model": current.model,
        "service_tier": current.service_tier,
        "provenance": current.provenance,
        "validation_warnings": list(current.validation_warnings),
        "grade": interval.grade,
        "basis": (
            "adjacent_compatible_observations"
            if interval.grade == "deterministic"
            else "exact_observation"
        ),
        "source_generation": generation,
        "delta_used_percent": interval.delta_used_percent,
        "elapsed_hours": interval.elapsed_hours,
        "percentage_points_per_hour": interval.percentage_points_per_hour,
        "local_tokens_per_percentage_point": (
            interval.local_tokens_per_percentage_point
        ),
        "local_calls_per_percentage_point": (
            interval.local_calls_per_percentage_point
        ),
        "local_turns_per_percentage_point": (
            interval.local_turns_per_percentage_point
        ),
        "local_usage": {
            **asdict(usage),
            "total_tokens": usage.total_tokens,
        },
        "estimated_cost_usd": estimate.estimated_cost_usd,
        "estimated_credits": estimate.estimated_credits,
        "pricing_coverage": {
            "rated_tokens": estimate.rated_tokens,
            "total_tokens": estimate.total_tokens,
            "coverage_percent": estimate.coverage_percent,
            "unrated_models": list(estimate.unrated_models),
            "provenance": estimate.provenance,
        },
        "limitations": limitations,
    }
    return payload


def _observation(row: sqlite3.Row) -> AllowanceObservation:
    return AllowanceObservation(
        allowance_observation_id=str(row["allowance_observation_id"]),
        observed_at=_timestamp(row["observed_at"]),
        window_kind=str(row["window_kind"]),
        limit_id=row["limit_id"],
        plan_type=row["plan_type"],
        used_percent=float(row["used_percent"]),
        duration_minutes=row["duration_minutes"],
        resets_at=row["resets_at"],
        model=row["model"],
        service_tier=row["service_tier"],
        provenance=str(row["provenance"]),
        validation_warnings=_warnings(row["validation_warnings"]),
    )


def _previous_observation(
    row: sqlite3.Row,
    current: AllowanceObservation,
) -> AllowanceObservation | None:
    identifier = row["previous_observation_id"]
    if identifier is None:
        return None
    return AllowanceObservation(
        allowance_observation_id=str(identifier),
        observed_at=_timestamp(row["previous_observed_at"]),
        window_kind=current.window_kind,
        limit_id=current.limit_id,
        plan_type=current.plan_type,
        used_percent=float(row["previous_used_percent"]),
        duration_minutes=row["previous_duration_minutes"],
        resets_at=row["previous_resets_at"],
        model=row["previous_model"],
        service_tier=row["previous_service_tier"],
        provenance=str(row["previous_provenance"]),
        validation_warnings=_warnings(row["previous_validation_warnings"]),
    )


def _local_usage(
    connection: sqlite3.Connection,
    *,
    generation: int,
    previous: AllowanceObservation | None,
    current: AllowanceObservation,
) -> dict[str, LocalUsage]:
    if previous is None:
        return {}
    rows = connection.execute(
        _LOCAL_USAGE_SQL,
        (
            generation,
            _timestamp_text(previous.observed_at),
            _timestamp_text(current.observed_at),
        ),
    )
    return {
        str(row["model"]): LocalUsage(
            uncached_input_tokens=int(row["uncached_input_tokens"] or 0),
            cached_input_tokens=int(row["cached_input_tokens"] or 0),
            reasoning_tokens=int(row["reasoning_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            calls=int(row["calls"] or 0),
            turns=int(row["turns"] or 0),
        )
        for row in rows
    }
def _coverage(
    intervals: list[dict[str, Any]],
    configured: bool,
) -> dict[str, Any]:
    total_tokens = sum(
        int(item["pricing_coverage"]["total_tokens"]) for item in intervals
    )
    rated_tokens = sum(
        int(item["pricing_coverage"]["rated_tokens"]) for item in intervals
    )
    return {
        "generation_bound": True,
        "raw_content": False,
        "observations": {
            "basis": "upstream_reported",
            "observed_count": len(intervals),
            "missing_count": 0,
            "coverage_percent": 100.0,
        },
        "ratios": {
            "basis": "deterministic_adjacent_observations",
            "calculated_count": sum(
                item["grade"] == "deterministic" for item in intervals
            ),
            "total_count": len(intervals),
        },
        "pricing": {
            "basis": "source_stamped_local_rate_card",
            "configured": configured,
            "rated_tokens": rated_tokens,
            "total_tokens": total_tokens,
            "coverage_percent": (
                100.0 if total_tokens == 0 else 100.0 * rated_tokens / total_tokens
            ),
        },
    }


def _warnings(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, str):
        return ()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return ("invalid_validation_warnings",)
    if not isinstance(value, list):
        return ("invalid_validation_warnings",)
    return tuple(str(item) for item in value if isinstance(item, str))


def _timestamp(raw: Any) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("allowance observation timestamp is invalid")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("allowance observation timestamp is invalid") from exc
    if value.tzinfo is None:
        raise ValueError("allowance observation timestamp lacks timezone")
    return value


def _timestamp_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _encode_cursor(
    *,
    generation: int,
    publication_id: str,
    offset: int,
) -> str:
    payload = json.dumps(
        {"g": generation, "o": offset, "p": publication_id, "v": 1},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(
    cursor: str | None,
    *,
    generation: int,
    publication_id: str,
) -> int:
    if cursor is None:
        return 0
    try:
        encoded = cursor.encode()
        padding = b"=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
        if (
            payload["g"] != generation
            or payload["p"] != publication_id
            or payload["v"] != 1
        ):
            raise ValueError
        offset = int(payload["o"])
        if offset < 0 or offset > MAX_ALLOWANCE_OFFSET:
            raise ValueError
        return offset
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError(
            "allowance cursor does not match analytical publication"
        ) from exc
