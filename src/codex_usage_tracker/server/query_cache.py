"""Generation-keyed immutable cache for bounded aggregate dashboard responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qsl

from codex_usage_tracker.store.connection import connect_read_only

CacheStatus = Literal["hit", "miss", "coalesced", "bypass"]


@dataclass(frozen=True, slots=True)
class AggregateQueryCacheKey:
    """All inputs that can change one aggregate response."""

    route: str
    query: tuple[tuple[str, str], ...]
    source_revision: str
    privacy_mode: str
    dependencies: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class AggregateQueryResult:
    """One detached response plus cache provenance."""

    payload: dict[str, Any]
    status: CacheStatus
    source_revision: str
    payload_bytes: int
    stored: bool


class AggregateQueryCache:
    """Cache serialized aggregate payloads and coalesce identical builders."""

    def __init__(self, *, max_entries: int = 64, max_payload_bytes: int = 256 * 1_024) -> None:
        if max_entries <= 0 or max_payload_bytes <= 0:
            raise ValueError("cache bounds must be positive")
        self._max_entries = max_entries
        self._max_payload_bytes = max_payload_bytes
        self._entries: OrderedDict[AggregateQueryCacheKey, bytes] = OrderedDict()
        self._in_flight: dict[AggregateQueryCacheKey, Future[bytes]] = {}
        self._lock = threading.Lock()

    @property
    def max_entries(self) -> int:
        """Return the fixed LRU entry bound for diagnostics and tests."""

        return self._max_entries

    def get_or_compute(
        self,
        key: AggregateQueryCacheKey,
        build: Callable[[], dict[str, object]],
    ) -> AggregateQueryResult:
        """Return a detached cache entry or compute it once for all concurrent callers."""

        with self._lock:
            body = self._entries.pop(key, None)
            if body is not None:
                self._entries[key] = body
                return _result(key, body, "hit", stored=True)
            future = self._in_flight.get(key)
            owner = future is None
            if future is None:
                future = Future()
                self._in_flight[key] = future

        if not owner:
            body = future.result()
            return _result(
                key,
                body,
                "coalesced",
                stored=len(body) <= self._max_payload_bytes,
            )

        try:
            body = _serialize(build())
        except BaseException as exc:
            with self._lock:
                self._in_flight.pop(key, None)
                future.set_exception(exc)
            raise

        status: CacheStatus = "miss" if len(body) <= self._max_payload_bytes else "bypass"
        with self._lock:
            if status == "miss":
                self._entries[key] = body
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
            self._in_flight.pop(key, None)
            future.set_result(body)
        return _result(key, body, status, stored=status == "miss")


def cached_aggregate_payload(
    cache: AggregateQueryCache | None,
    *,
    route: str,
    query: str,
    db_path: Path,
    privacy_mode: str,
    dependencies: Sequence[Path],
    semantic_inputs: Sequence[tuple[str, str]] = (),
    cacheable: bool = True,
    build: Callable[[], dict[str, object]],
) -> dict[str, object]:
    """Build directly or return one generation-keyed aggregate response."""

    if cache is None:
        return build()
    source_revision = current_source_revision(db_path)
    if not cacheable:
        payload = build()
        payload["query_cache"] = _cache_metadata(
            status="bypass",
            source_revision=source_revision,
            payload_bytes=None,
            stored=False,
        )
        return payload
    key = aggregate_query_cache_key(
        route=route,
        query=query,
        source_revision=source_revision,
        privacy_mode=privacy_mode,
        dependencies=dependencies,
        semantic_inputs=semantic_inputs,
    )
    result = cache.get_or_compute(key, build)
    payload: dict[str, object] = result.payload
    payload["query_cache"] = _cache_metadata(
        status=result.status,
        source_revision=result.source_revision,
        payload_bytes=result.payload_bytes,
        stored=result.stored,
    )
    return payload


def aggregate_query_cache_key(
    *,
    route: str,
    query: str,
    source_revision: str,
    privacy_mode: str,
    dependencies: Sequence[Path] = (),
    semantic_inputs: Sequence[tuple[str, str]] = (),
) -> AggregateQueryCacheKey:
    """Build a stable key from the request, source generation, and local configuration."""

    dependency_revisions = tuple(
        sorted(
            [
                (f"config:{_dependency_name(path)}", _dependency_revision(path))
                for path in dependencies
            ]
            + [(f"semantic:{name}", value) for name, value in semantic_inputs]
        )
    )
    return AggregateQueryCacheKey(
        route=route,
        query=_canonical_query(query),
        source_revision=source_revision,
        privacy_mode=privacy_mode,
        dependencies=dependency_revisions,
    )


def current_source_revision(db_path: Path) -> str:
    """Read the aggregate generation without schema writes or writer locks."""

    if not db_path.exists():
        return "generation:0"
    with connect_read_only(db_path, timeout=0.1) as conn:
        try:
            row = conn.execute(
                "SELECT generation FROM compression_source_state WHERE singleton = 1"
            ).fetchone()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc).lower():
                raise
            row = None
    generation = int(row[0] if row is not None else 0)
    return f"generation:{generation}"


def _cache_metadata(
    *,
    status: CacheStatus,
    source_revision: str,
    payload_bytes: int | None,
    stored: bool,
) -> dict[str, object]:
    return {
        "status": status,
        "source_revision": source_revision,
        "freshness": "current",
        "payload_bytes": payload_bytes,
        "stored": stored,
    }


def _serialize(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_query(query: str) -> tuple[tuple[str, str], ...]:
    values_by_name: dict[str, list[str]] = {}
    for name, value in parse_qsl(query, keep_blank_values=True):
        values_by_name.setdefault(name, []).append(value)
    return tuple((name, value) for name in sorted(values_by_name) for value in values_by_name[name])


def _result(
    key: AggregateQueryCacheKey,
    body: bytes,
    status: CacheStatus,
    *,
    stored: bool,
) -> AggregateQueryResult:
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise TypeError("aggregate cache payload must be a JSON object")
    return AggregateQueryResult(
        payload=payload,
        status=status,
        source_revision=key.source_revision,
        payload_bytes=len(body),
        stored=stored,
    )


def _dependency_name(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def _dependency_revision(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "missing"
