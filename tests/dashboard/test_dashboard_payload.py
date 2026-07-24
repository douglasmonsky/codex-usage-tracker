from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.dashboard.api import dashboard_payload
from codex_usage_tracker.store.api import export_usage_csv, refresh_usage_index
from tests.store_dashboard_helpers import _make_codex_home


def test_shared_dashboard_payload_and_csv_remain_aggregate_only(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage.csv"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, limit=0)
    exported = export_usage_csv(output_path=csv_path, db_path=db_path, limit=0)
    serialized = json.dumps(payload)

    assert exported == 4
    assert len(payload["rows"]) == 4
    assert "SECRET RAW PROMPT" not in serialized
    assert "SECRET RAW PROMPT" not in csv_path.read_text(encoding="utf-8")


def test_shared_dashboard_payload_preserves_live_console_metadata(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, include_rows=False)

    assert payload["rows"] == []
    assert payload["observed_usage"]["source"] == "token_count.rate_limits"
    assert payload["observed_usage"]["windows"][0]["key"] == "primary"
    assert payload["project_metadata_privacy"]["mode"] == "normal"
