"""Signals and drivers for guided aggregate diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from codex_usage_tracker.diagnostics.snapshot_constants import (
    DIAGNOSTIC_COMMANDS_SECTION,
    DIAGNOSTIC_TOOL_OUTPUT_SECTION,
    DIAGNOSTIC_USAGE_DRAIN_SECTION,
)
from codex_usage_tracker.store.api import query_diagnostic_snapshot

TOP_ROW_LIMIT = 5


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


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
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
