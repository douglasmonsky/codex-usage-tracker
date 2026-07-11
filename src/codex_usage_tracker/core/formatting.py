"""Human-readable report formatting."""

from __future__ import annotations

from typing import Any, cast


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
        lines.append(_formatted_call_line(index, row))
    return "\n".join(lines)


def _formatted_call_line(index: int, row: dict[str, Any]) -> str:
    return (
        f"{index}. {row.get('event_timestamp') or 'Unknown time'} | "
        f"{_call_thread_label(row)} | {row.get('model') or 'unknown'} "
        f"({row.get('effort') or 'unknown'}) | "
        f"last call {_fmt_int(row.get('total_tokens'))} tokens | "
        f"cache {_fmt_pct(row.get('cache_ratio'))} | "
        f"context {_fmt_pct(row.get('context_window_percent'))}"
        f"{_call_suffixes(row)}"
    )


def _call_thread_label(row: dict[str, Any]) -> object:
    return (
        row.get("thread_name")
        or row.get("parent_thread_name")
        or row.get("resolved_parent_thread_name")
        or row.get("session_id")
        or "Unknown"
    )


def _call_suffixes(row: dict[str, Any]) -> str:
    return (
        f"{_cost_suffix(row, prefix=' | estimated cost ')}"
        f"{_call_flags_suffix(row)}"
        f"{_call_action_suffix(row)}"
    )


def _call_flags_suffix(row: dict[str, Any]) -> str:
    flags = row.get("efficiency_flags") or []
    if not flags:
        return ""
    return f" | flags: {', '.join(flags)}"


def _call_action_suffix(row: dict[str, Any]) -> str:
    action = row.get("recommended_action")
    if not action:
        return ""
    return f" | action: {action}"


def format_recommendations(payload: dict[str, Any]) -> str:
    rows = _formatted_recommendation_rows(payload)
    if not rows:
        return "No aggregate recommendations are currently flagged."

    lines = ["Codex usage recommendations", ""]
    _append_formatted_recommendation_threads(lines, payload.get("threads"))
    lines.append("Top calls:")
    for index, row in enumerate(rows, 1):
        lines.append(_formatted_recommendation_call(index, row))
    return "\n".join(lines)


def _formatted_recommendation_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows")
    return cast(list[dict[str, Any]], rows) if isinstance(rows, list) else []


def _append_formatted_recommendation_threads(lines: list[str], threads: object) -> None:
    if not isinstance(threads, list) or not threads:
        return
    lines.append("Top threads:")
    for thread in cast(list[dict[str, Any]], threads[:5]):
        lines.append(_formatted_recommendation_thread(thread))
    lines.append("")


def _formatted_recommendation_thread(thread: dict[str, Any]) -> str:
    return (
        f"- {thread.get('thread') or 'Unknown thread'}: "
        f"score {_fmt_decimal(thread.get('recommendation_score'))}, "
        f"{_fmt_int(thread.get('call_count'))} calls, "
        f"{_fmt_int(thread.get('total_tokens'))} tokens"
    )


def _formatted_recommendation_call(index: int, row: dict[str, Any]) -> str:
    primary = _formatted_primary_recommendation(row)
    return (
        f"{index}. {_formatted_recommendation_thread_label(row)} | {row.get('model') or 'unknown'} "
        f"({row.get('effort') or 'unknown'}) | "
        f"score {_fmt_decimal(row.get('recommendation_score'))} | "
        f"{primary.get('title') or row.get('primary_signal') or 'Recommendation'}: "
        f"{row.get('recommended_action') or primary.get('action') or 'Review aggregate usage.'}"
    )


def _formatted_primary_recommendation(row: dict[str, Any]) -> dict[str, Any]:
    primary = row.get("primary_recommendation") or {}
    return primary if isinstance(primary, dict) else {}


def _formatted_recommendation_thread_label(row: dict[str, Any]) -> object:
    return (
        row.get("thread_attachment_label")
        or row.get("thread_name")
        or row.get("parent_thread_name")
        or row.get("session_id")
        or "Unknown"
    )


def format_doctor(report: dict[str, Any]) -> str:
    lines = [
        f"Codex Usage Tracker doctor: {str(report.get('status', 'unknown')).upper()}",
        f"Failures: {report.get('failures', 0)} | warnings: {report.get('warnings', 0)}",
        "",
    ]
    lines.extend(_doctor_environment_lines(report.get("environment")))
    lines.extend(_doctor_check_lines(report.get("checks", [])))
    lines.extend(_doctor_suggestion_lines(report.get("repair_suggestions")))
    return "\n".join(lines)


def _doctor_environment_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines = ["Environment:"]
    for formatter in (
        _doctor_package_lines,
        _doctor_python_lines,
        _doctor_path_lines,
        _doctor_log_lines,
        _doctor_asset_lines,
    ):
        lines.extend(formatter(value))
    lines.append("")
    return lines


def _doctor_package_lines(environment: dict[str, Any]) -> list[str]:
    package = environment.get("package")
    if not isinstance(package, dict):
        return []
    return [f"Package: {package.get('name', 'unknown')} {package.get('version', 'unknown')}"]


def _doctor_python_lines(environment: dict[str, Any]) -> list[str]:
    python = environment.get("python")
    if not isinstance(python, dict):
        return []
    return [
        f"Python: {python.get('version', 'unknown')} ({python.get('implementation', 'unknown')})"
    ]


def _doctor_path_lines(environment: dict[str, Any]) -> list[str]:
    paths = environment.get("paths")
    if not isinstance(paths, dict):
        return []
    return [
        f"Codex home: {paths.get('codex_home', 'unknown')}",
        f"Database: {paths.get('db_path', 'unknown')}",
        f"Dashboard: {paths.get('dashboard_path', 'unknown')}",
    ]


def _doctor_log_lines(environment: dict[str, Any]) -> list[str]:
    codex_logs = environment.get("codex_logs")
    if not isinstance(codex_logs, dict):
        return []
    sessions_status = "found" if codex_logs.get("sessions_dir_exists") else "missing"
    return [f"Codex logs: {sessions_status}, {_fmt_int(codex_logs.get('jsonl_files'))} JSONL files"]


def _doctor_asset_lines(environment: dict[str, Any]) -> list[str]:
    assets = environment.get("dashboard_assets")
    if not isinstance(assets, dict):
        return []
    asset_status = "available" if assets.get("available") else "missing"
    missing = assets.get("missing")
    suffix = f" ({len(missing)} missing)" if isinstance(missing, list) and missing else ""
    return [f"Dashboard assets: {asset_status}{suffix}"]


def _doctor_check_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for check in value:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status", "unknown")).upper()
        lines.append(f"- [{status}] {check.get('name')}: {check.get('detail')}")
        remediation = check.get("remediation")
        if remediation:
            lines.append(f"  Next: {remediation}")
    return lines


def _doctor_suggestion_lines(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return []
    return ["", "Repair suggestions:", *(f"- {suggestion}" for suggestion in value)]


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
            f"- {model}: {status}; {_fmt_int(row.get('total_tokens'))} tokens{_cost_suffix(row)}"
        )
    return "\n".join(lines)


def format_source_coverage(report: dict[str, Any], limit: int = 20) -> str:
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        return "No source provenance records found. Run refresh_usage_index first."

    lines = [
        "Codex source coverage",
        "",
        f"Source records: {_fmt_int(report.get('source_record_count'))} across "
        f"{_fmt_int(report.get('source_file_count'))} source files",
        f"Parser versions: {_fmt_int(report.get('parser_version_count'))}",
        f"Warning records: {_fmt_int(report.get('warning_record_count'))}",
        "",
    ]
    for row in rows[:limit]:
        lines.append(
            f"- {row.get('raw_shape_label') or 'unknown'} via "
            f"{row.get('parser_adapter') or 'unknown'} "
            f"{row.get('parser_version') or 'unknown'}: "
            f"{_fmt_int(row.get('record_count'))} records, "
            f"{_fmt_int(row.get('source_file_count'))} files, "
            f"{_fmt_int(row.get('warning_record_count'))} warning records"
        )
    return "\n".join(lines)


def _fmt_int(value: object) -> str:
    if not isinstance(value, int | float | str):
        return "0"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def _fmt_pct(value: object) -> str:
    if not isinstance(value, int | float | str):
        return "0.0%"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _fmt_money(value: object) -> str:
    if not isinstance(value, int | float | str):
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return "$0.00"
    if amount < 0.01:
        return f"${amount:.4f}"
    return f"${amount:.2f}"


def _fmt_decimal(value: object) -> str:
    if not isinstance(value, int | float | str):
        return "0.0"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "0.0"


def _cost_suffix(row: dict[str, Any], prefix: str = ", estimated cost ") -> str:
    if row.get("estimated_cost_usd") is None:
        return ""
    marker = "*" if row.get("pricing_estimated") else ""
    return f"{prefix}{_fmt_money(row.get('estimated_cost_usd'))}{marker}"
