"""Allowance history and change-evidence diagnostics."""

from typing import Any

from codex_usage_tracker.allowance_intelligence.model import (
    EVIDENCE_GRADES,
    WINDOW_KIND_CHOICES,
    build_allowance_analysis,
)

__all__ = (
    "AllowanceReport",
    "EVIDENCE_GRADES",
    "WINDOW_KIND_CHOICES",
    "build_allowance_analysis",
    "build_allowance_diagnostics_report",
    "build_allowance_export_report",
    "build_allowance_history_report",
)


def __getattr__(name: str) -> Any:
    """Load report builders lazily to keep store materialization acyclic."""

    if name in {
        "AllowanceReport",
        "build_allowance_diagnostics_report",
        "build_allowance_export_report",
        "build_allowance_history_report",
    }:
        from codex_usage_tracker.allowance_intelligence import reports

        return getattr(reports, name)
    raise AttributeError(name)
