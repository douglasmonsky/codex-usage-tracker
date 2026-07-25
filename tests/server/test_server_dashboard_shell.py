from __future__ import annotations

from codex_usage_tracker.server import dashboard_shell as server_dashboard_shell


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
