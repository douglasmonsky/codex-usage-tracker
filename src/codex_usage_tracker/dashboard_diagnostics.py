"""Dashboard-facing diagnostic filters."""

from __future__ import annotations


_DASHBOARD_BENIGN_PARSER_DIAGNOSTICS = {
    "duplicate_cumulative_total",
}


def dashboard_parser_diagnostics(metadata: dict[str, str]) -> dict[str, int]:
    """Return parser diagnostics worth surfacing in the dashboard chrome.

    Duplicate cumulative totals are common in Codex logs when identical aggregate
    counters are emitted more than once. The parser keeps that count for doctor
    and inspect-log workflows, but it is not usually actionable enough to alarm
    dashboard users.
    """

    diagnostics: dict[str, int] = {}
    for key, value in metadata.items():
        if not key.startswith("parser_"):
            continue
        diagnostic_key = key.removeprefix("parser_")
        if diagnostic_key in _DASHBOARD_BENIGN_PARSER_DIAGNOSTICS:
            continue
        count = _safe_int(value)
        if count:
            diagnostics[diagnostic_key] = count
    return diagnostics


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
