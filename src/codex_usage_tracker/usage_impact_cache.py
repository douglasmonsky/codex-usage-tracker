"""Server-side usage-impact cache for live dashboard row slices."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codex_usage_tracker.allowance import annotate_rows_with_allowance, load_allowance_config
from codex_usage_tracker.call_origin import ensure_call_origin
from codex_usage_tracker.pricing import annotate_rows_with_efficiency, load_pricing_config
from codex_usage_tracker.store import (
    query_usage_api_events,
    query_usage_status,
    refresh_metadata,
)
from codex_usage_tracker.threads import annotate_thread_attachments
from codex_usage_tracker.usage_impact import annotate_rows_with_usage_impact
from codex_usage_tracker.usage_impact_store import (
    query_usage_impact_map_for_records,
    replace_usage_impact_from_annotated_rows,
)


@dataclass(frozen=True)
class _FileSignature:
    path: str
    mtime_ns: int | None
    size_bytes: int | None


@dataclass(frozen=True)
class _ImpactCacheKey:
    include_archived: bool
    latest_refresh_at: str
    scoped_rows: int
    max_event_timestamp: str
    pricing: _FileSignature
    allowance: _FileSignature
    rate_card: _FileSignature


class UsageImpactCache:
    """Cache full-history usage-impact estimates across live row-slice requests."""

    def __init__(
        self,
        *,
        db_path: Path,
        pricing_path: Path,
        allowance_path: Path,
        rate_card_path: Path,
    ) -> None:
        self._db_path = db_path
        self._pricing_path = pricing_path
        self._allowance_path = allowance_path
        self._rate_card_path = rate_card_path
        self._condition = threading.Condition()
        self._cache: dict[bool, tuple[_ImpactCacheKey, dict[str, dict[str, Any]]]] = {}
        self._building: set[_ImpactCacheKey] = set()

    def invalidate(self) -> None:
        """Drop cached estimates after an explicit refresh."""

        with self._condition:
            self._cache.clear()
            self._condition.notify_all()

    def warm_async(self, *, include_archived: bool) -> None:
        """Warm estimates in the background without blocking first dashboard paint."""

        key = self._cache_key(include_archived=include_archived)
        with self._condition:
            cached = self._cache.get(include_archived)
            if cached is not None and cached[0] == key:
                return
            if self._is_building_scope_locked(include_archived):
                return
            self._building.add(key)
        thread = threading.Thread(
            target=self._warm_safely,
            kwargs={"include_archived": include_archived, "key": key},
            name=f"codex-usage-impact-cache-{int(include_archived)}",
            daemon=True,
        )
        thread.start()

    def rebuild(self, *, include_archived: bool) -> dict[str, dict[str, Any]]:
        """Rebuild and persist usage-impact estimates synchronously."""

        key = self._cache_key(include_archived=include_archived)
        impact_by_record_id = self._build_impact_map(include_archived=include_archived)
        with self._condition:
            self._cache[include_archived] = (key, impact_by_record_id)
            self._building.discard(key)
            self._condition.notify_all()
        return impact_by_record_id

    def copy_usage_impact(
        self,
        rows: list[dict[str, Any]],
        *,
        include_archived: bool,
        block: bool = True,
    ) -> list[dict[str, Any]]:
        """Return copied rows with cached usage-impact estimates attached."""

        if not rows:
            return []
        record_ids = [str(row.get("record_id") or "") for row in rows if row.get("record_id")]
        persisted, persisted_pending = query_usage_impact_map_for_records(
            self._db_path,
            record_ids,
        )
        missing = any(record_id not in persisted for record_id in record_ids)
        if persisted and not missing and not persisted_pending:
            return _copy_persisted_usage_impact(rows, persisted, pending=False)
        if not block:
            self.warm_async(include_archived=include_archived)
            return _copy_persisted_usage_impact(rows, persisted, pending=True)
        impact_by_record_id = self._impact_by_record_id(
            include_archived=include_archived,
            block=block,
        )
        pending = impact_by_record_id is None
        copied: list[dict[str, Any]] = []
        default_impact = {"primary": None, "secondary": None}
        for row in rows:
            next_row = dict(row)
            record_id = str(row.get("record_id") or "")
            next_row["usage_impact"] = (
                default_impact
                if impact_by_record_id is None
                else impact_by_record_id.get(record_id, default_impact)
            )
            if pending:
                next_row["usage_impact_pending"] = True
            copied.append(next_row)
        return copied

    def _warm_safely(self, *, include_archived: bool, key: _ImpactCacheKey) -> None:
        try:
            impact_by_record_id = self._build_impact_map(include_archived=include_archived)
        except Exception:
            with self._condition:
                self._building.discard(key)
                self._condition.notify_all()
            # Cache warming is a latency optimization; foreground API requests
            # still surface normal errors if the database or config is broken.
            return
        with self._condition:
            self._cache[include_archived] = (key, impact_by_record_id)
            self._building.discard(key)
            self._condition.notify_all()

    def _impact_by_record_id(
        self,
        *,
        include_archived: bool,
        block: bool,
    ) -> dict[str, dict[str, Any]] | None:
        key = self._cache_key(include_archived=include_archived)
        with self._condition:
            cached = self._cache.get(include_archived)
            if cached is not None and cached[0] == key:
                return cached[1]
            while self._is_building_scope_locked(include_archived):
                if not block:
                    return None
                self._condition.wait()
                cached = self._cache.get(include_archived)
                if cached is not None and cached[0] == key:
                    return cached[1]
            if not block:
                self._building.add(key)
                thread = threading.Thread(
                    target=self._warm_safely,
                    kwargs={"include_archived": include_archived, "key": key},
                    name=f"codex-usage-impact-cache-{int(include_archived)}",
                    daemon=True,
                )
                thread.start()
                return None
            self._building.add(key)
        try:
            impact_by_record_id = self._build_impact_map(include_archived=include_archived)
        except Exception:
            with self._condition:
                self._building.discard(key)
                self._condition.notify_all()
            raise
        with self._condition:
            self._cache[include_archived] = (key, impact_by_record_id)
            self._building.discard(key)
            self._condition.notify_all()
            return impact_by_record_id

    def _build_impact_map(self, *, include_archived: bool) -> dict[str, dict[str, Any]]:
        pricing = load_pricing_config(self._pricing_path)
        allowance = load_allowance_config(
            self._allowance_path,
            rate_card_path=self._rate_card_path,
        )
        rows = query_usage_api_events(
            db_path=self._db_path,
            limit=None,
            offset=0,
            include_archived=include_archived,
            sort="time",
            direction="asc",
        )
        rows = annotate_thread_attachments([ensure_call_origin(row) for row in rows])
        rows = annotate_rows_with_allowance(
            annotate_rows_with_efficiency(rows, pricing),
            allowance,
        )
        annotated_rows = annotate_rows_with_usage_impact(rows)
        replace_usage_impact_from_annotated_rows(
            db_path=self._db_path,
            rows=annotated_rows,
        )
        impact_by_record_id, _pending = query_usage_impact_map_for_records(
            self._db_path,
            [str(row.get("record_id")) for row in annotated_rows if row.get("record_id")],
        )
        return impact_by_record_id

    def _cache_key(self, *, include_archived: bool) -> _ImpactCacheKey:
        metadata = refresh_metadata(self._db_path)
        counts = query_usage_status(
            db_path=self._db_path,
            include_archived=include_archived,
        )
        return _ImpactCacheKey(
            include_archived=include_archived,
            latest_refresh_at=str(metadata.get("latest_refresh_at") or ""),
            scoped_rows=int(counts.get("scoped_rows") or 0),
            max_event_timestamp=str(counts.get("max_event_timestamp") or ""),
            pricing=_file_signature(self._pricing_path),
            allowance=_file_signature(self._allowance_path),
            rate_card=_file_signature(self._rate_card_path),
        )

    def _is_building_scope_locked(self, include_archived: bool) -> bool:
        return any(key.include_archived == include_archived for key in self._building)


def _file_signature(path: Path) -> _FileSignature:
    try:
        stat = path.stat()
    except OSError:
        return _FileSignature(path=str(path), mtime_ns=None, size_bytes=None)
    return _FileSignature(
        path=str(path),
        mtime_ns=int(stat.st_mtime_ns),
        size_bytes=int(stat.st_size),
    )


def _copy_persisted_usage_impact(
    rows: list[dict[str, Any]],
    impact_by_record_id: dict[str, dict[str, Any]],
    *,
    pending: bool,
) -> list[dict[str, Any]]:
    default_impact = {"primary": None, "secondary": None}
    copied: list[dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        record_id = str(row.get("record_id") or "")
        next_row["usage_impact"] = impact_by_record_id.get(record_id, default_impact)
        if pending:
            next_row["usage_impact_pending"] = True
        copied.append(next_row)
    return copied
