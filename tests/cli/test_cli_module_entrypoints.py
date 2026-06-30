"""CLI module entrypoint compatibility tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.cli import main as cli_main


def test_console_script_target_is_callable() -> None:
    assert callable(cli_main)


def test_cli_package_module_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codex_usage_tracker.cli", "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )

    assert f"codex-usage-tracker {__version__}" in result.stdout


def _subprocess_env() -> dict[str, str]:
    repo_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    src = str(repo_root / "src")
    env["PYTHONPATH"] = src if not env.get("PYTHONPATH") else f"{src}{os.pathsep}{env['PYTHONPATH']}"
    return env
