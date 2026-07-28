from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import codex_usage_tracker.kernel.application.service as application_service
import codex_usage_tracker.kernel.interfaces.mcp.server as mcp_server
from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.interfaces.mcp.server import (
    MAX_MESSAGE_BYTES,
    MAX_MODEL_CONTENT_BYTES,
    McpServer,
    _model_content,
)
from scripts.smoke_installed_package import _write_mcp

from .support import active_runtime, logical_split_runtime, synthetic_sources


def test_mcp_catalog_and_calls_use_structured_results_without_duplication(
    tmp_path: Path,
) -> None:
    app = KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=lambda _paths, _preset: None,
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


def test_guided_scope_batch_and_evidence_use_three_read_only_mcp_calls(
    tmp_path: Path,
) -> None:
    launches = []
    runtime = active_runtime(tmp_path)
    app = KernelApplication(
        runtime,
        worker_launcher=lambda paths, _preset: launches.append(paths),
        source_provider=lambda _home: synthetic_sources(),
    )
    server = McpServer(app)
    operational_before = runtime.kernel.operational.read_bytes()
    analytical_before = runtime.kernel.analytical.read_bytes()

    status = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "usage_status", "arguments": {}},
        }
    )["result"]["structuredContent"]
    batch = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {
                    "include_guidance": True,
                    "requests": [
                        {
                            "dataset": "calls",
                            "operation": "share",
                            "dimensions": ["thread"],
                            "measures": ["calls", "total_tokens"],
                            "limit": 10,
                        },
                        {
                            "dataset": "calls",
                            "operation": "aggregate",
                            "dimensions": ["model", "effort"],
                            "measures": ["calls", "total_tokens"],
                            "limit": 10,
                        },
                    ],
                },
            },
        }
    )["result"]["structuredContent"]
    selector = batch["results"][0]["evidence_selectors"][0]
    evidence = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "usage_evidence",
                "arguments": {
                    "selector": selector,
                    "view": "summary",
                    "limit": 10,
                },
            },
        }
    )["result"]["structuredContent"]

    assert status["generation"] == 1
    assert {result["generation"] for result in batch["results"]} == {1}
    assert evidence["generation"] == 1
    assert batch["guidance"]["templates"]["concentration"]["kind"] == (
        "query_template"
    )
    assert launches == []
    assert runtime.kernel.operational.read_bytes() == operational_before
    assert runtime.kernel.analytical.read_bytes() == analytical_before


def test_mcp_executes_named_top_threads_template_in_one_query_call(
    tmp_path: Path,
) -> None:
    server = McpServer(
        KernelApplication(
            active_runtime(tmp_path),
            worker_launcher=lambda _paths, _preset: None,
            source_provider=lambda _home: synthetic_sources(),
        )
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {
                    "include_guidance": True,
                    "requests": [{"template": "top_threads"}],
                },
            },
        }
    )

    result = response["result"]["structuredContent"]
    model_content = json.loads(result["model_summary"])
    query = result["results"][0]
    cost_context = result["results"][1]
    assert query["dataset"] == "calls"
    assert query["operation"] == "share"
    assert query["grade"] == "exact"
    assert query["normalized_scope"]["dimensions"] == ["thread"]
    assert query["rows"]
    assert "total_tokens" in query["rows"][0]
    assert query["evidence_selectors"]
    assert cost_context["grade"] == "estimated"
    assert "configured_cost_usd" in cost_context["rows"][0]
    assert result["guidance"]["templates"]["top_threads"]["requests"]
    assert model_content["results"][0]["rows"] == query["rows"]
    assert model_content["results"][0]["evidence_selectors"] == (
        query["evidence_selectors"]
    )
    assert "measure_coverage" in model_content["results"][1]
    text_content = response["result"]["content"][0]["text"]
    assert text_content == "Kernel result is available in structuredContent."
    assert result["model_summary"].startswith('{"results":[{"rows":')
    assert len(result["model_summary"].encode()) <= 65_536
    assert len(json.dumps(response, separators=(",", ":")).encode()) <= (
        MAX_MESSAGE_BYTES
    )


def test_mcp_top_threads_preserves_logical_identity_across_both_results(
    tmp_path: Path,
) -> None:
    server = McpServer(
        KernelApplication(
            logical_split_runtime(tmp_path),
            worker_launcher=lambda _paths, _preset: None,
        )
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {
                    "requests": [{"template": "top_threads"}],
                },
            },
        }
    )

    result = response["result"]["structuredContent"]
    model_content = json.loads(result["model_summary"])
    token_threads = [row["thread"] for row in result["results"][0]["rows"]]
    cost_threads = [row["thread"] for row in result["results"][1]["rows"]]
    assert token_threads == cost_threads
    assert len(token_threads) == len(set(token_threads)) == 2
    assert model_content["results"][0]["rows"] == result["results"][0]["rows"]
    assert model_content["results"][1]["rows"] == result["results"][1]["rows"]


@pytest.mark.parametrize(
    ("template", "result_count"),
    [
        ("weekly_drivers", 1),
        ("week_over_week", 1),
        ("latest_incremental_change", 2),
    ],
)
def test_mcp_executes_curated_agent_templates_in_one_call(
    tmp_path: Path,
    template: str,
    result_count: int,
) -> None:
    server = McpServer(
        KernelApplication(
            active_runtime(tmp_path),
            worker_launcher=lambda _paths, _preset: None,
            source_provider=lambda _home: synthetic_sources(),
        )
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {"requests": [{"template": template}]},
            },
        }
    )

    result = response["result"]["structuredContent"]
    assert len(result["results"]) == result_count
    assert {item["generation"] for item in result["results"]} == {1}
    assert all(item["rows"] for item in result["results"])
    assert len(result["model_summary"].encode()) <= MAX_MODEL_CONTENT_BYTES


def test_query_guidance_is_visible_in_bounded_model_summary(
    tmp_path: Path,
) -> None:
    server = McpServer(
        KernelApplication(
            RuntimePaths(tmp_path / "codex-home", tmp_path / "cache"),
            worker_launcher=lambda _paths, _preset: None,
        )
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {
                    "requests": [],
                    "include_guidance": True,
                },
            },
        }
    )

    result = response["result"]["structuredContent"]
    summary = json.loads(result["model_summary"])
    assert summary["guidance"]["templates"]["top_threads"]["label"]
    assert "requests" not in summary["guidance"]["templates"]["top_threads"]
    assert summary["guidance"]["datasets"]["calls"]["measures"]
    assert summary["guidance"]["filter_grammar"]["scalar_operators"]
    assert len(result["model_summary"].encode()) <= MAX_MODEL_CONTENT_BYTES


def test_mcp_response_envelope_fails_closed_at_byte_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = McpServer(
        KernelApplication(
            active_runtime(tmp_path),
            worker_launcher=lambda _paths, _preset: None,
            source_provider=lambda _home: synthetic_sources(),
        )
    )
    monkeypatch.setattr(mcp_server, "MAX_MESSAGE_BYTES", 1)

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {
                    "requests": [{"template": "top_threads"}],
                },
            },
        }
    )

    assert response["result"]["isError"] is True
    assert response["result"]["content"] == [
        {
            "type": "text",
            "text": "kernel response exceeds byte budget; lower request limits",
        }
    ]


def test_query_model_content_is_bounded_and_aggregate_only() -> None:
    rows = [
        {
            "thread": f"thread-{index:04d}",
            "thread_label": f"Synthetic project {index:04d}",
            "total_tokens": index * 100,
            "padding": "x" * 1_000,
        }
        for index in range(100)
    ]

    content = _model_content(
        "usage_query",
        {
            "results": [
                {
                    "dataset": "calls",
                    "operation": "share",
                    "generation": 1,
                    "grade": "exact",
                    "matched_count": 100,
                    "returned_count": 100,
                    "truncated": False,
                    "rows": rows,
                    "evidence_selectors": [
                        f"thread:thread-{index:04d}" for index in range(100)
                    ],
                    "coverage": {"measures": {}},
                }
            ]
        },
    )
    projected = json.loads(content)

    assert len(content.encode()) <= MAX_MODEL_CONTENT_BYTES
    assert projected["results"][0]["model_rows_returned"] < 100
    assert projected["results"][0]["model_rows_truncated"] is True
    assert "prompt" not in content
    assert "reasoning" not in content


def test_mcp_refresh_transports_hydration_preset(tmp_path: Path) -> None:
    launches = []
    server = McpServer(
        KernelApplication(
            RuntimePaths(tmp_path / "codex-home", tmp_path / "cache"),
            worker_launcher=lambda _paths, preset: launches.append(
                preset.value
            ),
            source_provider=lambda _home: (),
        )
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_refresh",
                "arguments": {"preset": "complete"},
            },
        }
    )

    assert "error" not in response
    assert launches == ["complete"]


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


def test_mcp_query_response_budget_returns_a_structured_tool_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(application_service, "MAX_QUERY_RESPONSE_BYTES", 1)
    server = McpServer(
        KernelApplication(
            RuntimePaths(tmp_path / "codex-home", tmp_path / "cache"),
            worker_launcher=lambda _paths, _preset: None,
        )
    )

    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "usage_query",
                "arguments": {
                    "requests": [],
                    "include_guidance": True,
                },
            },
        }
    )

    assert response["result"]["isError"] is True
    assert response["result"]["content"] == [
        {
            "type": "text",
            "text": "query response exceeds byte budget; lower request limits",
        }
    ]


def test_invalid_envelopes_and_inputs_are_rejected_before_side_effects(
    tmp_path: Path,
) -> None:
    launches = []
    app = KernelApplication(
        active_runtime(tmp_path),
        worker_launcher=lambda paths, _preset: launches.append(paths),
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
        KernelApplication(runtime, worker_launcher=lambda _paths, _preset: None)
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
