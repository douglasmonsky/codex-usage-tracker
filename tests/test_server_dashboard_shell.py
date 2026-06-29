from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_dashboard_shell


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
        "projects_path": tmp_path / "projects.json",
    }


def test_dashboard_shell_payload_builds_lightweight_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def dashboard_payload(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"shell_boot": True}

    monkeypatch.setattr(server_dashboard_shell, "dashboard_payload", dashboard_payload)

    payload = server_dashboard_shell.dashboard_shell_payload(
        "history=all&include_archived=false&lang=es",
        **_paths(tmp_path),
        privacy_mode="strict",
        since="2026-06-01",
        api_token="token",
        context_api_enabled=True,
        include_archived_default=False,
        language_default="en",
    )

    assert payload == {"shell_boot": True}
    assert calls["limit"] == 0
    assert calls["offset"] == 0
    assert calls["include_rows"] is False
    assert calls["include_archived"] is False
    assert calls["language"] == "es"
    assert calls["privacy_mode"] == "strict"
    assert calls["api_token"] == "token"
    assert calls["context_api_enabled"] is True


def test_dashboard_shell_payload_history_scope_controls_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def dashboard_payload(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {}

    monkeypatch.setattr(server_dashboard_shell, "dashboard_payload", dashboard_payload)

    server_dashboard_shell.dashboard_shell_payload(
        "history=active",
        **_paths(tmp_path),
        privacy_mode="normal",
        since=None,
        api_token="token",
        context_api_enabled=False,
        include_archived_default=True,
        language_default="en",
    )

    assert calls["include_archived"] is False
    assert calls["language"] == "en"
