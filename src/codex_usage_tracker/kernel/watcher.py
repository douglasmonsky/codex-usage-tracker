"""Optional host watcher adapter over the explicit ingestion service."""

from __future__ import annotations

from pathlib import Path

from .ingest import KernelIngestor, RefreshResult, RefreshTrigger


class KernelWatcher:
    """Coalesce one observed source set into the shared refresh path."""

    def __init__(self, ingestor: KernelIngestor, *, owner_id: str) -> None:
        self._ingestor = ingestor
        self._owner_id = owner_id

    def catch_up(self, sources: list[Path]) -> RefreshResult:
        """Catch up complete lines without ever starting the first build."""

        return self._ingestor.refresh(
            sources,
            trigger=RefreshTrigger.WATCHER,
            owner_id=self._owner_id,
        )
