"""Compatibility module alias for ``codex_usage_tracker.pricing.allowance``."""

from __future__ import annotations

import sys
from importlib import import_module

_impl = import_module("codex_usage_tracker.pricing.allowance")
sys.modules[__name__] = _impl
