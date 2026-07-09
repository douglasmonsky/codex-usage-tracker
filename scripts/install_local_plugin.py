#!/usr/bin/env python3
"""Compatibility wrapper for registering the local Codex plugin."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from codex_usage_tracker.cli.plugin_installer import install_plugin  # noqa: E402
from codex_usage_tracker.core.paths import (  # noqa: E402
    DEFAULT_MARKETPLACE_PATH,
    DEFAULT_PLUGIN_LINK,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Register Codex Usage Tracker as a local Codex plugin. "
            "Prefer `codex-usage-tracker install-plugin` for installed packages."
        )
    )
    parser.add_argument("--plugin-dir", type=Path, default=DEFAULT_PLUGIN_LINK)
    parser.add_argument("--marketplace", type=Path, default=DEFAULT_MARKETPLACE_PATH)
    parser.add_argument(
        "--python", type=Path, default=Path(sys.executable), dest="python_executable"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing generated plugin directory or source-checkout symlink.",
    )
    args = parser.parse_args()

    result = install_plugin(
        plugin_dir=args.plugin_dir,
        marketplace_path=args.marketplace,
        python_executable=args.python_executable,
        force=args.force,
    )
    replacement_note = " Replaced existing plugin path." if result.replaced_existing else ""
    print(f"Installed Codex Usage Tracker plugin at {result.plugin_dir}.{replacement_note}")
    print(f"MCP Python: {result.python_executable}")
    print(f"Updated marketplace: {result.marketplace_path}")
    print("Restart Codex to discover the plugin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
