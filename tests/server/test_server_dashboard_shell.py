from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.cli.plugin_installer import install_plugin
from codex_usage_tracker.server import dashboard_shell as server_dashboard_shell


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
    codex_home = tmp_path / ".codex"
    install_plugin(
        plugin_dir=codex_home.parent / "plugins" / "codex-usage-tracker",
        marketplace_path=tmp_path / "marketplace.json",
    )
    real_readiness = server_dashboard_shell.conversational_readiness
    readiness_homes: list[Path] = []

    def capture_readiness(*, codex_home: Path) -> dict[str, object]:
        readiness_homes.append(codex_home)
        return real_readiness(codex_home=codex_home)

    def dashboard_payload(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"shell_boot": True}

    monkeypatch.setattr(server_dashboard_shell, "dashboard_payload", dashboard_payload)
    monkeypatch.setattr(server_dashboard_shell, "conversational_readiness", capture_readiness)
    monkeypatch.setattr(
        server_dashboard_shell,
        "home_summary_payload",
        lambda **kwargs: {"schema": "codex-usage-tracker-home-summary-v1"},
    )

    payload = server_dashboard_shell.dashboard_shell_payload(
        "history=all&include_archived=false&lang=es",
        codex_home=codex_home,
        **_paths(tmp_path),
        privacy_mode="strict",
        since="2026-06-01",
        api_token="token",
        context_api_enabled=True,
        include_archived_default=False,
        language_default="en",
        limit_default=5000,
    )

    assert payload["shell_boot"] is True
    assert payload["conversational_analysis"]["state"] == "ready"
    assert payload["home_summary"] == {"schema": "codex-usage-tracker-home-summary-v1"}
    assert readiness_homes == [codex_home]
    assert str(codex_home) not in str(payload["conversational_analysis"])
    assert calls["limit"] == 5000
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
    monkeypatch.setattr(
        server_dashboard_shell,
        "home_summary_payload",
        lambda **kwargs: {"schema": "codex-usage-tracker-home-summary-v1"},
    )

    server_dashboard_shell.dashboard_shell_payload(
        "history=active",
        codex_home=tmp_path / ".codex",
        **_paths(tmp_path),
        privacy_mode="normal",
        since=None,
        api_token="token",
        context_api_enabled=False,
        include_archived_default=True,
        language_default="en",
        limit_default=5000,
    )

    assert calls["include_archived"] is False
    assert calls["language"] == "en"


def test_react_boot_defers_home_summary_without_reading_the_database() -> None:
    payload = server_dashboard_shell.react_dashboard_boot_payload(
        "",
        api_token="token",
        context_api_enabled=False,
        include_archived_default=False,
        language_default="en",
        limit_default=5000,
        privacy_mode="normal",
        since=None,
    )

    assert payload["home_summary_deferred"] is True
    assert "home_summary" not in payload
