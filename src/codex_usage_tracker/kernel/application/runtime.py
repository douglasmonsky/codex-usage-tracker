"""Runtime path and source discovery policy for the kernel interfaces."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ..models import KernelPaths
from ..operational import kernel_paths

CODEX_HOME_ENV = "CODEX_HOME"
CACHE_ROOT_ENV = "CODEX_USAGE_TRACKER_CACHE_ROOT"


@dataclass(frozen=True)
class RuntimePaths:
    codex_home: Path
    cache_root: Path

    @property
    def kernel(self) -> KernelPaths:
        return kernel_paths(self.cache_root)


def default_runtime_paths(
    environ: Mapping[str, str] | None = None,
) -> RuntimePaths:
    source = os.environ if environ is None else environ
    codex_home = Path(
        source.get(CODEX_HOME_ENV, str(Path.home() / ".codex"))
    ).expanduser()
    cache_root = Path(
        source.get(
            CACHE_ROOT_ENV,
            str(codex_home / "codex-usage-tracker" / "kernel-v1"),
        )
    ).expanduser()
    return RuntimePaths(codex_home.resolve(), cache_root.resolve())


def discover_sources(codex_home: Path) -> tuple[Path, ...]:
    """Return deterministic JSONL sources without opening their contents."""

    roots = (
        codex_home.resolve() / "sessions",
        codex_home.resolve() / "archived_sessions",
    )
    return tuple(
        sorted(
            (
                path.resolve()
                for root in roots
                if root.is_dir()
                for path in root.rglob("*.jsonl")
                if path.is_file()
            ),
            key=str,
        )
    )
