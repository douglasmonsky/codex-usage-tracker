from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

from store_dashboard_helpers import SESSION_ID, _usage_event, _write_pricing

from codex_usage_tracker.store import query_usage_api_events, upsert_usage_events
from codex_usage_tracker.usage_impact_cache import UsageImpactCache


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
    assert calls == 2


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
    assert first[0]["usage_impact"] == {"primary": None, "secondary": None}

    release.set()
    second = cache.copy_usage_impact(rows, include_archived=False, block=True)

    assert "usage_impact_pending" not in second[0]
    assert second[0]["usage_impact"]["primary"]["estimate_percent"] == 0.12
