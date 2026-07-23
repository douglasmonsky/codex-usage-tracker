"""Compatibility wrapper for ``codex_usage_tracker.cli.mcp_server``."""

from __future__ import annotations

import sys
from importlib import import_module

_impl = import_module("codex_usage_tracker.cli.mcp_server")

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
