from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.interfaces.cli.main import COMMANDS
from codex_usage_tracker.kernel.interfaces.http.app import API_PREFIX, ROUTES
from codex_usage_tracker.kernel.interfaces.mcp.catalog import (
    FORBIDDEN_TOOL_NAMES,
    TOOL_SPECS,
)
from codex_usage_tracker.kernel.interfaces.schema_catalog import validate_input

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPECTED_TOOLS = (
    "usage_status",
    "usage_refresh",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
)


def test_catalog_routes_and_cli_are_exact_and_legacy_free() -> None:
    assert tuple(spec.name for spec in TOOL_SPECS) == _EXPECTED_TOOLS
    assert not (set(_EXPECTED_TOOLS) & FORBIDDEN_TOOL_NAMES)
    assert "usage_analyze" in FORBIDDEN_TOOL_NAMES
    assert API_PREFIX == "/api/kernel/v1"
    assert set(ROUTES) == {
        ("GET", f"{API_PREFIX}/status"),
        ("POST", f"{API_PREFIX}/refresh"),
        ("POST", f"{API_PREFIX}/query"),
        ("POST", f"{API_PREFIX}/evidence"),
        ("GET", f"{API_PREFIX}/allowance"),
        ("GET", f"{API_PREFIX}/jobs/{{job_id}}"),
        ("GET", f"{API_PREFIX}/events"),
    }
    assert COMMANDS == (
        "setup",
        "status",
        "refresh",
        "query",
        "export",
        "open",
        "service",
        "config",
        "content",
        "repair",
        "package",
    )


def test_public_tool_schemas_are_small_deterministic_and_coherent() -> None:
    schema_root = (
        _REPO_ROOT
        / "src"
        / "codex_usage_tracker"
        / "kernel"
        / "interfaces"
        / "schemas"
    )
    files = {path.stem: path for path in schema_root.glob("*.json")}

    assert set(files) == set(_EXPECTED_TOOLS)
    for spec in TOOL_SPECS:
        path = files[spec.name]
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload == spec.input_schema
        assert payload["type"] == "object"
        assert payload.get("additionalProperties") is False
        assert len(path.read_bytes()) <= 8_192


def test_usage_query_schema_allows_compact_guidance_discovery() -> None:
    validate_input(
        "usage_query",
        {"requests": [], "include_guidance": True},
    )


def test_usage_query_schema_teaches_closed_named_and_typed_requests() -> None:
    validate_input(
        "usage_query",
        {
            "requests": [
                {"template": "top_threads"},
                {
                    "dataset": "calls",
                    "operation": "share",
                    "dimensions": ["thread"],
                    "measures": ["total_tokens"],
                    "limit": 5,
                },
            ]
        },
    )

    for request in (
        {"template": "missing"},
        {"template": "top_threads", "dataset": "calls"},
        {"template": "top_threads", "allow_partial": True},
        {"dataset": "calls", "operation": "share", "unknown": True},
    ):
        with pytest.raises(ValueError):
            validate_input("usage_query", {"requests": [request]})


def test_release_plugin_declares_one_server_and_is_publishable() -> None:
    plugin = json.loads(
        (_REPO_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    mcp = json.loads((_REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))

    assert plugin["version"] == "0.28.0"
    assert plugin["mcpServers"] == "./.mcp.json"
    assert plugin["skills"] == "./skills/"
    assert plugin["bundle"]["runtime_version"] == "0.28.0"
    assert plugin["bundle"]["publishable"] is True
    assert list(mcp["mcpServers"]) == ["codex-usage-tracker"]
    server = mcp["mcpServers"]["codex-usage-tracker"]
    assert server["command"] == "codex-usage-tracker"
    assert server["args"] == ["_mcp"]
    assert "cwd" not in server
    assert "CODEX_USAGE_TRACKER_MCP_PROFILE" not in server.get("env", {})

    marketplace = json.loads(
        (
            _REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
        ).read_text(encoding="utf-8")
    )
    assert marketplace["name"] == "codex-usage-tracker"
    assert marketplace["plugins"] == [
        {
            "category": "Productivity",
            "name": "codex-usage-tracker",
            "policy": {
                "authentication": "ON_INSTALL",
                "installation": "AVAILABLE",
            },
            "source": {"path": ".", "source": "local"},
        }
    ]
