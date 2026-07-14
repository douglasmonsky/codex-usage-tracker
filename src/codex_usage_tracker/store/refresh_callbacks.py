"""Dependency-inversion callbacks for derived refresh stages."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

DerivedFactSyncCallback = Callable[
    [sqlite3.Connection, tuple[str, ...], frozenset[str], bool],
    None,
]
