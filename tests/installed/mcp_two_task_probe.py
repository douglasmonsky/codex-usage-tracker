#!/usr/bin/env python3
"""Installed-wheel two-task MCP reliability probe using synthetic usage only."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, TypedDict

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class CallMetric(TypedDict):
    task: str
    tool: str
    wall_ms: float
    server_elapsed_ms: float
    payload_bytes: int


@dataclass
class ProbeLedger:
    calls: list[CallMetric] = field(default_factory=list)

    def record(self, *, task: str, tool: str, wall_ms: float, payload: Mapping[str, Any]) -> None:
        server_ms = payload.get("server_elapsed_ms")
        if not isinstance(server_ms, int | float) or isinstance(server_ms, bool):
            raise AssertionError(f"{tool} omitted numeric server_elapsed_ms")
        self.calls.append(
            {
                "task": task,
                "tool": tool,
                "wall_ms": round(wall_ms, 3),
                "server_elapsed_ms": round(float(server_ms), 3),
                "payload_bytes": len(
                    json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
                ),
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--plugin-config", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--append-rows", type=int, default=10_000)
    args = parser.parse_args()
    if args.append_rows < 1_000:
        parser.error("--append-rows must be at least 1000 so progress overlap is observable")
    summary = asyncio.run(
        run_probe(
            python=args.python,
            home=args.home,
            plugin_config=args.plugin_config,
            expected_version=args.expected_version,
            append_rows=args.append_rows,
        )
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


async def run_probe(
    *,
    python: Path,
    home: Path,
    plugin_config: Path,
    expected_version: str,
    append_rows: int,
) -> dict[str, object]:
    env = _server_env(home, plugin_config)
    parameters = StdioServerParameters(
        command=str(python),
        args=["-m", "codex_usage_tracker.interfaces.mcp.server"],
        env=env,
    )
    source_path = _sole_session_log(home / ".codex")
    ledger = ProbeLedger()
    tail_index = append_rows + 1

    async with _session(parameters) as task_a, _session(parameters) as task_b:
        status = await _call(ledger, "A", task_a, "usage_status", {})
        _assert_identity(status, expected_version)
        baseline = await _query_calls(ledger, "A", task_a)
        baseline_count = _total_matched(baseline)

        _append_token_rows(source_path, start=1, count=append_rows)
        started = await _call(
            ledger,
            "A",
            task_a,
            "usage_refresh",
            {"history": "active", "aggregate_only": True, "execution": "async"},
            timeout_seconds=30,
        )
        job_id = _job_id(started)

        joined = await _call(
            ledger,
            "B",
            task_b,
            "usage_refresh",
            {"history": "active", "aggregate_only": True, "execution": "async"},
            timeout_seconds=30,
        )
        if _job_id(joined) != job_id:
            raise AssertionError("independent MCP tasks did not join one refresh job")

        tail_appended = False
        observed_running_stage = ""
        running_query: dict[str, Any] | None = None
        status_payload: dict[str, Any] = started
        for attempt in range(400):
            status_payload = await _call(
                ledger,
                "B",
                task_b,
                "usage_job_status",
                {"job_id": job_id, "include_result": True},
            )
            job = _result(status_payload)
            stage = str(job.get("stage", ""))
            state = str(job.get("state", ""))
            if state == "running" and stage not in {"queued", "planning"}:
                observed_running_stage = stage
                if not tail_appended:
                    _append_token_rows(source_path, start=tail_index, count=1)
                    tail_appended = True
                if running_query is None:
                    running_query = await _query_calls(ledger, "B", task_b)
            if state in {"completed", "failed", "cancelled"}:
                break
            await asyncio.sleep(min(0.25, 0.02 + attempt * 0.005))
        else:
            raise AssertionError("refresh job did not reach a terminal state")

        completed_job = _result(status_payload)
        if completed_job.get("state") != "completed":
            raise AssertionError(f"refresh job failed: {completed_job.get('error')!r}")
        if not tail_appended:
            raise AssertionError("refresh completed before a fixed-boundary overlap was observed")
        if running_query is None:
            raise AssertionError("no last-committed query ran while refresh was active")
        if _total_matched(running_query) < baseline_count:
            raise AssertionError("last-committed query regressed below the baseline snapshot")

        first_result = completed_job.get("result")
        if not isinstance(first_result, Mapping):
            raise AssertionError("completed refresh omitted its durable result")
        first_refresh = first_result.get("refresh")
        if not isinstance(first_refresh, Mapping):
            raise AssertionError("completed refresh omitted refresh counters")
        if int(first_refresh.get("parsed_events", -1)) != append_rows:
            raise AssertionError(
                "first refresh did not stop at the fixed boundary: "
                f"{first_refresh.get('parsed_events')!r}"
            )

        followup = await _call(
            ledger,
            "B",
            task_b,
            "usage_refresh",
            {"history": "active", "aggregate_only": True, "execution": "auto"},
            timeout_seconds=30,
        )
        followup_refresh = _result(followup).get("refresh")
        if not isinstance(followup_refresh, Mapping):
            raise AssertionError("tail follow-up did not complete synchronously")
        if int(followup_refresh.get("parsed_events", -1)) != 1:
            raise AssertionError("tail follow-up did not hydrate exactly one appended row")

        final_query = await _query_calls(ledger, "B", task_b)
        final_count = _total_matched(final_query)
        if final_count != baseline_count + append_rows + 1:
            raise AssertionError(
                f"final call count {final_count} did not match incremental expectation"
            )
        record_id = _first_record_id(final_query)
        evidence = await _call(
            ledger,
            "B",
            task_b,
            "usage_evidence",
            {
                "selector_kind": "call",
                "selector_id": record_id,
                "section": "summary",
                "limit": 1,
                "history": "active",
            },
        )
        _assert_exact_evidence(evidence, record_id)
        analysis_job_id, analysis_result = await _analyze_token_waste(
            ledger,
            "B",
            task_b,
        )
        if analysis_result.get("source_revision") is None:
            raise AssertionError("completed analysis omitted its committed source generation")
        reused = await _call(
            ledger,
            "B",
            task_b,
            "usage_analyze",
            _analysis_arguments(),
            timeout_seconds=30,
        )
        if _job_id(reused) != analysis_job_id:
            raise AssertionError("repeated normalized analysis did not reuse its durable result")

    async with _session(parameters) as restarted:
        restarted_status = await _call(
            ledger,
            "C",
            restarted,
            "usage_job_status",
            {"job_id": job_id, "include_result": True},
        )
        if _result(restarted_status).get("state") != "completed":
            raise AssertionError("completed refresh was not durable across MCP restart")
        _assert_identity(
            await _call(ledger, "C", restarted, "usage_status", {}),
            expected_version,
        )
        durable_analysis = await _call(
            ledger,
            "C",
            restarted,
            "usage_job_status",
            {"job_id": analysis_job_id, "include_result": True},
        )
        if _result(durable_analysis).get("state") != "completed":
            raise AssertionError("completed analysis was not durable across MCP restart")

    max_server_ms = max(float(call["server_elapsed_ms"]) for call in ledger.calls)
    max_payload_bytes = max(int(call["payload_bytes"]) for call in ledger.calls)
    return {
        "schema": "codex-usage-tracker.installed-two-task-probe.v1",
        "synthetic": True,
        "tasks": 3,
        "mcp_calls": len(ledger.calls),
        "joined_job_id": job_id,
        "observed_running_stage": observed_running_stage,
        "baseline_calls": baseline_count,
        "final_calls": final_count,
        "hydrated_initial_append": append_rows,
        "hydrated_followup_tail": 1,
        "analysis_job_id": analysis_job_id,
        "analysis_cache_reused": True,
        "max_server_elapsed_ms": round(max_server_ms, 3),
        "max_payload_bytes": max_payload_bytes,
        "calls": ledger.calls,
    }


@asynccontextmanager
async def _session(parameters: StdioServerParameters) -> AsyncIterator[ClientSession]:
    with Path(os.devnull).open("w", encoding="utf-8") as errlog:
        async with stdio_client(parameters, errlog=errlog) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


async def _call(
    ledger: ProbeLedger,
    task: str,
    session: ClientSession,
    tool: str,
    arguments: dict[str, object],
    *,
    timeout_seconds: int = 10,
) -> dict[str, Any]:
    started = perf_counter()
    response = await session.call_tool(
        tool,
        arguments,
        read_timeout_seconds=timedelta(seconds=timeout_seconds),
    )
    elapsed_ms = (perf_counter() - started) * 1_000
    if response.isError:
        raise AssertionError(f"{tool} returned an MCP error: {response.content!r}")
    payload = response.structuredContent
    if not isinstance(payload, dict):
        raise AssertionError(f"{tool} omitted structured JSON content")
    ledger.record(task=task, tool=tool, wall_ms=elapsed_ms, payload=payload)
    return payload


async def _query_calls(
    ledger: ProbeLedger,
    task: str,
    session: ClientSession,
) -> dict[str, Any]:
    return await _call(
        ledger,
        task,
        session,
        "usage_query",
        {
            "entity": "call",
            "measures": ["tokens", "uncached_tokens", "cached_tokens"],
            "order_by": "tokens",
            "order": "desc",
            "limit": 5,
            "history": "active",
        },
    )


async def _analyze_token_waste(
    ledger: ProbeLedger,
    task: str,
    session: ClientSession,
) -> tuple[str, dict[str, Any]]:
    started = await _call(
        ledger,
        task,
        session,
        "usage_analyze",
        _analysis_arguments(),
        timeout_seconds=30,
    )
    if started.get("result_schema") == (
        "codex-usage-tracker.analysis-refresh-dependency.v1"
    ):
        dependency = _result(started)
        refresh_job = dependency.get("refresh_job")
        if not isinstance(refresh_job, Mapping):
            raise AssertionError("stale analysis dependency omitted its refresh job")
        refresh_job_id = refresh_job.get("job_id")
        if not isinstance(refresh_job_id, str):
            raise AssertionError("stale analysis dependency omitted a refresh job id")
        await _poll_terminal_job(ledger, task, session, refresh_job_id)
        resume = dependency.get("resume")
        if not isinstance(resume, Mapping) or not isinstance(resume.get("arguments"), Mapping):
            raise AssertionError("stale analysis dependency omitted its exact resume request")
        started = await _call(
            ledger,
            task,
            session,
            "usage_analyze",
            dict(resume["arguments"]),
            timeout_seconds=30,
        )
    analysis_job_id = _job_id(started)
    completed = await _poll_terminal_job(
        ledger,
        task,
        session,
        analysis_job_id,
    )
    result = completed.get("result")
    if not isinstance(result, dict):
        raise AssertionError("completed analysis omitted its durable result")
    if result.get("goal") != "token_waste":
        raise AssertionError("completed analysis did not preserve the requested goal")
    return analysis_job_id, result


async def _poll_terminal_job(
    ledger: ProbeLedger,
    task: str,
    session: ClientSession,
    job_id: str,
) -> dict[str, Any]:
    for _attempt in range(400):
        payload = await _call(
            ledger,
            task,
            session,
            "usage_job_status",
            {"job_id": job_id, "include_result": True},
        )
        result = _result(payload)
        state = result.get("state")
        if state == "completed":
            return result
        if state in {"failed", "cancelled"}:
            raise AssertionError(f"job {job_id} failed: {result.get('error')!r}")
        poll_after = result.get("poll_after_ms", 100)
        delay = (
            max(10, min(250, int(poll_after))) / 1_000
            if isinstance(poll_after, int) and not isinstance(poll_after, bool)
            else 0.1
        )
        await asyncio.sleep(delay)
    raise AssertionError(f"job {job_id} did not reach a terminal state")


def _analysis_arguments() -> dict[str, object]:
    return {
        "goal": "token_waste",
        "filters": None,
        "history": "active",
        "evidence_limit": 4,
        "comparison": None,
        "execution": "async",
    }


def _server_env(home: Path, plugin_config: Path) -> dict[str, str]:
    payload = json.loads(plugin_config.read_text(encoding="utf-8"))
    server = payload.get("mcpServers", {}).get("codex-usage-tracker", {})
    configured = server.get("env", {})
    if not isinstance(configured, dict):
        raise AssertionError("plugin MCP env is not an object")
    env = dict(os.environ)
    env.update({str(key): str(value) for key, value in configured.items()})
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CODEX_USAGE_TRACKER_MCP_PROFILE"] = "core"
    env["CODEX_USAGE_TRACKER_REFRESH_WORKERS"] = "1"
    env.pop("PYTHONPATH", None)
    return env


def _sole_session_log(codex_home: Path) -> Path:
    paths = sorted((codex_home / "sessions").rglob("*.jsonl"))
    if len(paths) != 1:
        raise AssertionError(f"expected one synthetic session log, found {len(paths)}")
    return paths[0]


def _append_token_rows(path: Path, *, start: int, count: int) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for index in range(start, start + count):
            total = 300 + index * 100
            row = {
                "timestamp": f"2026-06-30T12:{index // 60 % 60:02d}:{index % 60:02d}.000Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": total - 40,
                            "cached_input_tokens": 20,
                            "output_tokens": 40,
                            "reasoning_output_tokens": 10,
                            "total_tokens": total,
                        },
                        "last_token_usage": {
                            "input_tokens": 80,
                            "cached_input_tokens": 20,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                            "total_tokens": 100,
                        },
                        "model_context_window": 258_400,
                    },
                },
            }
            handle.write(json.dumps(row, separators=(",", ":")) + "\n")


def _assert_identity(payload: Mapping[str, Any], expected_version: str) -> None:
    result = _result(payload)
    plugin = result.get("plugin_bundle")
    if not isinstance(plugin, Mapping):
        raise AssertionError("usage_status omitted plugin bundle identity")
    if plugin.get("runtime_version") != expected_version:
        raise AssertionError("usage_status runtime version did not match installed wheel")
    if plugin.get("state") != "coherent":
        raise AssertionError(f"plugin bundle is not coherent: {plugin.get('state')!r}")
    mcp = result.get("mcp")
    if not isinstance(mcp, Mapping) or mcp.get("current_task_exposure") != "verified":
        raise AssertionError("usage_status did not verify current-task MCP exposure")


def _assert_exact_evidence(payload: Mapping[str, Any], record_id: str) -> None:
    result = _result(payload)
    selector = result.get("selector")
    records = result.get("records")
    if not isinstance(selector, Mapping) or selector.get("id") != record_id:
        raise AssertionError("evidence selector did not preserve the exact record id")
    if not isinstance(records, list) or len(records) != 1:
        raise AssertionError("exact call evidence did not return one record")
    record_selectors = records[0].get("selectors")
    if not isinstance(record_selectors, Mapping) or record_selectors.get(
        "record_id"
    ) != record_id:
        raise AssertionError("evidence record id did not match its selector")


def _result(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise AssertionError("core MCP envelope omitted object result")
    return result


def _job_id(payload: Mapping[str, Any]) -> str:
    job_id = _result(payload).get("job_id")
    if not isinstance(job_id, str) or not job_id:
        raise AssertionError("refresh did not return a job id")
    return job_id


def _total_matched(payload: Mapping[str, Any]) -> int:
    value = _result(payload).get("total_matched")
    if not isinstance(value, int) or isinstance(value, bool):
        raise AssertionError("usage_query omitted exact total_matched")
    return value


def _first_record_id(payload: Mapping[str, Any]) -> str:
    rows = _result(payload).get("rows")
    if not isinstance(rows, list) or not rows:
        raise AssertionError("usage_query returned no call rows")
    record_id = rows[0].get("record_id")
    if not isinstance(record_id, str) or not record_id:
        raise AssertionError("usage_query call row omitted record_id")
    return record_id


if __name__ == "__main__":
    raise SystemExit(main())
