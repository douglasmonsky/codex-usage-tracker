from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.kernel.ingest import KernelIngestor
from codex_usage_tracker.kernel.operational import kernel_paths
from codex_usage_tracker.kernel.watcher import KernelWatcher


def test_watcher_never_starts_first_build(tmp_path: Path) -> None:
    paths = kernel_paths(tmp_path / "cache")
    watcher = KernelWatcher(
        KernelIngestor(paths.analytical, paths.operational),
        owner_id="watcher-1",
    )

    with pytest.raises(ValueError, match="existing active kernel"):
        watcher.catch_up([])
    assert not paths.analytical.exists()
