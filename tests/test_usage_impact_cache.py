from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from store_dashboard_helpers import SESSION_ID, _usage_event, _write_pricing

from codex_usage_tracker.store import connect, query_usage_api_events, upsert_usage_events
from codex_usage_tracker.usage_impact_cache import UsageImpactCache
from codex_usage_tracker.usage_impact_store import (
    query_usage_impact_recalculation_record_ids,
    query_usage_impact_rows,
    replace_usage_impact_from_annotated_rows,
)


def test_usage_impact_cache_reuses_full_history_estimates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from codex_usage_tracker import usage_impact_cache as cache_module

    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    events = []
    for index in range(5):
        events.append(
            replace(
                _usage_event(
                    record_id=f"baseline-{index}",
                    session_id=SESSION_ID,
                    thread_key="thread:Cache test",
                    event_timestamp=f"2026-06-15T12:{index * 2:02d}:00Z",
                    cumulative_total_tokens=100 + index * 100,
                ),
                rate_limit_primary_used_percent=10 + index,
                rate_limit_primary_window_minutes=300,
                rate_limit_primary_resets_at=1781562696,
            )
        )
        events.append(
            replace(
                _usage_event(
                    record_id=f"observed-{index}",
                    session_id=SESSION_ID,
                    thread_key="thread:Cache test",
                    event_timestamp=f"2026-06-15T12:{index * 2 + 1:02d}:00Z",
                    cumulative_total_tokens=150 + index * 100,
                ),
                rate_limit_primary_used_percent=11 + index,
                rate_limit_primary_window_minutes=300,
                rate_limit_primary_resets_at=1781562696,
            )
        )
    events.append(
        _usage_event(
            record_id="target",
            session_id=SESSION_ID,
            thread_key="thread:Cache test",
            event_timestamp="2026-06-15T12:15:00Z",
            cumulative_total_tokens=1000,
        )
    )
    upsert_usage_events(events, db_path=db_path)

    calls = 0
    original_annotate = cache_module.annotate_rows_with_usage_impact

    def counting_annotate(rows):
        nonlocal calls
        calls += 1
        return original_annotate(rows)

    monkeypatch.setattr(cache_module, "annotate_rows_with_usage_impact", counting_annotate)
    cache = UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )
    rows = query_usage_api_events(db_path=db_path, limit=1, include_archived=False)

    first = cache.copy_usage_impact(rows, include_archived=False)
    second = cache.copy_usage_impact(rows, include_archived=False)
    cache.invalidate()
    third = cache.copy_usage_impact(rows, include_archived=False)

    assert first[0]["usage_impact"] == second[0]["usage_impact"]
    assert third[0]["usage_impact"] == first[0]["usage_impact"]
    assert first[0]["record_id"] == "target"
    assert first[0]["usage_impact"]["primary"]["estimate_percent"] > 0
    assert calls == 1
    persisted = query_usage_impact_rows(db_path=db_path, record_id="target", limit=0)
    assert {row["window_type"] for row in persisted} == {"primary", "secondary"}
    assert persisted[0]["status"] in {"fresh", "unavailable"}


def test_usage_impact_cache_can_return_pending_without_blocking(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    event = _usage_event(
        record_id="target",
        session_id=SESSION_ID,
        thread_key="thread:Cache pending",
        event_timestamp="2026-06-15T12:00:00Z",
        cumulative_total_tokens=1000,
    )
    upsert_usage_events([event], db_path=db_path)
    rows = query_usage_api_events(db_path=db_path, limit=1, include_archived=False)
    cache = UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )
    started = threading.Event()
    release = threading.Event()

    def slow_build(*, include_archived: bool):
        assert include_archived is False
        started.set()
        assert release.wait(timeout=5)
        return {
            "target": {
                "primary": {
                    "estimate_percent": 0.12,
                    "lower_percent": 0.10,
                    "upper_percent": 0.14,
                },
                "secondary": None,
            }
        }

    monkeypatch.setattr(cache, "_build_impact_map", slow_build)

    first = cache.copy_usage_impact(rows, include_archived=False, block=False)

    assert started.wait(timeout=1)
    assert first[0]["record_id"] == "target"
    assert first[0]["usage_impact_pending"] is True
    assert first[0]["usage_impact"]["primary"]["status"] == "pending"
    assert first[0]["usage_impact"]["secondary"]["status"] == "pending"

    release.set()
    second = cache.copy_usage_impact(rows, include_archived=False, block=True)

    assert "usage_impact_pending" not in second[0]
    assert second[0]["usage_impact"]["primary"]["estimate_percent"] == 0.12


def test_usage_impact_cache_can_return_pending_without_scheduling_warm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    event = _usage_event(
        record_id="target",
        session_id=SESSION_ID,
        thread_key="thread:Cache pending",
        event_timestamp="2026-06-15T12:00:00Z",
        cumulative_total_tokens=1000,
    )
    upsert_usage_events([event], db_path=db_path)
    rows = query_usage_api_events(db_path=db_path, limit=1, include_archived=False)
    cache = UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )

    def fail_if_scheduled(*, include_archived: bool) -> None:
        raise AssertionError("live row slices must not schedule a full usage-impact warm")

    monkeypatch.setattr(cache, "warm_async", fail_if_scheduled)

    result = cache.copy_usage_impact(
        rows,
        include_archived=False,
        block=False,
        schedule_warm=False,
    )

    assert result[0]["record_id"] == "target"
    assert result[0]["usage_impact_pending"] is True
    assert result[0]["usage_impact"]["primary"]["status"] == "pending"
    assert result[0]["usage_impact"]["secondary"]["status"] == "pending"


def test_usage_impact_cache_warm_async_is_single_flight_per_history_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from codex_usage_tracker import usage_impact_cache as cache_module

    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    cache = UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )
    signature = cache_module._FileSignature(path="missing", mtime_ns=None, size_bytes=None)
    key_counter = 0

    def changing_cache_key(*, include_archived: bool):
        nonlocal key_counter
        key_counter += 1
        return cache_module._ImpactCacheKey(
            include_archived=include_archived,
            latest_refresh_at=f"refresh-{key_counter}",
            scoped_rows=key_counter,
            max_event_timestamp=f"2026-06-15T12:00:{key_counter:02d}Z",
            pricing=signature,
            allowance=signature,
            rate_card=signature,
        )

    started_threads: list[object] = []

    class FakeThread:
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs
            started_threads.append(self)

        def start(self) -> None:
            return None

    monkeypatch.setattr(cache, "_cache_key", changing_cache_key)
    monkeypatch.setattr(cache_module.threading, "Thread", FakeThread)

    cache.warm_async(include_archived=False)
    cache.warm_async(include_archived=False)
    cache.warm_async(include_archived=True)

    assert len(started_threads) == 2


def test_usage_impact_cache_warm_pending_targets_recalculation_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = _write_pricing(tmp_path / "pricing.json")
    events = [
        _usage_event(
            record_id="fresh",
            session_id=SESSION_ID,
            thread_key="thread:Cache pending",
            event_timestamp="2026-06-15T12:00:00Z",
            cumulative_total_tokens=100,
        ),
        _usage_event(
            record_id="target",
            session_id=SESSION_ID,
            thread_key="thread:Cache pending",
            event_timestamp="2026-06-15T12:01:00Z",
            cumulative_total_tokens=200,
        ),
    ]
    upsert_usage_events(events, db_path=db_path)
    replace_usage_impact_from_annotated_rows(
        db_path=db_path,
        rows=[
            {
                "record_id": "fresh",
                "total_tokens": 100,
                "usage_credits": 1.0,
                "usage_impact": {
                    "primary": {
                        "estimate_percent": 0.1,
                        "lower_percent": 0.05,
                        "upper_percent": 0.15,
                        "basis": "credits",
                        "source": "observed_interval",
                    },
                    "secondary": None,
                },
            },
            {
                "record_id": "target",
                "total_tokens": 200,
                "usage_credits": 2.0,
                "usage_impact": {
                    "primary": {
                        "estimate_percent": 0.2,
                        "lower_percent": 0.1,
                        "upper_percent": 0.3,
                        "basis": "credits",
                        "source": "observed_interval",
                    },
                    "secondary": None,
                },
            },
        ],
    )
    with connect(db_path) as conn:
        conn.execute(
            """
            UPDATE usage_impact
            SET status = 'stale'
            WHERE record_id = 'target'
            """
        )
    captured_record_ids: list[list[str]] = []

    class ImmediateThread:
        def __init__(self, *args, **kwargs) -> None:
            self.kwargs = kwargs

        def start(self) -> None:
            self.kwargs["target"](**self.kwargs["kwargs"])

    cache = UsageImpactCache(
        db_path=db_path,
        pricing_path=pricing_path,
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
    )

    def capture_rebuild(record_ids: list[str], *, include_archived: bool) -> dict[str, int]:
        assert include_archived is False
        captured_record_ids.append(record_ids)
        return {"records": len(record_ids), "rows": len(record_ids) * 2}

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    monkeypatch.setattr(cache, "_rebuild_records", capture_rebuild)

    pending_ids = query_usage_impact_recalculation_record_ids(
        db_path=db_path,
        include_archived=False,
    )
    cache.warm_pending_async(include_archived=False)

    assert pending_ids == ["target"]
    assert captured_record_ids == [["target"]]


def test_usage_impact_read_model_materializes_without_raw_content(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    replace_usage_impact_from_annotated_rows(
        db_path=db_path,
        rows=[
            {
                "record_id": "record-secret",
                "total_tokens": 100,
                "usage_credits": 1.5,
                "rate_limit_primary_used_percent": 10,
                "rate_limit_primary_window_minutes": 300,
                "rate_limit_primary_resets_at": 1781562696,
                "usage_impact": {
                    "primary": {
                        "estimate_percent": 0.25,
                        "lower_percent": 0.1,
                        "upper_percent": 0.3,
                        "observed_delta_percent": 1.0,
                        "interval_call_count": 4,
                        "basis": "credits",
                        "source": "observed_interval",
                        "previous_observed_record_id": "baseline",
                        "previous_used_percent": 9.0,
                        "next_observed_record_id": "record-secret",
                        "source_note": "SECRET RAW PROMPT should not persist",
                    },
                    "secondary": None,
                },
            }
        ],
    )

    rows = query_usage_impact_rows(db_path=db_path, record_id="record-secret", limit=0)
    serialized = str(rows)

    assert len(rows) == 2
    assert rows[0]["record_id"] == "record-secret"
    assert any(row["estimated_usage_percent"] == 0.25 for row in rows)
    assert "SECRET RAW PROMPT" not in serialized
