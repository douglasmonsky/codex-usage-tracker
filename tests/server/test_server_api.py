from __future__ import annotations

from functools import partial
from pathlib import Path

import pytest

from codex_usage_tracker.interfaces.http.v2 import ApplicationHttpV2Services, HttpV2Facade
from codex_usage_tracker.server import api as server_api
from codex_usage_tracker.server.query_cache import AggregateQueryCache


@pytest.mark.parametrize(
    ("language", "dashboard_message", "legacy_message"),
    [
        (
            None,
            "Serving Codex usage dashboard at http://127.0.0.1:8765/react-dashboard.html",
            "Legacy dashboard fallback remains available at http://127.0.0.1:8765/dashboard.html",
        ),
        (
            "zh-Hans",
            "Codex 用量仪表盘正在运行：http://127.0.0.1:8765/react-dashboard.html",
            "旧版仪表盘备用入口：http://127.0.0.1:8765/dashboard.html",
        ),
    ],
)
def test_serve_dashboard_opens_react_dashboard_and_prints_legacy_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
    language: str | None,
    dashboard_message: str,
    legacy_message: str,
) -> None:
    opened: list[str] = []
    handlers: list[object] = []

    class FakeServer:
        def __init__(self, address: tuple[str, int], handler: object) -> None:
            self.address = address
            self.handler = handler
            handlers.append(handler)
            self.closed = False

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def server_close(self) -> None:
            self.closed = True

    def generate_dashboard(**kwargs: object) -> Path:
        return Path(str(kwargs["output_path"]))

    monkeypatch.setattr(server_api, "generate_dashboard", generate_dashboard)
    monkeypatch.setattr(server_api, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(server_api.webbrowser, "open", opened.append)

    server_api.serve_dashboard(
        db_path=tmp_path / "usage.sqlite3",
        output_path=tmp_path / "dashboard.html",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        thresholds_path=tmp_path / "thresholds.json",
        projects_path=tmp_path / "projects.json",
        host="127.0.0.1",
        port=8765,
        open_browser=True,
        language=language,
    )

    output = capsys.readouterr().out
    assert opened == ["http://127.0.0.1:8765/react-dashboard.html"]
    assert dashboard_message in output
    assert legacy_message in output
    assert handlers
    handler = handlers[0]
    assert isinstance(handler, partial)
    query_cache = handler.keywords["query_cache"]
    assert isinstance(query_cache, AggregateQueryCache)
    assert query_cache.max_entries == 64
    facade = handler.keywords["http_v2_facade"]
    assert isinstance(facade, HttpV2Facade)
    assert isinstance(facade.services, ApplicationHttpV2Services)
    assert facade.services.application.paths.projects_path == tmp_path / "projects.json"


def test_serve_dashboard_starts_requested_refresh_after_binding(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    events: list[object] = []

    class FakeServer:
        def __init__(self, address: tuple[str, int], handler: object) -> None:
            events.append(("bound", address, handler))

        def serve_forever(self) -> None:
            events.append("serving")
            raise KeyboardInterrupt

        def server_close(self) -> None:
            events.append("closed")

    def start_refresh(self, **kwargs: object) -> dict[str, object]:
        events.append(("refresh", kwargs))
        return {"job_id": "startup-job"}

    monkeypatch.setattr(server_api, "ThreadingHTTPServer", FakeServer)
    monkeypatch.setattr(
        server_api,
        "generate_dashboard",
        lambda **kwargs: Path(str(kwargs["output_path"])),
    )
    monkeypatch.setattr(server_api.RefreshJobRegistry, "start_refresh", start_refresh)

    server_api.serve_dashboard(
        db_path=tmp_path / "usage.sqlite3",
        output_path=tmp_path / "dashboard.html",
        codex_home=tmp_path / "codex-home",
        host="127.0.0.1",
        port=8765,
        refresh_on_start=True,
    )

    assert events[0][0] == "bound"
    assert events[1][0] == "refresh"
    assert events[1][1]["aggregate_only"] is False
    assert events[2:] == ["serving", "closed"]
    assert "Background refresh started: startup-job" in capsys.readouterr().out
