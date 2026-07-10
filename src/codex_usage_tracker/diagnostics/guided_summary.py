"""Plain-language aggregate diagnostics for usage drivers."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.diagnostics.guided_signals import (
    TOP_ROW_LIMIT,
    _base_signals,
    _drivers,
    _float,
    _int,
    _label,
    _ratio,
    _snapshot_signals,
    _source_log_count,
    _thread_label,
)
from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_GUIDED_SUMMARY_SCHEMA,
    DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    history_scope as history_scope_label,
)
from codex_usage_tracker.diagnostics.snapshot_payloads import (
    ready_payload,
    snapshot_metadata,
    utc_now,
)
from codex_usage_tracker.store.api import (
    query_dashboard_events,
    upsert_diagnostic_snapshot,
)


def refresh_guided_summary_snapshot(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Recompute and persist the guided aggregate diagnostic summary."""

    history_scope = history_scope_label(include_archived)
    computed_at = utc_now()
    rows = query_dashboard_events(
        db_path=db_path,
        limit=0,
        include_archived=include_archived,
    )
    analysis = build_guided_summary(rows, db_path=db_path, history_scope=history_scope)
    snapshot = snapshot_metadata(
        computed_at=computed_at,
        history_scope=history_scope,
        source_logs_scanned=analysis["summary"]["source_logs_scanned"],
        usage_rows_scanned=analysis["summary"]["usage_rows"],
    )
    payload = ready_payload(
        schema=DIAGNOSTIC_GUIDED_SUMMARY_SCHEMA,
        section=DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
        snapshot=snapshot,
        refreshed=True,
        summary=analysis["summary"],
        drivers=analysis["drivers"],
        top_threads=analysis["top_threads"],
        top_models=analysis["top_models"],
        top_efforts=analysis["top_efforts"],
        token_mix=analysis["token_mix"],
        signals=analysis["signals"],
    )
    payload["notes"].append(
        "Guided summary uses aggregate metadata only and ranks likely review areas; "
        "it does not prove causation."
    )
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
        history_scope=history_scope,
        payload=payload,
        computed_at=computed_at,
        source_logs_scanned=analysis["summary"]["source_logs_scanned"],
        usage_rows_scanned=analysis["summary"]["usage_rows"],
        raw_content_included=False,
    )
    return payload


def build_guided_summary(
    rows: list[dict[str, Any]],
    *,
    db_path: Path = DEFAULT_DB_PATH,
    history_scope: str,
) -> dict[str, Any]:
    """Build a guided usage-driver summary from aggregate dashboard rows."""

    totals = _aggregate_rows(rows)
    top_threads = _top_groups(rows, _thread_label)
    top_models = _top_groups(rows, lambda row: _label(row.get("model"), "unknown model"))
    top_efforts = _top_groups(rows, lambda row: _label(row.get("effort"), "unknown effort"))
    token_mix = _token_mix(totals)
    signals = _base_signals(
        rows=rows,
        totals=totals,
        top_threads=top_threads,
        top_models=top_models,
        token_mix=token_mix,
    )
    signals.extend(_snapshot_signals(db_path=db_path, history_scope=history_scope))
    drivers = _drivers(
        top_threads=top_threads,
        top_models=top_models,
        top_efforts=top_efforts,
        token_mix=token_mix,
        signals=signals,
    )
    summary = {
        **totals,
        "thread_count": len({row["label"] for row in top_threads}),
        "model_count": len({row["label"] for row in top_models}),
        "effort_count": len({row["label"] for row in top_efforts}),
        "source_logs_scanned": _source_log_count(rows),
        "signal_count": len(signals),
        "driver_count": len(drivers),
    }
    return {
        "summary": summary,
        "drivers": drivers,
        "top_threads": top_threads[:TOP_ROW_LIMIT],
        "top_models": top_models[:TOP_ROW_LIMIT],
        "top_efforts": top_efforts[:TOP_ROW_LIMIT],
        "token_mix": token_mix,
        "signals": signals,
    }


def _aggregate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, int | float] = {
        "usage_rows": len(rows),
        "total_tokens": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "uncached_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
        "subagent_rows": 0,
        "high_context_rows": 0,
    }
    for row in rows:
        for key in (
            "total_tokens",
            "input_tokens",
            "cached_input_tokens",
            "uncached_input_tokens",
            "output_tokens",
            "reasoning_output_tokens",
        ):
            totals[key] += _int(row.get(key))
        if row.get("thread_source") == "subagent" or row.get("parent_session_id"):
            totals["subagent_rows"] += 1
        if _float(row.get("context_window_percent")) >= 0.6:
            totals["high_context_rows"] += 1
    totals["cache_ratio"] = _ratio(
        totals["cached_input_tokens"],
        totals["input_tokens"],
    )
    totals["reasoning_output_ratio"] = _ratio(
        totals["reasoning_output_tokens"],
        totals["output_tokens"],
    )
    totals["subagent_row_share"] = _ratio(totals["subagent_rows"], totals["usage_rows"])
    totals["high_context_row_share"] = _ratio(
        totals["high_context_rows"],
        totals["usage_rows"],
    )
    return totals


def _top_groups(
    rows: list[dict[str, Any]],
    label_for_row: Any,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = defaultdict(_empty_group)
    total_tokens = sum(_int(row.get("total_tokens")) for row in rows)
    for row in rows:
        label = label_for_row(row)
        group = groups[label]
        group["label"] = label
        group["calls"] += 1
        group["total_tokens"] += _int(row.get("total_tokens"))
        group["uncached_input_tokens"] += _int(row.get("uncached_input_tokens"))
        group["cached_input_tokens"] += _int(row.get("cached_input_tokens"))
        group["input_tokens"] += _int(row.get("input_tokens"))
        group["output_tokens"] += _int(row.get("output_tokens"))
        group["reasoning_output_tokens"] += _int(row.get("reasoning_output_tokens"))
    ordered = sorted(
        groups.values(),
        key=lambda group: (group["total_tokens"], group["uncached_input_tokens"]),
        reverse=True,
    )
    for group in ordered:
        group["share_of_total_tokens"] = _ratio(group["total_tokens"], total_tokens)
        group["cache_ratio"] = _ratio(
            group["cached_input_tokens"],
            group["input_tokens"],
        )
        group["reasoning_output_ratio"] = _ratio(
            group["reasoning_output_tokens"],
            group["output_tokens"],
        )
    return ordered


def _empty_group() -> dict[str, Any]:
    return {
        "label": "",
        "calls": 0,
        "total_tokens": 0,
        "uncached_input_tokens": 0,
        "cached_input_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }


def _token_mix(totals: dict[str, Any]) -> dict[str, Any]:
    total_tokens = _int(totals.get("total_tokens"))
    return {
        "uncached_input_share": _ratio(totals.get("uncached_input_tokens"), total_tokens),
        "cached_input_share": _ratio(totals.get("cached_input_tokens"), total_tokens),
        "output_share": _ratio(totals.get("output_tokens"), total_tokens),
        "reasoning_output_share": _ratio(
            totals.get("reasoning_output_tokens"),
            total_tokens,
        ),
        "cache_ratio": _float(totals.get("cache_ratio")),
        "reasoning_output_ratio": _float(totals.get("reasoning_output_ratio")),
    }
