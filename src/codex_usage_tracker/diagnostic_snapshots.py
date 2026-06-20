"""On-demand aggregate diagnostic report snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_usage_tracker.paths import DEFAULT_DB_PATH
from codex_usage_tracker.store import (
    connect,
    query_diagnostic_snapshot,
    upsert_diagnostic_snapshot,
)
from codex_usage_tracker.store_schema import init_db

DIAGNOSTIC_OVERVIEW_SCHEMA = "codex-usage-tracker-diagnostic-overview-v1"
DIAGNOSTIC_OVERVIEW_SECTION = "overview"
DIAGNOSTIC_HISTORY_ACTIVE = "active"
DIAGNOSTIC_HISTORY_ALL = "all"
DIAGNOSTIC_OVERVIEW_NOTES = [
    "Diagnostic snapshots are recomputed only by explicit diagnostic refresh.",
    "Overview totals use persisted aggregate usage rows and do not include raw context.",
]


@dataclass(frozen=True)
class DiagnosticSnapshotReport:
    """Resolved diagnostic snapshot payload for CLI and API surfaces."""

    payload: dict[str, Any]

    def render(self) -> str:
        if self.payload.get("status") != "ready":
            return "No diagnostic overview snapshot. Run diagnostics overview --refresh first."
        snapshot = self.payload.get("snapshot") or {}
        overview = self.payload.get("overview") or {}
        return "\n".join(
            [
                "Diagnostic overview snapshot",
                f"Computed: {snapshot.get('computed_at')}",
                f"History scope: {snapshot.get('history_scope')}",
                f"Usage rows: {_int_text(overview.get('usage_rows'))}",
                f"Total tokens: {_int_text(overview.get('total_tokens'))}",
                f"Cached input: {_int_text(overview.get('cached_input_tokens'))}",
                f"Uncached input: {_int_text(overview.get('uncached_input_tokens'))}",
                f"Cache ratio: {_pct_text(overview.get('cache_ratio'))}",
            ]
        )


def build_diagnostic_overview_report(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
    refresh: bool = False,
) -> DiagnosticSnapshotReport:
    """Return the latest overview snapshot, optionally recomputing it first."""

    if refresh:
        return DiagnosticSnapshotReport(
            refresh_diagnostic_overview_snapshot(
                db_path=db_path,
                include_archived=include_archived,
            )
        )
    return DiagnosticSnapshotReport(
        diagnostic_overview_payload(
            db_path=db_path,
            include_archived=include_archived,
        )
    )


def refresh_diagnostic_overview_snapshot(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Recompute and persist the aggregate overview diagnostic snapshot."""

    history_scope = _history_scope(include_archived)
    computed_at = _utc_now()
    overview, source_logs_scanned = _compute_overview(
        db_path=db_path,
        include_archived=include_archived,
    )
    snapshot = _snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
    )
    payload = _ready_payload(snapshot=snapshot, overview=overview, refreshed=True)
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=source_logs_scanned,
        usage_rows_scanned=int(overview["usage_rows"]),
        raw_content_included=False,
    )
    return payload


def diagnostic_overview_payload(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the latest persisted overview snapshot without recomputing it."""

    history_scope = _history_scope(include_archived)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope=history_scope,
    )
    if stored is None:
        return _missing_payload(history_scope=history_scope)
    payload = dict(stored["payload"])
    payload["status"] = "ready"
    payload["refreshed"] = False
    payload["snapshot"] = _snapshot_metadata(
        computed_at=str(stored["computed_at"]),
        history_scope=str(stored["history_scope"]),
        source_logs_scanned=int(stored["source_logs_scanned"]),
        usage_rows_scanned=int(stored["usage_rows_scanned"]),
    )
    payload["raw_context_included"] = bool(stored["raw_content_included"])
    return payload


def _compute_overview(
    *,
    db_path: Path,
    include_archived: bool,
) -> tuple[dict[str, Any], int]:
    usage_where = "" if include_archived else "WHERE is_archived = 0"
    source_where = "" if include_archived else "WHERE is_archived = 0"
    with connect(db_path) as conn:
        init_db(conn)
        usage_row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS usage_rows,
                COUNT(DISTINCT session_id) AS session_count,
                COUNT(DISTINCT thread_key) AS thread_count,
                COUNT(DISTINCT model) AS model_count,
                MIN(event_timestamp) AS first_event_timestamp,
                MAX(event_timestamp) AS latest_event_timestamp,
                coalesce(SUM(input_tokens), 0) AS input_tokens,
                coalesce(SUM(cached_input_tokens), 0) AS cached_input_tokens,
                coalesce(SUM(uncached_input_tokens), 0) AS uncached_input_tokens,
                coalesce(SUM(output_tokens), 0) AS output_tokens,
                coalesce(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
                coalesce(SUM(total_tokens), 0) AS total_tokens,
                AVG(cache_ratio) AS avg_cache_ratio
            FROM usage_events
            {usage_where}
            """
        ).fetchone()
        facts_row = conn.execute(
            f"""
            SELECT COUNT(*) AS diagnostic_fact_rows
            FROM call_diagnostic_facts AS facts
            JOIN usage_events ON usage_events.record_id = facts.record_id
            {usage_where}
            """
        ).fetchone()
        source_row = conn.execute(
            f"SELECT COUNT(*) AS source_logs_scanned FROM source_files {source_where}"
        ).fetchone()
    input_tokens = _int_value(usage_row["input_tokens"])
    cached_input_tokens = _int_value(usage_row["cached_input_tokens"])
    overview = {
        "usage_rows": _int_value(usage_row["usage_rows"]),
        "session_count": _int_value(usage_row["session_count"]),
        "thread_count": _int_value(usage_row["thread_count"]),
        "model_count": _int_value(usage_row["model_count"]),
        "first_event_timestamp": usage_row["first_event_timestamp"],
        "latest_event_timestamp": usage_row["latest_event_timestamp"],
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": _int_value(usage_row["uncached_input_tokens"]),
        "output_tokens": _int_value(usage_row["output_tokens"]),
        "reasoning_output_tokens": _int_value(usage_row["reasoning_output_tokens"]),
        "total_tokens": _int_value(usage_row["total_tokens"]),
        "cache_ratio": cached_input_tokens / input_tokens if input_tokens else 0.0,
        "avg_call_cache_ratio": float(usage_row["avg_cache_ratio"] or 0),
        "diagnostic_fact_rows": _int_value(facts_row["diagnostic_fact_rows"]),
    }
    return overview, _int_value(source_row["source_logs_scanned"])


def _ready_payload(
    *,
    snapshot: dict[str, Any],
    overview: dict[str, Any],
    refreshed: bool,
) -> dict[str, Any]:
    return {
        "schema": DIAGNOSTIC_OVERVIEW_SCHEMA,
        "section": DIAGNOSTIC_OVERVIEW_SECTION,
        "status": "ready",
        "refreshed": refreshed,
        "raw_context_included": False,
        "snapshot": snapshot,
        "overview": overview,
        "notes": list(DIAGNOSTIC_OVERVIEW_NOTES),
    }


def _missing_payload(*, history_scope: str) -> dict[str, Any]:
    return {
        "schema": DIAGNOSTIC_OVERVIEW_SCHEMA,
        "section": DIAGNOSTIC_OVERVIEW_SECTION,
        "status": "missing",
        "refreshed": False,
        "raw_context_included": False,
        "snapshot": None,
        "overview": None,
        "history_scope": history_scope,
        "notes": list(DIAGNOSTIC_OVERVIEW_NOTES),
    }


def _snapshot_metadata(
    *,
    computed_at: str,
    history_scope: str,
    source_logs_scanned: int,
    usage_rows_scanned: int,
) -> dict[str, Any]:
    return {
        "computed_at": computed_at,
        "history_scope": history_scope,
        "source_logs_scanned": int(source_logs_scanned),
        "usage_rows_scanned": int(usage_rows_scanned),
        "raw_content_included": False,
    }


def _history_scope(include_archived: bool) -> str:
    return DIAGNOSTIC_HISTORY_ALL if include_archived else DIAGNOSTIC_HISTORY_ACTIVE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _int_value(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value:
        return int(value)
    return 0


def _int_text(value: object) -> str:
    return f"{_int_value(value):,}"


def _pct_text(value: object) -> str:
    try:
        ratio = float(value) if isinstance(value, int | float | str) and value != "" else 0.0
    except (TypeError, ValueError):
        ratio = 0.0
    return f"{ratio:.1%}"
