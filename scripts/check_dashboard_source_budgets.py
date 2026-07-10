#!/usr/bin/env python3
"""Enforce ratcheted size budgets for the React dashboard source tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import NamedTuple


class BudgetGroup(NamedTuple):
    name: str
    suffixes: tuple[str, ...]
    max_physical: int
    max_nonblank: int
    tests_only: bool | None = None


GROUPS = (
    BudgetGroup("source", (".ts", ".tsx"), 500, 400, False),
    BudgetGroup("tests", (".test.ts", ".test.tsx"), 600, 500, True),
    BudgetGroup("styles", (".css", ".scss"), 400, 300),
)
BASELINE_VERSION = 1
DEFAULT_BASELINE = Path(".agent-maintainer/dashboard-source-baseline.json")


def _is_test(path: Path) -> bool:
    return path.name.endswith((".test.ts", ".test.tsx"))


def _matches(path: Path, group: BudgetGroup) -> bool:
    if not path.name.endswith(group.suffixes):
        return False
    if group.tests_only is None:
        return True
    return _is_test(path) is group.tests_only


def _line_counts(path: Path) -> tuple[int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return len(lines), sum(bool(line.strip()) for line in lines)


def _current_exceptions(root: Path) -> dict[str, dict[str, int | str]]:
    source_root = root / "frontend" / "dashboard" / "src"
    exceptions: dict[str, dict[str, int | str]] = {}
    for path in sorted(source_root.rglob("*")):
        if not path.is_file():
            continue
        for group in GROUPS:
            if not _matches(path, group):
                continue
            physical, nonblank = _line_counts(path)
            if physical > group.max_physical or nonblank > group.max_nonblank:
                exceptions[path.relative_to(root).as_posix()] = {
                    "group": group.name,
                    "physical": physical,
                    "nonblank": nonblank,
                }
            break
    return exceptions


def _write_baseline(path: Path, exceptions: dict[str, dict[str, int | str]]) -> None:
    payload = {"version": BASELINE_VERSION, "exceptions": exceptions}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_baseline(path: Path) -> dict[str, dict[str, int | str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != BASELINE_VERSION:
        raise ValueError(f"unsupported baseline version in {path}")
    exceptions = payload.get("exceptions")
    if not isinstance(exceptions, dict):
        raise ValueError(f"invalid exceptions map in {path}")
    return exceptions


def _compare(
    baseline: dict[str, dict[str, int | str]],
    current: dict[str, dict[str, int | str]],
) -> list[str]:
    errors: list[str] = []
    for path, counts in current.items():
        allowed = baseline.get(path)
        if allowed is None:
            errors.append(f"new oversized {counts['group']} file: {path}")
            continue
        for metric in ("physical", "nonblank"):
            if int(counts[metric]) > int(allowed[metric]):
                errors.append(
                    f"{path} {metric} lines grew from {allowed[metric]} to {counts[metric]}"
                )
            elif int(counts[metric]) < int(allowed[metric]):
                errors.append(
                    f"{path} {metric} lines fell from {allowed[metric]} to {counts[metric]}; "
                    "refresh the baseline to lock in the improvement"
                )
    for path in sorted(set(baseline) - set(current)):
        errors.append(f"stale oversized-file exception: {path}; refresh the baseline")
    return errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--write-baseline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = args.root.resolve()
    baseline_path = args.baseline
    if not baseline_path.is_absolute():
        baseline_path = root / baseline_path
    current = _current_exceptions(root)
    if args.write_baseline:
        _write_baseline(baseline_path, current)
        print(f"Wrote {len(current)} dashboard source exceptions to {baseline_path}")
        return 0
    try:
        baseline = _load_baseline(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Dashboard source budget baseline error: {exc}")
        return 2
    errors = _compare(baseline, current)
    if errors:
        print("Dashboard source budget failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Dashboard source budget passed ({len(current)} ratcheted exceptions).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
