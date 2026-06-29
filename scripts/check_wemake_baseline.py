#!/usr/bin/env python3
"""Run the current narrow wemake baseline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_LINE_LENGTH = "100"
BASELINE_FILES = (
    "src/codex_usage_tracker/__main__.py",
    "src/codex_usage_tracker/diagnostic_snapshot_constants.py",
    "src/codex_usage_tracker/diagnostics_types.py",
    "src/codex_usage_tracker/paths.py",
    "src/codex_usage_tracker/server_routes.py",
    "src/codex_usage_tracker/store_usage_timing.py",
    "src/codex_usage_tracker/usage_drain_boundary_scopes.py",
)


def main() -> int:
    """Run flake8 with wemake enabled on files that already pass."""
    command = [
        sys.executable,
        "-m",
        "flake8",
        f"--max-line-length={MAX_LINE_LENGTH}",
        *BASELINE_FILES,
    ]
    return subprocess.call(command, cwd=REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
