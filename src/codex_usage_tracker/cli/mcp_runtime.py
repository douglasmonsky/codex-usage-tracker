"""Inert decorator compatibility for legacy MCP implementation modules."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

_Handler = TypeVar("_Handler", bound=Callable[..., object])


class _LegacyToolDecorator:
    """Preserve old decorators without creating an import-time tool registry."""

    def tool(self, *_args: object, **_kwargs: object) -> Callable[[_Handler], _Handler]:
        def preserve(handler: _Handler) -> _Handler:
            return handler

        return preserve


mcp = _LegacyToolDecorator()

__all__ = ["mcp"]
