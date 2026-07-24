"""Compatibility alias for ingestion fact classifiers."""

from __future__ import annotations

import sys
from importlib import import_module

sys.modules[__name__] = import_module("codex_usage_tracker.ingest.fact_classifiers")
