"""Compatibility facade for ``codex_usage_tracker.server``."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_API_MODULE = "codex_usage_tracker.server.api"
_COMPAT_MODULES = {
    "server_context": "codex_usage_tracker.server.context",
    "server_usage_refresh": "codex_usage_tracker.server.usage_refresh",
    "server_utils": "codex_usage_tracker.server.utils",
}


def __getattr__(name: str) -> Any:
    if name in _COMPAT_MODULES:
        return import_module(_COMPAT_MODULES[name])
    module = import_module(_API_MODULE)
    try:
        return getattr(module, name)
    except AttributeError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
