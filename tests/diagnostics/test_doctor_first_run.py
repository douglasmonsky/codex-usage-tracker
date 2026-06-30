from __future__ import annotations

import sys
from pathlib import Path

from codex_usage_tracker.core.formatting import format_doctor
from codex_usage_tracker.diagnostics.api import run_doctor


def test_doctor_reports_first_run_environment(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    sessions_dir = codex_home / "sessions" / "2026" / "06"
    sessions_dir.mkdir(parents=True)
    (sessions_dir / "session.jsonl").write_text("{}\n", encoding="utf-8")

    report = run_doctor(
        codex_home=codex_home,
        db_path=tmp_path / "usage.sqlite3",
        dashboard_path=tmp_path / "dashboard.html",
        pricing_path=tmp_path / "pricing.json",
        plugin_link=tmp_path / "plugins" / "codex-usage-tracker",
        marketplace_path=tmp_path / "marketplace.json",
        repo_root=None,
    )

    environment = report["environment"]

    assert environment["package"]["version"]
    assert environment["python"]["version"] == sys.version.split()[0]
    assert environment["paths"]["codex_home"] == str(codex_home)
    assert environment["paths"]["db_path"] == str(tmp_path / "usage.sqlite3")
    assert environment["codex_logs"]["sessions_dir_exists"] is True
    assert environment["codex_logs"]["jsonl_files"] == 1
    assert environment["dashboard_assets"]["available"] is True
    assert environment["dashboard_assets"]["missing"] == []

    text = format_doctor(report)

    assert "Environment:" in text
    assert "Package: codex-usage-tracker" in text
    assert "Codex logs:" in text
    assert "Dashboard assets: available" in text
