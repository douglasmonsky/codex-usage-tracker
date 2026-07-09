"""Shared boundary diagnostic scope helpers."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

BOUNDARY_RISK_SCOPE_STARTS = MappingProxyType(
    {
        "all_after_first": 1,
        "all_after_10": 10,
        "time_ordered_holdout_20": 0.8,
        "latest_500": -500,
        "latest_100": -100,
    }
)


def boundary_scope_start_index(rows: list[dict[str, Any]], start: int | float) -> int:
    if not rows:
        return 0
    if isinstance(start, float):
        proportional_index = int(len(rows) * start)
        last_index = len(rows) - 1
        return max(1, min(last_index, proportional_index))
    if start < 0:
        return max(len(rows) + start, 1)
    return start
