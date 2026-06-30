"""Plain-language aggregate diagnostics for usage drivers."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_DB_PATH
from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_GUIDED_SUMMARY_SCHEMA,
    DIAGNOSTIC_GUIDED_SUMMARY_SECTION,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
    DIAGNOSTIC_USAGE_DRAIN_SECTION,
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
    query_diagnostic_snapshot,
    upsert_diagnostic_snapshot,
)

TOP_ROW_LIMIT = 5


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
    totals = {
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


def _base_signals(
    *,
    rows: list[dict[str, Any]],
    totals: dict[str, Any],
    top_threads: list[dict[str, Any]],
    top_models: list[dict[str, Any]],
    token_mix: dict[str, Any],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if top_threads:
        top = top_threads[0]
        signals.append(
            _signal(
                "thread-concentration",
                "Thread concentration",
                f"{top['label']} accounts for {_percent(top['share_of_total_tokens'])} of tokens.",
                "Review whether this thread still needs its full accumulated context.",
                severity="high" if top["share_of_total_tokens"] >= 0.35 else "review",
                metric=top["share_of_total_tokens"],
            )
        )
    if top_models:
        top = top_models[0]
        signals.append(
            _signal(
                "model-mix",
                "Model mix",
                f"{top['label']} is the largest model bucket by tokens.",
                "Compare model choice against the actual work in the heaviest calls.",
                metric=top["share_of_total_tokens"],
            )
        )
    if _float(totals.get("cache_ratio")) < 0.35 and _int(totals.get("input_tokens")):
        signals.append(
            _signal(
                "low-cache-reuse",
                "Low cache reuse",
                f"Overall cache ratio is {_percent(totals['cache_ratio'])}.",
                "Look for repeated file reads, cold resumes, or broad context restatement.",
                severity="medium",
                metric=totals["cache_ratio"],
            )
        )
    if token_mix["reasoning_output_share"] >= 0.25:
        signals.append(
            _signal(
                "reasoning-heavy",
                "Reasoning-heavy output",
                f"Reasoning output is {_percent(token_mix['reasoning_output_share'])} of total tokens.",
                "Check whether effort settings match task complexity.",
                severity="medium",
                metric=token_mix["reasoning_output_share"],
            )
        )
    if _float(totals.get("subagent_row_share")) > 0:
        signals.append(
            _signal(
                "subagent-share",
                "Subagent activity",
                f"Subagent-linked rows are {_percent(totals['subagent_row_share'])} of calls.",
                "Separate direct work from delegated work when explaining usage growth.",
                metric=totals["subagent_row_share"],
            )
        )
    if rows and _float(totals.get("high_context_row_share")) >= 0.1:
        signals.append(
            _signal(
                "context-pressure",
                "Context pressure",
                f"{_percent(totals['high_context_row_share'])} of calls used at least 60% of context.",
                "Inspect high-context threads before deciding whether to split work.",
                severity="medium",
                metric=totals["high_context_row_share"],
            )
        )
    return signals


def _snapshot_signals(*, db_path: Path, history_scope: str) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    commands = _stored_payload(
        db_path=db_path,
        section=DIAGNOSTIC_COMMANDS_SECTION,
        history_scope=history_scope,
    )
    if commands:
        summary = commands.get("summary") or {}
        shell_calls = _int(summary.get("shell_function_calls"))
        command_roots = _int(summary.get("command_root_count"))
        if shell_calls:
            signals.append(
                _signal(
                    "command-activity",
                    "Command activity",
                    f"{shell_calls:,} shell calls across {command_roots:,} command roots.",
                    "Use the Commands panel to see whether repetitive tooling is driving usage.",
                    metric=shell_calls,
                )
            )
    tool_output = _stored_payload(
        db_path=db_path,
        section=DIAGNOSTIC_TOOL_OUTPUT_SECTION,
        history_scope=history_scope,
    )
    if tool_output:
        summary = tool_output.get("summary") or {}
        output_tokens = _int(summary.get("original_token_sum"))
        if output_tokens:
            signals.append(
                _signal(
                    "tool-output-tokens",
                    "Tool output volume",
                    f"Terminal/tool outputs account for {output_tokens:,} parsed output tokens.",
                    "Trim noisy command output or use narrower file reads where possible.",
                    metric=output_tokens,
                )
            )
    usage_drain = _stored_payload(
        db_path=db_path,
        section=DIAGNOSTIC_USAGE_DRAIN_SECTION,
        history_scope=history_scope,
    )
    if usage_drain:
        summary = usage_drain.get("summary") or {}
        positive_spans = _int(summary.get("positive_usage_spans"))
        if positive_spans:
            signals.append(
                _signal(
                    "usage-drain-spans",
                    "Visible usage movement",
                    f"{positive_spans:,} positive visible-usage spans are available.",
                    "Use Usage Drain for allowance projection caveats and trend context.",
                    metric=positive_spans,
                )
            )
    return signals


def _drivers(
    *,
    top_threads: list[dict[str, Any]],
    top_models: list[dict[str, Any]],
    top_efforts: list[dict[str, Any]],
    token_mix: dict[str, Any],
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    drivers: list[dict[str, Any]] = []
    if top_threads:
        top = top_threads[0]
        drivers.append(
            _driver(
                "top-thread",
                "Top thread by tokens",
                top["label"],
                top["total_tokens"],
                top["share_of_total_tokens"],
                "Compare this thread against newer handoff threads before changing workflow.",
            )
        )
    if top_models:
        top = top_models[0]
        drivers.append(
            _driver(
                "top-model",
                "Top model bucket",
                top["label"],
                top["total_tokens"],
                top["share_of_total_tokens"],
                "Check whether the model choice matches the work that dominates usage.",
            )
        )
    if top_efforts:
        top = top_efforts[0]
        drivers.append(
            _driver(
                "top-effort",
                "Top effort bucket",
                top["label"],
                top["total_tokens"],
                top["share_of_total_tokens"],
                "Compare effort mix with task complexity before changing defaults.",
            )
        )
    drivers.append(
        _driver(
            "uncached-input-share",
            "Uncached input share",
            "uncached input",
            token_mix["uncached_input_share"],
            token_mix["uncached_input_share"],
            "High uncached share is a good place to look for repeated context loading.",
            value_kind="ratio",
        )
    )
    if signals:
        signal = signals[0]
        drivers.append(
            {
                "key": "top-signal",
                "title": "Top review signal",
                "label": signal["title"],
                "value": signal["metric"],
                "value_kind": "number",
                "share": None,
                "action": signal["action"],
            }
        )
    return drivers[:TOP_ROW_LIMIT]


def _driver(
    key: str,
    title: str,
    label: str,
    value: int | float,
    share: float,
    action: str,
    *,
    value_kind: str = "tokens",
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "label": label,
        "value": value,
        "value_kind": value_kind,
        "share": share,
        "action": action,
    }


def _signal(
    key: str,
    title: str,
    finding: str,
    action: str,
    *,
    severity: str = "review",
    metric: int | float | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "severity": severity,
        "finding": finding,
        "action": action,
        "metric": metric,
    }


def _stored_payload(*, db_path: Path, section: str, history_scope: str) -> dict[str, Any] | None:
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=section,
        history_scope=history_scope,
    )
    if not stored:
        return None
    payload = stored.get("payload") or {}
    if payload.get("status") != "ready":
        return None
    return payload


def _thread_label(row: dict[str, Any]) -> str:
    return _label(
        row.get("thread_name")
        or row.get("resolved_parent_thread_name")
        or row.get("parent_thread_name")
        or row.get("thread_key")
        or row.get("session_id"),
        "unknown thread",
    )


def _source_log_count(rows: list[dict[str, Any]]) -> int:
    return len({str(row.get("source_file")) for row in rows if row.get("source_file")})


def _label(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _ratio(numerator: object, denominator: object) -> float:
    denom = _float(denominator)
    if denom <= 0:
        return 0.0
    return _float(numerator) / denom


def _percent(value: object) -> str:
    return f"{_float(value):.1%}"
