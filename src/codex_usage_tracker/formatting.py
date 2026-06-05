"""Human-readable report formatting."""

from __future__ import annotations

from typing import Any


def format_summary(rows: list[dict[str, Any]], group_by: str) -> str:
    if not rows:
        return "No Codex usage records found. Run refresh_usage_index first."

    lines = [f"Codex usage summary by {group_by}", ""]
    for row in rows:
        label = row.get("group_key") or "Unknown"
        total = _fmt_int(row.get("total_tokens"))
        calls = _fmt_int(row.get("model_calls"))
        sessions = _fmt_int(row.get("sessions"))
        cached = _fmt_int(row.get("cached_input_tokens"))
        uncached = _fmt_int(row.get("uncached_input_tokens"))
        output = _fmt_int(row.get("output_tokens"))
        reasoning = _fmt_int(row.get("reasoning_output_tokens"))
        cache_ratio = _fmt_pct(row.get("avg_cache_ratio"))
        cost = _cost_suffix(row)
        lines.append(
            f"- {label}: {total} total tokens across {calls} model calls "
            f"({sessions} sessions, {cached} cached input, {uncached} uncached input, "
            f"{output} output, {reasoning} reasoning output, avg cache {cache_ratio}{cost})"
        )
    return "\n".join(lines)


def format_session(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No usage records found for that session."

    first = rows[0]
    thread = (
        first.get("thread_name")
        or first.get("parent_thread_name")
        or first.get("resolved_parent_thread_name")
        or first.get("session_id")
    )
    lines = [
        f"Codex session usage: {thread}",
        f"Session: {first.get('session_id')}",
        "",
    ]
    for index, row in enumerate(rows, 1):
        label = row.get("event_timestamp") or f"call {index}"
        lines.append(
            f"{index}. {label} | {row.get('model') or 'unknown'} "
            f"({row.get('effort') or 'unknown'}) | "
            f"last call {_fmt_int(row.get('total_tokens'))} tokens | "
            f"cumulative {_fmt_int(row.get('cumulative_total_tokens'))} tokens | "
            f"cache {_fmt_pct(row.get('cache_ratio'))} | "
            f"context {_fmt_pct(row.get('context_window_percent'))}"
        )
    return "\n".join(lines)


def format_calls(rows: list[dict[str, Any]], title: str = "Most expensive Codex calls") -> str:
    if not rows:
        return "No Codex usage records found. Run refresh_usage_index first."

    lines = [title, ""]
    for index, row in enumerate(rows, 1):
        thread = (
            row.get("thread_name")
            or row.get("parent_thread_name")
            or row.get("resolved_parent_thread_name")
            or row.get("session_id")
            or "Unknown"
        )
        flags = row.get("efficiency_flags") or []
        flag_suffix = f" | flags: {', '.join(flags)}" if flags else ""
        cost = _cost_suffix(row, prefix=" | estimated cost ")
        lines.append(
            f"{index}. {row.get('event_timestamp') or 'Unknown time'} | "
            f"{thread} | {row.get('model') or 'unknown'} "
            f"({row.get('effort') or 'unknown'}) | "
            f"last call {_fmt_int(row.get('total_tokens'))} tokens | "
            f"cache {_fmt_pct(row.get('cache_ratio'))} | "
            f"context {_fmt_pct(row.get('context_window_percent'))}"
            f"{cost}{flag_suffix}"
        )
    return "\n".join(lines)


def format_doctor(report: dict[str, Any]) -> str:
    lines = [
        f"Codex Usage Tracker doctor: {str(report.get('status', 'unknown')).upper()}",
        f"Failures: {report.get('failures', 0)} | warnings: {report.get('warnings', 0)}",
        "",
    ]
    for check in report.get("checks", []):
        status = str(check.get("status", "unknown")).upper()
        lines.append(f"- [{status}] {check.get('name')}: {check.get('detail')}")
        remediation = check.get("remediation")
        if remediation:
            lines.append(f"  Next: {remediation}")
    suggestions = report.get("repair_suggestions")
    if isinstance(suggestions, list) and suggestions:
        lines.extend(["", "Repair suggestions:"])
        for suggestion in suggestions:
            lines.append(f"- {suggestion}")
    return "\n".join(lines)


def format_pricing_coverage(report: dict[str, Any], limit: int = 20) -> str:
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        return "No Codex usage records found. Run refresh_usage_index first."

    lines = [
        "Codex pricing coverage",
        "",
        f"Models: {_fmt_int(report.get('model_count'))} "
        f"({_fmt_int(report.get('priced_model_count'))} priced, "
        f"{_fmt_int(report.get('unpriced_model_count'))} unpriced)",
        f"Token coverage: {_fmt_pct(report.get('priced_token_ratio'))} priced "
        f"({_fmt_int(report.get('priced_tokens'))} of {_fmt_int(report.get('total_tokens'))} tokens)",
        f"Estimated total cost: {_fmt_money(report.get('estimated_cost_usd'))}",
        "",
    ]
    for row in rows[:limit]:
        model = row.get("model") or "Unknown"
        status = "unpriced"
        if row.get("pricing_estimated"):
            status = f"estimated as {row.get('priced_as')}"
        elif row.get("priced_as"):
            status = f"priced as {row.get('priced_as')}"
        lines.append(
            f"- {model}: {status}; {_fmt_int(row.get('total_tokens'))} tokens"
            f"{_cost_suffix(row)}"
        )
    return "\n".join(lines)


def _fmt_int(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _fmt_money(value: object) -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return "$0.00"
    if amount < 0.01:
        return f"${amount:.4f}"
    return f"${amount:.2f}"


def _cost_suffix(row: dict[str, Any], prefix: str = ", estimated cost ") -> str:
    if row.get("estimated_cost_usd") is None:
        return ""
    marker = "*" if row.get("pricing_estimated") else ""
    return f"{prefix}{_fmt_money(row.get('estimated_cost_usd'))}{marker}"
