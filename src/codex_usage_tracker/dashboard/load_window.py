"""Dashboard data-window payload normalization."""

from __future__ import annotations


def dashboard_load_window_payload(
    value: str | None,
    *,
    since: str | None,
    limit: int | None,
    live: bool,
) -> dict[str, object]:
    """Return normalized current and default dashboard data windows."""

    if value in {"day", "week", "rows", "all"}:
        normalized = value
    elif since:
        normalized = "week"
    else:
        normalized = "all" if limit is None else "rows"
    return {
        "load_window": normalized,
        "default_load_window": "all" if live else normalized,
        "since": since,
    }
