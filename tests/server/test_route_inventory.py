from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.core.json_contracts import known_json_schemas
from codex_usage_tracker.server.route_inventory import DASHBOARD_ROUTE_PROFILES
from codex_usage_tracker.server.routes import (
    GET_DIAGNOSTIC_FACT_ROUTES,
    GET_DYNAMIC_ROUTE_METHODS,
    GET_ROUTE_METHODS,
    POST_ROUTE_METHODS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
QUERY_CONTRACTS_PATH = (
    REPO_ROOT / "frontend" / "dashboard" / "src" / "data" / "dashboardQueryContracts.json"
)


def test_route_inventory_covers_every_registered_api_route_once() -> None:
    expected = {
        *(("GET", path) for path in GET_ROUTE_METHODS),
        *(("GET", path) for path in GET_DIAGNOSTIC_FACT_ROUTES),
        *(("GET", path) for path in GET_DYNAMIC_ROUTE_METHODS),
        *(("POST", path) for path in POST_ROUTE_METHODS),
    }
    actual = [(profile.method, profile.path) for profile in DASHBOARD_ROUTE_PROFILES]

    assert len(actual) == len(set(actual))
    assert set(actual) == expected


def test_route_inventory_has_decision_ready_execution_metadata() -> None:
    for profile in DASHBOARD_ROUTE_PROFILES:
        assert profile.path.startswith("/api/")
        assert profile.handler.startswith("_handle_")
        assert profile.owner.startswith(("server.", "interfaces.http."))
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

    stable_v2 = [profile for profile in DASHBOARD_ROUTE_PROFILES if profile.exposure == "stable"]
    assert {(profile.method, profile.path) for profile in stable_v2} == {
        ("GET", "/api/v2/status"),
        ("POST", "/api/v2/refresh"),
        ("GET", "/api/v2/jobs/{job_id}"),
        ("POST", "/api/v2/analyze"),
        ("POST", "/api/v2/query"),
        ("POST", "/api/v2/evidence"),
        ("POST", "/api/v2/allowance"),
        ("GET", "/api/v2/capabilities"),
    }
    assert all(profile.output_limit_bytes is not None for profile in stable_v2)
    assert all(
        profile.input_limit_bytes is not None for profile in stable_v2 if profile.method == "POST"
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


def test_frontend_query_contracts_match_registered_routes_and_schemas() -> None:
    contracts = json.loads(QUERY_CONTRACTS_PATH.read_text(encoding="utf-8"))
    ids = [contract["id"] for contract in contracts]
    endpoints = [contract["endpoint"] for contract in contracts]
    registered_paths = {profile.path for profile in DASHBOARD_ROUTE_PROFILES}
    schemas = set(known_json_schemas())

    assert len(ids) == len(set(ids))
    assert len(endpoints) == len(set(endpoints))
    assert {contract["dataClass"] for contract in contracts} <= {
        "snapshot",
        "aggregate",
        "detail",
        "heavyJob",
        "userAction",
    }
    for contract in contracts:
        endpoint = contract["endpoint"]
        if endpoint == "/api/diagnostics/{snapshot}":
            assert any(path.startswith("/api/diagnostics/") for path in registered_paths)
        else:
            assert endpoint in registered_paths
        if contract["schema"] is not None:
            assert contract["schema"] in schemas

    assert {
        contract["id"]: contract["schema"]
        for contract in contracts
        if contract["id"]
        in {
            "overview-summary",
            "overview-recommendations",
            "calls",
            "threads",
            "thread-calls",
        }
    } == {
        "overview-summary": "codex-usage-tracker-summary-v1",
        "overview-recommendations": "codex-usage-tracker-recommendations-v1",
        "calls": "codex-usage-tracker-calls-v1",
        "threads": "codex-usage-tracker-threads-v1",
        "thread-calls": "codex-usage-tracker-thread-calls-v1",
    }
