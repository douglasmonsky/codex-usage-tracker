from __future__ import annotations

from functools import partial
from pathlib import Path

from codex_usage_tracker.server import api as server_api
from codex_usage_tracker.server.query_cache import AggregateQueryCache


def test_serve_dashboard_opens_react_dashboard_and_prints_legacy_fallback(
    tmp_path: Path,
    monkeypatch,
    capsys,
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
    )

    output = capsys.readouterr().out
    assert opened == ["http://127.0.0.1:8765/react-dashboard.html"]
    assert "Serving Codex usage dashboard at http://127.0.0.1:8765/react-dashboard.html" in output
    assert (
        "Legacy dashboard fallback remains available at http://127.0.0.1:8765/dashboard.html"
        in output
    )
    assert handlers
    handler = handlers[0]
    assert isinstance(handler, partial)
    query_cache = handler.keywords["query_cache"]
    assert isinstance(query_cache, AggregateQueryCache)
    assert query_cache.max_entries == 64
