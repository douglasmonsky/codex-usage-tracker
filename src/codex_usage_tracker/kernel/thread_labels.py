"""Bounded prompt-derived thread labels from Codex session metadata."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

from .identity import stable_id

MAX_THREAD_LABEL_CHARACTERS = 160
MAX_SESSION_INDEX_BYTES = 64 * 1024 * 1024
MAX_SESSION_INDEX_LINE_BYTES = 64 * 1024
MAX_SESSION_INDEX_ENTRIES = 250_000


def load_thread_labels(sources: Iterable[Path]) -> dict[str, str]:
    """Read bounded session-index metadata adjacent to selected sources."""

    labels: dict[str, str] = {}
    for index_path in _session_index_paths(sources):
        labels.update(_read_session_index(index_path))
    return labels


def load_thread_label_hashes(codex_home: Path) -> dict[str, str]:
    """Return cached session-hash labels without exposing session IDs."""

    path = codex_home.resolve() / "session_index.jsonl"
    try:
        stat = path.stat()
    except OSError:
        return {}
    return dict(
        _cached_thread_label_hashes(
            path,
            stat.st_mtime_ns,
            stat.st_size,
        )
    )


def thread_label_revision(codex_home: Path) -> dict[str, int] | None:
    """Return a bounded cache identity for session-index metadata."""

    path = codex_home.resolve() / "session_index.jsonl"
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"modified_ns": stat.st_mtime_ns, "size_bytes": stat.st_size}


def sanitize_thread_label(value: Any) -> str | None:
    """Collapse controls and whitespace into bounded untrusted display text."""

    if not isinstance(value, str):
        return None
    characters = (
        " " if character.isspace() or unicodedata.category(character).startswith("C") else character
        for character in value
    )
    collapsed = " ".join("".join(characters).split())
    if not collapsed:
        return None
    return collapsed[:MAX_THREAD_LABEL_CHARACTERS].rstrip()


def _session_index_paths(sources: Iterable[Path]) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for source in sources:
        resolved = source.resolve()
        parts = resolved.parts
        for marker in ("sessions", "archived_sessions"):
            if marker not in parts:
                continue
            marker_index = parts.index(marker)
            root = Path(*parts[:marker_index])
            candidate = root / "session_index.jsonl"
            if candidate.is_file():
                paths.add(candidate)
            break
    return tuple(sorted(paths, key=str))


def _read_session_index(path: Path) -> dict[str, str]:
    if path.stat().st_size > MAX_SESSION_INDEX_BYTES:
        return {}
    labels: dict[str, str] = {}
    with path.open("rb") as handle:
        while len(labels) < MAX_SESSION_INDEX_ENTRIES:
            line = handle.readline(MAX_SESSION_INDEX_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_SESSION_INDEX_LINE_BYTES:
                _discard_line_remainder(handle)
                continue
            try:
                payload = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            session_id = payload.get("id")
            label = sanitize_thread_label(payload.get("thread_name"))
            if isinstance(session_id, str) and session_id and label is not None:
                labels[session_id] = label
    return labels


@lru_cache(maxsize=8)
def _cached_thread_label_hashes(
    path: Path,
    modified_ns: int,
    size_bytes: int,
) -> tuple[tuple[str, str], ...]:
    del modified_ns, size_bytes
    return tuple(
        sorted(
            (
                (stable_id("sess", session_id), label)
                for session_id, label in _read_session_index(path).items()
            ),
            key=lambda item: item[0],
        )
    )


def _discard_line_remainder(handle: Any) -> None:
    while True:
        remainder = handle.readline(MAX_SESSION_INDEX_LINE_BYTES + 1)
        if not remainder or remainder.endswith(b"\n"):
            return
