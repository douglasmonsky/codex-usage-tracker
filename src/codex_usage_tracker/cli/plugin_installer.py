"""Install a generated local Codex plugin wrapper for the package."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from codex_usage_tracker.core.paths import DEFAULT_MARKETPLACE_PATH, DEFAULT_PLUGIN_LINK
from codex_usage_tracker.core.version import __version__

PLUGIN_NAME = "codex-usage-tracker"


@dataclass(frozen=True)
class PluginInstallResult:
    plugin_dir: Path
    marketplace_path: Path
    python_executable: Path
    replaced_existing: bool


@dataclass(frozen=True)
class PluginUninstallResult:
    plugin_dir: Path
    marketplace_path: Path
    removed_plugin_path: bool
    removed_marketplace_entry: bool


def install_plugin(
    *,
    plugin_dir: Path = DEFAULT_PLUGIN_LINK,
    marketplace_path: Path = DEFAULT_MARKETPLACE_PATH,
    python_executable: Path | None = None,
    force: bool = False,
) -> PluginInstallResult:
    """Create or refresh a local Codex plugin wrapper for this installed package."""

    plugin_dir = plugin_dir.expanduser()
    marketplace_path = marketplace_path.expanduser()
    python_path = _absolute_path(Path(python_executable or sys.executable))
    replaced_existing = _prepare_plugin_dir(plugin_dir, force=force)
    _write_plugin_files(plugin_dir=plugin_dir, python_executable=python_path)
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace = _load_marketplace(marketplace_path)
    _upsert_marketplace_entry(marketplace, plugin_dir)
    marketplace_path.write_text(
        json.dumps(marketplace, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return PluginInstallResult(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        python_executable=python_path,
        replaced_existing=replaced_existing,
    )


def uninstall_plugin(
    *,
    plugin_dir: Path = DEFAULT_PLUGIN_LINK,
    marketplace_path: Path = DEFAULT_MARKETPLACE_PATH,
) -> PluginUninstallResult:
    """Remove the package-owned local Codex plugin wrapper and marketplace entry."""

    plugin_dir = plugin_dir.expanduser()
    marketplace_path = marketplace_path.expanduser()
    removed_plugin_path = _remove_plugin_dir(plugin_dir)
    removed_marketplace_entry = False
    if marketplace_path.exists():
        marketplace = _load_marketplace(marketplace_path)
        removed_marketplace_entry = _remove_marketplace_entry(marketplace)
        marketplace_path.write_text(
            json.dumps(marketplace, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    return PluginUninstallResult(
        plugin_dir=plugin_dir,
        marketplace_path=marketplace_path,
        removed_plugin_path=removed_plugin_path,
        removed_marketplace_entry=removed_marketplace_entry,
    )


def _prepare_plugin_dir(plugin_dir: Path, *, force: bool) -> bool:
    if plugin_dir.is_symlink():
        if not force:
            raise FileExistsError(
                f"{plugin_dir} is a symlink. Use --force to replace the old source-checkout plugin link."
            )
        plugin_dir.unlink()
        plugin_dir.mkdir(parents=True, exist_ok=True)
        return True
    if plugin_dir.exists():
        if not _is_existing_tracker_plugin(plugin_dir):
            raise FileExistsError(
                f"{plugin_dir} exists but does not look like a Codex Usage Tracker plugin."
            )
        if not force:
            return False
        shutil.rmtree(plugin_dir)
        plugin_dir.mkdir(parents=True, exist_ok=True)
        return True
    plugin_dir.mkdir(parents=True, exist_ok=True)
    return False


def _remove_plugin_dir(plugin_dir: Path) -> bool:
    if plugin_dir.is_symlink():
        target = plugin_dir.resolve()
        if target.exists() and not _is_existing_tracker_plugin(target):
            raise FileExistsError(
                f"{plugin_dir} points to {target}, which does not look like a Codex Usage Tracker plugin."
            )
        plugin_dir.unlink()
        return True
    if not plugin_dir.exists():
        return False
    if not _is_existing_tracker_plugin(plugin_dir):
        raise FileExistsError(
            f"{plugin_dir} exists but does not look like a Codex Usage Tracker plugin."
        )
    shutil.rmtree(plugin_dir)
    return True


def _is_existing_tracker_plugin(plugin_dir: Path) -> bool:
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(manifest, dict) and manifest.get("name") == PLUGIN_NAME


def _absolute_path(path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded
    return Path.cwd() / expanded


def _write_plugin_files(*, plugin_dir: Path, python_executable: Path) -> None:
    (plugin_dir / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(plugin_manifest(), indent=2) + "\n",
        encoding="utf-8",
    )
    (plugin_dir / ".mcp.json").write_text(
        json.dumps(_mcp_config(python_executable), indent=2) + "\n",
        encoding="utf-8",
    )
    _copy_tree("assets", plugin_dir / "assets")
    _copy_tree("skills", plugin_dir / "skills")


def _copy_tree(resource_name: str, destination: Path) -> None:
    source = resources.files("codex_usage_tracker.plugin_data").joinpath(resource_name)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    _copy_resource_tree(source, destination)


def _copy_resource_tree(source: Any, destination: Path) -> None:
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _copy_resource_tree(child, target)
        else:
            with child.open("rb") as input_file, target.open("wb") as output_file:
                shutil.copyfileobj(input_file, output_file)


def plugin_manifest() -> dict[str, Any]:
    """Return the package-owned Codex plugin manifest."""

    return {
        "name": PLUGIN_NAME,
        "version": __version__,
        "description": (
            "Unofficial local, evidence-backed Codex usage analyst with MCP tools "
            "and an Evidence Console."
        ),
        "author": {"name": "Douglas Monsky"},
        "homepage": "https://github.com/douglasmonsky/codex-usage-tracker",
        "repository": "https://github.com/douglasmonsky/codex-usage-tracker",
        "license": "MIT",
        "keywords": ["codex", "tokens", "usage", "mcp", "dashboard"],
        "skills": "./skills/",
        "mcpServers": "./.mcp.json",
        "interface": {
            "displayName": "Codex Usage Tracker",
            "shortDescription": (
                "Local, evidence-backed Codex usage analyst with MCP tools and an Evidence Console"
            ),
            "longDescription": (
                "Unofficial independent project, not made by, affiliated with, endorsed by, "
                "sponsored by, or supported by OpenAI. Reads local Codex session logs to "
                "power MCP-based usage analysis, allowance diagnostics, token-waste "
                "investigations, shareable aggregate reports, and a supporting local "
                "Evidence Console without uploading logs."
            ),
            "developerName": "Douglas Monsky",
            "category": "Productivity",
            "capabilities": ["Interactive", "Read", "Write"],
            "websiteURL": "https://github.com/douglasmonsky/codex-usage-tracker",
            "privacyPolicyURL": "https://github.com/douglasmonsky/codex-usage-tracker",
            "termsOfServiceURL": "https://github.com/douglasmonsky/codex-usage-tracker",
            "defaultPrompt": [
                "What drove my Codex usage this week?",
                "Look through my usage for token waste",
                "Compare model and effort usage",
                "Check whether my weekly allowance changed",
            ],
            "brandColor": "#2563EB",
            "composerIcon": "./assets/icon.svg",
            "logo": "./assets/icon.svg",
            "screenshots": [],
        },
    }


def _mcp_config(python_executable: Path) -> dict[str, Any]:
    server: dict[str, Any] = {
        "command": str(python_executable),
        "args": ["-m", "codex_usage_tracker.interfaces.mcp.server"],
        "cwd": ".",
        "env": {"CODEX_USAGE_TRACKER_MCP_PROFILE": "core"},
    }
    source_root = _source_checkout_for_python(python_executable)
    if source_root:
        server["env"]["PYTHONPATH"] = str(source_root / "src")
    return {"mcpServers": {PLUGIN_NAME: server}}


def _source_checkout_for_python(python_executable: Path) -> Path | None:
    """Return a source checkout root when the Python executable lives in its venv."""

    path = python_executable.expanduser()
    parents = list(path.parents)
    if len(parents) < 3:
        return None
    candidate = parents[2]
    if (candidate / "src" / "codex_usage_tracker").is_dir() and (
        candidate / "pyproject.toml"
    ).exists():
        return candidate
    return None


def _load_marketplace(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "name": "local",
            "interface": {"displayName": "Local Plugins"},
            "plugins": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid marketplace JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Marketplace JSON must be an object: {path}")
    data.setdefault("name", "local")
    data.setdefault("interface", {"displayName": "Local Plugins"})
    data.setdefault("plugins", [])
    if not isinstance(data["plugins"], list):
        raise SystemExit(f"Marketplace plugins field must be a list: {path}")
    return data


def _upsert_marketplace_entry(marketplace: dict[str, Any], plugin_dir: Path) -> None:
    entry = {
        "name": PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": _marketplace_plugin_path(plugin_dir),
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Productivity",
    }
    plugins = marketplace["plugins"]
    for index, existing in enumerate(plugins):
        if isinstance(existing, dict) and existing.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            return
    plugins.append(entry)


def _remove_marketplace_entry(marketplace: dict[str, Any]) -> bool:
    plugins = marketplace["plugins"]
    before = len(plugins)
    marketplace["plugins"] = [
        entry
        for entry in plugins
        if not (isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME)
    ]
    return len(marketplace["plugins"]) != before


def _marketplace_plugin_path(plugin_dir: Path) -> str:
    default_parent = Path.home() / "plugins"
    try:
        relative = plugin_dir.resolve().relative_to(default_parent.resolve())
    except ValueError:
        return str(plugin_dir.resolve())
    return f"./plugins/{relative.as_posix()}"
