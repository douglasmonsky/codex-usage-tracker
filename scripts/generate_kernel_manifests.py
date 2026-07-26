#!/usr/bin/env python3
"""Validate and transition the frozen Product Kernel Reset manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RETIRED_PATH = _REPO_ROOT / "config" / "kernel-retired-surfaces-v1.json"
_DISPOSITION_PATH = _REPO_ROOT / "config" / "kernel-code-disposition-v1.json"
_K1_MERGE = "d8da9bccdb6674e7dca4c0872c36a1346949dc13"


def build_retired_surface_manifest() -> dict[str, Any]:
    """Return the immutable K1 public-surface inventory."""

    return _load(_RETIRED_PATH)


def build_code_disposition_manifest() -> dict[str, Any]:
    """Return the K1 path inventory with its current transition states."""

    return _load(_DISPOSITION_PATH)


def apply_quarantine_transition() -> None:
    """Advance every K1 non-keep path to the K1A removed state."""

    payload = build_code_disposition_manifest()
    payload["source_ref"] = _K1_MERGE
    payload["quarantine_base"] = _K1_MERGE
    for entry in payload["entries"]:
        if entry["disposition"] != "keep":
            entry["status"] = "removed"
    _DISPOSITION_PATH.write_text(_compact_manifest(payload), encoding="utf-8")


def manifest_failures(
    disposition: dict[str, Any] | None = None,
) -> list[str]:
    """Return deterministic failures for both frozen inventories."""

    current = disposition or build_code_disposition_manifest()
    base = _load_from_git(_K1_MERGE, "config/kernel-code-disposition-v1.json")
    retired = build_retired_surface_manifest()
    failures: list[str] = []

    paths = [entry["path"] for entry in current["entries"]]
    if len(paths) != len(set(paths)):
        failures.append("code disposition contains duplicate paths")
    base_paths = _git_lines("ls-tree", "-r", "--name-only", _K1_MERGE)
    if sorted(paths) != base_paths:
        failures.append("code disposition paths differ from the merged K1 tree")
    digest = hashlib.sha256(
        ("\n".join(sorted(paths)) + "\n").encode("utf-8")
    ).hexdigest()
    if current["resolver_input_sha256"] != digest:
        failures.append("code disposition resolver hash does not match frozen paths")
    if current.get("quarantine_base") != _K1_MERGE:
        failures.append("code disposition does not name the merged K1 quarantine base")
    if current.get("source_ref") != _K1_MERGE:
        failures.append("code disposition source ref is not the merged K1 commit")

    base_by_path = {entry["path"]: entry for entry in base["entries"]}
    for entry in current["entries"]:
        path = entry["path"]
        base_entry = base_by_path.get(path)
        if base_entry is None:
            continue
        immutable = {key: value for key, value in entry.items() if key != "status"}
        base_immutable = {
            key: value for key, value in base_entry.items() if key != "status"
        }
        if immutable != base_immutable:
            failures.append(f"{path}: immutable K1 disposition decision changed")

    surface_keys = [
        (entry["surface_type"], entry["public_name"])
        for entry in retired["entries"]
    ]
    if len(surface_keys) != len(set(surface_keys)):
        failures.append("retired-surface inventory contains duplicate names")

    for path, payload in (
        (_DISPOSITION_PATH, current),
        (_RETIRED_PATH, retired),
    ):
        if disposition is None and path.read_text(
            encoding="utf-8"
        ) != _compact_manifest(payload):
            failures.append(f"{path.name} is not canonical")
    return failures


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_from_git(ref: str, path: str) -> dict[str, Any]:
    payload = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "show", f"{ref}:{path}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(payload)


def _git_lines(*args: str) -> list[str]:
    return subprocess.run(
        ["git", "-C", str(_REPO_ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()


def _compact_manifest(payload: dict[str, Any]) -> str:
    entries = payload["entries"]
    header = {key: value for key, value in payload.items() if key != "entries"}
    lines = ["{"]
    for key, value in header.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value, sort_keys=True)},")
    lines.append('  "entries": [')
    for index, entry in enumerate(entries):
        suffix = "," if index + 1 < len(entries) else ""
        lines.append(
            f"    {json.dumps(entry, sort_keys=True, separators=(',', ':'))}{suffix}"
        )
    lines.extend(["  ]", "}", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply-quarantine", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.apply_quarantine:
        apply_quarantine_transition()
    failures = manifest_failures()
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    if args.check:
        print("Kernel manifests are canonical and frozen.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
