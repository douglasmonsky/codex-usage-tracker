from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from codex_usage_tracker import __version__
from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.plugin_installer import install_plugin, uninstall_plugin


def test_install_plugin_writes_generated_wrapper_and_marketplace(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    python_path = tmp_path / ".venv" / "bin" / "python"

    result = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=python_path,
    )
    second = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=python_path,
    )

    manifest = json.loads((plugin_dir / ".codex-plugin" / "plugin.json").read_text())
    mcp_config = json.loads((plugin_dir / ".mcp.json").read_text())
    marketplace = json.loads(marketplace_path.read_text())

    assert result.plugin_dir == plugin_dir
    assert result.replaced_existing is False
    assert second.replaced_existing is False
    assert manifest["name"] == "codex-usage-tracker"
    assert manifest["version"] == __version__
    assert manifest["interface"]["defaultPrompt"][:3] == [
        "Open dashboard",
        "Heaviest thread?",
        "Thread leaderboard",
    ]
    assert (plugin_dir / "assets" / "icon.svg").exists()
    assert (plugin_dir / "skills" / "codex-usage-api" / "SKILL.md").exists()
    assert (plugin_dir / "skills" / "codex-usage-tracker" / "SKILL.md").exists()
    assert mcp_config["mcpServers"]["codex-usage-tracker"]["command"] == str(python_path)
    assert mcp_config["mcpServers"]["codex-usage-tracker"]["args"] == [
        "-m",
        "codex_usage_tracker.mcp_server",
    ]
    assert marketplace["plugins"] == [
        {
            "name": "codex-usage-tracker",
            "source": {"source": "local", "path": str(plugin_dir.resolve())},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        }
    ]


def test_install_plugin_refuses_non_plugin_path_without_force(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "README.md").write_text("not a generated plugin", encoding="utf-8")

    with pytest.raises(FileExistsError):
        install_plugin(plugin_dir=plugin_dir, marketplace_path=tmp_path / "marketplace.json")


def test_install_plugin_refuses_different_plugin_manifest(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    (plugin_dir / ".codex-plugin").mkdir(parents=True)
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "different-plugin"}),
        encoding="utf-8",
    )

    with pytest.raises(FileExistsError):
        install_plugin(plugin_dir=plugin_dir, marketplace_path=tmp_path / "marketplace.json")


def test_install_plugin_preserves_requested_relative_python(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=Path(".venv/bin/python"),
    )

    mcp_config = json.loads((plugin_dir / ".mcp.json").read_text())

    assert mcp_config["mcpServers"]["codex-usage-tracker"]["command"] == str(
        tmp_path / ".venv" / "bin" / "python"
    )


def test_install_plugin_adds_pythonpath_for_source_checkout_venv(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    python_path = repo_root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    (repo_root / "src" / "codex_usage_tracker").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[project]\nname = 'sample'\n", encoding="utf-8")
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"

    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=python_path,
    )

    mcp_config = json.loads((plugin_dir / ".mcp.json").read_text())
    server = mcp_config["mcpServers"]["codex-usage-tracker"]

    assert server["env"] == {"PYTHONPATH": str(repo_root / "src")}


def test_install_plugin_force_replaces_existing_symlink(tmp_path: Path) -> None:
    source_plugin = tmp_path / "source"
    source_plugin.mkdir()
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    plugin_dir.parent.mkdir()
    plugin_dir.symlink_to(source_plugin, target_is_directory=True)

    result = install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=tmp_path / "marketplace.json",
        python_executable=Path("/usr/bin/python3"),
        force=True,
    )

    assert result.replaced_existing is True
    assert plugin_dir.is_dir()
    assert not plugin_dir.is_symlink()
    assert (plugin_dir / ".codex-plugin" / "plugin.json").exists()


def test_uninstall_plugin_removes_only_tracker_wrapper_and_marketplace_entry(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=tmp_path / ".venv" / "bin" / "python",
    )

    result = uninstall_plugin(plugin_dir=plugin_dir, marketplace_path=marketplace_path)
    marketplace = json.loads(marketplace_path.read_text())

    assert result.removed_plugin_path is True
    assert result.removed_marketplace_entry is True
    assert not plugin_dir.exists()
    assert marketplace["plugins"] == []


def test_uninstall_plugin_refuses_unrelated_path(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "README.md").write_text("not a generated plugin", encoding="utf-8")

    with pytest.raises(FileExistsError):
        uninstall_plugin(plugin_dir=plugin_dir, marketplace_path=tmp_path / "marketplace.json")


def test_doctor_accepts_generated_plugin_directory(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    python_path = _fake_python(tmp_path)
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=python_path,
    )

    report = run_doctor(
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        dashboard_path=tmp_path / "dashboard.html",
        pricing_path=tmp_path / "pricing.json",
        plugin_link=plugin_dir,
        marketplace_path=marketplace_path,
        repo_root=None,
    )
    checks = {check["name"]: check for check in report["checks"]}

    assert checks["Plugin root"]["status"] == "pass"
    assert str(plugin_dir) in checks["Plugin root"]["detail"]
    assert checks["Plugin registration"]["status"] == "pass"
    assert checks["MCP config"]["status"] == "pass"
    assert checks["MCP runtime"]["status"] == "pass"


def test_doctor_detects_mcp_python_that_cannot_import_server(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    python_path = _fake_python(tmp_path, exit_code=1)
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=python_path,
    )

    report = run_doctor(
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        dashboard_path=tmp_path / "dashboard.html",
        pricing_path=tmp_path / "pricing.json",
        plugin_link=plugin_dir,
        marketplace_path=marketplace_path,
        repo_root=None,
        suggest_repair=True,
    )
    checks = {check["name"]: check for check in report["checks"]}

    assert report["status"] == "fail"
    assert checks["MCP runtime"]["status"] == "fail"
    assert "cannot import the server" in checks["MCP runtime"]["detail"]
    assert any("install-plugin --python .venv/bin/python --force" in suggestion for suggestion in report["repair_suggestions"])


def _fake_python(tmp_path: Path, *, exit_code: int = 0) -> Path:
    if os.name == "nt":
        pytest.skip("fake shell Python is only used on POSIX test runners")
    path = tmp_path / f"python-{exit_code}"
    path.write_text(f"#!/bin/sh\nexit {exit_code}\n", encoding="utf-8")
    path.chmod(0o755)
    return path
