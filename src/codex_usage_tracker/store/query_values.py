"""Typed value coercion for SQLite query result rows."""

from __future__ import annotations

from typing import Any


def row_int(row: Any, field: str) -> int:
    return int(row[field] or 0)


def row_float(row: Any, field: str) -> float:
    return float(row[field] or 0.0)
