from __future__ import annotations

import argparse
import http.client
import importlib
import sys
import threading
import urllib.error
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from codex_usage_tracker.interfaces.cli.parser import build_parser
from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
from codex_usage_tracker.server.api import _UsageDashboardHandler

_ROOT = Path(__file__).resolve().parents[2]
_REMOVED_COMMANDS = {"dashboard", "open-dashboard"}
_REPLACEMENT = "codex-usage-tracker open"
_UPGRADE_GUIDE = (
    "https://github.com/douglasmonsky/codex-usage-tracker/blob/main/docs/upgrading-to-0.25.0.md"
)
_REMOVED_SCREENSHOTS = {
    "dashboard-call-investigator-evidence.png",
    "dashboard-call-investigator-preview.png",
    "dashboard-call-investigator.png",
    "dashboard-calls-preview.png",
    "dashboard-calls.png",
    "dashboard-details.png",
    "dashboard-diagnostics-git-expanded.png",
    "dashboard-diagnostics.png",
    "dashboard-insights.png",
    "dashboard-threads.png",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        fp: object,
        code: int,
        message: str,
        headers: object,
        new_url: str,
    ) -> None:
        del request, fp, code, message, headers, new_url
        return None


def _top_level_choices(parser: argparse.ArgumentParser) -> set[str]:
    subparsers = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    return set(subparsers.choices)


def _http_error(
    opener: urllib.request.OpenerDirector,
    request: str | urllib.request.Request,
) -> urllib.error.HTTPError:
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        opener.open(request, timeout=5)  # noqa: S310 - local synthetic test server
    return exc_info.value


def test_removed_static_commands_are_absent_from_the_parser() -> None:
    parser = build_parser()

    assert _REMOVED_COMMANDS.isdisjoint(_top_level_choices(parser))
    with pytest.raises(SystemExit) as dashboard_exit:
        parser.parse_args(["dashboard"])
    with pytest.raises(SystemExit) as open_exit:
        parser.parse_args(["open-dashboard"])
    assert dashboard_exit.value.code == 2
    assert open_exit.value.code == 2


@pytest.mark.parametrize("command", sorted(_REMOVED_COMMANDS))
def test_removed_static_commands_print_exact_migration_help(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_main = importlib.import_module("codex_usage_tracker.cli.main")
    monkeypatch.setattr(sys, "argv", ["codex-usage-tracker", command])
    monkeypatch.setitem(cli_main._COMMAND_HANDLERS, command, lambda _args: 99)

    assert cli_main.main() == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert _REPLACEMENT in captured.err
    assert _UPGRADE_GUIDE in captured.err


def test_removed_static_mcp_tool_is_absent_from_every_profile() -> None:
    for profile in ("core", "full", "developer"):
        assert "generate_usage_dashboard" not in {tool.name for tool in tools_for_profile(profile)}


def test_only_live_console_assets_and_locales_remain_packaged() -> None:
    dashboard_root = _ROOT / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard"
    assert sorted(path.name for path in dashboard_root.iterdir()) == [
        "locales",
        "react",
    ]

    package_patterns = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"dashboard/*"' not in package_patterns
    assert '"dashboard/locales/*"' in package_patterns
    assert '"dashboard/react/*"' in package_patterns

    for screenshots_root in (
        _ROOT / "docs" / "assets",
        _ROOT / "src" / "codex_usage_tracker" / "plugin_data" / "docs" / "assets",
    ):
        assert _REMOVED_SCREENSHOTS.isdisjoint(path.name for path in screenshots_root.iterdir())


def test_removed_static_modules_are_absent() -> None:
    dashboard_package = _ROOT / "src" / "codex_usage_tracker" / "dashboard"

    assert not (dashboard_package / "assets.py").exists()
    assert not (dashboard_package / "pricing_snapshot.py").exists()


def test_current_tooling_and_docs_use_live_console_replacements() -> None:
    preview_generator = (_ROOT / "scripts" / "generate_social_preview.py").read_text(
        encoding="utf-8"
    )
    assert _REMOVED_SCREENSHOTS.isdisjoint(
        screenshot for screenshot in _REMOVED_SCREENSHOTS if screenshot in preview_generator
    )
    for retained_screenshot in (
        "evidence-console-home.png",
        "evidence-console-explore-calls.png",
        "evidence-console-evidence-call.png",
    ):
        assert retained_screenshot in preview_generator

    current_docs = "\n".join(
        (_ROOT / relative_path).read_text(encoding="utf-8")
        for relative_path in (
            "README.md",
            "docs/architecture.md",
            "docs/install.md",
            "docs/pricing-and-credits.md",
        )
    )
    for removed_claim in (
        "codex-usage-tracker dashboard --pricing",
        "dashboard generator",
        "dashboard generation plus",
        "CSV export, dashboard generation",
        "builds aggregate-first static dashboard payloads",
    ):
        assert removed_claim not in current_docs


def test_server_redirects_root_and_returns_data_free_gone_page(
    tmp_path: Path,
) -> None:
    served_root = tmp_path / "served"
    served_root.mkdir()
    handler = partial(
        _UsageDashboardHandler,
        directory=str(served_root),
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        limit=5000,
        since=None,
        codex_home=tmp_path / ".codex",
        include_archived=False,
        dashboard_name="custom-dashboard.html",
        context_chars=2000,
        api_token="secret-test-token",
        context_api_enabled=True,
        refresh_lock=threading.Lock(),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        opener = urllib.request.build_opener(_NoRedirect)

        root = _http_error(opener, f"{base_url}/")
        assert root.code == 302
        assert root.headers["Location"] == "/react-dashboard.html"

        removed = _http_error(opener, f"{base_url}/dashboard.html")
        removed_body = removed.read().decode("utf-8")
        assert removed.code == 410
        assert "/react-dashboard.html" in removed_body
        assert "secret-test-token" not in removed_body
        assert '"rows"' not in removed_body
        assert "usage-data" not in removed_body

        configured = _http_error(opener, f"{base_url}/custom-dashboard.html")
        assert configured.code == 404

        for path, expected_status in (
            ("/", 302),
            ("/dashboard.html", 410),
        ):
            request = urllib.request.Request(f"{base_url}{path}", method="HEAD")
            response = _http_error(opener, request)
            assert response.code == expected_status
            assert response.read() == b""
            if path == "/dashboard.html":
                assert int(response.headers["Content-Length"]) == len(removed_body.encode("utf-8"))

        sentinel = tmp_path / "outside-assets.txt"
        sentinel.write_text("synthetic-private-sentinel", encoding="utf-8")
        sentinel_suffix = sentinel.as_posix().lstrip("/")
        for separator in ("/", "%2F"):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request(
                    "GET",
                    f"/codex-usage-tracker-assets/{separator}{sentinel_suffix}",
                )
                response = connection.getresponse()
                response_body = response.read()
            finally:
                connection.close()
            assert response.status == 404
            assert b"synthetic-private-sentinel" not in response_body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
