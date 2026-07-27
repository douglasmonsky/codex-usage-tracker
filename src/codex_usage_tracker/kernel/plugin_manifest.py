"""Deterministic integration plugin identity and atomic cache installation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

BUNDLE_SCHEMA = "codex-usage-tracker.kernel-plugin-bundle.v1"
_PLUGIN_PATH = Path(".codex-plugin/plugin.json")
_MCP_PATH = Path(".mcp.json")
_SKILL_PATH = Path("skills/usage-kernel/SKILL.md")
BUNDLE_PATHS = (_MCP_PATH, _SKILL_PATH)
_EXPECTED_MANIFEST = {
    "name": "codex-usage-tracker",
    "version": "0.26.0-dev.0",
    "mcpServers": "./.mcp.json",
    "skills": "./skills/",
}


def bundle_digest(root: Path) -> str:
    digest = hashlib.sha256()
    manifest = _validated_manifest(root)
    manifest["bundle"] = dict(manifest["bundle"])
    manifest["bundle"].pop("digest", None)
    manifest_payload = json.dumps(
        manifest,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    inputs = (
        (_PLUGIN_PATH, manifest_payload),
        *(
            (relative, _bundle_bytes(root, relative))
            for relative in BUNDLE_PATHS
        ),
    )
    for relative, payload in inputs:
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _bundle_bytes(root: Path, relative: Path) -> bytes:
    target = root.resolve() / relative
    if not target.is_file() or target.is_symlink():
        raise ValueError(f"plugin bundle path is invalid: {relative}")
    return target.read_bytes()


def canonical_manifest(root: Path) -> dict[str, Any]:
    payload = _validated_manifest(root)
    bundle = payload["bundle"]
    bundle["digest"] = bundle_digest(root)
    return payload


def write_manifest(root: Path) -> Path:
    path = root.resolve() / _PLUGIN_PATH
    payload = canonical_manifest(root)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def install_bundle(source: Path, cache_root: Path) -> Path:
    root = source.resolve()
    declared = _validated_manifest(root)["bundle"].get("digest")
    computed = bundle_digest(root)
    if declared != computed:
        raise ValueError("plugin bundle digest does not match")
    payload = canonical_manifest(root)
    name = _safe_segment(payload.get("name"), "plugin name")
    version = _safe_segment(payload.get("version"), "plugin version")
    parent = cache_root.resolve() / name
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / version
    staging = Path(tempfile.mkdtemp(prefix=f".{version}.install-", dir=parent))
    backup = parent / f".{version}.backup"
    try:
        _copy_bundle(root, staging)
        if target.exists():
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(target, backup)
        os.replace(staging, target)
        if backup.exists():
            shutil.rmtree(backup)
    except BaseException:
        if not target.exists() and backup.exists():
            os.replace(backup, target)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def _copy_bundle(source: Path, destination: Path) -> None:
    for relative in (*BUNDLE_PATHS, _PLUGIN_PATH):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
    installed = json.loads((destination / _PLUGIN_PATH).read_text(encoding="utf-8"))
    expected = installed["bundle"]["digest"]
    if expected != bundle_digest(destination):
        raise ValueError("installed plugin bundle digest does not match")


def _safe_segment(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise ValueError(f"{label} is invalid")
    return value


def _validated_manifest(root: Path) -> dict[str, Any]:
    path = root.resolve() / _PLUGIN_PATH
    if not path.is_file() or path.is_symlink():
        raise ValueError("plugin manifest path is invalid")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("plugin bundle manifest is invalid")
    for key, expected in _EXPECTED_MANIFEST.items():
        if payload.get(key) != expected:
            raise ValueError(f"plugin manifest {key} is invalid")
    bundle = payload.get("bundle")
    if (
        not isinstance(bundle, dict)
        or bundle.get("schema") != BUNDLE_SCHEMA
        or bundle.get("runtime_version") != "0.26.0.dev0"
        or bundle.get("publishable") is not False
    ):
        raise ValueError("plugin bundle manifest is invalid")
    return payload


def main() -> None:
    write_manifest(Path.cwd())


if __name__ == "__main__":
    main()
