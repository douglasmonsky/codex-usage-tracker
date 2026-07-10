"""Small coercion helpers for nullable SQLite result values."""

from __future__ import annotations

from typing import Any


def row_int(row: Any, field: str) -> int:
    """Return a nullable numeric row value as an integer."""

    return int(row[field] or 0)


def row_float(row: Any, field: str) -> float:
    """Return a nullable numeric row value as a float."""

    return float(row[field] or 0.0)
