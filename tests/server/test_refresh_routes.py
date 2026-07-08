from __future__ import annotations

from codex_usage_tracker.server.routes import GET_ROUTE_METHODS


def test_refresh_polling_routes_are_registered() -> None:
    assert GET_ROUTE_METHODS["/api/refresh/start"] == "_handle_refresh_start"
    assert GET_ROUTE_METHODS["/api/refresh/status"] == "_handle_refresh_status"
