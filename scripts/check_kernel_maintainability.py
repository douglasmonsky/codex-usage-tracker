#!/usr/bin/env python3
"""Enforce lean source-size and Xenon bounds on the replacement kernel."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def maintainability_failures(
    source_root: Path,
    *,
    max_physical: int = 600,
    max_source: int = 600,
) -> list[str]:
    """Return deterministic kernel-only maintainability failures."""

    python_files = sorted(source_root.rglob("*.py")) if source_root.is_dir() else []
    failures: list[str] = []
    for path in python_files:
        lines = path.read_text(encoding="utf-8").splitlines()
        physical = len(lines)
        source = sum(
            bool(line.strip()) and not line.lstrip().startswith("#")
            for line in lines
        )
        relative = path.relative_to(source_root)
        if physical > max_physical:
            failures.append(
                f"{relative}: physical lines {physical} exceed {max_physical}"
            )
        if source > max_source:
            failures.append(f"{relative}: source lines {source} exceed {max_source}")

    if python_files:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "xenon",
                "-b",
                "B",
                "-m",
                "B",
                "-a",
                "B",
                "--paths-in-front",
                *map(str, python_files),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            failures.extend(
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
            )
            failures.extend(
                line.strip()
                for line in result.stderr.splitlines()
                if line.strip()
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        type=Path,
        default=_REPO_ROOT / "src" / "codex_usage_tracker" / "kernel",
    )
    args = parser.parse_args()
    failures = maintainability_failures(args.source_root)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("Kernel maintainability budget passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
