#!/usr/bin/env python3
"""Generate or verify deterministic K6 schemas and plugin identity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_usage_tracker.kernel.interfaces.schema_catalog import SCHEMAS
from codex_usage_tracker.kernel.plugin_manifest import canonical_manifest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_ROOT = (
    _REPO_ROOT
    / "src"
    / "codex_usage_tracker"
    / "kernel"
    / "interfaces"
    / "schemas"
)
_PLUGIN_PATH = _REPO_ROOT / ".codex-plugin" / "plugin.json"


def generated_assets() -> dict[Path, str]:
    assets = {
        _SCHEMA_ROOT / f"{name}.json": _compact(payload)
        for name, payload in SCHEMAS.items()
    }
    assets[_PLUGIN_PATH] = json.dumps(
        canonical_manifest(_REPO_ROOT),
        indent=2,
        sort_keys=True,
    ) + "\n"
    return assets


def asset_failures() -> list[str]:
    return [
        f"{path.relative_to(_REPO_ROOT)} is not canonical"
        for path, expected in generated_assets().items()
        if not path.is_file() or path.read_text(encoding="utf-8") != expected
    ]


def write_assets() -> None:
    for path, payload in generated_assets().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")


def _compact(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        failures = asset_failures()
        if failures:
            print("\n".join(failures))
            return 1
        print("Kernel interface assets are canonical.")
        return 0
    write_assets()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
