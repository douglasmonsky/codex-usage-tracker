"""Deterministic identity and coherence checks for installed plugin bundles."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from codex_usage_tracker.core.version import __version__

PLUGIN_NAME = "codex-usage-tracker"
PLUGIN_BUNDLE_SCHEMA = "codex-usage-tracker.plugin-bundle.v1"
PLUGIN_COHERENCE_SCHEMA = "codex-usage-tracker.plugin-coherence.v1"
_BUNDLE_DIRS = ("assets", "skills")

CacheState = Literal["absent", "coherent", "invalidated"]


def plugin_bundle_digest(plugin_dir: Path) -> str:
    """Hash package-owned immutable plugin resources in stable path order."""
    entries: list[tuple[str, bytes]] = []
    for directory_name in _BUNDLE_DIRS:
        directory = plugin_dir / directory_name
        if not directory.is_dir():
            raise FileNotFoundError(f"plugin bundle is missing {directory_name}/")
        entries.extend(
            (path.relative_to(plugin_dir).as_posix(), path.read_bytes())
            for path in directory.rglob("*")
            if path.is_file()
        )
    return _digest_entries(entries)


def packaged_plugin_bundle_digest() -> str:
    """Hash the immutable plugin resources bundled in the installed package."""
    root = resources.files("codex_usage_tracker.plugin_data")
    entries: list[tuple[str, bytes]] = []
    for directory_name in _BUNDLE_DIRS:
        directory = root.joinpath(directory_name)
        if not directory.is_dir():
            raise FileNotFoundError(f"packaged plugin bundle is missing {directory_name}/")
        entries.extend(_resource_entries(directory, prefix=directory_name))
    return _digest_entries(entries)


def _digest_entries(entries: list[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative_text, content in sorted(entries):
        relative = relative_text.encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return f"sha256:{digest.hexdigest()}"


def _resource_entries(resource: Any, *, prefix: str) -> list[tuple[str, bytes]]:
    entries: list[tuple[str, bytes]] = []
    for child in resource.iterdir():
        relative = f"{prefix}/{child.name}"
        if child.is_dir():
            entries.extend(_resource_entries(child, prefix=relative))
        elif child.is_file():
            entries.append((relative, child.read_bytes()))
    return entries


def plugin_bundle_manifest(digest: str) -> dict[str, str]:
    """Return the manifest identity block for one immutable resource bundle."""
    _validate_digest(digest)
    return {
        "schema": PLUGIN_BUNDLE_SCHEMA,
        "digest": digest,
        "runtime_version": __version__,
    }


def inspect_plugin_bundle(
    *,
    plugin_dir: Path,
    plugin_cache_root: Path,
) -> dict[str, object]:
    """Compare installed and exact-version cached plugin resources."""
    installed_manifest = _read_manifest(plugin_dir)
    version = _manifest_version(installed_manifest)
    installed = _bundle_observation(plugin_dir, installed_manifest)
    cache_path = _cache_path(plugin_cache_root, version)
    if not cache_path.exists():
        cache: dict[str, object] = {
            "state": "absent",
            "manifest_version": None,
            "declared_digest": None,
            "computed_digest": None,
            "matches_declared": False,
            "matches_installed": False,
        }
        state = "not_cached" if installed["matches_declared"] else "mismatch"
    else:
        if cache_path.is_symlink():
            cache = _invalid_cache_observation("symlink")
        else:
            try:
                cache_manifest = _read_manifest(cache_path)
            except (OSError, ValueError):
                cache = _invalid_cache_observation("invalid_manifest")
            else:
                if cache_manifest.get("name") != PLUGIN_NAME:
                    cache = _invalid_cache_observation("unowned")
                else:
                    cache = _bundle_observation(cache_path, cache_manifest)
                    cache["state"] = "present"
                    cache["matches_installed"] = bool(
                        cache["computed_digest"] == installed["computed_digest"]
                        and cache["declared_digest"] == installed["declared_digest"]
                        and cache["manifest_version"] == installed["manifest_version"]
                    )
        state = (
            "coherent"
            if installed["matches_declared"]
            and cache["matches_declared"]
            and cache["matches_installed"]
            else "mismatch"
        )
    return {
        "schema": PLUGIN_COHERENCE_SCHEMA,
        "state": state,
        "runtime_version": __version__,
        "installed": installed,
        "cache": cache,
    }


def invalidate_stale_plugin_cache(
    *,
    plugin_dir: Path,
    plugin_cache_root: Path,
) -> CacheState:
    """Remove only an owned, exact-version cache whose bundle identity is stale."""
    manifest = _read_manifest(plugin_dir)
    version = _manifest_version(manifest)
    cache_path = _cache_path(plugin_cache_root, version)
    if not cache_path.exists():
        return "absent"
    if cache_path.is_symlink():
        raise RuntimeError("refusing to replace a symlinked Codex Usage Tracker cache")
    try:
        cached_manifest = _read_manifest(cache_path)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "same-version plugin cache has no valid ownership manifest; "
            "remove it manually before reinstalling"
        ) from exc
    if cached_manifest.get("name") != PLUGIN_NAME:
        raise RuntimeError("same-version plugin cache is not owned by Codex Usage Tracker")
    observation = inspect_plugin_bundle(
        plugin_dir=plugin_dir,
        plugin_cache_root=plugin_cache_root,
    )
    if observation["state"] == "coherent":
        return "coherent"
    shutil.rmtree(cache_path)
    return "invalidated"


def _bundle_observation(
    plugin_dir: Path,
    manifest: Mapping[str, Any],
) -> dict[str, object]:
    declared = _declared_digest(manifest)
    try:
        computed = plugin_bundle_digest(plugin_dir)
    except OSError:
        computed = None
    return {
        "manifest_version": manifest.get("version"),
        "declared_digest": declared,
        "computed_digest": computed,
        "matches_declared": bool(declared and declared == computed),
    }


def _invalid_cache_observation(state: str) -> dict[str, object]:
    return {
        "state": state,
        "manifest_version": None,
        "declared_digest": None,
        "computed_digest": None,
        "matches_declared": False,
        "matches_installed": False,
    }


def _read_manifest(plugin_dir: Path) -> Mapping[str, Any]:
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("plugin manifest is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("plugin manifest must be an object")
    return payload


def _manifest_version(manifest: Mapping[str, Any]) -> str:
    version = manifest.get("version")
    if not isinstance(version, str) or not version or Path(version).name != version:
        raise ValueError("plugin manifest version is not a safe cache component")
    return version


def _declared_digest(manifest: Mapping[str, Any]) -> str | None:
    bundle = manifest.get("bundle")
    if not isinstance(bundle, Mapping):
        return None
    digest = bundle.get("digest")
    return digest if isinstance(digest, str) else None


def _cache_path(plugin_cache_root: Path, version: str) -> Path:
    root = plugin_cache_root.expanduser()
    return root / version


def _validate_digest(digest: str) -> None:
    prefix, separator, value = digest.partition(":")
    if prefix != "sha256" or separator != ":" or len(value) != 64:
        raise ValueError("plugin bundle digest must be sha256:<64 lowercase hex>")
    if any(character not in "0123456789abcdef" for character in value):
        raise ValueError("plugin bundle digest must be sha256:<64 lowercase hex>")
