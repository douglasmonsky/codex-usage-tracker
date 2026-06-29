"""Run Codex Usage Tracker CLI with ``python -m codex_usage_tracker.cli``."""

from __future__ import annotations

import sys

from codex_usage_tracker.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
