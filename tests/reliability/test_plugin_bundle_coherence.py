from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from codex_usage_tracker import __version__
from codex_usage_tracker.application.status import plugin_bundle_status
from codex_usage_tracker.cli.plugin_installer import install_plugin
from codex_usage_tracker.core.plugin_identity import (
    PLUGIN_BUNDLE_SCHEMA,
    inspect_plugin_bundle,
    plugin_bundle_digest,
)
from codex_usage_tracker.diagnostics.api import run_doctor


def test_installer_records_one_bundle_identity_in_manifest_and_mcp_env(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"

    result = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=tmp_path / ".venv" / "bin" / "python",
        plugin_cache_root=tmp_path / "cache",
    )

    manifest = json.loads((plugin_dir / ".codex-plugin" / "plugin.json").read_text())
    mcp_server = json.loads((plugin_dir / ".mcp.json").read_text())["mcpServers"][
        "codex-usage-tracker"
    ]
    bundle = manifest["bundle"]

    assert manifest["version"] == __version__
    assert bundle == {
        "schema": PLUGIN_BUNDLE_SCHEMA,
        "digest": result.bundle_digest,
        "launcher_digest": bundle["launcher_digest"],
        "runtime_version": __version__,
    }
    assert result.bundle_digest.startswith("sha256:")
    assert bundle["launcher_digest"].startswith("sha256:")
    assert mcp_server["env"]["CODEX_USAGE_TRACKER_PLUGIN_VERSION"] == __version__
    assert (
        mcp_server["env"]["CODEX_USAGE_TRACKER_PLUGIN_BUNDLE_DIGEST"]
        == result.bundle_digest
    )
    assert result.cache_state == "absent"
    assert result.cache_invalidated is False


def test_bundle_identity_ignores_generated_python_bytecode(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    (plugin_dir / "assets").mkdir(parents=True)
    script_dir = plugin_dir / "skills" / "tracker" / "scripts"
    script_dir.mkdir(parents=True)
    (plugin_dir / "assets" / "icon.svg").write_text("<svg/>", encoding="utf-8")
    (script_dir / "run_mcp.py").write_text("print('synthetic')\n", encoding="utf-8")
    expected = plugin_bundle_digest(plugin_dir)
    cache_dir = script_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "run_mcp.cpython-314.pyc").write_bytes(b"synthetic bytecode")

    assert plugin_bundle_digest(plugin_dir) == expected


def test_installer_invalidates_only_stale_same_version_tracker_cache(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = tmp_path / "cache"
    marketplace = tmp_path / "marketplace.json"
    python = tmp_path / ".venv" / "bin" / "python"
    first = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=python,
        plugin_cache_root=cache_root,
    )
    cached = cache_root / __version__
    shutil.copytree(plugin_dir, cached)
    cached_skill = cached / "skills" / "codex-usage-api" / "SKILL.md"
    cached_skill.write_text(cached_skill.read_text() + "\nstale cache\n")

    second = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=python,
        plugin_cache_root=cache_root,
    )

    assert first.cache_invalidated is False
    assert second.cache_invalidated is True
    assert second.cache_state == "invalidated"
    assert not cached.exists()


def test_installer_preserves_coherent_same_version_cache(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = tmp_path / "cache"
    marketplace = tmp_path / "marketplace.json"
    python = tmp_path / ".venv" / "bin" / "python"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=python,
        plugin_cache_root=cache_root,
    )
    cached = cache_root / __version__
    shutil.copytree(plugin_dir, cached)

    result = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=python,
        plugin_cache_root=cache_root,
    )

    assert result.cache_invalidated is False
    assert result.cache_state == "coherent"
    assert cached.is_dir()


def test_legacy_manifest_still_detects_cached_launcher_drift(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = tmp_path / "cache"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=tmp_path / "first-venv" / "bin" / "python",
        plugin_cache_root=cache_root,
    )
    cached = cache_root / __version__
    shutil.copytree(plugin_dir, cached)
    for root in (plugin_dir, cached):
        manifest_path = root / ".codex-plugin" / "plugin.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["bundle"].pop("launcher_digest")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert (
        inspect_plugin_bundle(plugin_dir=plugin_dir, plugin_cache_root=cache_root)[
            "state"
        ]
        == "coherent"
    )
    cached_mcp = cached / ".mcp.json"
    cached_config = json.loads(cached_mcp.read_text(encoding="utf-8"))
    cached_config["mcpServers"]["codex-usage-tracker"]["command"] = "/stale/python"
    cached_mcp.write_text(json.dumps(cached_config), encoding="utf-8")

    assert (
        inspect_plugin_bundle(plugin_dir=plugin_dir, plugin_cache_root=cache_root)[
            "state"
        ]
        == "mismatch"
    )


def test_installer_invalidates_same_version_cache_for_changed_python(
    tmp_path: Path,
) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = tmp_path / "cache"
    marketplace = tmp_path / "marketplace.json"
    first_python = tmp_path / "first-venv" / "bin" / "python"
    second_python = tmp_path / "second-venv" / "bin" / "python"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=first_python,
        plugin_cache_root=cache_root,
    )
    cached = cache_root / __version__
    shutil.copytree(plugin_dir, cached)

    result = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=second_python,
        plugin_cache_root=cache_root,
    )

    assert result.cache_invalidated is True
    assert result.cache_state == "invalidated"
    assert not cached.exists()


def test_installer_refuses_to_delete_unowned_same_version_cache(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    cached = cache_root / __version__
    (cached / ".codex-plugin").mkdir(parents=True)
    (cached / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "different-plugin", "version": __version__})
    )

    with pytest.raises(RuntimeError, match="not owned by Codex Usage Tracker"):
        install_plugin(
            plugin_dir=tmp_path / "plugins" / "codex-usage-tracker",
            marketplace_path=tmp_path / "marketplace.json",
            python_executable=tmp_path / ".venv" / "bin" / "python",
            plugin_cache_root=cache_root,
        )

    assert cached.is_dir()


def test_bundle_inspection_detects_installed_and_cached_byte_drift(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = tmp_path / "cache"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=tmp_path / ".venv" / "bin" / "python",
        plugin_cache_root=cache_root,
    )
    cached = cache_root / __version__
    shutil.copytree(plugin_dir, cached)

    coherent = inspect_plugin_bundle(plugin_dir=plugin_dir, plugin_cache_root=cache_root)
    assert coherent["state"] == "coherent"
    assert coherent["installed"]["matches_declared"] is True
    assert coherent["cache"]["matches_installed"] is True

    cached_skill = cached / "skills" / "codex-usage-tracker" / "SKILL.md"
    cached_skill.write_text(cached_skill.read_text() + "\ndrift\n")

    drifted = inspect_plugin_bundle(plugin_dir=plugin_dir, plugin_cache_root=cache_root)
    assert drifted["state"] == "mismatch"
    assert drifted["cache"]["matches_declared"] is False
    assert drifted["cache"]["matches_installed"] is False


def test_doctor_fails_closed_on_cached_bundle_drift(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = (
        codex_home / "plugins" / "cache" / "local" / "codex-usage-tracker"
    )
    marketplace = tmp_path / "marketplace.json"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace,
        python_executable=tmp_path / ".venv" / "bin" / "python",
        codex_home=codex_home,
    )
    cached = cache_root / __version__
    shutil.copytree(plugin_dir, cached)
    cached_skill = cached / "skills" / "codex-usage-api" / "SKILL.md"
    cached_skill.write_text(cached_skill.read_text() + "\ndrift\n")

    report = run_doctor(
        codex_home=codex_home,
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        plugin_link=plugin_dir,
        marketplace_path=marketplace,
        repo_root=plugin_dir,
        suggest_repair=True,
    )
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["Plugin bundle coherence"]["status"] == "fail"
    assert "installed and cached bundle digests differ" in checks[
        "Plugin bundle coherence"
    ]["detail"]
    assert (
        "codex-usage-tracker install-plugin --force"
        in checks["Plugin bundle coherence"]["remediation"]
    )


def test_usage_status_proves_current_tool_exposure_and_bundle_coherence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_status

    codex_home = tmp_path / ".codex"
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    cache_root = (
        codex_home / "plugins" / "cache" / "local" / "codex-usage-tracker"
    )
    result = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=tmp_path / ".venv" / "bin" / "python",
        codex_home=codex_home,
    )
    shutil.copytree(plugin_dir, cache_root / __version__)
    monkeypatch.setenv("CODEX_USAGE_TRACKER_PLUGIN_VERSION", __version__)
    monkeypatch.setenv(
        "CODEX_USAGE_TRACKER_PLUGIN_BUNDLE_DIGEST",
        result.bundle_digest,
    )

    payload = build_usage_status(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        codex_home=codex_home,
        home=tmp_path,
    )
    status = payload["result"]

    assert status["mcp"]["current_task_exposure"] == "verified"
    assert status["plugin_bundle"]["state"] == "coherent"
    assert status["plugin_bundle"]["runtime_version"] == __version__
    assert status["plugin_bundle"]["installed"]["computed_digest"] == result.bundle_digest
    assert all(
        limitation["code"] != "mcp.current_task_exposure_unverified"
        for limitation in payload["limitations"]
    )


def test_usage_status_plugin_error_does_not_expose_local_paths(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    plugin_dir.mkdir(parents=True)

    status = plugin_bundle_status(codex_home=tmp_path / ".codex", home=tmp_path)

    assert status["state"] == "invalid"
    assert status["error"] == {
        "code": "plugin_bundle.invalid",
        "message": "The installed plugin bundle could not be verified.",
    }
    assert str(tmp_path) not in json.dumps(status)
