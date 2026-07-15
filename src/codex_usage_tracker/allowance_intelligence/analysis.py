"""Persisted read-through analysis for allowance change detection."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from codex_usage_tracker.allowance_intelligence.change_detection import (
    DETECTOR_VERSION,
    detect_cycle_change,
)
from codex_usage_tracker.pricing.allowance_config import load_allowance_config

ANALYSIS_SCHEMA = "codex-usage-tracker-allowance-analysis-v2"


def build_allowance_analysis(
    connection: sqlite3.Connection,
    *,
    rate_card_revision: str | None = None,
    archive_scope: str = "active",
    window_kind: str = "weekly",
    cohort_key: str = "codex",
    forecast_horizon: int = 1,
    parameters: dict[str, int] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a semantically cached, aggregate-only change analysis."""
    request = _analysis_request(
        connection,
        rate_card_revision=rate_card_revision,
        archive_scope=archive_scope,
        window_kind=window_kind,
        cohort_key=cohort_key,
        forecast_horizon=forecast_horizon,
        parameters=parameters,
    )
    cached = _read_snapshot(connection, request["snapshot_id"])
    if cached is not None:
        return cached
    source_revision = request["source_revision"]
    data_as_of = request["data_as_of"]
    resolved_rate_revision = request["rate_card_revision"]
    resolved = request["parameters"]
    snapshot_id = request["snapshot_id"]
    generated_at = (now or datetime.now(timezone.utc)).isoformat()

    cycles = _analysis_cycles(
        connection,
        source_revision=source_revision,
        archive_scope=archive_scope,
        window_kind=window_kind,
        cohort_key=cohort_key,
    )
    detected = detect_cycle_change(
        cycles,
        semantic_key=snapshot_id,
        min_cycles_per_side=resolved["min_cycles_per_side"],
        permutation_count=resolved["permutation_count"],
    )
    payload = {
        "schema": ANALYSIS_SCHEMA,
        "snapshot_id": snapshot_id,
        "source_revision": source_revision,
        "model_version": DETECTOR_VERSION,
        "rate_card_revision": resolved_rate_revision,
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "archive_scope": archive_scope,
        "window_kind": window_kind,
        "cohort_key": cohort_key,
        "forecast_horizon": forecast_horizon,
        "parameters": resolved,
        **detected,
    }
    cache_model_version = (
        f"{DETECTOR_VERSION}:{resolved_rate_revision}:"
        f"{hashlib.sha256(json.dumps(resolved, sort_keys=True).encode()).hexdigest()[:16]}"
    )
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    connection.execute(
        """INSERT INTO allowance_analysis_snapshots
        (snapshot_id,source_revision,model_version,archive_scope,window_kind,
         cohort_key,forecast_horizon,status,result_json,created_at,completed_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            snapshot_id,
            source_revision,
            cache_model_version,
            archive_scope,
            window_kind,
            cohort_key,
            forecast_horizon,
            "completed",
            serialized,
            generated_at,
            generated_at,
        ),
    )
    return payload


def read_allowance_analysis(
    connection: sqlite3.Connection,
    *,
    rate_card_revision: str | None = None,
    archive_scope: str = "active",
    window_kind: str = "weekly",
    cohort_key: str = "codex",
    forecast_horizon: int = 1,
    parameters: dict[str, int] | None = None,
) -> dict[str, Any] | None:
    """Read a compatible persisted result without starting analysis work."""
    request = _analysis_request(
        connection,
        rate_card_revision=rate_card_revision,
        archive_scope=archive_scope,
        window_kind=window_kind,
        cohort_key=cohort_key,
        forecast_horizon=forecast_horizon,
        parameters=parameters,
    )
    return _read_snapshot(connection, request["snapshot_id"])


def _analysis_request(
    connection: sqlite3.Connection,
    *,
    rate_card_revision: str | None,
    archive_scope: str,
    window_kind: str,
    cohort_key: str,
    forecast_horizon: int,
    parameters: dict[str, int] | None,
) -> dict[str, Any]:
    if archive_scope not in {"active", "all"}:
        raise ValueError("archive_scope must be active or all")
    if window_kind != "weekly":
        raise ValueError("change analysis currently supports weekly windows only")
    if forecast_horizon < 1:
        raise ValueError("forecast_horizon must be positive")
    source = connection.execute(
        "SELECT source_revision, latest_observed_at FROM allowance_source_state WHERE state_id = 1"
    ).fetchone()
    source_revision = str(source[0]) if source else "missing"
    data_as_of = _normalized_time(source[1] if source else None)
    resolved_rate_revision = rate_card_revision or _rate_card_revision()
    if not resolved_rate_revision.strip():
        raise ValueError("rate_card_revision must not be empty")
    provided = parameters or {}
    unknown = set(provided) - {"min_cycles_per_side", "permutation_count"}
    if unknown:
        raise ValueError(f"unknown analysis parameters: {', '.join(sorted(unknown))}")
    resolved = {
        "min_cycles_per_side": 3,
        "permutation_count": 1_999,
        **provided,
    }
    minimum = resolved["min_cycles_per_side"]
    permutations = resolved["permutation_count"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError("min_cycles_per_side must be an integer of at least 2")
    if (
        isinstance(permutations, bool)
        or not isinstance(permutations, int)
        or not 99 <= permutations <= 100_000
    ):
        raise ValueError("permutation_count must be an integer between 99 and 100000")
    semantic = {
        "source_revision": source_revision,
        "model_version": DETECTOR_VERSION,
        "rate_card_revision": resolved_rate_revision,
        "archive_scope": archive_scope,
        "window_kind": window_kind,
        "cohort_key": cohort_key,
        "forecast_horizon": forecast_horizon,
        "parameters": resolved,
    }
    encoded = json.dumps(semantic, sort_keys=True, separators=(",", ":"))
    snapshot_id = hashlib.sha256(encoded.encode()).hexdigest()
    return {
        "snapshot_id": snapshot_id,
        "source_revision": source_revision,
        "rate_card_revision": resolved_rate_revision,
        "data_as_of": data_as_of,
        "parameters": resolved,
    }


def _read_snapshot(
    connection: sqlite3.Connection, snapshot_id: str
) -> dict[str, Any] | None:
    cached = connection.execute(
        "SELECT result_json FROM allowance_analysis_snapshots WHERE snapshot_id = ?",
        (snapshot_id,),
    ).fetchone()
    return dict(json.loads(str(cached[0]))) if cached and cached[0] else None


def _analysis_cycles(
    connection: sqlite3.Connection,
    *,
    source_revision: str,
    archive_scope: str,
    window_kind: str,
    cohort_key: str,
) -> list[dict[str, Any]]:
    archive = "" if archive_scope == "all" else "AND is_archived = 0"
    cycles = [
        dict(row)
        for row in connection.execute(
            f"""SELECT * FROM allowance_cycles
            WHERE source_revision = ? AND window_kind = ? AND cohort_key = ? {archive}
            ORDER BY last_observed_at, cycle_id""",
            (source_revision, window_kind, cohort_key),
        )
    ]
    ratios = {
        str(row["cycle_id"]): float(row["credits"]) / float(row["movement"])
        for row in connection.execute(
            f"""SELECT cycle_id, SUM(estimated_credits) AS credits,
            SUM(visible_percent_delta) AS movement
            FROM allowance_intervals
            WHERE source_revision = ? AND window_kind = ? AND cohort_key = ? {archive}
              AND eligible_for_change_detection = 1 AND point_kind = 'positive'
            GROUP BY cycle_id
            HAVING credits > 0 AND movement > 0""",
            (source_revision, window_kind, cohort_key),
        )
    }
    for cycle in cycles:
        cycle["credits_per_percent"] = ratios.get(str(cycle["cycle_id"]))
    return cycles


def _normalized_time(value: object) -> str:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc).isoformat()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).isoformat()


def _rate_card_revision() -> str:
    config = load_allowance_config()
    encoded = json.dumps(
        {
            "credit_rates": config.credit_rates,
            "aliases": config.aliases,
            "rate_metadata": config.rate_metadata,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()
