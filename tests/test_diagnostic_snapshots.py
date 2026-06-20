from __future__ import annotations

import json
from pathlib import Path

from store_dashboard_helpers import _assert_contract, _make_codex_home

from codex_usage_tracker.diagnostic_snapshots import (
    DIAGNOSTIC_OVERVIEW_SECTION,
    build_diagnostic_overview_report,
)
from codex_usage_tracker.store import (
    query_diagnostic_snapshot,
    refresh_usage_index,
    upsert_diagnostic_snapshot,
)


def test_diagnostic_overview_snapshot_is_explicit_and_aggregate_only(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"

    missing_before_refresh = build_diagnostic_overview_report(db_path=db_path).payload
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    missing_after_usage_refresh = build_diagnostic_overview_report(db_path=db_path).payload
    refreshed = build_diagnostic_overview_report(db_path=db_path, refresh=True).payload
    stored = build_diagnostic_overview_report(db_path=db_path).payload

    _assert_contract(missing_before_refresh)
    _assert_contract(missing_after_usage_refresh)
    _assert_contract(refreshed)
    _assert_contract(stored)
    assert missing_before_refresh["status"] == "missing"
    assert missing_after_usage_refresh["status"] == "missing"
    assert refreshed["status"] == "ready"
    assert refreshed["refreshed"] is True
    assert stored["status"] == "ready"
    assert stored["refreshed"] is False
    assert refreshed["overview"]["usage_rows"] == 4
    assert refreshed["overview"]["total_tokens"] == 400
    assert refreshed["snapshot"]["history_scope"] == "active"
    assert refreshed["snapshot"]["raw_content_included"] is False

    serialized = json.dumps(refreshed, sort_keys=True)
    assert "SECRET RAW PROMPT" not in serialized
    assert "sk-proj" not in serialized
    assert "/tmp/codex-usage-tracker" not in serialized
    assert "AGENTS.md instructions" not in serialized


def test_usage_refresh_does_not_recompute_diagnostic_overview_snapshot(
    tmp_path: Path,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    build_diagnostic_overview_report(db_path=db_path, refresh=True)

    stale_payload = {
        "schema": "codex-usage-tracker-diagnostic-overview-v1",
        "section": DIAGNOSTIC_OVERVIEW_SECTION,
        "status": "ready",
        "refreshed": True,
        "raw_context_included": False,
        "snapshot": {
            "computed_at": "2000-01-01T00:00:00+00:00",
            "history_scope": "active",
            "source_logs_scanned": 1,
            "usage_rows_scanned": 1,
            "raw_content_included": False,
        },
        "overview": {"usage_rows": 1, "total_tokens": 7},
        "notes": [],
    }
    upsert_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope="active",
        payload=stale_payload,
        computed_at="2000-01-01T00:00:00+00:00",
        source_logs_scanned=1,
        usage_rows_scanned=1,
    )

    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    stored = query_diagnostic_snapshot(
        db_path=db_path,
        section=DIAGNOSTIC_OVERVIEW_SECTION,
        history_scope="active",
    )

    assert stored is not None
    assert stored["computed_at"] == "2000-01-01T00:00:00+00:00"
    assert stored["payload"]["overview"]["total_tokens"] == 7
