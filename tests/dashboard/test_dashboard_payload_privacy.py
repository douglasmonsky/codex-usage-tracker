from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.dashboard.api import dashboard_payload
from codex_usage_tracker.store.api import EVENT_COLUMNS, export_usage_csv, refresh_usage_index
from tests.store_dashboard_helpers import _make_codex_home


def test_dashboard_payload_and_csv_privacy_mode_redact_project_metadata(tmp_path: Path) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    csv_path = tmp_path / "usage-redacted.csv"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)

    payload = dashboard_payload(db_path=db_path, privacy_mode="strict")
    exported = export_usage_csv(
        output_path=csv_path,
        db_path=db_path,
        privacy_mode="redacted",
    )
    csv_text = csv_path.read_text(encoding="utf-8")
    csv_header = csv_text.splitlines()[0].split(",")
    rows = payload["rows"]
    assert isinstance(rows, list)
    first_row = rows[0]
    assert isinstance(first_row, dict)
    project_privacy = payload["project_metadata_privacy"]
    assert isinstance(project_privacy, dict)

    assert exported == 4
    assert payload["privacy_mode"] == "strict"
    assert project_privacy["cwd_redacted"] is True
    assert str(first_row["cwd"]).startswith("[redacted cwd:")
    assert str(first_row["project_name"]).startswith("Project ")
    assert first_row["project_relative_cwd"] is None
    assert first_row["git_branch"] is None
    assert first_row["git_remote_label"] is None
    assert "/tmp/codex-usage-tracker" not in json.dumps(payload)
    assert "/tmp/codex-usage-tracker" not in csv_text
    assert "[redacted cwd:" in csv_text
    assert csv_header == EVENT_COLUMNS
