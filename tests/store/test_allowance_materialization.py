from dataclasses import replace
from datetime import datetime, timezone

from codex_usage_tracker.store.allowance_materialization import materialize_allowance_intelligence
from codex_usage_tracker.store.api import connect, upsert_usage_events
from tests.store_dashboard_helpers import _usage_event


def test_materialization_is_canonical_idempotent_and_archive_safe(tmp_path):
    db = tmp_path / "usage.sqlite3"
    active = _usage_event(record_id="active", session_id="s", thread_key="t", event_timestamp="2025-12-31T23:58:00Z", cumulative_total_tokens=10, rate_limit_primary_used_percent=10.0, rate_limit_primary_window_minutes=10080, rate_limit_primary_resets_at=2_000_000_000)
    archived = replace(_usage_event(record_id="archived", session_id="s2", thread_key="t2", event_timestamp="2025-12-31T23:59:00Z", cumulative_total_tokens=20, rate_limit_primary_used_percent=20.0, rate_limit_primary_window_minutes=10080, rate_limit_primary_resets_at=2_000_000_000), is_archived=True)
    upsert_usage_events([active, archived], db)
    with connect(db) as conn:
        assert materialize_allowance_intelligence(conn, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert not materialize_allowance_intelligence(conn, now=datetime(2026, 1, 1, tzinfo=timezone.utc))
        assert conn.execute("SELECT COUNT(*) FROM allowance_cycles WHERE is_archived=0").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM allowance_cycles WHERE is_archived=1").fetchone()[0] == 1
        assert conn.execute("SELECT allowance_generation FROM allowance_source_state").fetchone()[0] == 1
