from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.diagnostics import run_doctor
from codex_usage_tracker.plugin_installer import install_plugin


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
    assert manifest["version"] == "0.2.0"
    assert (plugin_dir / "assets" / "icon.svg").exists()
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


def test_doctor_accepts_generated_plugin_directory(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugins" / "codex-usage-tracker"
    marketplace_path = tmp_path / "marketplace.json"
    install_plugin(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=tmp_path / ".venv" / "bin" / "python",
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
    assert checks["Plugin registration"]["status"] == "pass"
    assert checks["MCP config"]["status"] == "pass"
