from __future__ import annotations

import json
import multiprocessing
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pytest

from codex_usage_tracker.kernel import content as content_module
from codex_usage_tracker.kernel import writer
from codex_usage_tracker.kernel.application import KernelApplication, RuntimePaths
from codex_usage_tracker.kernel.content import ContextComposition
from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.interfaces.http.app import API_PREFIX
from codex_usage_tracker.kernel.interfaces.http.server import create_server
from codex_usage_tracker.kernel.interfaces.mcp.server import McpServer
from codex_usage_tracker.kernel.lease import RefreshLeaseRepository
from codex_usage_tracker.kernel.live import GenerationJournal
from codex_usage_tracker.kernel.models import CutoverState
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)
from tests.kernel.test_ingest_pipeline import _token_line

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MATRIX_PATH = _REPO_ROOT / "config" / "kernel-fault-recovery-scale-v1.json"
_FAULT_SCENARIOS = {
    "corrupt_partial_jsonl",
    "file_append_during_scan",
    "replacement_and_truncation",
    "process_kill_at_writer_boundaries",
    "stale_and_live_foreign_leases",
    "disk_full_and_read_only_cache",
    "interrupted_staging_atomic_promotion",
    "watcher_restart_and_replay_expiry",
    "slow_or_disconnected_sse_client",
    "malformed_query_cursor_selector",
    "optional_content_worker_crash",
    "old_cache_rollback",
}
_SCALE_SCENARIOS = {
    "one_hundred_thousand_calls",
    "many_small_files_and_one_large_file",
    "one_thousand_active_threads",
    "high_tool_call_fan_out",
    "concurrent_console_mcp_export_refresh_reads",
    "long_running_append_active_source",
}


def test_k15_fault_and_scale_matrix_is_complete_and_executable() -> None:
    matrix = json.loads(_MATRIX_PATH.read_text(encoding="utf-8"))

    assert matrix["schema"] == "codex-usage-tracker.kernel-fault-recovery-scale.v1"
    assert matrix["feature_changes"] is False
    assert matrix["synthetic_fixtures_only"] is True
    assert {item["id"] for item in matrix["fault_matrix"]} == _FAULT_SCENARIOS
    assert {item["id"] for item in matrix["scale_matrix"]} == _SCALE_SCENARIOS
    assert all(item["proofs"] for item in matrix["fault_matrix"])
    assert all(item["proofs"] for item in matrix["scale_matrix"])
    assert matrix["upgrade_proofs"] == [
        "tests/kernel/test_fault_recovery_scale.py::"
        "test_ci_executes_public_026_to_candidate_upgrade_smoke"
    ]

    collected = _collected_test_ids()
    proofs = [
        proof
        for item in (*matrix["fault_matrix"], *matrix["scale_matrix"])
        for proof in item["proofs"]
    ]
    proofs.extend(matrix["upgrade_proofs"])
    for proof in proofs:
        assert proof in collected, f"missing K15 proof: {proof}"


def test_ci_executes_public_026_to_candidate_upgrade_smoke() -> None:
    workflow = (
        _REPO_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert workflow.count("--upgrade-from 0.26.0") == 1
    assert workflow.count("--upgrade-from 0.27.0") == 1


def test_corrupt_lines_are_counted_while_valid_rows_still_commit(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "rollout-corrupt.jsonl"
    source.parent.mkdir()
    complete = _source_prefix("corrupt-session") + "{not-json}\n"
    tail = _token_line("event-2", 20)
    source.write_text(
        complete + _token_line("event-1", 10) + tail[:-8],
        encoding="utf-8",
    )
    paths = kernel_paths(tmp_path / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)

    first = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="owner-1",
    )
    with sqlite3.connect(paths.analytical) as connection:
        diagnostics = connection.execute(
            "SELECT parse_warning_count, trailing_incomplete_bytes FROM sources"
        ).fetchone()
    assert first.inserted_calls == 1
    assert diagnostics is not None
    assert diagnostics[0] == 1
    assert diagnostics[1] > 0

    with source.open("a", encoding="utf-8") as handle:
        handle.write(tail[-8:])
    second = ingestor.refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id="owner-2",
    )
    assert second.inserted_calls == 1
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 2


@pytest.mark.filterwarnings(
    "ignore:This process.*multi-threaded.*:DeprecationWarning"
)
def test_every_writer_boundary_failure_recovers_without_false_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boundary_count = _count_append_writer_boundaries(
        tmp_path / "count",
        monkeypatch,
    )
    assert boundary_count >= 3

    boundaries: list[tuple[str, int]] = [
        ("analytical", boundary)
        for boundary in range(1, boundary_count + 1)
    ]
    boundaries.extend(
        [
            ("after_lease", 0),
            ("after_cutover_begin", 0),
            ("after_promotion", 0),
            ("before_job_completion", 0),
        ]
    )
    context = multiprocessing.get_context("fork")
    for kind, boundary in boundaries:
        workspace = tmp_path / f"{kind}-{boundary}"
        source, paths = _initial_source(workspace)
        _append_calls(source, 400, start=1)
        process = context.Process(
            target=_abrupt_refresh,
            args=(workspace, kind, boundary),
        )
        process.start()
        process.join(timeout=10)
        assert not process.is_alive()
        assert process.exitcode == 91

        interrupted = load_cutover_control(paths.operational)
        assert interrupted.state in {
            CutoverState.ACTIVE,
            CutoverState.BUILDING,
        }
        assert interrupted.active_generation in {1, 2}
        _expire_refresh_leases(paths.operational)
        recovered = KernelIngestor(
            paths.analytical,
            paths.operational,
        ).refresh(
            [source],
            trigger=RefreshTrigger.MCP_USAGE_REFRESH,
            owner_id=f"recovered-{kind}-{boundary}",
        )
        assert recovered.generation == 2
        with sqlite3.connect(paths.analytical) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM model_calls"
            ).fetchone()[0] == 401
        with sqlite3.connect(paths.operational) as connection:
            states = {
                str(row[0])
                for row in connection.execute(
                    "SELECT state FROM refresh_runs"
                )
            }
        assert states <= {"completed", "interrupted"}
        assert "completed" in states


@pytest.mark.parametrize(
    "failure",
    ["analytical_disk_full", "operational_disk_full", "operational_read_only"],
)
def test_disk_failures_do_not_replace_the_active_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    source, paths = _initial_source(tmp_path / failure)
    replacement = source.with_suffix(".replacement")
    replacement.write_text(
        _source_prefix("replacement-session") + _token_line("replacement", 20),
        encoding="utf-8",
    )
    replacement.replace(source)
    prior = load_cutover_control(paths.operational)
    assert prior.active_kernel_path is not None
    analytical_before = prior.active_kernel_path.read_bytes()

    with monkeypatch.context() as patch:
        if failure == "analytical_disk_full":
            @contextmanager
            def disk_full(path):
                del path
                raise sqlite3.OperationalError("database or disk is full")
                yield

            patch.setattr(writer, "short_writer_transaction", disk_full)
        else:
            original_plans = KernelIngestor._plans
            error = (
                sqlite3.OperationalError("database or disk is full")
                if failure == "operational_disk_full"
                else PermissionError("read-only cache directory")
            )

            def block_operational_after_acquire(self, observations, path):
                plans = original_plans(self, observations, path)
                patch.setattr(
                    RefreshLeaseRepository,
                    "_connection",
                    _blocked_operational_connection(error),
                )
                return plans

            patch.setattr(KernelIngestor, "_plans", block_operational_after_acquire)
        with pytest.raises(
            (PermissionError, sqlite3.OperationalError),
        ):
            KernelIngestor(paths.analytical, paths.operational).refresh(
                [source],
                trigger=RefreshTrigger.CLI_REFRESH,
                owner_id=failure,
            )

    failed = load_cutover_control(paths.operational)
    expected_state = (
        CutoverState.FAILED
        if failure == "analytical_disk_full"
        else CutoverState.ACTIVE
    )
    assert failed.state is expected_state
    assert failed.active_generation == prior.active_generation == 1
    assert failed.active_kernel_path == prior.active_kernel_path
    assert failed.active_kernel_path.read_bytes() == analytical_before
    _expire_refresh_leases(paths.operational)
    recovered = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id=f"{failure}-recovered",
    )
    assert recovered.generation == 2


def test_many_small_and_one_large_source_are_ingested_exactly(
    tmp_path: Path,
) -> None:
    sources = []
    for index in range(40):
        source = tmp_path / "sessions" / f"small-{index:03}.jsonl"
        _write_source(source, f"small-{index}", calls=1)
        sources.append(source)
    large = tmp_path / "sessions" / "large.jsonl"
    _write_source(large, "large", calls=160)
    sources.append(large)
    paths = kernel_paths(tmp_path / "cache")

    result = KernelIngestor(paths.analytical, paths.operational).refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="mixed-source-scale",
    )

    assert result.inserted_calls == 200
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0] == 41
        assert connection.execute(
            "SELECT COUNT(*) FROM model_calls"
        ).fetchone()[0] == 200


def test_one_thousand_threads_with_high_tool_fan_out_are_exact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions" / "thread-scale.jsonl"
    source.parent.mkdir()
    lines = []
    for index in range(1_000):
        lines.append(_source_prefix(f"thread-{index}", turn=f"turn-{index}"))
        lines.extend(
            _tool_line(f"call-{index}-{tool}", f"tool-{tool}")
            for tool in range(4)
        )
        lines.append(_token_line(f"event-{index}", 10))
    source.write_text("".join(lines), encoding="utf-8")
    paths = kernel_paths(tmp_path / "cache")

    result = KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="thread-tool-scale",
    )

    assert result.inserted_calls == 1_000
    assert result.inserted_tools == 4_000
    with sqlite3.connect(paths.analytical) as connection:
        assert connection.execute("SELECT COUNT(*) FROM threads").fetchone()[0] == 1_000
        assert connection.execute(
            "SELECT COUNT(*) FROM tool_calls"
        ).fetchone()[0] == 4_000


def test_console_mcp_and_export_reads_stay_on_the_active_generation_during_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, paths = _initial_source(tmp_path)
    _append_calls(source, 400, start=1)
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: (source,),
    )
    writer_paused = threading.Event()
    release_writer = threading.Event()
    original_insert = writer._insert_rows
    calls = 0

    def pause_after_first_batch(connection, table, rows):
        nonlocal calls
        calls += 1
        if calls == 2:
            writer_paused.set()
            if not release_writer.wait(timeout=5):
                raise TimeoutError("synthetic concurrent reads did not finish")
        return original_insert(connection, table, rows)

    monkeypatch.setattr(writer, "_insert_rows", pause_after_first_batch)
    errors = []

    def refresh() -> None:
        try:
            KernelIngestor(paths.analytical, paths.operational).refresh(
                [source],
                trigger=RefreshTrigger.MCP_USAGE_REFRESH,
                owner_id="concurrent-refresh",
            )
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=refresh)
    thread.start()
    assert writer_paused.wait(timeout=5)
    query = _query_payload()
    server = create_server(application)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    export_path = tmp_path / "concurrent-export.json"
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            http_future = executor.submit(_http_query, host, port, query)
            mcp_future = executor.submit(_mcp_query, application, query)
            export_future = executor.submit(
                _cli_export,
                runtime,
                query,
                export_path,
            )
            http_result = http_future.result(timeout=5)
            mcp_result = mcp_future.result(timeout=5)
            export_result = export_future.result(timeout=5)
        assert http_result["results"][0]["generation"] == 1
        assert mcp_result["results"][0]["generation"] == 1
        assert export_result["results"][0]["generation"] == 1
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        release_writer.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert load_cutover_control(paths.operational).active_generation == 2


@pytest.mark.filterwarnings(
    "ignore:This process.*multi-threaded.*:DeprecationWarning"
)
def test_abrupt_content_worker_death_recovers_without_accounting_changes(
    tmp_path: Path,
) -> None:
    source, paths = _initial_source(tmp_path)
    del source
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    content = ContextComposition(runtime.content, runtime.kernel.operational)
    content.enable(privacy_confirmed=True)
    accounting_before = paths.analytical.read_bytes()
    context = multiprocessing.get_context("fork")
    process = context.Process(
        target=_abrupt_content_index,
        args=(runtime,),
    )

    process.start()
    process.join(timeout=10)

    assert not process.is_alive()
    assert process.exitcode == 92
    assert paths.analytical.read_bytes() == accounting_before
    assert content.status()["indexed_generation"] is None
    recovered = content.index()
    assert recovered["indexed_generation"] == 1
    assert recovered["events"] >= 1
    assert content.delete()["state"] == "disabled"
    assert paths.analytical.read_bytes() == accounting_before


def test_real_sse_slow_and_disconnected_clients_do_not_block_reads(
    tmp_path: Path,
) -> None:
    source, paths = _initial_source(tmp_path)
    del source
    journal = GenerationJournal(paths.operational, retention=200)
    for generation in range(2, 102):
        journal.publish_generation(
            generation,
            publication_id=f"publication-{generation}",
            changed_sources=1,
            inserted_calls=1,
            inserted_tools=0,
            deleted_rows=0,
        )
    runtime = RuntimePaths(tmp_path / "codex-home", tmp_path / "cache")
    application = KernelApplication(
        runtime,
        worker_launcher=lambda _paths: None,
        source_provider=lambda _home: (),
    )
    server = create_server(application)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    host = str(server.server_address[0])
    port = int(server.server_address[1])
    slow = socket.create_connection((host, port), timeout=5)
    disconnected = socket.create_connection((host, port), timeout=5)
    request = (
        f"GET {API_PREFIX}/events?limit=100 HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Last-Event-ID: 1\r\n"
        "Connection: close\r\n\r\n"
    ).encode()
    try:
        slow.sendall(request)
        disconnected.sendall(request)
        disconnected.shutdown(socket.SHUT_RDWR)
        disconnected.close()
        status_request = Request(
            f"http://{host}:{port}{API_PREFIX}/status",
            headers={"Host": f"127.0.0.1:{port}"},
        )
        with urlopen(status_request, timeout=5) as response:
            status = json.loads(response.read())
        assert status["generation"] == 1
        assert b"event: snapshot_required" in _recv_http_response(slow)
    finally:
        slow.close()
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)
    assert not worker.is_alive()


def _collected_test_ids() -> set[str]:
    tests = set()
    for path in (_REPO_ROOT / "tests" / "kernel").rglob("test_*.py"):
        relative = path.relative_to(_REPO_ROOT).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("def test_"):
                name = line.removeprefix("def ").split("(", maxsplit=1)[0]
                tests.add(f"{relative}::{name}")
    return tests


def _source_prefix(session: str, *, turn: str = "turn-1") -> str:
    return (
        '{"timestamp":"2026-01-01T00:00:00Z","type":"session_meta",'
        f'"payload":{{"id":"{session}"}}}}\n'
        '{"timestamp":"2026-01-01T00:00:00Z","type":"turn_context",'
        f'"payload":{{"turn_id":"{turn}","model":"gpt-synthetic",'
        '"effort":"low"}}\n'
    )


def _tool_line(call_id: str, tool_name: str) -> str:
    return json.dumps(
        {
            "timestamp": "2026-01-01T00:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "call_id": call_id,
                "name": tool_name,
            },
        },
        separators=(",", ":"),
    ) + "\n"


def _write_source(path: Path, session: str, *, calls: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _source_prefix(session)
        + "".join(_token_line(f"{session}-{index}", 10) for index in range(calls)),
        encoding="utf-8",
    )


def _initial_source(root: Path):
    source = root / "sessions" / "rollout.jsonl"
    _write_source(source, "initial-session", calls=1)
    paths = kernel_paths(root / "cache")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id="initial",
    )
    return source, paths


def _append_calls(source: Path, count: int, *, start: int) -> None:
    with source.open("a", encoding="utf-8") as handle:
        handle.write(
            "".join(
                _token_line(f"event-{index}", index)
                for index in range(start, start + count)
            )
        )


def _count_append_writer_boundaries(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> int:
    source, paths = _initial_source(root)
    _append_calls(source, 400, start=1)
    original = writer._timed_writer
    count = 0

    @contextmanager
    def counted(path, timings, assert_fence=None):
        nonlocal count
        with original(path, timings, assert_fence) as connection:
            yield connection
        count += 1

    with monkeypatch.context() as patch:
        patch.setattr(writer, "_timed_writer", counted)
        KernelIngestor(paths.analytical, paths.operational).refresh(
            [source],
            trigger=RefreshTrigger.MCP_USAGE_REFRESH,
            owner_id="count-boundaries",
        )
    return count


def _abrupt_refresh(root: Path, kind: str, boundary: int) -> None:
    source = root / "sessions" / "rollout.jsonl"
    paths = kernel_paths(root / "cache")
    if kind == "analytical":
        original_writer = writer._timed_writer
        seen = 0

        @contextmanager
        def killed_writer(path, timings, assert_fence=None):
            nonlocal seen
            with original_writer(path, timings, assert_fence) as connection:
                yield connection
            seen += 1
            if seen == boundary:
                os._exit(91)

        writer._timed_writer = killed_writer
    elif kind == "after_lease":
        def killed_plans(self, observations, path):
            del self, observations, path
            os._exit(91)

        setattr(KernelIngestor, "_plans", killed_plans)  # noqa: B010
    elif kind == "after_cutover_begin":
        original_begin = KernelIngestor._begin_cutover

        def killed_begin(self, refresh_run_id, path):
            original_begin(self, refresh_run_id, path)
            os._exit(91)

        setattr(KernelIngestor, "_begin_cutover", killed_begin)  # noqa: B010
    elif kind == "after_promotion":
        original_promote = KernelIngestor._promote

        def killed_promote(self, path, generation):
            original_promote(self, path, generation)
            os._exit(91)

        setattr(KernelIngestor, "_promote", killed_promote)  # noqa: B010
    elif kind == "before_job_completion":
        def killed_complete(self, refresh_run_id, *, generation, result):
            del self, refresh_run_id, generation, result
            os._exit(91)

        setattr(  # noqa: B010
            RefreshLeaseRepository,
            "complete",
            killed_complete,
        )
    else:
        raise AssertionError(f"unknown abrupt boundary: {kind}")
    KernelIngestor(paths.analytical, paths.operational).refresh(
        [source],
        trigger=RefreshTrigger.MCP_USAGE_REFRESH,
        owner_id=f"abrupt-{kind}-{boundary}",
    )
    os._exit(93)


def _expire_refresh_leases(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            UPDATE refresh_runs
            SET lease_expires_at = '0'
            WHERE state IN ('queued', 'running')
            """
        )


def _blocked_operational_connection(error: BaseException):
    @contextmanager
    def blocked(_self):
        raise type(error)(str(error))
        yield

    return blocked


def _recv_http_response(connection: socket.socket) -> bytes:
    chunks: list[bytes] = []
    while True:
        chunk = connection.recv(16_384)
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)


def _http_query(
    host: str,
    port: int,
    query: dict[str, Any],
) -> dict[str, Any]:
    request = Request(
        f"http://{host}:{port}{API_PREFIX}/query",
        data=json.dumps(query).encode(),
        headers={
            "Content-Type": "application/json",
            "Host": f"127.0.0.1:{port}",
        },
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        return json.loads(response.read())


def _mcp_query(
    application: KernelApplication,
    query: dict[str, Any],
) -> dict[str, Any]:
    response = McpServer(application).handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "usage_query", "arguments": query},
        }
    )
    assert response is not None
    return response["result"]["structuredContent"]


def _cli_export(
    runtime: RuntimePaths,
    query: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(runtime.codex_home)
    environment["CODEX_USAGE_TRACKER_CACHE_ROOT"] = str(runtime.cache_root)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_usage_tracker.kernel.interfaces.cli.main",
            "export",
            "--request",
            json.dumps(query, separators=(",", ":")),
            "--output",
            str(output),
        ],
        cwd=_REPO_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return json.loads(output.read_text(encoding="utf-8"))


def _abrupt_content_index(runtime: RuntimePaths) -> None:
    original = content_module._scan_source

    def killed_scan(*args, **kwargs):
        original(*args, **kwargs)
        os._exit(92)

    content_module._scan_source = killed_scan
    ContextComposition(runtime.content, runtime.kernel.operational).index()
    os._exit(93)


def _query_payload() -> dict[str, Any]:
    return {
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["model"],
                "measures": ["calls", "total_tokens"],
                "limit": 10,
            }
        ]
    }
