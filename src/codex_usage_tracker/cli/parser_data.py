"""Compatibility alias for CLI data parser helpers."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("codex_usage_tracker.interfaces.cli.parser_data")
