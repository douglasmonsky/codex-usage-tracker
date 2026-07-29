from __future__ import annotations

import hashlib
import json
import selectors
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol, cast

import psutil  # type: ignore[import-untyped]

from .canonical import canonical_json_bytes, canonical_sha256
from .dbhub import (
    DBHUB_NPM_INTEGRITY,
    DBHUB_PACKAGE,
    DBHUB_VERSION,
    DbhubCustomTool,
    build_dbhub_run,
)

DBHUB_MEASUREMENTS_FILE = "dbhub-measurements.json"
_REQUEST_TIMEOUT_SECONDS = 30.0
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_EXPECTED_TOOLS = frozenset({"execute_sql", "search_objects", "top_sessions"})
_UNAVAILABLE_MEASUREMENT = {
    "reason_code": "tooling_does_not_report",
    "status": "unavailable",
}
_TOP_SESSIONS_SQL = """
SELECT
    session_id,
    calls,
    uncached_input_tokens,
    cached_input_tokens,
    reasoning_tokens,
    output_tokens
FROM session_usage_current
ORDER BY
    uncached_input_tokens DESC,
    cached_input_tokens DESC,
    output_tokens DESC,
    session_id
LIMIT 25
""".strip()


class DbhubRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProtocolResponse:
    payload: Mapping[str, object]
    raw: bytes


class _DbhubClient(Protocol):
    def __enter__(self) -> _DbhubClient: ...

    def __exit__(self, *args: object) -> None: ...

    def initialize(self) -> ProtocolResponse: ...

    def list_tools(self) -> ProtocolResponse: ...

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> ProtocolResponse: ...

    def process_tree_cpu_ns(self) -> int: ...


class _StderrDigest:
    def __init__(self, stream: IO[bytes]) -> None:
        self._stream = stream
        self._byte_count = 0
        self._digest = hashlib.sha256()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._drain, name="dbhub-stderr", daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        while chunk := self._stream.read(64 * 1024):
            with self._lock:
                self._byte_count += len(chunk)
                self._digest.update(chunk)

    def finish(self) -> None:
        self._thread.join(timeout=1.0)

    def diagnostic(self) -> str:
        with self._lock:
            return f"stderr_bytes={self._byte_count} stderr_sha256={self._digest.hexdigest()}"


class _BinaryMcpClient:
    def __init__(self, argv: tuple[str, ...], timeout_seconds: float) -> None:
        self._timeout_seconds = timeout_seconds
        try:
            self._process = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
            )
        except OSError as error:
            raise DbhubRunnerError("DBHub process could not be started") from error
        if (
            self._process.stdin is None
            or self._process.stdout is None
            or self._process.stderr is None
        ):
            self._process.kill()
            raise DbhubRunnerError("DBHub process pipes are unavailable")
        self._stdin = self._process.stdin
        self._stdout = self._process.stdout
        self._stderr = _StderrDigest(self._process.stderr)
        self._next_id = 1

    def __enter__(self) -> _BinaryMcpClient:
        return self

    def __exit__(self, *args: object) -> None:
        try:
            self._stdin.close()
            self._process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2.0)
        finally:
            self._stdout.close()
            if self._process.stderr is not None:
                self._process.stderr.close()
            self._stderr.finish()

    def _write(self, payload: Mapping[str, object]) -> None:
        try:
            self._stdin.write(canonical_json_bytes(payload))
            self._stdin.flush()
        except (BrokenPipeError, OSError) as error:
            raise DbhubRunnerError(
                f"DBHub protocol write failed ({self._stderr.diagnostic()})"
            ) from error

    def _readline(self) -> bytes:
        selector = selectors.DefaultSelector()
        try:
            selector.register(self._stdout, selectors.EVENT_READ)
            if not selector.select(self._timeout_seconds):
                raise DbhubRunnerError(
                    f"DBHub protocol response timed out ({self._stderr.diagnostic()})"
                )
            raw = self._stdout.readline(_MAX_RESPONSE_BYTES + 1)
        finally:
            selector.close()
        if not raw:
            raise DbhubRunnerError(f"DBHub protocol stream closed ({self._stderr.diagnostic()})")
        if len(raw) > _MAX_RESPONSE_BYTES or not raw.endswith(b"\n"):
            raise DbhubRunnerError("DBHub protocol response is unbounded or not newline-delimited")
        return raw

    def _request(self, method: str, params: Mapping[str, object]) -> ProtocolResponse:
        request_id = self._next_id
        self._next_id += 1
        self._write(
            {
                "id": request_id,
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )
        raw = self._readline()
        try:
            parsed = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DbhubRunnerError("DBHub returned invalid JSON") from error
        if not isinstance(parsed, dict) or parsed.get("id") != request_id:
            raise DbhubRunnerError("DBHub response does not match the request")
        if "error" in parsed:
            error_value = parsed["error"]
            error_code = error_value.get("code") if isinstance(error_value, dict) else None
            raise DbhubRunnerError(f"DBHub request failed with protocol error {error_code!r}")
        if "result" not in parsed:
            raise DbhubRunnerError("DBHub response is missing a result")
        return ProtocolResponse(payload=cast(dict[str, object], parsed), raw=raw)

    def initialize(self) -> ProtocolResponse:
        response = self._request(
            "initialize",
            {
                "capabilities": {},
                "clientInfo": {"name": "codex-usage-tracker-ck04", "version": "1"},
                "protocolVersion": "2025-06-18",
            },
        )
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return response

    def list_tools(self) -> ProtocolResponse:
        return self._request("tools/list", {})

    def call_tool(self, name: str, arguments: Mapping[str, object]) -> ProtocolResponse:
        return self._request("tools/call", {"arguments": arguments, "name": name})

    def process_tree_cpu_ns(self) -> int:
        try:
            root = psutil.Process(self._process.pid)
            processes = (root, *root.children(recursive=True))
        except (psutil.NoSuchProcess, psutil.AccessDenied) as error:
            raise DbhubRunnerError("DBHub process tree cannot be sampled") from error
        total_seconds = 0.0
        for process in processes:
            try:
                cpu_times = process.cpu_times()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            total_seconds += cpu_times.user + cpu_times.system
        return round(total_seconds * 1_000_000_000)


def verify_live_npm_integrity(
    *,
    command_runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
) -> str:
    argv = (
        "npm",
        "view",
        f"{DBHUB_PACKAGE}@{DBHUB_VERSION}",
        "dist.integrity",
        "--json",
    )
    try:
        completed = command_runner(
            argv,
            check=False,
            capture_output=True,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DbhubRunnerError("npm registry integrity lookup failed") from error
    if completed.returncode != 0:
        stderr_digest = hashlib.sha256(completed.stderr).hexdigest()
        raise DbhubRunnerError(
            "npm registry integrity lookup failed "
            f"(stderr_bytes={len(completed.stderr)} stderr_sha256={stderr_digest})"
        )
    try:
        integrity = json.loads(completed.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DbhubRunnerError("npm registry integrity response is invalid") from error
    if integrity != DBHUB_NPM_INTEGRITY:
        raise DbhubRunnerError("npm registry integrity differs from the frozen DBHub pin")
    return cast(str, integrity)


def _result(response: ProtocolResponse) -> Mapping[str, object]:
    result = response.payload.get("result")
    if not isinstance(result, dict):
        raise DbhubRunnerError("DBHub response result is invalid")
    return result


def _tool_data(response: ProtocolResponse) -> Mapping[str, object]:
    content = _result(response).get("content")
    if not isinstance(content, list) or len(content) != 1:
        raise DbhubRunnerError("DBHub tool response content is invalid")
    item = content[0]
    if (
        not isinstance(item, dict)
        or item.get("type") != "text"
        or not isinstance(item.get("text"), str)
    ):
        raise DbhubRunnerError("DBHub tool response is not one text item")
    try:
        envelope = json.loads(item["text"])
    except json.JSONDecodeError as error:
        raise DbhubRunnerError("DBHub tool response text is invalid JSON") from error
    if not isinstance(envelope, dict) or envelope.get("success") is not True:
        raise DbhubRunnerError("DBHub tool response reports failure")
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise DbhubRunnerError("DBHub tool response data is invalid")
    return data


def _rows(response: ProtocolResponse) -> tuple[dict[str, object], ...]:
    data = _tool_data(response)
    rows = data.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 25:
        raise DbhubRunnerError("DBHub top-sessions route returned an invalid row count")
    if not all(isinstance(row, dict) for row in rows):
        raise DbhubRunnerError("DBHub top-sessions rows are invalid")
    return tuple(cast(dict[str, object], row) for row in rows)


def _snapshot_state(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        mode = path.stat().st_mode & 0o777
    except OSError as error:
        raise DbhubRunnerError("DBHub disposable snapshot cannot be verified") from error
    return digest.hexdigest(), mode


def _verify_initialization(response: ProtocolResponse) -> None:
    result = _result(response)
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict) or server_info.get("version") != DBHUB_VERSION:
        raise DbhubRunnerError("DBHub server identity differs from the frozen version")


def _verify_tool_set(response: ProtocolResponse) -> None:
    tools = _result(response).get("tools")
    if not isinstance(tools, list):
        raise DbhubRunnerError("DBHub tool list is invalid")
    names = {
        tool.get("name")
        for tool in tools
        if isinstance(tool, dict) and isinstance(tool.get("name"), str)
    }
    if names != _EXPECTED_TOOLS or len(tools) != len(_EXPECTED_TOOLS):
        raise DbhubRunnerError("DBHub exposed tool set differs from the frozen contract")


def collect_dbhub_research(
    *,
    source_snapshot: Path,
    run_root: Path,
    qualification_run_id: str,
    registry_integrity_lookup: Callable[[], str] = verify_live_npm_integrity,
    client_factory: Callable[[tuple[str, ...], float], _DbhubClient] = _BinaryMcpClient,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, object]:
    integrity = registry_integrity_lookup()
    if integrity != DBHUB_NPM_INTEGRITY:
        raise DbhubRunnerError("npm registry integrity differs from the frozen DBHub pin")
    top_sessions = DbhubCustomTool(
        name="top_sessions",
        description="Return the 25 synthetic sessions with the most uncached input tokens.",
        statement=_TOP_SESSIONS_SQL,
    )
    run = build_dbhub_run(
        source_snapshot=source_snapshot,
        run_root=run_root,
        custom_tools=(top_sessions,),
        max_rows=25,
    )
    samples: dict[str, list[dict[str, object]]] = {
        "generic": [],
        "named_preset": [],
    }
    route_identity: tuple[int, str] | None = None
    with run.runtime_access(), client_factory(run.argv, _REQUEST_TIMEOUT_SECONDS) as client:
        _verify_initialization(client.initialize())
        _verify_tool_set(client.list_tools())
        for sequence_index in range(10):
            route = "generic" if sequence_index % 2 == 0 else "named_preset"
            before_state = _snapshot_state(run.snapshot_path)
            cpu_before = client.process_tree_cpu_ns()
            wall_before = clock_ns()
            if route == "generic":
                search = client.call_tool(
                    "search_objects",
                    {"object_type": "table", "pattern": "session_usage_current"},
                )
                search_data = _tool_data(search)
                if search_data.get("count") != 1:
                    raise DbhubRunnerError(
                        "DBHub schema search did not resolve the synthetic table"
                    )
                query = client.call_tool("execute_sql", {"sql": _TOP_SESSIONS_SQL})
                raw_response_bytes = len(search.raw) + len(query.raw)
                result_rows = _rows(query)
                mcp_calls = 2
            else:
                query = client.call_tool("top_sessions", {})
                raw_response_bytes = len(query.raw)
                result_rows = _rows(query)
                mcp_calls = 1
            wall_time_ns = clock_ns() - wall_before
            process_cpu_ns = client.process_tree_cpu_ns() - cpu_before
            after_state = _snapshot_state(run.snapshot_path)
            if before_state != after_state or after_state[0] != run.snapshot_sha256:
                raise DbhubRunnerError("DBHub disposable snapshot changed during a trial")
            result_sha256 = canonical_sha256(result_rows)
            current_identity = (len(result_rows), result_sha256)
            if route_identity is None:
                route_identity = current_identity
            elif current_identity != route_identity:
                raise DbhubRunnerError("generic and named_preset results differ")
            samples[route].append(
                {
                    "correct": True,
                    "mcp_calls": mcp_calls,
                    "process_cpu_ns": max(1, process_cpu_ns),
                    "response_bytes": raw_response_bytes,
                    "result_rows": len(result_rows),
                    "result_sha256": result_sha256,
                    "sample_id": f"{route}.{sequence_index // 2:02d}",
                    "scanned_rows": dict(_UNAVAILABLE_MEASUREMENT),
                    "sequence_index": sequence_index,
                    "sql_statements": dict(_UNAVAILABLE_MEASUREMENT),
                    "wall_time_ns": max(1, wall_time_ns),
                }
            )
    run.verify_unchanged()
    evidence: dict[str, object] = {
        "engine_level_read_only": False,
        "input_artifact_id": "dbhub.invocation",
        "model_operability": {
            "owner_packet_id": "CK-11",
            "required_evidence_fields": [
                "authorization",
                "exact_model_id",
                "host_version",
                "reasoning_effort",
                "runtime_version",
                "synthetic_input_artifact_id",
                "synthetic_input_sha256",
                "token_source",
            ],
            "status": "deferred",
        },
        "output_artifact_id": "dbhub.measurements",
        "package": run.package,
        "package_integrity": run.package_integrity,
        "snapshot_sha256_after": run.snapshot_sha256,
        "snapshot_sha256_before": run.snapshot_sha256,
        "tool_level_read_only": True,
        "trials": [
            {
                "executed_route": route,
                "executed_tool": "execute_sql" if route == "generic" else "top_sessions",
                "qualification_run_id": qualification_run_id,
                "samples": samples[route],
                "trial_id": route,
            }
            for route in ("generic", "named_preset")
        ],
        "version": run.version,
    }
    output_path = run_root / DBHUB_MEASUREMENTS_FILE
    try:
        with output_path.open("xb") as output:
            output.write(canonical_json_bytes(evidence))
    except FileExistsError as error:
        raise DbhubRunnerError("DBHub measurements already exist") from error
    return evidence
