"""Compatibility alias for localized CLI interface help."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("codex_usage_tracker.interfaces.cli.help_i18n")
