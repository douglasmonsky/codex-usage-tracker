from __future__ import annotations

import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from codex_usage_tracker.server.query_cache import (
    AggregateQueryCache,
    aggregate_query_cache_key,
    cached_aggregate_payload,
    current_source_revision,
)
from codex_usage_tracker.store.api import upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_cache_returns_immutable_copies() -> None:
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    key = aggregate_query_cache_key(
        route="/api/summary",
        query="limit=20&group_by=date",
        source_revision="generation:1",
        privacy_mode="normal",
    )

    first = cache.get_or_compute(key, lambda: {"rows": [{"group_key": "2026-07-14"}]})
    rows = first.payload["rows"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0]["group_key"] = "mutated"
    second = cache.get_or_compute(key, lambda: {"rows": []})

    assert first.status == "miss"
    assert first.stored is True
    assert second.status == "hit"
    assert second.stored is True
    assert second.payload["rows"] == [{"group_key": "2026-07-14"}]


def test_cache_coalesces_identical_in_flight_requests() -> None:
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    key = aggregate_query_cache_key(
        route="/api/recommendations",
        query="limit=20",
        source_revision="generation:2",
        privacy_mode="normal",
    )
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def build() -> dict[str, object]:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(timeout=2)
        return {"rows": [{"record_id": "call-1"}]}

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(cache.get_or_compute, key, build)
        assert entered.wait(timeout=2)
        follower = executor.submit(cache.get_or_compute, key, build)
        release.set()
        results = [owner.result(timeout=2), follower.result(timeout=2)]

    assert calls == 1
    assert {result.status for result in results} == {"miss", "coalesced"}
    assert results[0].payload == results[1].payload


def test_cache_bypasses_storage_for_oversized_payloads() -> None:
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=32)
    key = aggregate_query_cache_key(
        route="/api/recommendations",
        query="limit=10000",
        source_revision="generation:3",
        privacy_mode="normal",
    )
    calls = 0

    def build() -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"rows": [{"summary": "x" * 64}]}

    first = cache.get_or_compute(key, build)
    second = cache.get_or_compute(key, build)

    assert calls == 2
    assert first.status == second.status == "bypass"
    assert first.stored is second.stored is False
    assert first.payload_bytes > 32


def test_cache_marks_oversized_coalesced_payload_as_not_stored() -> None:
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=32)
    key = aggregate_query_cache_key(
        route="/api/recommendations",
        query="limit=10000",
        source_revision="generation:3",
        privacy_mode="normal",
    )
    entered = threading.Event()
    release = threading.Event()

    def build() -> dict[str, object]:
        entered.set()
        assert release.wait(timeout=2)
        return {"rows": [{"summary": "x" * 64}]}

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner = executor.submit(cache.get_or_compute, key, build)
        assert entered.wait(timeout=2)
        follower = executor.submit(cache.get_or_compute, key, build)
        release.set()
        results = [owner.result(timeout=2), follower.result(timeout=2)]

    assert {result.status for result in results} == {"bypass", "coalesced"}
    assert all(result.stored is False for result in results)


def test_cache_retries_after_builder_failure() -> None:
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    key = aggregate_query_cache_key(
        route="/api/summary",
        query="group_by=date",
        source_revision="generation:4",
        privacy_mode="normal",
    )

    with pytest.raises(RuntimeError, match="synthetic failure"):
        cache.get_or_compute(key, lambda: (_ for _ in ()).throw(RuntimeError("synthetic failure")))

    recovered = cache.get_or_compute(key, lambda: {"rows": []})

    assert recovered.status == "miss"
    assert recovered.stored is True


def test_cache_key_canonicalizes_query_order_and_tracks_semantic_inputs(tmp_path: Path) -> None:
    config = tmp_path / "pricing.json"
    config.write_text('{"version": 1}', encoding="utf-8")
    base = aggregate_query_cache_key(
        route="/api/summary",
        query="limit=20&group_by=date",
        source_revision="generation:4",
        privacy_mode="normal",
        dependencies=(config,),
    )

    reordered = aggregate_query_cache_key(
        route="/api/summary",
        query="group_by=date&limit=20",
        source_revision="generation:4",
        privacy_mode="normal",
        dependencies=(config,),
    )
    redacted = aggregate_query_cache_key(
        route="/api/summary",
        query="group_by=date&limit=20",
        source_revision="generation:4",
        privacy_mode="redact-projects",
        dependencies=(config,),
    )
    config.write_text('{"version": 2}', encoding="utf-8")
    reconfigured = aggregate_query_cache_key(
        route="/api/summary",
        query="group_by=date&limit=20",
        source_revision="generation:4",
        privacy_mode="normal",
        dependencies=(config,),
    )

    assert base == reordered
    assert base != redacted
    assert base != reconfigured

    repeated_values = aggregate_query_cache_key(
        route="/api/summary",
        query="model=gpt-5.6&model=gpt-5.5&limit=20",
        source_revision="generation:4",
        privacy_mode="normal",
    )
    reversed_values = aggregate_query_cache_key(
        route="/api/summary",
        query="limit=20&model=gpt-5.5&model=gpt-5.6",
        source_revision="generation:4",
        privacy_mode="normal",
    )

    assert repeated_values != reversed_values

    next_day = aggregate_query_cache_key(
        route="/api/summary",
        query="preset=today",
        source_revision="generation:4",
        privacy_mode="normal",
        semantic_inputs=(("calendar_date", "2026-07-15"),),
    )
    prior_day = aggregate_query_cache_key(
        route="/api/summary",
        query="preset=today",
        source_revision="generation:4",
        privacy_mode="normal",
        semantic_inputs=(("calendar_date", "2026-07-14"),),
    )

    assert prior_day != next_day


def test_source_revision_advances_after_aggregate_write(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    before = current_source_revision(db_path)

    upsert_usage_events(
        [
            _usage_event(
                record_id="call-1",
                session_id="session-1",
                thread_key="thread:one",
                event_timestamp="2026-07-14T12:00:00Z",
                cumulative_total_tokens=100,
            )
        ],
        db_path=db_path,
    )

    assert before == "generation:0"
    assert current_source_revision(db_path) == "generation:1"


def test_source_revision_remains_readable_during_active_writer(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events(
        [
            _usage_event(
                record_id="call-1",
                session_id="session-1",
                thread_key="thread:one",
                event_timestamp="2026-07-14T12:00:00Z",
                cumulative_total_tokens=100,
            )
        ],
        db_path=db_path,
    )
    writer = sqlite3.connect(db_path, timeout=0.1)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "UPDATE compression_source_state SET generation = generation + 1 WHERE singleton = 1"
        )

        started = time.perf_counter()
        revision = current_source_revision(db_path)
        elapsed = time.perf_counter() - started
    finally:
        writer.rollback()
        writer.close()

    assert revision == "generation:1"
    assert elapsed < 0.25


def test_intentionally_large_request_bypasses_before_serialization(tmp_path: Path) -> None:
    marker = object()
    payload = cached_aggregate_payload(
        AggregateQueryCache(max_entries=2, max_payload_bytes=32),
        route="/api/recommendations",
        query="limit=10000",
        db_path=tmp_path / "usage.sqlite3",
        privacy_mode="normal",
        dependencies=(),
        semantic_inputs=(),
        cacheable=False,
        build=lambda: {"rows": [marker]},
    )

    assert payload["rows"] == [marker]
    assert payload["query_cache"] == {
        "status": "bypass",
        "source_revision": "generation:0",
        "freshness": "current",
        "payload_bytes": None,
        "stored": False,
    }
