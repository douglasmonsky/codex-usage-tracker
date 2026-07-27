from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.plugin_manifest import (
    bundle_digest,
    canonical_manifest,
    install_bundle,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_bundle_digest_and_manifest_are_deterministic() -> None:
    first = bundle_digest(_REPO_ROOT)
    second = bundle_digest(_REPO_ROOT)
    manifest = canonical_manifest(_REPO_ROOT)

    assert first == second
    assert first.startswith("sha256:")
    assert manifest["bundle"]["digest"] == first
    assert manifest["bundle"]["publishable"] is True


def test_same_version_cache_install_replaces_exact_bundle(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shutil.copytree(
        _REPO_ROOT / ".codex-plugin",
        source / ".codex-plugin",
    )
    shutil.copyfile(_REPO_ROOT / ".mcp.json", source / ".mcp.json")
    (source / "skills" / "usage-kernel").mkdir(parents=True)
    skill = source / "skills" / "usage-kernel" / "SKILL.md"
    shutil.copyfile(
        _REPO_ROOT / "skills" / "usage-kernel" / "SKILL.md",
        skill,
    )
    first_digest = bundle_digest(source)
    manifest_path = source / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bundle"]["digest"] = first_digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    installed = install_bundle(source, tmp_path / "cache")
    stale = installed / "stale.txt"
    stale.write_text("must disappear", encoding="utf-8")
    skill.write_text(skill.read_text(encoding="utf-8") + "\nUpdated.\n", encoding="utf-8")
    second_digest = bundle_digest(source)
    manifest["bundle"]["digest"] = second_digest
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    replaced = install_bundle(source, tmp_path / "cache")

    assert replaced == installed
    assert not stale.exists()
    assert bundle_digest(replaced) == second_digest
    assert second_digest != first_digest


def test_manifest_wiring_is_covered_by_bundle_attestation(tmp_path: Path) -> None:
    source = tmp_path / "source"
    shutil.copytree(_REPO_ROOT / ".codex-plugin", source / ".codex-plugin")
    shutil.copyfile(_REPO_ROOT / ".mcp.json", source / ".mcp.json")
    shutil.copytree(_REPO_ROOT / "skills", source / "skills")
    manifest_path = source / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mcpServers"] = "./wrong.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="mcpServers"):
        bundle_digest(source)
