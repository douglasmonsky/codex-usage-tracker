"""Owner-only local paths for the agent-kernel analytical cache."""

from __future__ import annotations

import os
import stat
from pathlib import Path

ANALYTICAL_CACHE_FILENAME = "agent-usage-kernel-v1.sqlite3"


class OwnerOnlyPathError(RuntimeError):
    """The local cache directory is unsafe for usage metadata."""


def _default_cache_root() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME")
    if configured:
        return Path(configured)
    return Path.home() / "Library" / "Caches"


def ensure_owner_only_directory(path: Path) -> Path:
    """Create and verify a directory that only the current user can access."""
    if path.is_symlink():
        raise OwnerOnlyPathError(f"cache directory must not be a symlink: {path}")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise OwnerOnlyPathError(f"cache path is not a directory: {path}")
    if info.st_uid != os.getuid():
        raise OwnerOnlyPathError(f"cache directory is not owned by this user: {path}")
    if stat.S_IMODE(info.st_mode) != 0o700:
        raise OwnerOnlyPathError(f"cache directory permissions must be 0700: {path}")
    return path


def agent_kernel_cache_path(cache_root: Path | None = None) -> Path:
    """Resolve the canonical, owner-only analytical database path."""

    root = ensure_owner_only_directory(
        (cache_root or _default_cache_root()) / "codex-usage-tracker"
    )
    return root / ANALYTICAL_CACHE_FILENAME
