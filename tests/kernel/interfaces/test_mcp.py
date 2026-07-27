from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.interfaces.mcp.server import McpServer
from scripts.smoke_installed_package import _write_mcp

from .support import active_runtime, synthetic_sources


def test_mcp_catalog_and_calls_use_structured_results_without_duplication(
    tmp_path: Path,
) -> None:
    app = KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: synthetic_sources(),
    )
    server = McpServer(app)

    initialized = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        }
    )
    listed = server.handle(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    )
    called = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "usage_status", "arguments": {}},
        }
    )

    assert initialized["result"]["serverInfo"]["name"] == "codex-usage-tracker"
    assert [tool["name"] for tool in listed["result"]["tools"]] == [
        "usage_status",
        "usage_refresh",
        "usage_query",
        "usage_evidence",
        "usage_allowance",
        "usage_job_status",
    ]
    result = called["result"]
    assert result["structuredContent"]["generation"] == 1
    assert result["content"] == [
        {
            "type": "text",
            "text": "Kernel result is available in structuredContent.",
        }
    ]
    assert json.dumps(result["structuredContent"], sort_keys=True) not in str(
        result["content"]
    )


def test_direct_stdio_handshake_lists_exact_catalog(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    environment["CODEX_HOME"] = str(tmp_path / "codex-home")
    environment["CODEX_USAGE_TRACKER_CACHE_ROOT"] = str(tmp_path / "cache")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "codex_usage_tracker.kernel.interfaces.mcp.server",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    requests = (
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    for request in requests:
        process.stdin.write(json.dumps(request).encode() + b"\n")
    process.stdin.flush()
    responses = [json.loads(process.stdout.readline()) for _ in requests]
    process.terminate()
    process.wait(timeout=5)

    assert responses[0]["result"]["capabilities"]["tools"]["listChanged"] is False
    assert len(responses[1]["result"]["tools"]) == 6
    assert process.returncode is not None


def test_invalid_envelopes_and_inputs_are_rejected_before_side_effects(
    tmp_path: Path,
) -> None:
    launches = []
    app = KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=launches.append,
        source_provider=lambda _home: synthetic_sources(),
    )
    server = McpServer(app)

    wrong_version = server.handle(
        {"jsonrpc": "1.0", "id": 1, "method": "ping", "params": {}}
    )
    notification = server.handle(
        {"jsonrpc": "2.0", "method": "tools/call", "params": {}}
    )
    initialized = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {"protocolVersion": "1900-01-01"},
        }
    )
    invalid_refresh = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "usage_refresh",
                "arguments": {"wait_seconds": 31, "unexpected": True},
            },
        }
    )

    assert wrong_version["error"]["code"] == -32600
    assert notification is None
    assert initialized["result"]["protocolVersion"] == "2025-06-18"
    assert invalid_refresh["result"]["isError"] is True
    assert launches == []


def test_corrupt_cache_returns_a_sanitized_tool_error(tmp_path: Path) -> None:
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    runtime.kernel.operational.parent.mkdir(parents=True)
    runtime.kernel.operational.write_bytes(b"not sqlite")
    server = McpServer(
        KernelApplication(runtime, worker_launcher=lambda _paths: None)
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "usage_status", "arguments": {}},
        }
    )

    assert response["result"]["isError"] is True
    assert response["result"]["content"][0]["text"] == (
        "kernel cache is unavailable"
    )


def test_installed_smoke_terminates_a_nonresponsive_mcp_process() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    started = time.monotonic()
    with pytest.raises(TimeoutError, match="deadline"):
        _write_mcp(
            process,
            {"jsonrpc": "2.0", "id": 1, "method": "ping"},
            timeout=0.05,
        )

    assert time.monotonic() - started < 2
    assert process.poll() is not None
