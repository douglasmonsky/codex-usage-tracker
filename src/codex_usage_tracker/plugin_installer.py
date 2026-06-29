"""Compatibility module alias for ``codex_usage_tracker.cli.plugin_installer``."""

from __future__ import annotations

import sys
from importlib import import_module

_impl = import_module("codex_usage_tracker.cli.plugin_installer")
sys.modules[__name__] = _impl
