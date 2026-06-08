"""Source adapter contracts for aggregate usage ingestion."""

from __future__ import annotations

from collections.abc import Iterable, MutableMapping
from pathlib import Path
from typing import Protocol, TypeAlias

from codex_usage_tracker.models import SessionInfo, UsageEvent

SessionIndex: TypeAlias = dict[str, SessionInfo]

SOURCE_CODEX = "codex"
SOURCE_CLAUDE_CODE = "claude-code"
SOURCE_ALL = "all"
SOURCE_CHOICES = (SOURCE_CODEX, SOURCE_CLAUDE_CODE, SOURCE_ALL)


class UsageSourceAdapter(Protocol):
    source_provider: str
    source_app: str
    source_format: str

    def discover_logs(self, root: Path, *, include_archived: bool = False) -> list[Path]:
        """Return local log paths for this source."""

    def load_session_index(self, root: Path) -> SessionIndex:
        """Return source metadata keyed by session id without raw transcript content."""

    def parse_file(
        self,
        path: Path,
        session_index: SessionIndex | None = None,
        stats: MutableMapping[str, int] | None = None,
    ) -> list[UsageEvent]:
        """Parse one source log into aggregate usage events."""


def parse_files(
    adapter: UsageSourceAdapter,
    paths: Iterable[Path],
    session_index: SessionIndex | None = None,
    stats: MutableMapping[str, int] | None = None,
) -> list[UsageEvent]:
    events: list[UsageEvent] = []
    for path in paths:
        events.extend(adapter.parse_file(path, session_index=session_index, stats=stats))
    return events
