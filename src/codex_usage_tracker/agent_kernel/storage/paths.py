"""Owner-only local paths for the agent-kernel analytical cache."""

from __future__ import annotations

import os
from pathlib import Path

from .._platform import is_owner_only_directory

ANALYTICAL_CACHE_FILENAME = "agent-usage-kernel-v1.sqlite3"


class OwnerOnlyPathError(RuntimeError):
    """The local cache directory is unsafe for usage metadata."""


def _default_cache_root() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME")
    if configured:
        return Path(configured)
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data)
    if __import__("sys").platform == "darwin":
        return Path.home() / "Library" / "Caches"
    return Path.home() / ".cache"


def ensure_owner_only_directory(path: Path) -> Path:
    """Create and verify a directory that only the current user can access."""
    if path.is_symlink():
        raise OwnerOnlyPathError(f"cache directory must not be a symlink: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not is_owner_only_directory(path):
        raise OwnerOnlyPathError(f"cache directory is not owner-only: {path}")
    return path


def agent_kernel_cache_path(cache_root: Path | None = None) -> Path:
    """Resolve the canonical, owner-only analytical database path."""

    root = ensure_owner_only_directory(
        (cache_root or _default_cache_root()) / "codex-usage-tracker"
    )
    return root / ANALYTICAL_CACHE_FILENAME
