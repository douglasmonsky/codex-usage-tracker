"""Compatibility facade for ``codex_usage_tracker.parser``."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__: list[str] = []

_API_MODULE = "codex_usage_tracker.parser.api"


def __getattr__(name: str) -> Any:
    module = import_module(_API_MODULE)
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
