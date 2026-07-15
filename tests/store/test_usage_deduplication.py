from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from codex_usage_tracker.core.models import UsageEvent
from codex_usage_tracker.store.api import connect, upsert_usage_events


def test_clone_copy_is_physical_but_not_billable(tmp_path: Path) -> None:
    original = _event("original", "/original.jsonl")
    copied = replace(original, record_id="clone", session_id="clone", source_file="/clone.jsonl")
    new = replace(copied, record_id="new", event_timestamp="2026-07-14T12:01:00Z")
    db_path = tmp_path / "usage.sqlite3"
    upsert_usage_events([original, copied, new], db_path)
    with connect(db_path) as conn:
        assert conn.execute("SELECT count(*) FROM usage_events").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM canonical_usage_events").fetchone()[0] == 2
        assert conn.execute("SELECT duplicate_reason FROM usage_events WHERE is_duplicate=1").fetchone()[0] == "copied_usage_fingerprint"


def _event(record_id: str, source_file: str) -> UsageEvent:
    return UsageEvent(record_id, "original", None, None, "2026-07-14T12:00:00Z", source_file, 1, "turn", "2026-07-14T11:59:00Z", None, "gpt-5.5", "high", None, None, None, None, None, 0, None, None, None, None, None, None, None, None, None, None, None, 258400, 90, 20, 10, 5, 100, 190, 40, 20, 10, 200)
