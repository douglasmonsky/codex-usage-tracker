"""Explicit experiment and maintainer handlers for the developer MCP profile."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from importlib import import_module

DEVELOPER_TOOL_NAMES = (
    "usage_dogfood_start",
    "usage_dogfood_status",
    "usage_dogfood_result",
    "usage_visualization_suggest",
    "usage_visualization_render",
)

_MODULE_TOOL_NAMES = (
    (
        "codex_usage_tracker.cli.mcp_server",
        ("usage_dogfood_start", "usage_dogfood_status", "usage_dogfood_result"),
    ),
    (
        "codex_usage_tracker.cli.mcp_visualization",
        ("usage_visualization_suggest", "usage_visualization_render"),
    ),
)


@lru_cache(maxsize=1)
def developer_handlers() -> dict[str, Callable[..., object]]:
    """Resolve developer-only handlers without registering another server."""
    handlers: dict[str, Callable[..., object]] = {}
    for module_name, names in _MODULE_TOOL_NAMES:
        module = import_module(module_name)
        for name in names:
            handler = getattr(module, name, None)
            if not callable(handler):
                raise LookupError(f"missing developer handler: {name}")
            handlers[name] = handler
    if set(handlers) != set(DEVELOPER_TOOL_NAMES):
        raise LookupError("invalid developer handler catalog")
    return handlers


def developer_handler(name: str) -> Callable[..., object]:
    """Return one exact developer callable with its original signature."""
    try:
        return developer_handlers()[name]
    except KeyError as exc:
        raise LookupError(f"unknown developer handler: {name}") from exc
