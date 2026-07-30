"""Bounded, deterministic source inventory and history selection."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...domain.identity import semantic_id
from ...domain.time import validate_utc_microseconds
from ..contracts import (
    SOURCE_KIND,
    SourceInventory,
    SourceState,
    TimeRangeConfidence,
    TimeRangeHint,
)

_FINGERPRINT_BYTES = 4096


@dataclass(frozen=True, slots=True)
class SourcePlan:
    """An inventory row plus its local hydration path, when materialized."""

    inventory: SourceInventory
    path: Path | None


def _sha256_slice(path: Path, *, start: int | None = None, length: int = _FINGERPRINT_BYTES) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        if start is not None:
            handle.seek(start)
        digest.update(handle.read(length))
    return digest.hexdigest()


def _relative_key(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative.startswith(("/", "./", "../")) or ".." in relative.split("/"):
        raise ValueError(f"source path escapes root: {relative}")
    return relative


def _stable_manifestation_key(manifestation_id: str, technical_path_key: str) -> int:
    digest = hashlib.sha256(f"{manifestation_id}\0{technical_path_key}".encode()).digest()
    value = int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)
    return max(1, value)


def _bounded_jsonl_paths(root: Path, limit: int) -> dict[str, Path]:
    """Walk only far enough to report a bounded inventory plus overflow."""

    found: dict[str, Path] = {}
    pending = [root]
    while pending and len(found) <= limit:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name, reverse=True)
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
            elif entry.is_file(follow_symlinks=False) and path.suffix == ".jsonl":
                found[_relative_key(root, path)] = path
                if len(found) > limit:
                    return found
    return found


def _load_manifest(manifest: Path | dict[str, Any] | None) -> dict[str, Any] | None:
    if manifest is None:
        return None
    if isinstance(manifest, Path):
        value = json.loads(manifest.read_text(encoding="utf-8"))
    else:
        value = manifest
    if not isinstance(value, dict) or not isinstance(value.get("sources", []), list):
        raise ValueError("synthetic manifest must contain a sources list")
    return value


def _manifest_hint(entry: dict[str, Any]) -> tuple[TimeRangeHint | None, TimeRangeConfidence]:
    raw_hint = entry.get("time_range_hint")
    confidence = TimeRangeConfidence(str(entry.get("time_range_confidence", "unavailable")))
    if raw_hint is None:
        if confidence is not TimeRangeConfidence.UNAVAILABLE:
            raise ValueError("manifest confidence requires a time_range_hint")
        return None, confidence
    if not isinstance(raw_hint, dict):
        raise ValueError("time_range_hint must be an object or null")
    start_us = raw_hint.get("start_us")
    end_us = raw_hint.get("end_us")
    validate_utc_microseconds(start_us, allow_none=False)
    validate_utc_microseconds(end_us, allow_none=False)
    if type(start_us) is not int or type(end_us) is not int:
        raise ValueError("time_range_hint bounds must be integers")
    return TimeRangeHint(start_us, end_us), confidence


def discover_inventory(
    root: Path,
    *,
    manifest: Path | dict[str, Any] | None = None,
    max_files: int = 4096,
    max_bytes: int = 1 << 40,
) -> tuple[SourcePlan, ...]:
    """Return a bounded inventory without loading source records into memory.

    A synthetic manifest may supply conservative time hints and deferred rows.
    Without one, source bounds remain unavailable; filesystem modification time
    is recorded only as selection metadata and never as event time.
    """

    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"source root is not a directory: {root}")
    if max_files <= 0 or max_bytes < 0:
        raise ValueError("source budgets must be positive files and nonnegative bytes")
    manifest_value = _load_manifest(manifest)
    manifest_by_path = {
        str(entry["path"]): entry
        for entry in (manifest_value or {}).get("sources", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    materialized = _bounded_jsonl_paths(root, max_files)
    # A supplied manifest is the authoritative source inventory.  Fixture
    # lifecycle phase artifacts and other sibling JSONL files are not source
    # manifestations unless the manifest explicitly names them.
    keys = sorted(manifest_by_path if manifest_value is not None else materialized)
    overflow = len(keys) > max_files
    if overflow:
        keys = keys[:max_files]
    plans: list[SourcePlan] = []
    manifestation_ids_seen: set[str] = set()
    for rank, key in enumerate(keys):
        entry = manifest_by_path.get(key, {})
        path = materialized.get(key)
        state = SourceState(str(entry.get("state", "active")))
        if path is not None:
            stat_result = path.stat()
            size_bytes = stat_result.st_size
            modified_at_us = stat_result.st_mtime_ns // 1_000
            prefix = _sha256_slice(path)
            suffix = _sha256_slice(path, start=max(0, size_bytes - _FINGERPRINT_BYTES))
        else:
            size_bytes = int(entry.get("bytes", 0))
            modified_at_us = None
            prefix = None
            suffix = None
        manifestation_id = str(entry.get("manifestation_id") or semantic_id("source-manifestation", [SOURCE_KIND, key]))
        if manifestation_id in manifestation_ids_seen:
            manifestation_id = semantic_id("source-manifestation", [manifestation_id, key])
        manifestation_ids_seen.add(manifestation_id)
        manifestation_key = int(entry.get("manifestation_key", _stable_manifestation_key(manifestation_id, key)))
        while manifestation_key in {item.inventory.manifestation_key for item in plans}:
            manifestation_key += 1
        revision = str(entry.get("revision", entry.get("content_sha256", "revision-1")))
        hint, confidence = _manifest_hint(entry)
        logical_source = str(entry.get("logical_source", key))
        source_key = str(entry.get("source_key", logical_source))
        content_revision = str(entry.get("content_revision", entry.get("content_sha256", revision)))
        inventory = SourceInventory(
            source_key=source_key,
            manifestation_key=manifestation_key,
            manifestation_id=manifestation_id,
            source_kind=str(entry.get("source_kind", "codex-jsonl")),
            technical_path_key=key,
            display_label=str(entry.get("display_label", Path(key).name)),
            size_bytes=size_bytes,
            modified_at_us=modified_at_us,
            prefix_fingerprint=prefix,
            suffix_fingerprint=suffix,
            content_revision=content_revision,
            source_rank=rank,
            state=state,
            time_range_hint=hint,
            time_range_confidence=confidence,
            selected=False,
            filesystem_identity=(
                None
                if path is None
                else f"{path.stat().st_dev}:{path.stat().st_ino}"
            ),
        )
        plans.append(SourcePlan(inventory=inventory, path=path))
    if overflow:
        overflow_id = semantic_id("source-manifestation", [SOURCE_KIND, "deferred-file-budget", max_files])
        plans.append(
            SourcePlan(
                inventory=SourceInventory(
                    source_key=f"deferred:file-budget:{max_files}",
                    manifestation_key=_stable_manifestation_key(overflow_id, "__deferred__/file-budget"),
                    manifestation_id=overflow_id,
                    source_kind=SOURCE_KIND,
                    technical_path_key="__deferred__/file-budget",
                    display_label="deferred source inventory beyond file budget",
                    size_bytes=0,
                    modified_at_us=None,
                    prefix_fingerprint=None,
                    suffix_fingerprint=None,
                    content_revision="deferred",
                    source_rank=len(plans),
                    state=SourceState.DEFERRED,
                    time_range_hint=None,
                    time_range_confidence=TimeRangeConfidence.UNAVAILABLE,
                    selected=False,
                    deferred_reason="file_budget",
                ),
                path=None,
            )
        )
    return tuple(plans)


def select_sources(
    plans: Iterable[SourcePlan],
    *,
    window: tuple[int, int] | None = None,
    max_files: int = 4096,
    max_bytes: int = 1 << 40,
) -> tuple[SourcePlan, ...]:
    """Select sources with explicit deferred coverage under file/byte budgets."""

    if max_files <= 0 or max_bytes < 0:
        raise ValueError("source budgets must be positive files and nonnegative bytes")
    if window is not None:
        start_us, end_us = window
        validate_utc_microseconds(start_us, allow_none=False)
        validate_utc_microseconds(end_us, allow_none=False)
        if start_us > end_us:
            raise ValueError("history window start must not exceed end")
    selected_count = 0
    selected_bytes = 0
    result: list[SourcePlan] = []
    for plan in sorted(plans, key=lambda item: item.inventory.source_rank):
        item = plan.inventory
        eligible = item.state is not SourceState.DEFERRED
        if window is not None and item.time_range_confidence is TimeRangeConfidence.TRUSTED:
            assert item.time_range_hint is not None
            eligible = eligible and item.time_range_hint.overlaps_closed_window(*window)
        if item.state is SourceState.MISSING or plan.path is None:
            eligible = False
        reason: str | None = None
        if eligible and selected_count < max_files and selected_bytes + item.size_bytes <= max_bytes:
            selected_count += 1
            selected_bytes += item.size_bytes
            result.append(SourcePlan(_replace_selection(item, True), plan.path))
        else:
            if item.state is SourceState.DEFERRED or plan.path is None:
                reason = "source_not_materialized"
            elif not eligible:
                reason = "trusted_time_range_nonoverlap"
            elif selected_count >= max_files:
                reason = "file_budget"
            else:
                reason = "byte_budget"
            result.append(SourcePlan(_replace_selection(item, False, reason), plan.path))
    return tuple(result)


def _replace_selection(item: SourceInventory, selected: bool, reason: str | None = None) -> SourceInventory:
    values = {field: getattr(item, field) for field in item.__dataclass_fields__}
    values["selected"] = selected
    values["deferred_reason"] = reason
    return SourceInventory(**values)
