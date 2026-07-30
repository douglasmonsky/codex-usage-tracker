from __future__ import annotations

import importlib
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
dbhub_runner = importlib.import_module("shared.dbhub_runner")


def _source_snapshot(path: Path) -> tuple[dict[str, object], ...]:
    rows = tuple(
        {
            "cached_input_tokens": index * 3,
            "calls": index + 1,
            "output_tokens": index * 5,
            "reasoning_tokens": index * 7,
            "session_id": f"session-{index:02d}",
            "uncached_input_tokens": 10_000 - index,
        }
        for index in range(30)
    )
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE session_usage_current (
                session_id TEXT PRIMARY KEY,
                calls INTEGER NOT NULL,
                uncached_input_tokens INTEGER NOT NULL,
                cached_input_tokens INTEGER NOT NULL,
                reasoning_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO session_usage_current (
                session_id,
                calls,
                uncached_input_tokens,
                cached_input_tokens,
                reasoning_tokens,
                output_tokens
            ) VALUES (
                :session_id,
                :calls,
                :uncached_input_tokens,
                :cached_input_tokens,
                :reasoning_tokens,
                :output_tokens
            )
            """,
            rows,
        )
    return rows[:25]


class _Clock:
    def __init__(self) -> None:
        self.value = 1_000_000

    def __call__(self) -> int:
        self.value += 10_000
        return self.value


class _FakeClient:
    def __init__(
        self,
        rows: tuple[dict[str, object], ...],
        *,
        alter_named_result: bool = False,
    ) -> None:
        self._rows = rows
        self._alter_named_result = alter_named_result
        self._cpu_ns = 1_000_000
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def initialize(self) -> dbhub_runner.ProtocolResponse:
        return dbhub_runner.ProtocolResponse(
            payload={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "serverInfo": {"name": "DBHub MCP Server", "version": "0.24.0"},
                },
            },
            raw=b'{"id":1,"jsonrpc":"2.0","result":{}}\n',
        )

    def list_tools(self) -> dbhub_runner.ProtocolResponse:
        return dbhub_runner.ProtocolResponse(
            payload={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {"name": "execute_sql"},
                        {"name": "search_objects"},
                        {"name": "top_sessions"},
                    ]
                },
            },
            raw=b'{"id":2,"jsonrpc":"2.0","result":{"tools":[]}}\n',
        )

    def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> dbhub_runner.ProtocolResponse:
        self.calls.append((name, arguments))
        if name == "search_objects":
            data: object = {
                "count": 1,
                "results": [{"name": "session_usage_current", "type": "table"}],
            }
            raw = b"s" * 10
        else:
            rows = list(self._rows)
            if name == "top_sessions" and self._alter_named_result:
                rows = rows[:-1]
            data = {"count": len(rows), "rows": rows}
            raw = b"n" * 15 if name == "top_sessions" else b"e" * 20
        return dbhub_runner.ProtocolResponse(
            payload={
                "jsonrpc": "2.0",
                "id": len(self.calls) + 2,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"data": data, "success": True}),
                        }
                    ]
                },
            },
            raw=raw,
        )

    def process_tree_cpu_ns(self) -> int:
        self._cpu_ns += 1_000
        return self._cpu_ns


def _client_factory(
    client: _FakeClient,
) -> Callable[[tuple[str, ...], float], _FakeClient]:
    def factory(_argv: tuple[str, ...], _timeout_seconds: float) -> _FakeClient:
        return client

    return factory


def test_collect_dbhub_research_runs_two_routes_in_global_alternating_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate-a.sqlite"
    expected_rows = _source_snapshot(source)
    client = _FakeClient(expected_rows)
    output_root = tmp_path / "dbhub-run"

    evidence = dbhub_runner.collect_dbhub_research(
        source_snapshot=source,
        run_root=output_root,
        qualification_run_id="qualification.standard",
        registry_integrity_lookup=lambda: shared.DBHUB_NPM_INTEGRITY,
        client_factory=_client_factory(client),
        clock_ns=_Clock(),
    )

    trials = evidence["trials"]
    assert [trial["trial_id"] for trial in trials] == ["generic", "named_preset"]
    assert [
        (sample["sequence_index"], trial["executed_route"])
        for trial in trials
        for sample in trial["samples"]
    ] == [
        (0, "generic"),
        (2, "generic"),
        (4, "generic"),
        (6, "generic"),
        (8, "generic"),
        (1, "named_preset"),
        (3, "named_preset"),
        (5, "named_preset"),
        (7, "named_preset"),
        (9, "named_preset"),
    ]
    generic, named = trials
    assert generic["executed_tool"] == "search_objects+execute_sql"
    assert named["executed_tool"] == "top_sessions"
    assert {sample["response_bytes"] for sample in generic["samples"]} == {30}
    assert {sample["response_bytes"] for sample in named["samples"]} == {15}
    assert {sample["mcp_calls"] for sample in generic["samples"]} == {2}
    assert {sample["mcp_calls"] for sample in named["samples"]} == {1}
    assert {sample["result_sha256"] for trial in trials for sample in trial["samples"]} == {
        shared.canonical_sha256(expected_rows)
    }
    assert all(
        sample["scanned_rows"]
        == {"reason_code": "tooling_does_not_report", "status": "unavailable"}
        and sample["sql_statements"]
        == {"reason_code": "tooling_does_not_report", "status": "unavailable"}
        for trial in trials
        for sample in trial["samples"]
    )
    assert [name for name, _ in client.calls] == [
        "search_objects",
        "execute_sql",
        "top_sessions",
        "search_objects",
        "execute_sql",
        "top_sessions",
        "search_objects",
        "execute_sql",
        "top_sessions",
        "search_objects",
        "execute_sql",
        "top_sessions",
        "search_objects",
        "execute_sql",
        "top_sessions",
    ]
    assert evidence["model_operability"] == {
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
    }
    assert evidence["snapshot_sha256_before"] == evidence["snapshot_sha256_after"]
    snapshot = output_root / "synthetic-snapshot.sqlite"
    assert snapshot.is_file()
    assert os.stat(snapshot).st_mode & 0o222 == 0
    output = output_root / dbhub_runner.DBHUB_MEASUREMENTS_FILE
    assert output.read_bytes() == shared.canonical_json_bytes(evidence)


def test_collect_dbhub_research_rejects_route_result_drift(tmp_path: Path) -> None:
    source = tmp_path / "candidate-a.sqlite"
    expected_rows = _source_snapshot(source)
    client = _FakeClient(expected_rows, alter_named_result=True)

    with pytest.raises(
        dbhub_runner.DbhubRunnerError,
        match="generic and named_preset results differ",
    ):
        dbhub_runner.collect_dbhub_research(
            source_snapshot=source,
            run_root=tmp_path / "dbhub-run",
            qualification_run_id="qualification.standard",
            registry_integrity_lookup=lambda: shared.DBHUB_NPM_INTEGRITY,
            client_factory=_client_factory(client),
            clock_ns=_Clock(),
        )


def test_verify_live_npm_integrity_uses_exact_package_version() -> None:
    commands: list[tuple[str, ...]] = []

    def run_command(
        argv: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        commands.append(argv)
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(shared.DBHUB_NPM_INTEGRITY).encode("utf-8"),
            stderr=b"",
        )

    assert (
        dbhub_runner.verify_live_npm_integrity(command_runner=run_command)
        == shared.DBHUB_NPM_INTEGRITY
    )
    assert commands == [
        (
            "npm",
            "view",
            "@bytebase/dbhub@0.24.0",
            "dist.integrity",
            "--json",
        )
    ]


def test_verify_live_npm_integrity_rejects_registry_drift() -> None:
    def run_command(
        argv: tuple[str, ...],
        **_kwargs: object,
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=b'"sha512-different"',
            stderr=b"",
        )

    with pytest.raises(
        dbhub_runner.DbhubRunnerError,
        match="npm registry integrity differs",
    ):
        dbhub_runner.verify_live_npm_integrity(command_runner=run_command)
