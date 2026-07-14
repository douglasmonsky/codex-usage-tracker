from __future__ import annotations

from codex_usage_tracker.server.route_inventory import DASHBOARD_ROUTE_PROFILES
from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
)


def test_route_inventory_covers_every_registered_api_route_once() -> None:
    expected = {
        *(("GET", path) for path in GET_ROUTE_METHODS),
        *(("GET", path) for path in GET_DIAGNOSTIC_FACT_ROUTES),
        *(("POST", path) for path in POST_ROUTE_METHODS),
    }
    actual = [(profile.method, profile.path) for profile in DASHBOARD_ROUTE_PROFILES]

    assert len(actual) == len(set(actual))
    assert set(actual) == expected


def test_route_inventory_has_decision_ready_execution_metadata() -> None:
    for profile in DASHBOARD_ROUTE_PROFILES:
        assert profile.path.startswith("/api/")
        assert profile.handler.startswith("_handle_")
        assert profile.owner.startswith("server.")
        assert profile.scope_behavior
        assert profile.result_bound
        assert profile.cache_behavior

    recommendations = next(
        profile for profile in DASHBOARD_ROUTE_PROFILES if profile.path == "/api/recommendations"
    )
    assert recommendations.workload == "bounded_report"
    assert recommendations.may_scan_all_history is True

    heavy_routes = [
        profile for profile in DASHBOARD_ROUTE_PROFILES if profile.workload == "heavy_analysis"
    ]
    assert heavy_routes
    assert all(profile.execution == "async_start" for profile in heavy_routes)
    assert not any(
        profile.execution == "synchronous" and profile.workload == "heavy_analysis"
        for profile in DASHBOARD_ROUTE_PROFILES
    )

    compression = {
        profile.path: profile
        for profile in DASHBOARD_ROUTE_PROFILES
        if profile.path.startswith("/api/compression/")
    }
    assert compression["/api/compression/start"].execution == "async_start"
    assert compression["/api/compression/start"].workload == "heavy_analysis"
    assert compression["/api/compression/status"].execution == "poll"
    assert compression["/api/compression/status"].workload == "interactive"
    assert compression["/api/compression/profile"].execution == "synchronous"
    assert compression["/api/compression/profile"].workload == "bounded_report"
