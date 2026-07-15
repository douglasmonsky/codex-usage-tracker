"""Persisted read-through analysis for allowance change detection."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from codex_usage_tracker.allowance_intelligence.capacity_history import (
    load_capacity_cycles,
)
from codex_usage_tracker.allowance_intelligence.change_detection import (
    MULTI_DETECTOR_VERSION,
    detect_cycle_changes,
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
    parameters: dict[str, int | float] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a semantically cached, aggregate-only change analysis."""
    request = allowance_analysis_request(
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
        return _with_usage_quality(connection, cached)
    source_revision = request["source_revision"]
    data_as_of = request["data_as_of"]
    resolved_rate_revision = request["rate_card_revision"]
    resolved = request["parameters"]
    snapshot_id = request["snapshot_id"]
    generated_at = (now or datetime.now(timezone.utc)).isoformat()

    cycles = load_capacity_cycles(
        connection,
        source_revision=source_revision,
        archive_scope=archive_scope,
        window_kind=window_kind,
        cohort_key=cohort_key,
    )
    detected = detect_cycle_changes(
        cycles,
        semantic_key=snapshot_id,
        min_cycles_per_regime=int(resolved["min_cycles_per_regime"]),
        permutation_count=int(resolved["permutation_count"]),
        familywise_alpha=float(resolved["familywise_alpha"]),
    )
    payload = {
        "schema": ANALYSIS_SCHEMA,
        "snapshot_id": snapshot_id,
        "source_revision": source_revision,
        "model_version": MULTI_DETECTOR_VERSION,
        "rate_card_revision": resolved_rate_revision,
        "generated_at": generated_at,
        "data_as_of": data_as_of,
        "archive_scope": archive_scope,
        "window_kind": window_kind,
        "cohort_key": cohort_key,
        "forecast_horizon": forecast_horizon,
        "parameters": resolved,
        "quality": _usage_quality(connection),
        **detected,
    }
    cache_model_version = (
        f"{MULTI_DETECTOR_VERSION}:{resolved_rate_revision}:"
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
    parameters: dict[str, int | float] | None = None,
) -> dict[str, Any] | None:
    """Read a compatible persisted result without starting analysis work."""
    request = allowance_analysis_request(
        connection,
        rate_card_revision=rate_card_revision,
        archive_scope=archive_scope,
        window_kind=window_kind,
        cohort_key=cohort_key,
        forecast_horizon=forecast_horizon,
        parameters=parameters,
    )
    payload = _read_snapshot(connection, request["snapshot_id"])
    return _with_usage_quality(connection, payload) if payload is not None else None


def allowance_analysis_request(
    connection: sqlite3.Connection,
    *,
    rate_card_revision: str | None,
    archive_scope: str,
    window_kind: str,
    cohort_key: str,
    forecast_horizon: int,
    parameters: dict[str, int | float] | None,
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
    provided = dict(parameters or {})
    unknown = set(provided) - {
        "min_cycles_per_regime",
        "min_cycles_per_side",
        "permutation_count",
        "familywise_alpha",
    }
    if unknown:
        raise ValueError(f"unknown analysis parameters: {', '.join(sorted(unknown))}")
    if "min_cycles_per_regime" in provided and "min_cycles_per_side" in provided:
        raise ValueError(
            "use min_cycles_per_regime; do not provide the compatibility alias together"
        )
    if "min_cycles_per_side" in provided:
        provided["min_cycles_per_regime"] = provided.pop("min_cycles_per_side")
    resolved = {
        "min_cycles_per_regime": 4,
        "permutation_count": 1_999,
        "familywise_alpha": 0.05,
        **provided,
    }
    minimum = resolved["min_cycles_per_regime"]
    permutations = resolved["permutation_count"]
    alpha = resolved["familywise_alpha"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 2:
        raise ValueError("min_cycles_per_regime must be an integer of at least 2")
    if (
        isinstance(permutations, bool)
        or not isinstance(permutations, int)
        or not 99 <= permutations <= 100_000
    ):
        raise ValueError("permutation_count must be an integer between 99 and 100000")
    if (
        isinstance(alpha, bool)
        or not isinstance(alpha, int | float)
        or not 0 < float(alpha) < 1
    ):
        raise ValueError("familywise_alpha must be between 0 and 1")
    semantic = {
        "source_revision": source_revision,
        "model_version": MULTI_DETECTOR_VERSION,
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
        "model_version": MULTI_DETECTOR_VERSION,
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


def _with_usage_quality(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
) -> dict[str, Any]:
    result = dict(payload)
    result["quality"] = {**dict(result.get("quality") or {}), **_usage_quality(connection)}
    return result


def _usage_quality(connection: sqlite3.Connection) -> dict[str, Any]:
    try:
        copied_rows = int(
            connection.execute("SELECT count(*) FROM usage_events WHERE is_duplicate=1").fetchone()[0]
        )
    except sqlite3.OperationalError:
        copied_rows = 0
    return {"canonical": True, "copied_rows_excluded": copied_rows}
