"""Progress contract for persisted diagnostic snapshot refreshes."""

from __future__ import annotations

from collections.abc import Callable

DiagnosticProgressCallback = Callable[..., None]


def emit_refresh_progress(
    callback: DiagnosticProgressCallback | None,
    completed_units: int,
    current_unit: str,
) -> None:
    """Publish one completed unit in the fixed 10-snapshot refresh plan."""
    if callback is None:
        return
    callback(
        stage="persisting_snapshots",
        completed_units=completed_units,
        total_units=10,
        current_unit=current_unit,
    )
