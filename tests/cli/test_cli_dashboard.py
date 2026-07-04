from __future__ import annotations

import argparse
import json
from pathlib import Path

from codex_usage_tracker.cli import dashboard as cli_dashboard
from codex_usage_tracker.core.json_contracts import validate_json_payload_contract


def test_serve_dashboard_json_reports_react_url_and_legacy_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    served: dict[str, object] = {}

    def serve_dashboard(**kwargs: object) -> None:
        served.update(kwargs)

    monkeypatch.setattr(cli_dashboard, "serve_dashboard", serve_dashboard)
    monkeypatch.setattr(cli_dashboard, "refresh_usage_index", lambda **_: {"schema": "ignored"})

    args = argparse.Namespace(
        allowance=tmp_path / "allowance.json",
        as_json=True,
        codex_home=tmp_path / "codex-home",
        context_api="explicit",
        context_chars=2000,
        db=tmp_path / "usage.sqlite3",
        host="127.0.0.1",
        include_archived=False,
        lang="en",
        limit=5000,
        no_context_api=False,
        open=True,
        output=tmp_path / "dashboard.html",
        port=8765,
        pricing=tmp_path / "pricing.json",
        privacy_mode="normal",
        projects=tmp_path / "projects.json",
        rate_card=tmp_path / "rate-card.json",
        refresh=False,
        since=None,
        thresholds=tmp_path / "thresholds.json",
    )

    assert cli_dashboard.run_serve_dashboard(args) == 0

    payload = json.loads(capsys.readouterr().out)
    validate_json_payload_contract(payload)
    assert payload["dashboard_url"] == "http://127.0.0.1:8765/react-dashboard.html"
    assert payload["legacy_dashboard_url"] == "http://127.0.0.1:8765/dashboard.html"
    assert payload["dashboard_path"] == str(tmp_path / "dashboard.html")
    assert served["open_browser"] is True
