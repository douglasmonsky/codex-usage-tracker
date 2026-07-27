#!/usr/bin/env python3
"""Freeze deterministic agent-outcome fixtures and privacy-safe scorecards."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import queue
import re
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile
from collections.abc import Iterator, Mapping
from datetime import datetime, timedelta, timezone
from email.parser import Parser
from pathlib import Path
from typing import Any

try:
    import tomllib  # type: ignore[import-not-found,import-untyped]
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

from codex_usage_tracker.kernel.ingest import KernelIngestor, RefreshTrigger
from codex_usage_tracker.kernel.operational import (
    kernel_paths,
    load_cutover_control,
)
from codex_usage_tracker.kernel.plugin_manifest import bundle_digest

try:
    from scripts.smoke_installed_catalog import MCP_TOOLS
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from smoke_installed_catalog import MCP_TOOLS  # type: ignore[import-not-found,no-redef]

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONTRACT = _REPO_ROOT / "config" / "product-recovery-agent-baseline-v1.json"
_ANSWER_SCHEMA = _REPO_ROOT / "config" / "product-recovery-agent-answer-v1.schema.json"
_SCORECARD_SCHEMA = (
    _REPO_ROOT / "config" / "product-recovery-agent-scorecard-v1.schema.json"
)
_MEASUREMENT_KEYS = frozenset(
    {
        "elapsed_ms",
        "final_answer_ms",
        "first_tool_ms",
        "response_bytes",
        "started_at",
        "tracker_ms",
    }
)
_SAFE_STRING = re.compile(r"^[A-Za-z0-9 .,:;_+@=-]{0,256}$")
_PATH_OR_URI = re.compile(
    r"(^|[ (])(?:~[/\\]|\\.\\.?[/\\]|[/\\]|[A-Za-z]:[/\\]|"
    r"(?:file|https?|ssh|vscode)://|%2[fF]|%5[cC])"
)
_SELECTOR_PROMPTS = frozenset({"evidence_timeline", "expensive_thread_calls"})


def load_contract(path: Path = _DEFAULT_CONTRACT) -> dict[str, Any]:
    """Load and minimally validate the frozen R1 benchmark contract."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "codex-usage-tracker.agent-outcome-baseline.v1":
        raise ValueError("agent-outcome benchmark schema is invalid")
    required = {
        "gates",
        "history_profiles",
        "privacy",
        "prompt_suite",
        "scenarios",
        "scorecard_schema",
        "supported_hosts",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"agent-outcome benchmark fields are missing: {missing}")
    return payload


def _profile(contract: Mapping[str, Any], profile: str) -> Mapping[str, Any]:
    for candidate in contract["history_profiles"]:
        if candidate["id"] == profile:
            return candidate
    raise ValueError(f"unknown history profile: {profile}")


def _json_line(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode()


def _session_line(thread: int) -> bytes:
    return _json_line(
        {
            "payload": {
                "id": f"00000000-0000-4000-8000-{thread:012d}",
            },
            "timestamp": "2026-07-01T00:00:00.000Z",
            "type": "session_meta",
        }
    )


def _turn_line(thread: int, turn: int, timestamp: str) -> bytes:
    models = ("gpt-5.4", "gpt-5.5", "gpt-5.6-sol")
    efforts = ("low", "medium", "high")
    return _json_line(
        {
            "payload": {
                "effort": efforts[(thread + turn) % len(efforts)],
                "model": models[(thread * 3 + turn) % len(models)],
                "turn_id": f"turn-{thread:04d}-{turn:04d}",
            },
            "timestamp": timestamp,
            "type": "turn_context",
        }
    )


def _call_line(
    *,
    call: int,
    thread: int,
    turn: int,
    timestamp: str,
    allowance: bool,
) -> bytes:
    input_tokens = 1_000 + ((thread * 97 + turn * 31 + call * 17) % 24_000)
    cached_tokens = (input_tokens * ((thread + call) % 9)) // 10
    output_tokens = 50 + ((thread + turn + call * 13) % 1_200)
    reasoning_tokens = (turn * 29 + call * 11) % 800
    payload: dict[str, Any] = {
        "info": {
            "last_token_usage": {
                "cached_input_tokens": cached_tokens,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_output_tokens": reasoning_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            "model_context_window": 200_000,
        },
        "type": "token_count",
    }
    if allowance:
        payload["rate_limits"] = {
            "limit_id": "synthetic-limit",
            "plan_type": "synthetic",
            "primary": {
                "resets_at": "2026-07-08T00:00:00Z",
                "used_percent": float((thread + turn + call) % 100),
                "window_minutes": 10_080,
            },
        }
    return _json_line(
        {
            "event_id": f"event-{thread:04d}-{turn:04d}-{call:02d}",
            "payload": payload,
            "timestamp": timestamp,
            "type": "event_msg",
        }
    )


def _tool_line(
    *,
    tool: int,
    thread: int,
    turn: int,
    timestamp: str,
) -> bytes:
    names = ("exec_command", "view_image", "mcp__synthetic__lookup", "write_stdin")
    return _json_line(
        {
            "payload": {
                "name": names[(thread + turn + tool) % len(names)],
                "type": "function_call",
            },
            "timestamp": timestamp,
            "type": "response_item",
        }
    )


def _activity_line(timestamp: str) -> bytes:
    return _json_line(
        {
            "payload": {"type": "task_complete"},
            "timestamp": timestamp,
            "type": "event_msg",
        }
    )


def _timestamp(
    thread: int,
    turn: int,
    *,
    profile: Mapping[str, Any],
    source_ordinal: int,
) -> str:
    history_days = profile.get("history_days")
    if history_days is None:
        point = datetime(2026, 7, 1, tzinfo=timezone.utc) + timedelta(
            days=(thread + turn) % 28,
            seconds=thread * 7 + turn,
        )
        return point.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    source_count = int(profile["threads"])
    day_offset = source_ordinal * int(history_days) // max(1, source_count)
    point = datetime(2023, 7, 29, tzinfo=timezone.utc) + timedelta(
        days=day_offset,
        seconds=turn,
    )
    return point.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _source_bytes(
    *,
    thread: int,
    profile: Mapping[str, Any],
    call_offset: int,
    seed: int,
) -> Iterator[bytes]:
    synthetic_thread = thread + seed % 100_000
    yield _session_line(synthetic_thread)
    call_ordinal = 0
    for turn in range(int(profile["turns_per_thread"])):
        timestamp = _timestamp(
            synthetic_thread,
            turn,
            profile=profile,
            source_ordinal=thread,
        )
        yield _turn_line(synthetic_thread, turn, timestamp)
        for call in range(int(profile["model_calls_per_turn"])):
            call_ordinal += 1
            yield _call_line(
                call=call,
                thread=synthetic_thread,
                turn=turn,
                timestamp=timestamp,
                allowance=(
                    (call_offset + call_ordinal) % int(profile["allowance_every_calls"]) == 0
                ),
            )
        for tool in range(int(profile["tool_calls_per_turn"])):
            yield _tool_line(
                tool=tool,
                thread=synthetic_thread,
                turn=turn,
                timestamp=timestamp,
            )
        for _ in range(int(profile["activity_events_per_turn"])):
            yield _activity_line(timestamp)


def generate_history(
    workspace: Path,
    *,
    profile: str,
    seed: int,
    contract_path: Path = _DEFAULT_CONTRACT,
) -> dict[str, Any]:
    """Write a deterministic structural-only synthetic history."""

    contract = load_contract(contract_path)
    shape = _profile(contract, profile)
    sessions = workspace / "sessions"
    if workspace.exists() and any(workspace.iterdir()):
        raise FileExistsError(f"history workspace is not empty: {workspace.name}")
    sessions.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total_bytes = 0
    allowance_observations = 0
    calls_per_thread = int(shape["turns_per_thread"]) * int(shape["model_calls_per_turn"])
    for thread in range(int(shape["threads"])):
        relative = f"sessions/rollout-synthetic-{thread:04d}.jsonl"
        digest.update(relative.encode())
        digest.update(b"\0")
        path = workspace / relative
        with path.open("wb") as handle:
            for line in _source_bytes(
                thread=thread,
                profile=shape,
                call_offset=thread * calls_per_thread,
                seed=seed,
            ):
                handle.write(line)
                digest.update(line)
                total_bytes += len(line)
    total_calls = int(shape["threads"]) * calls_per_thread
    allowance_observations = total_calls // int(shape["allowance_every_calls"])
    threads = int(shape["threads"])
    turns = threads * int(shape["turns_per_thread"])
    return {
        "activity_events": turns * int(shape["activity_events_per_turn"]),
        "allowance_observations": allowance_observations,
        "model_calls": turns * int(shape["model_calls_per_turn"]),
        "profile": profile,
        "seed": seed,
        "source_bytes": total_bytes,
        "source_files": threads,
        "source_sha256": digest.hexdigest(),
        "threads": threads,
        "tool_calls": turns * int(shape["tool_calls_per_turn"]),
        "turns": turns,
    }


def _timed_refresh(
    ingestor: KernelIngestor,
    sources: list[Path],
    *,
    owner_id: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = ingestor.refresh(
        sources,
        trigger=RefreshTrigger.CLI_REFRESH,
        owner_id=owner_id,
    )
    return {
        "changed_sources": result.changed_sources,
        "deleted_rows": result.deleted_rows,
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "generation": result.generation,
        "inserted_calls": result.inserted_calls,
        "inserted_tools": result.inserted_tools,
        "joined": result.joined,
        "planner_reason": result.planner_reason,
        "writer_transactions": len(result.writer_transaction_ms),
    }


def run_storage_baseline(
    workspace: Path,
    *,
    profile: str,
    seed: int,
    contract_path: Path = _DEFAULT_CONTRACT,
) -> dict[str, Any]:
    """Measure cold, no-change, and one-call append-safe refreshes."""

    manifest = generate_history(
        workspace / "history",
        profile=profile,
        seed=seed,
        contract_path=contract_path,
    )
    sources = sorted((workspace / "history" / "sessions").glob("*.jsonl"))
    paths = kernel_paths(workspace / "cache")
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    cold = _timed_refresh(ingestor, sources, owner_id="r1-cold-build")
    no_change = _timed_refresh(ingestor, sources, owner_id="r1-no-change")
    with sources[0].open("ab") as handle:
        handle.write(
            _call_line(
                allowance=False,
                call=99,
                thread=0,
                timestamp="2026-07-29T00:00:00.000Z",
                turn=int(_profile(load_contract(contract_path), profile)["turns_per_thread"]) - 1,
            )
        )
    tail = _timed_refresh(ingestor, sources, owner_id="r1-append-tail")
    active_path = load_cutover_control(paths.operational).active_kernel_path
    if active_path is None:
        raise RuntimeError("storage baseline did not publish a generation")
    tables = (
        "threads",
        "turns",
        "model_calls",
        "tool_calls",
        "activity_events",
        "allowance_observations",
    )
    with sqlite3.connect(active_path) as connection:
        fact_rows = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
    return {
        "database_bytes": active_path.stat().st_size,
        "fact_rows": fact_rows,
        "manifest": manifest,
        "phases": {
            "append_safe_tail": tail,
            "cold_build": cold,
            "no_change": no_change,
        },
        "schema": "codex-usage-tracker.storage-baseline.v1",
    }


def run_lifecycle_baseline(
    workspace: Path,
    *,
    seed: int,
    contract_path: Path = _DEFAULT_CONTRACT,
) -> list[dict[str, Any]]:
    """Exercise automatable lifecycle paths and name unsupported host-only paths."""

    paths = kernel_paths(workspace / "cache")
    started = time.perf_counter()
    no_index = not paths.operational.exists()
    no_index_ms = (time.perf_counter() - started) * 1_000
    manifest = generate_history(
        workspace / "history",
        profile="small_ci",
        seed=seed,
        contract_path=contract_path,
    )
    sources = sorted((workspace / "history" / "sessions").glob("*.jsonl"))
    ingestor = KernelIngestor(paths.analytical, paths.operational)
    _timed_refresh(ingestor, sources, owner_id="r1-lifecycle-cold")
    warm_started = time.perf_counter()
    warm = load_cutover_control(paths.operational).active_kernel_path is not None
    warm_ms = (time.perf_counter() - warm_started) * 1_000
    no_change = _timed_refresh(ingestor, sources, owner_id="r1-lifecycle-no-change")
    with sources[0].open("ab") as handle:
        handle.write(
            _call_line(
                allowance=False,
                call=101,
                thread=0,
                timestamp="2026-07-29T00:00:00.000Z",
                turn=0,
            )
        )
    tail = _timed_refresh(ingestor, sources, owner_id="r1-lifecycle-tail")
    with sources[0].open("ab") as handle:
        for call in range(102, 134):
            handle.write(
                _call_line(
                    allowance=False,
                    call=call,
                    thread=0,
                    timestamp="2026-07-29T00:01:00.000Z",
                    turn=0,
                )
            )
    bounded = _timed_refresh(ingestor, sources, owner_id="r1-lifecycle-bounded")
    with sources[0].open("ab") as handle:
        for call in range(134, 646):
            handle.write(
                _call_line(
                    allowance=False,
                    call=call,
                    thread=0,
                    timestamp="2026-07-29T00:02:00.000Z",
                    turn=0,
                )
            )
    moving_result: dict[str, Any] = {}

    def refresh_moving_tail() -> None:
        moving_result.update(
            _timed_refresh(ingestor, sources, owner_id="r1-lifecycle-moving")
        )

    worker = threading.Thread(target=refresh_moving_tail)
    worker.start()
    with sources[0].open("ab") as handle:
        handle.write(
            _call_line(
                allowance=False,
                call=646,
                thread=0,
                timestamp="2026-07-29T00:03:00.000Z",
                turn=0,
            )
        )
    worker.join(timeout=30)
    if worker.is_alive():
        raise RuntimeError("moving-tail lifecycle refresh did not terminate")
    catch_up = _timed_refresh(ingestor, sources, owner_id="r1-lifecycle-catch-up")
    active = load_cutover_control(paths.operational).active_kernel_path
    if active is None:
        raise RuntimeError("moving-tail lifecycle did not publish a generation")
    with sqlite3.connect(active) as connection:
        final_calls = int(connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0])

    def measured(
        scenario: str,
        elapsed_ms: float,
        passed: bool,
        error_code: str | None = None,
    ) -> dict[str, Any]:
        return {
            "elapsed_ms": round(elapsed_ms, 3),
            "error_code": error_code,
            "measurement_source": "storage_runner",
            "outcome": "observed_pass" if passed else "observed_fail",
            "scenario": scenario,
        }

    return [
        measured("no_index", no_index_ms, no_index),
        measured("warm_generation", warm_ms, warm),
        measured(
            "no_change_refresh",
            float(no_change["elapsed_ms"]),
            no_change["planner_reason"] == "no_changes",
        ),
        measured(
            "append_safe_tail",
            float(tail["elapsed_ms"]),
            tail["inserted_calls"] == 1,
        ),
        measured(
            "bounded_tail",
            float(bounded["elapsed_ms"]),
            bounded["inserted_calls"] == 32,
        ),
        measured(
            "moving_tail",
            float(moving_result["elapsed_ms"]) + float(catch_up["elapsed_ms"]),
            catch_up["generation"] >= moving_result["generation"]
            and final_calls == int(manifest["model_calls"]) + 546,
        ),
        {
            "elapsed_ms": None,
            "error_code": "requires_async_job_host",
            "measurement_source": "storage_runner",
            "outcome": "unsupported",
            "scenario": "refresh_in_progress",
        },
        {
            "elapsed_ms": None,
            "error_code": "requires_browser_host",
            "measurement_source": "storage_runner",
            "outcome": "unsupported",
            "scenario": "browser_reopen",
        },
        {
            "elapsed_ms": None,
            "error_code": "requires_install_boundary",
            "measurement_source": "storage_runner",
            "outcome": "unsupported",
            "scenario": "plugin_upgrade",
        },
        {
            "elapsed_ms": None,
            "error_code": "requires_fresh_host",
            "measurement_source": "storage_runner",
            "outcome": "unsupported",
            "scenario": "fresh_host_task",
        },
        {
            "elapsed_ms": None,
            "error_code": "requires_stale_task_host",
            "measurement_source": "storage_runner",
            "outcome": "unsupported",
            "scenario": "stale_task_catalog",
        },
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_revision(repo_root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _verified_wheel_runtime(wheel: Path) -> dict[str, Any]:
    """Verify wheel bytes and execute its own MCP catalog from the archive."""

    try:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
            record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
            if len(metadata_names) != 1 or len(record_names) != 1:
                raise ValueError("candidate wheel metadata or RECORD is missing")
            metadata = Parser().parsestr(archive.read(metadata_names[0]).decode("utf-8"))
            record_name = record_names[0]
            records = list(
                csv.reader(io.StringIO(archive.read(record_name).decode("utf-8")))
            )
            recorded = {row[0]: row[1:] for row in records if len(row) == 3}
            if set(names) != set(recorded):
                raise ValueError("candidate wheel RECORD inventory differs from archive")
            for name in names:
                digest_field, size_field = recorded[name]
                payload = archive.read(name)
                if name == record_name:
                    if digest_field or size_field:
                        raise ValueError("candidate wheel RECORD self-entry is invalid")
                    continue
                if not digest_field.startswith("sha256="):
                    raise ValueError("candidate wheel RECORD digest is missing")
                actual = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).rstrip(b"=")
                if digest_field.removeprefix("sha256=").encode() != actual:
                    raise ValueError("candidate wheel RECORD digest mismatch")
                if size_field != str(len(payload)):
                    raise ValueError("candidate wheel RECORD size mismatch")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise ValueError("candidate wheel is not a valid wheel archive") from exc
    runtime_code = (
        "import json;"
        "from codex_usage_tracker.kernel import __version__;"
        "from codex_usage_tracker.kernel.interfaces.mcp.catalog import TOOL_SPECS;"
        "print(json.dumps({'version':__version__,'tools':[s.name for s in TOOL_SPECS]}))"
    )
    # Isolated mode deliberately ignores PYTHONPATH, so execute from the archive
    # by putting it on sys.path inside the child instead.
    runtime = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            f"import sys;sys.path.insert(0,{str(wheel.resolve())!r});{runtime_code}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if runtime.returncode != 0:
        raise ValueError("candidate wheel runtime could not be executed")
    try:
        observed = json.loads(runtime.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("candidate wheel runtime returned invalid identity") from exc
    if not isinstance(observed, dict):
        raise ValueError("candidate wheel runtime identity is invalid")
    return {
        "distribution": str(metadata.get("Name", "")),
        "metadata_version": str(metadata.get("Version", "")),
        "tools": observed.get("tools"),
        "version": observed.get("version"),
    }


def candidate_identity(
    *,
    repo_root: Path,
    wheel: Path,
    cached_bundle: Path,
) -> dict[str, Any]:
    """Bind all installed candidate surfaces without retaining local paths."""

    project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    plugin = json.loads((repo_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((repo_root / ".mcp.json").read_text(encoding="utf-8"))
    skill_header = (
        (repo_root / "skills" / "usage-kernel" / "SKILL.md")
        .read_text(encoding="utf-8")
        .splitlines()
    )
    skill_name = next(
        line.removeprefix("name:").strip() for line in skill_header if line.startswith("name:")
    )
    source_digest = bundle_digest(repo_root)
    cached_digest = bundle_digest(cached_bundle)
    declared_digest = plugin["bundle"]["digest"]
    version = str(project["version"])
    wheel_runtime = _verified_wheel_runtime(wheel)
    if wheel_runtime["distribution"] != str(project["name"]):
        raise ValueError("candidate wheel distribution differs from project")
    if wheel_runtime["metadata_version"] != version or wheel_runtime["version"] != version:
        raise ValueError("candidate wheel runtime version differs from project")
    if wheel_runtime["tools"] != list(MCP_TOOLS):
        raise ValueError("candidate wheel MCP catalog differs from frozen catalog")
    if plugin["version"] != version or plugin["bundle"]["runtime_version"] != version:
        raise ValueError("candidate package and plugin versions differ")
    if declared_digest != source_digest:
        raise ValueError("candidate plugin manifest digest is stale")
    if cached_digest != source_digest:
        raise ValueError("cached candidate bundle differs from source bundle")
    servers = mcp.get("mcpServers", {})
    if list(servers) != ["codex-usage-tracker"]:
        raise ValueError("candidate MCP server identity is invalid")
    return {
        "cached_bundle": {
            "digest": cached_digest,
            "registration": "installed_exact_bundle",
        },
        "mcp": {
            "server": "codex-usage-tracker",
            "catalog": list(MCP_TOOLS),
            "tools": len(MCP_TOOLS),
        },
        "plugin": {
            "digest": declared_digest,
            "name": plugin["name"],
            "version": plugin["version"],
        },
        "skill": {"name": skill_name},
        "source_revision": _git_revision(repo_root),
        "version": version,
        "wheel": {
            "name": wheel.name,
            "sha256": _sha256(wheel),
            "size_bytes": wheel.stat().st_size,
        },
    }


def _active_database(cache_root: Path) -> Path:
    paths = kernel_paths(cache_root)
    active = load_cutover_control(paths.operational).active_kernel_path
    if active is None:
        raise ValueError("agent benchmark cache has no committed generation")
    return active


def _fact(
    key: str,
    value: str | int | float | None,
    *,
    label: str | None = None,
    selector: str | None = None,
) -> dict[str, Any]:
    return {"key": key, "label": label, "selector": selector, "value": value}


def prompt_oracle(cache_root: Path, prompt_id: str) -> list[dict[str, Any]]:
    """Return one bounded deterministic oracle for every frozen prompt intent."""

    active = _active_database(cache_root)
    with sqlite3.connect(active) as connection:
        if prompt_id in {"top_threads", "weekly_drivers"}:
            time_filter = ""
            if prompt_id == "weekly_drivers":
                time_filter = (
                    "AND model_calls.event_at >= "
                    "datetime((SELECT MAX(event_at) FROM model_calls), '-7 days')"
                )
            rows = connection.execute(
                f"""
                SELECT threads.logical_thread_id, threads.display_label,
                       SUM(model_calls.input_tokens + model_calls.output_tokens)
                FROM model_calls
                JOIN threads ON threads.thread_id = model_calls.thread_id
                WHERE model_calls.duplicate_state = 'canonical' {time_filter}
                GROUP BY threads.logical_thread_id, threads.display_label
                ORDER BY 3 DESC, 1 ASC LIMIT 5
                """
            ).fetchall()
            return [
                _fact(
                    "thread_total_tokens",
                    int(tokens),
                    label=str(label),
                    selector=f"thread:{thread}",
                )
                for thread, label, tokens in rows
            ]
        if prompt_id == "week_over_week":
            current, previous = connection.execute(
                """
                WITH boundary AS (SELECT MAX(event_at) AS latest FROM model_calls)
                SELECT
                  SUM(CASE WHEN event_at >= datetime(latest, '-7 days')
                           THEN input_tokens + output_tokens ELSE 0 END),
                  SUM(CASE WHEN event_at < datetime(latest, '-7 days')
                            AND event_at >= datetime(latest, '-14 days')
                           THEN input_tokens + output_tokens ELSE 0 END)
                FROM model_calls, boundary
                WHERE duplicate_state = 'canonical'
                """
            ).fetchone()
            return [
                _fact("current_week_tokens", int(current or 0)),
                _fact("previous_week_tokens", int(previous or 0)),
                _fact("absolute_change_tokens", int(current or 0) - int(previous or 0)),
            ]
        if prompt_id == "model_effort_cost":
            rows = connection.execute(
                """
                SELECT model, COALESCE(effort, 'unknown'),
                       SUM(input_tokens + output_tokens)
                FROM model_calls WHERE duplicate_state = 'canonical'
                GROUP BY model, effort ORDER BY 3 DESC, 1, 2 LIMIT 5
                """
            ).fetchall()
            return [
                _fact("model_effort_tokens", int(tokens), label=f"{model} {effort}")
                for model, effort, tokens in rows
            ]
        if prompt_id == "four_token_classes":
            uncached, cached, reasoning, output = connection.execute(
                """
                SELECT SUM(input_tokens - cached_input_tokens),
                       SUM(cached_input_tokens), SUM(reasoning_tokens),
                       SUM(output_tokens)
                FROM model_calls WHERE duplicate_state = 'canonical'
                """
            ).fetchone()
            return [
                _fact("uncached_input_tokens", int(uncached or 0)),
                _fact("cached_input_tokens", int(cached or 0)),
                _fact("reasoning_tokens", int(reasoning or 0)),
                _fact("output_tokens", int(output or 0)),
            ]
        if prompt_id == "allowance_drain":
            count, earliest, latest = connection.execute(
                """
                SELECT COUNT(*), MIN(used_percent), MAX(used_percent)
                FROM allowance_observations WHERE duplicate_state = 'canonical'
                """
            ).fetchone()
            return [
                _fact("observations", int(count)),
                _fact("minimum_used_percent", float(earliest or 0)),
                _fact("maximum_used_percent", float(latest or 0)),
            ]
        if prompt_id == "tool_context":
            rows = connection.execute(
                """
                SELECT tool_name, COUNT(*), COALESCE(SUM(output_bytes), 0)
                FROM tool_calls GROUP BY tool_name ORDER BY 2 DESC, 1 LIMIT 5
                """
            ).fetchall()
            return [
                _fact("tool_calls", int(count), label=str(name))
                for name, count, _output_bytes in rows
            ]
        selected = connection.execute(
            """
            SELECT threads.thread_id, threads.logical_thread_id, threads.display_label
            FROM model_calls JOIN threads ON threads.thread_id = model_calls.thread_id
            WHERE model_calls.duplicate_state = 'canonical'
            GROUP BY threads.thread_id, threads.logical_thread_id, threads.display_label
            ORDER BY SUM(model_calls.input_tokens + model_calls.output_tokens) DESC,
                     threads.logical_thread_id
            LIMIT 1
            """
        ).fetchone()
        if selected is None:
            return []
        thread_id, logical_thread_id, thread_label = selected
        if prompt_id == "evidence_timeline":
            rows = connection.execute(
                """
                SELECT canonical_call_id, event_at
                FROM model_calls WHERE thread_id = ? AND duplicate_state = 'canonical'
                ORDER BY event_at, canonical_call_id LIMIT 5
                """,
                (thread_id,),
            ).fetchall()
            return [
                _fact(
                    "timeline_call",
                    str(event_at),
                    label=str(thread_label),
                    selector=f"call:{call_id}",
                )
                for call_id, event_at in rows
            ]
        if prompt_id == "expensive_thread_calls":
            rows = connection.execute(
                """
                SELECT canonical_call_id, input_tokens + output_tokens
                FROM model_calls WHERE thread_id = ? AND duplicate_state = 'canonical'
                ORDER BY 2 DESC, canonical_call_id LIMIT 5
                """,
                (thread_id,),
            ).fetchall()
            return [
                _fact(
                    "call_total_tokens",
                    int(tokens),
                    label=str(thread_label),
                    selector=f"call:{call_id}",
                )
                for call_id, tokens in rows
            ]
        if prompt_id == "latest_incremental_change":
            generation = int(
                connection.execute("SELECT MAX(generation) FROM generations").fetchone()[0]
            )
            calls = int(
                connection.execute(
                    "SELECT COUNT(*) FROM model_calls WHERE generation = ?",
                    (generation,),
                ).fetchone()[0]
            )
            return [
                _fact("generation", generation),
                _fact("generation_model_calls", calls),
                _fact(
                    "selected_thread",
                    str(logical_thread_id),
                    label=str(thread_label),
                    selector=f"thread:{logical_thread_id}",
                ),
            ]
    raise ValueError(f"unsupported prompt oracle: {prompt_id}")


def summarize_cli_observation(
    events: list[tuple[float, Mapping[str, Any]]],
    *,
    total_ms: float,
    host_version: str,
    candidate_registration: str,
    candidate_digest: str,
    candidate_version: str,
    catalog_tools: list[str],
    registration_observed: bool,
    handshake_observed: bool,
    exposure_observed: bool,
    prompt_id: str,
    expected_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reduce ephemeral Codex JSONL into one privacy-safe scorecard row."""

    mcp_started: dict[str, float] = {}
    tracker_ms = 0.0
    first_tool_ms: float | None = None
    mcp_calls = 0
    query_batches = 0
    response_bytes = 0
    final: dict[str, Any] | None = None
    terminal = False
    for observed_ms, event in events:
        event_type = event.get("type")
        item = event.get("item")
        item = item if isinstance(item, dict) else {}
        item_id = str(item.get("id", ""))
        if event_type == "item.started" and item.get("type") == "mcp_tool_call":
            mcp_started[item_id] = observed_ms
            mcp_calls += 1
            first_tool_ms = observed_ms if first_tool_ms is None else first_tool_ms
            if item.get("tool") == "usage_query":
                query_batches += 1
        elif event_type == "item.completed" and item.get("type") == "mcp_tool_call":
            tracker_ms += max(
                0.0,
                observed_ms - mcp_started.pop(item_id, observed_ms),
            )
            response_bytes += len(
                json.dumps(
                    item.get("result"),
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
            )
        elif event_type == "item.completed" and item.get("type") == "agent_message":
            try:
                candidate = json.loads(str(item.get("text", "")))
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                final = candidate
        elif event_type == "turn.completed":
            terminal = True
    final = final or {}
    facts_value = final.get("facts")
    facts: list[Any] = facts_value if isinstance(facts_value, list) else []
    success = final.get("success") is True and terminal
    accuracy = 1.0 if success and facts == expected_facts else 0.0
    labeled_facts = [
        fact for fact in facts if isinstance(fact, dict) and fact.get("label") is not None
    ]
    labels = bool(labeled_facts) and all(
        bool(fact.get("label")) and not str(fact.get("label")).startswith("Thread ")
        for fact in labeled_facts
    )
    grades = final.get("claim_grades", [])
    if isinstance(grades, dict):
        grades = list(grades.values())
    if not isinstance(grades, list):
        grades = []
    normalized_grades = sorted(
        {
            str(grade)
            for grade in grades
            if grade in {"estimate", "fact", "inference", "unsupported"}
        }
    )
    grade_separation = (
        bool(normalized_grades)
        and "unsupported" not in normalized_grades
        and set(normalized_grades).issubset({"estimate", "fact", "inference"})
    )
    usefulness = sum(
        (
            success,
            accuracy == 1.0,
            labels or not any(item.get("label") for item in expected_facts),
            grade_separation,
        )
    )
    selectors = [
        str(item["selector"])
        for item in expected_facts
        if item.get("selector") is not None
    ]
    selector_validity: float | str = (
        1.0
        if prompt_id in _SELECTOR_PROMPTS and selectors and facts == expected_facts
        else (0.0 if prompt_id in _SELECTOR_PROMPTS else "not_applicable")
    )
    complete_catalog = catalog_tools == list(MCP_TOOLS)
    fresh_task = all(
        (
            registration_observed,
            handshake_observed,
            exposure_observed,
            complete_catalog,
        )
    )
    return {
        "accuracy": accuracy,
        "candidate_digest": candidate_digest,
        "candidate_registration": candidate_registration,
        "candidate_version": candidate_version,
        "catalog_observed": complete_catalog,
        "catalog_tools": catalog_tools,
        "claim_grades": normalized_grades,
        "error_code": final.get("error_code")
        or (
            "oracle_mismatch"
            if success and accuracy < 1.0
            else (None if success else "agent_task_failed")
        ),
        "final_answer_ms": round(total_ms, 3),
        "first_tool_ms": round(first_tool_ms or total_ms, 3),
        "fresh_task": fresh_task,
        "generation": final.get("generation"),
        "handshake_observed": handshake_observed,
        "host": "codex_cli",
        "host_version": host_version,
        "human_labels": labels,
        "launch_method": "codex_exec_ephemeral",
        "mcp_calls": mcp_calls,
        "polls": sum(
            1
            for _, event in events
            if isinstance(event.get("item"), dict)
            and event["item"].get("tool") == "usage_job_status"
        ),
        "prompt_id": prompt_id,
        "query_batches": query_batches,
        "refresh_joins": 0,
        "refresh_starts": sum(
            1
            for _, event in events
            if isinstance(event.get("item"), dict) and event["item"].get("tool") == "usage_refresh"
        ),
        "response_bytes": response_bytes,
        "registration_observed": registration_observed,
        "retries": 0,
        "scenario": "warm_generation",
        "selector_validity": selector_validity,
        "success": success,
        "terminal_state": "completed" if terminal else "failed",
        "tracker_ms": round(tracker_ms, 3),
        "usefulness": usefulness,
        "exposure_observed": exposure_observed,
    }


def run_cli_host_task(
    *,
    repo_root: Path,
    cache_root: Path,
    prompt_id: str,
    candidate_registration: str,
    candidate_digest: str,
    candidate_version: str,
    catalog_tools: list[str],
    registration_observed: bool,
    handshake_observed: bool,
    exposure_observed: bool,
    timeout_seconds: float = 120,
) -> dict[str, Any]:
    """Run one fresh ephemeral Codex CLI task and retain only its scores."""

    contract = load_contract(repo_root / _DEFAULT_CONTRACT.relative_to(_REPO_ROOT))
    intents = {item["id"]: item["intent"] for item in contract["prompt_suite"]}
    if prompt_id not in intents:
        raise ValueError(f"unsupported prompt ID: {prompt_id}")
    prompt = (
        "Use the codex-usage-tracker usage-kernel skill. "
        f"This is synthetic benchmark prompt ID {prompt_id}. "
        f"{intents[prompt_id]} "
        "Call usage_status once, do not refresh, and use at most one "
        "usage_query call. Return only the requested structured result."
    )
    version = subprocess.run(
        ["codex", "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    environment = dict(os.environ)
    environment["CODEX_USAGE_TRACKER_CACHE_ROOT"] = str(cache_root.resolve())
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--json",
        "--output-schema",
        str(repo_root / _ANSWER_SCHEMA.relative_to(_REPO_ROOT)),
        "-C",
        str(repo_root),
        prompt,
    ]
    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    stdout = process.stdout
    if stdout is None:
        raise RuntimeError("Codex host stdout is unavailable")
    lines: queue.Queue[str | None] = queue.Queue()

    def read_lines() -> None:
        for line in stdout:
            lines.put(line)
        lines.put(None)

    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()
    events: list[tuple[float, Mapping[str, Any]]] = []
    deadline = started + timeout_seconds
    while time.perf_counter() < deadline:
        try:
            line = lines.get(timeout=0.1)
        except queue.Empty:
            if process.poll() is not None:
                break
            continue
        if line is None:
            break
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(((time.perf_counter() - started) * 1_000, event))
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    total_ms = (time.perf_counter() - started) * 1_000
    return summarize_cli_observation(
        events,
        total_ms=total_ms,
        host_version=version,
        candidate_registration=candidate_registration,
        candidate_digest=candidate_digest,
        candidate_version=candidate_version,
        catalog_tools=catalog_tools,
        registration_observed=registration_observed,
        handshake_observed=handshake_observed,
        exposure_observed=exposure_observed,
        prompt_id=prompt_id,
        expected_facts=prompt_oracle(cache_root, prompt_id),
    )


def _walk(value: Any, prefix: str = "") -> Iterator[tuple[str, str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else str(key)
            yield location, str(key), child
            yield from _walk(child, location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            location = f"{prefix}[{index}]"
            yield from _walk(child, location)


def _schema_failures(value: Any, schema: Mapping[str, Any], label: str) -> list[str]:
    """Validate the closed scorecard schema without adding a runtime dependency."""

    failures: list[str] = []
    expected = schema.get("type")
    expected_types = expected if isinstance(expected, list) else [expected]
    matches = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "null": value is None,
        None: True,
    }
    if not any(matches.get(item, False) for item in expected_types):
        return [f"{label} has invalid type"]
    if "const" in schema and value != schema["const"]:
        failures.append(f"{label} differs from constant")
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"{label} is unsupported")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        missing = sorted(set(schema.get("required", [])) - set(value))
        failures.extend(f"{label} is missing {key}" for key in missing)
        unexpected = sorted(set(value) - set(properties))
        if schema.get("additionalProperties") is False:
            failures.extend(f"{label} has unexpected property {key}" for key in unexpected)
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                failures.extend(_schema_failures(child, child_schema, f"{label}.{key}"))
    elif isinstance(value, list):
        if len(value) < int(schema.get("minItems", 0)):
            failures.append(f"{label} has too few items")
        if len(value) > int(schema.get("maxItems", len(value))):
            failures.append(f"{label} has too many items")
        child_schema = schema.get("items")
        if isinstance(child_schema, dict):
            for index, child in enumerate(value):
                failures.extend(_schema_failures(child, child_schema, f"{label}[{index}]"))
    elif isinstance(value, str):
        if len(value) < int(schema.get("minLength", 0)):
            failures.append(f"{label} is too short")
        if len(value) > int(schema.get("maxLength", len(value))):
            failures.append(f"{label} is too long")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            failures.append(f"{label} is below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            failures.append(f"{label} exceeds maximum")
    return failures


def scorecard_failures(
    scorecard: Mapping[str, Any],
    contract: Mapping[str, Any] | None = None,
) -> list[str]:
    """Return bounded schema, host-proof, and privacy failures."""

    contract = contract or load_contract()
    failures: list[str] = []
    schema_path = _REPO_ROOT / contract["privacy"]["scorecard_schema_path"]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    failures.extend(_schema_failures(scorecard, schema, "scorecard"))
    for location, _key, value in _walk(scorecard):
        if isinstance(value, str) and (
            _PATH_OR_URI.search(value) or not _SAFE_STRING.fullmatch(value)
        ):
            failures.append(f"forbidden local path-like value: {location}")
    if scorecard.get("schema") != contract["scorecard_schema"]:
        failures.append("scorecard schema is invalid")
    encoded = json.dumps(scorecard, separators=(",", ":"), sort_keys=True).encode()
    if len(encoded) > int(contract["privacy"]["max_scorecard_bytes"]):
        failures.append("scorecard exceeds bounded byte budget")
    runs = scorecard.get("runs")
    if not isinstance(runs, list):
        failures.append("scorecard runs must be an array")
        runs = []
    supported_hosts = {item["id"] for item in contract["supported_hosts"]}
    prompt_ids = {item["id"] for item in contract["prompt_suite"]}
    scenarios = {item["id"] for item in contract["scenarios"]}
    expected_pairs = {(host, prompt) for host in supported_hosts for prompt in prompt_ids}
    observed_pairs: set[tuple[Any, Any]] = set()
    host_contract = {item["id"]: item for item in contract["supported_hosts"]}
    prompt_contract = {item["id"]: item for item in contract["prompt_suite"]}
    candidate = scorecard.get("candidate", {})
    for index, run in enumerate(runs):
        if not isinstance(run, dict):
            continue
        observed_pairs.add((run.get("host"), run.get("prompt_id")))
        if run.get("host") not in supported_hosts:
            failures.append(f"runs[{index}] host is unsupported")
        if run.get("prompt_id") not in prompt_ids:
            failures.append(f"runs[{index}] prompt ID is unsupported")
        if run.get("scenario") not in scenarios:
            failures.append(f"runs[{index}] scenario is unsupported")
        expected_launch = host_contract.get(run.get("host"), {}).get("launch_method")
        if run.get("launch_method") != expected_launch:
            failures.append(f"runs[{index}] launch method is not fresh-host qualified")
        proof = (
            run.get("registration_observed") is True
            and run.get("handshake_observed") is True
            and run.get("catalog_observed") is True
            and run.get("exposure_observed") is True
            and run.get("catalog_tools") == list(MCP_TOOLS)
            and run.get("candidate_digest") == candidate.get("bundle_digest")
            and run.get("candidate_version") == candidate.get("version")
        )
        if run.get("fresh_task") is not proof:
            failures.append(f"runs[{index}] fresh-task proof is inconsistent")
        selector_required = prompt_contract.get(run.get("prompt_id"), {}).get(
            "selector_required"
        )
        if selector_required is False and run.get("selector_validity") != "not_applicable":
            failures.append(f"runs[{index}] selector validity must be not_applicable")
        if selector_required is True and run.get("selector_validity") not in {0, 1}:
            failures.append(f"runs[{index}] selector validity is missing")
    missing_pairs = sorted(expected_pairs - observed_pairs)
    extra_pairs = sorted(observed_pairs - expected_pairs)
    failures.extend(f"missing host prompt coverage: {host} {prompt}" for host, prompt in missing_pairs)
    failures.extend(f"duplicate or invalid host prompt coverage: {host} {prompt}" for host, prompt in extra_pairs)
    if len(observed_pairs) != len(runs):
        failures.append("host prompt coverage contains duplicates")
    scenario_runs = scorecard.get("scenario_runs", [])
    observed_scenarios = {
        item.get("scenario")
        for item in scenario_runs
        if isinstance(item, dict)
    }
    for scenario in sorted(scenarios - observed_scenarios):
        failures.append(f"missing measured scenario: {scenario}")
    if len(observed_scenarios) != len(scenario_runs):
        failures.append("scenario coverage contains duplicates")
    return sorted(set(failures))


def stable_scorecard_shape(value: Any) -> Any:
    """Remove volatile measurements while preserving structural outcomes."""

    if isinstance(value, dict):
        return {
            key: ("<measurement>" if key in _MEASUREMENT_KEYS else stable_scorecard_shape(child))
            for key, child in sorted(value.items())
        }
    if isinstance(value, list):
        return [stable_scorecard_shape(item) for item in value]
    return value


def _write_json(path: Path | None, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path is None:
        sys.stdout.write(encoded)
    else:
        path.write_text(encoded, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate-history")
    generate.add_argument("--profile", required=True)
    generate.add_argument("--seed", type=int, default=20260727)
    generate.add_argument("--workspace", type=Path, required=True)
    generate.add_argument("--output", type=Path)
    storage = subparsers.add_parser("storage-baseline")
    storage.add_argument("--profile", required=True)
    storage.add_argument("--seed", type=int, default=20260727)
    storage.add_argument("--workspace", type=Path, required=True)
    storage.add_argument("--output", type=Path)
    lifecycle = subparsers.add_parser("lifecycle-baseline")
    lifecycle.add_argument("--seed", type=int, default=20260727)
    lifecycle.add_argument("--workspace", type=Path, required=True)
    lifecycle.add_argument("--output", type=Path)
    candidate = subparsers.add_parser("candidate-identity")
    candidate.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    candidate.add_argument("--wheel", type=Path, required=True)
    candidate.add_argument("--cached-bundle", type=Path, required=True)
    candidate.add_argument("--output", type=Path)
    cli_host = subparsers.add_parser("run-cli-host")
    cli_host.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    cli_host.add_argument("--cache-root", type=Path, required=True)
    cli_host.add_argument("--prompt-id", default="top_threads")
    cli_host.add_argument("--candidate-registration", required=True)
    cli_host.add_argument("--candidate-digest", required=True)
    cli_host.add_argument("--candidate-version", required=True)
    cli_host.add_argument("--catalog-observed", action="store_true")
    cli_host.add_argument("--registration-observed", action="store_true")
    cli_host.add_argument("--handshake-observed", action="store_true")
    cli_host.add_argument("--exposure-observed", action="store_true")
    cli_host.add_argument("--timeout-seconds", type=float, default=120)
    cli_host.add_argument("--output", type=Path)
    validate = subparsers.add_parser("validate-scorecard")
    validate.add_argument("--scorecard", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "generate-history":
        _write_json(
            arguments.output,
            generate_history(
                arguments.workspace,
                profile=arguments.profile,
                seed=arguments.seed,
            ),
        )
        return 0
    if arguments.command == "storage-baseline":
        _write_json(
            arguments.output,
            run_storage_baseline(
                arguments.workspace,
                profile=arguments.profile,
                seed=arguments.seed,
            ),
        )
        return 0
    if arguments.command == "lifecycle-baseline":
        _write_json(
            arguments.output,
            {"scenario_runs": run_lifecycle_baseline(arguments.workspace, seed=arguments.seed)},
        )
        return 0
    if arguments.command == "candidate-identity":
        _write_json(
            arguments.output,
            candidate_identity(
                repo_root=arguments.repo_root,
                wheel=arguments.wheel,
                cached_bundle=arguments.cached_bundle,
            ),
        )
        return 0
    if arguments.command == "run-cli-host":
        _write_json(
            arguments.output,
            run_cli_host_task(
                repo_root=arguments.repo_root,
                cache_root=arguments.cache_root,
                prompt_id=arguments.prompt_id,
                candidate_registration=arguments.candidate_registration,
                candidate_digest=arguments.candidate_digest,
                candidate_version=arguments.candidate_version,
                catalog_tools=list(MCP_TOOLS) if arguments.catalog_observed else [],
                registration_observed=arguments.registration_observed,
                handshake_observed=arguments.handshake_observed,
                exposure_observed=arguments.exposure_observed,
                timeout_seconds=arguments.timeout_seconds,
            ),
        )
        return 0
    scorecard = json.loads(arguments.scorecard.read_text(encoding="utf-8"))
    failures = scorecard_failures(scorecard)
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    print("Agent-outcome scorecard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
