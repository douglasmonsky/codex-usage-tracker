"""Privacy-safe timing helpers for local dashboard API responses."""

from __future__ import annotations


def server_timing_header(
    *,
    started_at: float | None,
    finished_at: float,
) -> str | None:
    """Return a Server-Timing value without query strings or request content."""
    if started_at is None:
        return None
    duration_ms = max(0.0, (finished_at - started_at) * 1_000)
    return f"app;dur={duration_ms:.3f}"
