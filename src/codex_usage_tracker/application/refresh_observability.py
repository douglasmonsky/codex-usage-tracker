"""Privacy-safe source generations and tails for refresh observability."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

from codex_usage_tracker.application.protocols import SourceRepository
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.jobs.adapters import request_hash
from codex_usage_tracker.parser.api import find_session_logs
from codex_usage_tracker.store.connection import connect_read_only


def pending_source_tail(
    request: RefreshRequest,
    *,
    codex_home: Path,
    db_path: Path,
) -> dict[str, object]:
    """Report bounded post-commit source bytes without exposing source paths."""
    empty = {
        "tail_pending": False,
        "tail_pending_files": 0,
        "tail_pending_bytes": 0,
    }
    if not db_path.is_file():
        return empty
    logs = find_session_logs(codex_home, include_archived=request.history == "all")
    try:
        with connect_read_only(db_path) as conn:
            checkpoints = {
                str(row["source_file"]): int(row["parsed_until_byte"])
                for row in conn.execute(
                    "SELECT source_file, parsed_until_byte FROM source_files"
                )
            }
    except sqlite3.Error:
        return empty
    pending_files = 0
    pending_bytes = 0
    for path in logs:
        try:
            size_bytes = path.stat().st_size
        except OSError:
            continue
        remaining = max(0, size_bytes - checkpoints.get(str(path), 0))
        if remaining:
            pending_files += 1
            pending_bytes += remaining
    return {
        "tail_pending": pending_files > 0,
        "tail_pending_files": pending_files,
        "tail_pending_bytes": pending_bytes,
    }


def refresh_source_revision(
    request: RefreshRequest,
    *,
    codex_home: Path,
    source_repository: SourceRepository | None,
) -> str:
    """Fingerprint bounded local source metadata without retaining source paths."""
    logs = (
        source_repository.session_logs(include_archived=request.history == "all")
        if source_repository is not None
        else tuple(find_session_logs(codex_home, include_archived=request.history == "all"))
    )
    observations: list[tuple[str, int, int]] = []
    for path in logs:
        try:
            stat = path.stat()
        except OSError:
            continue
        observations.append(
            (
                hashlib.sha256(_normalized_path(path).encode("utf-8")).hexdigest(),
                int(stat.st_size),
                int(stat.st_mtime_ns),
            )
        )
    encoded = json.dumps(sorted(observations), separators=(",", ":"), sort_keys=True)
    return request_hash(encoded)


def _normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.expanduser().resolve(strict=False)))
