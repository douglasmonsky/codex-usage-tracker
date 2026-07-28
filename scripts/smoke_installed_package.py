#!/usr/bin/env python3
"""Smoke the installed lean kernel from a wheel or package index."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import venv
from pathlib import Path
from typing import Any, cast

try:
    from scripts.smoke_installed_catalog import (
        CLI_HELP_SUBCOMMANDS,
        MCP_TOOLS,
        RESOURCE_PATHS,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from smoke_installed_catalog import (  # type: ignore[import-not-found,no-redef]
        CLI_HELP_SUBCOMMANDS,
        MCP_TOOLS,
        RESOURCE_PATHS,
    )

try:
    import tomllib  # type: ignore[import-not-found,import-untyped]
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[import-not-found,no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_NAME = "codex-usage-tracking"
WHEEL_STEM = "codex_usage_tracking"
DEFAULT_DOCKER_IMAGE = (
    "python:3.14-slim@sha256:"
    "cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6"
)
_ORACLE = REPO_ROOT / "tests" / "kernel" / "fixtures" / "accounting-oracle-v1"

def _python(venv_root: Path) -> Path:
    return venv_root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _command(venv_root: Path) -> Path:
    directory = "Scripts" if os.name == "nt" else "bin"
    suffix = ".exe" if os.name == "nt" else ""
    return venv_root / directory / f"codex-usage-tracker{suffix}"


def _run_json(
    command: list[str | Path],
    *,
    environment: dict[str, str],
    timeout: float = 30,
) -> dict[str, object]:
    result = subprocess.run(
        [str(part) for part in command],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
        timeout=timeout,
    )
    payload = json.loads(result.stdout)
    if not isinstance(payload, dict):
        raise RuntimeError("installed command did not return a JSON object")
    return payload


def _resolve_install_target(args: argparse.Namespace, temp_dir: Path) -> str:
    if args.from_pypi:
        return (
            f"{DISTRIBUTION_NAME}=={args.version}"
            if args.version
            else DISTRIBUTION_NAME
        )
    if args.artifact_dir is not None:
        artifact_dir = args.artifact_dir.resolve()
        if not artifact_dir.is_dir():
            raise FileNotFoundError(
                f"artifact directory does not exist: {artifact_dir}"
            )
        pattern = args.version or "*"
        wheels = sorted(artifact_dir.glob(f"{WHEEL_STEM}-{pattern}-*.whl"))
        if len(wheels) != 1:
            raise FileNotFoundError(
                "expected exactly one matching wheel in artifact directory; "
                f"found {[path.name for path in wheels]}"
            )
        return str(wheels[0].resolve())

    version = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    dist = temp_dir / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--outdir", str(dist)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = dist / f"{WHEEL_STEM}-{version}-py3-none-any.whl"
    if not wheel.is_file():
        raise FileNotFoundError(f"expected built wheel was not created: {wheel}")
    return str(wheel)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _await(url: str) -> bytes:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return response.read()
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"installed service did not serve {url}")


def _write_mcp(
    process: subprocess.Popen[str],
    request: dict[str, object],
    *,
    timeout: float = 10,
) -> dict[str, object]:
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("installed MCP pipes are unavailable")
    stdout = process.stdout
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    lines: queue.Queue[str] = queue.Queue(maxsize=1)
    reader = threading.Thread(
        target=lambda: lines.put(stdout.readline()),
        daemon=True,
    )
    reader.start()
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty as exc:
        _stop_process(process)
        raise TimeoutError("installed MCP response deadline exceeded") from exc
    if not line:
        stderr = process.stderr.read() if process.stderr is not None else ""
        raise RuntimeError(f"installed MCP process exited without response: {stderr}")
    response = json.loads(line)
    if not isinstance(response, dict):
        raise RuntimeError("installed MCP response is invalid")
    return response


def _stop_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _call_mcp(
    process: subprocess.Popen[str],
    request_id: int,
    name: str,
    arguments: dict[str, object],
) -> dict[str, object]:
    response = _write_mcp(
        process,
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    result = response.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        raise RuntimeError(f"installed MCP call failed: {name}: {response}")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise RuntimeError(f"installed MCP call is unstructured: {name}")
    return structured


def _dogfood_query() -> dict[str, object]:
    return {
        "requests": [
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["thread"],
                "measures": ["calls", "total_tokens"],
                "limit": 25,
            },
            {
                "dataset": "calls",
                "operation": "share",
                "dimensions": ["thread"],
                "measures": ["total_tokens"],
                "limit": 25,
            },
            {
                "dataset": "calls",
                "operation": "aggregate",
                "dimensions": ["model", "effort"],
                "measures": ["calls", "total_tokens"],
                "limit": 25,
            },
            {
                "dataset": "calls",
                "operation": "comparison",
                "dimensions": ["model"],
                "measures": ["calls", "total_tokens"],
                "comparison": {
                    "current_start": "2026-01-02T00:00:00Z",
                    "current_end": "2026-01-03T00:00:00Z",
                    "previous_start": "2026-01-01T00:00:00Z",
                    "previous_end": "2026-01-02T00:00:00Z",
                },
                "limit": 25,
            },
            {
                "dataset": "tools",
                "operation": "aggregate",
                "dimensions": ["tool"],
                "measures": ["tools", "duration_ms", "output_bytes"],
                "limit": 25,
            },
            {
                "dataset": "turns",
                "operation": "aggregate",
                "dimensions": ["thread"],
                "measures": ["turns", "duration_ms"],
                "limit": 25,
            },
        ]
    }


def _assert_dogfood_results(results: list[object]) -> None:
    call_rows = _result_rows(results, 0)
    share_rows = _result_rows(results, 1)
    model_rows = _result_rows(results, 2)
    comparison_rows = _result_rows(results, 3)
    tool_rows = _result_rows(results, 4)
    turn_rows = _result_rows(results, 5)
    if (
        sum(int(row["calls"]) for row in call_rows) != 4
        or sum(int(row["total_tokens"]) for row in call_rows) != 515
    ):
        raise RuntimeError("installed MCP call totals differ from the oracle")
    if (
        sum(int(row["total_tokens"]) for row in share_rows) != 515
        or abs(sum(float(row["share_total_tokens"]) for row in share_rows) - 1)
        > 1e-12
    ):
        raise RuntimeError("installed MCP concentration differs from the oracle")
    actual_models = {
        (
            str(row["model"]),
            str(row["effort"]),
            int(row["calls"]),
            int(row["total_tokens"]),
        )
        for row in model_rows
    }
    if actual_models != {
        ("gpt-5.3-codex", "medium", 2, 155),
        ("gpt-5.4", "high", 2, 360),
    }:
        raise RuntimeError("installed MCP model matrix differs from the oracle")
    if (
        sum(int(row["current_calls"]) for row in comparison_rows) != 2
        or sum(int(row["current_total_tokens"]) for row in comparison_rows)
        != 155
        or sum(int(row["previous_calls"]) for row in comparison_rows) != 2
        or sum(int(row["previous_total_tokens"]) for row in comparison_rows)
        != 360
    ):
        raise RuntimeError("installed MCP comparison differs from the oracle")
    actual_tools = sum(int(row["tools"]) for row in tool_rows)
    actual_turns = sum(int(row["turns"]) for row in turn_rows)
    if actual_tools != 2 or actual_turns != 4:
        raise RuntimeError(
            "installed MCP structural totals differ from the oracle: "
            f"tools={actual_tools}, turns={actual_turns}"
        )


def _result_rows(
    results: list[object],
    index: int,
) -> list[dict[str, Any]]:
    if index >= len(results):
        raise RuntimeError("installed MCP dogfood result is missing")
    result = results[index]
    if not isinstance(result, dict):
        raise RuntimeError("installed MCP dogfood result is invalid")
    rows = result.get("rows")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("installed MCP dogfood rows are empty")
    if not all(isinstance(row, dict) for row in rows):
        raise RuntimeError("installed MCP dogfood row is invalid")
    return cast(list[dict[str, Any]], rows)


def _installed_mcp_command(
    config_path: Path,
    environment: dict[str, str],
) -> list[str]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    server = config["mcpServers"]["codex-usage-tracker"]
    if not isinstance(server, dict):
        raise RuntimeError("installed plugin MCP configuration is invalid")
    executable = shutil.which(server["command"], path=environment.get("PATH"))
    if executable is None:
        raise RuntimeError("installed plugin MCP executable is unavailable")
    return [executable, *server["args"]]


def _smoke_mcp(
    config_path: Path,
    environment: dict[str, str],
    *,
    expected_generation: int,
) -> None:
    command = _installed_mcp_command(config_path, environment)
    for task_number in range(2):
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            text=True,
        )
        try:
            _write_mcp(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {},
                },
            )
            listed = _write_mcp(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            result = listed.get("result")
            tools = (
                tuple(item["name"] for item in result["tools"])
                if isinstance(result, dict)
                else ()
            )
            if tools != MCP_TOOLS:
                raise RuntimeError(f"installed MCP catalog differs: {tools}")
            status = _call_mcp(process, 3, "usage_status", {})
            refresh = _call_mcp(
                process,
                4,
                "usage_refresh",
                {"wait_seconds": 30},
            )
            job = refresh.get("job")
            if not isinstance(job, dict):
                raise RuntimeError("installed MCP refresh returned no job")
            result = job.get("result")
            if (
                job.get("terminal") is not True
                or job.get("state") != "completed"
                or not isinstance(result, dict)
                or result.get("planner_reason") != "no_changes"
                or result.get("generation") != expected_generation
                or result.get("inserted_calls") != 0
            ):
                raise RuntimeError(
                    f"installed MCP no-change refresh is invalid: {refresh}"
                )
            job_status = _call_mcp(
                process,
                5,
                "usage_job_status",
                {
                    "job_id": job["job_id"],
                    "include_result": True,
                },
            )
            if (
                job_status.get("job_id") != job["job_id"]
                or job_status.get("terminal") is not True
                or job_status.get("result") != result
            ):
                raise RuntimeError("installed MCP terminal job state differs")
            query = _call_mcp(
                process,
                6,
                "usage_query",
                _dogfood_query(),
            )
            results = query.get("results")
            if not isinstance(results, list) or len(results) != 6:
                raise RuntimeError("installed MCP dogfood query is incomplete")
            _assert_dogfood_results(results)
            selectors = [
                selector
                for item in results
                if isinstance(item, dict)
                for selector in item.get("evidence_selectors", [])
                if isinstance(selector, str)
            ]
            if not selectors:
                raise RuntimeError("installed MCP dogfood returned no evidence")
            evidence = _call_mcp(
                process,
                7,
                "usage_evidence",
                {"selector": selectors[0], "view": "timeline", "limit": 10},
            )
            allowance = _call_mcp(
                process,
                8,
                "usage_allowance",
                {"limit": 10},
            )
            generations = {
                payload.get("generation")
                for payload in (status, evidence)
            }
            generations.update(
                item.get("generation")
                for item in results
                if isinstance(item, dict)
            )
            if generations != {expected_generation}:
                raise RuntimeError(
                    f"fresh MCP task {task_number + 1} mixed generations: "
                    f"{generations}"
                )
            if allowance.get("generation") not in {None, expected_generation}:
                raise RuntimeError(
                    f"fresh MCP task {task_number + 1} allowance generation "
                    f"is invalid: {allowance.get('generation')}"
                )
        finally:
            _stop_process(process)


def _smoke_service(
    command: Path,
    environment: dict[str, str],
    *,
    expected_generation: int,
) -> float:
    port = _free_port()
    server = subprocess.Popen(
        [command, "service", "serve", "--port", str(port)],
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        live_url = f"http://127.0.0.1:{port}/live"
        if b"data-console-shell" not in _await(live_url):
            raise RuntimeError("installed Evidence Console shell is missing")
        warm_samples: list[float] = []
        for _index in range(5):
            started = time.perf_counter()
            _await(live_url)
            warm_samples.append((time.perf_counter() - started) * 1_000)
        warm_p95_ms = max(warm_samples)
        if warm_p95_ms > 500:
            raise RuntimeError(
                f"installed warm Console p95 is too slow: {warm_p95_ms:.3f} ms"
            )
        status = json.loads(
            _await(f"http://127.0.0.1:{port}/api/kernel/v1/status")
        )
        if (
            status.get("state") != "active"
            or status.get("generation") != expected_generation
        ):
            raise RuntimeError(f"installed service status is invalid: {status}")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)
    return warm_p95_ms


def smoke_install(
    target: str,
    *,
    version: str | None = None,
    upgrade_from: str | None = None,
) -> None:
    with tempfile.TemporaryDirectory(prefix="kernel-installed-smoke-") as name:
        root = Path(name)
        venv_root = root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(venv_root)
        python = _python(venv_root)
        initial_target = (
            (
                str(Path(upgrade_from).resolve())
                if Path(upgrade_from).is_file()
                else f"{DISTRIBUTION_NAME}=={upgrade_from}"
            )
            if upgrade_from is not None
            else target
        )
        subprocess.run(
            [
                python,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-deps",
                initial_target,
            ],
            check=True,
        )
        codex_home = root / "codex"
        shutil.copytree(_ORACLE / "logs" / "sessions", codex_home / "sessions")
        shutil.copytree(
            _ORACLE / "logs" / "archived_sessions",
            codex_home / "archived_sessions",
        )
        cache_root = root / "cache"
        environment = os.environ.copy()
        environment["CODEX_HOME"] = str(codex_home)
        environment["CODEX_USAGE_TRACKER_CACHE_ROOT"] = str(cache_root)
        command = _command(venv_root)
        environment["PATH"] = (
            str(command.parent)
            + os.pathsep
            + environment.get("PATH", "")
        )
        prior_cache: dict[Path, bytes] | None = None
        if upgrade_from is not None:
            _run_json(
                [command, "refresh", "--wait", "30"],
                environment=environment,
                timeout=40,
            )
            prior = _run_json([command, "status"], environment=environment)
            if prior.get("state") != "active" or prior.get("generation") != 1:
                raise RuntimeError(
                    f"upgrade base did not activate generation 1: {prior}"
                )
            prior_cache = {
                path.relative_to(cache_root): path.read_bytes()
                for path in cache_root.rglob("*")
                if path.is_file()
            }
            subprocess.run(
                [
                    python,
                    "-m",
                    "pip",
                    "install",
                    "--quiet",
                    "--no-deps",
                    "--upgrade",
                    "--force-reinstall",
                    target,
                ],
                check=True,
            )
        plugin_root = root / "plugin"
        (plugin_root / ".codex-plugin").mkdir(parents=True)
        shutil.copy2(
            REPO_ROOT / ".codex-plugin" / "plugin.json",
            plugin_root / ".codex-plugin" / "plugin.json",
        )
        shutil.copy2(REPO_ROOT / ".mcp.json", plugin_root / ".mcp.json")

        initial = _run_json([command, "status"], environment=environment)
        if upgrade_from is None:
            if initial.get("state") != "absent" or cache_root.exists():
                raise RuntimeError(
                    "clean installed status must stay absent and read-only"
                )
        else:
            current_cache = {
                path.relative_to(cache_root): path.read_bytes()
                for path in cache_root.rglob("*")
                if path.is_file()
            }
            if (
                initial.get("state") != "active"
                or initial.get("generation") != 1
                or current_cache != prior_cache
            ):
                raise RuntimeError(
                    "installed upgrade changed the active cache before refresh"
                )
        help_text = subprocess.run(
            [command, "--help"],
            check=True,
            capture_output=True,
            env=environment,
            text=True,
        ).stdout
        if any(name not in help_text for name in CLI_HELP_SUBCOMMANDS):
            raise RuntimeError("installed CLI catalog is incomplete")
        installed_root = next(
            python.parent.parent.glob(
                "lib/python*/site-packages/codex_usage_tracker"
            )
        )
        missing_resources = [
            path
            for path in RESOURCE_PATHS
            if not (installed_root.parent / path).is_file()
        ]
        if missing_resources:
            raise RuntimeError(
                f"installed package resources are missing: {missing_resources}"
            )
        package = _run_json([command, "package"], environment=environment)
        if version is not None and package.get("version") != version:
            raise RuntimeError(f"installed version differs: {package}")
        _run_json(
            [command, "refresh", "--wait", "30", "--preset", "complete"],
            environment=environment,
            timeout=40,
        )
        active = _run_json([command, "status"], environment=environment)
        expected_generation = 2 if upgrade_from is not None else 1
        if (
            active.get("state") != "active"
            or active.get("generation") != expected_generation
        ):
            raise RuntimeError(f"installed refresh did not activate: {active}")
        content_status = _run_json(
            [command, "content", "status"],
            environment=environment,
        )
        if content_status.get("state") != "disabled":
            raise RuntimeError("installed content capability must default off")
        _run_json(
            [command, "content", "enable", "--confirm-private-content"],
            environment=environment,
        )
        content_index = _run_json(
            [command, "content", "index"],
            environment=environment,
        )
        indexed_events = content_index.get("events")
        if (
            content_index.get("indexed_generation") != expected_generation
            or not isinstance(indexed_events, int)
            or indexed_events < 1
        ):
            raise RuntimeError("installed content index is incomplete")
        context_request = json.dumps(
            {
                "requests": [
                    {
                        "dataset": "context",
                        "operation": "aggregate",
                        "dimensions": ["category"],
                        "measures": ["events", "observed_bytes"],
                        "limit": 25,
                    }
                ]
            },
            separators=(",", ":"),
        )
        context_query = _run_json(
            [command, "query", "--request", context_request],
            environment=environment,
        )
        context_results = context_query.get("results")
        first_context = (
            context_results[0]
            if isinstance(context_results, list)
            and context_results
            and isinstance(context_results[0], dict)
            else {}
        )
        if first_context.get("grade") != "exact":
            raise RuntimeError("installed context bytes are not labeled exact")
        _run_json(
            [command, "content", "delete"],
            environment=environment,
        )
        if _run_json([command, "status"], environment=environment).get(
            "generation"
        ) != expected_generation:
            raise RuntimeError("content deletion affected installed accounting")
        _smoke_mcp(
            plugin_root / ".mcp.json",
            environment,
            expected_generation=expected_generation,
        )
        warm_p95_ms = _smoke_service(
            command,
            environment,
            expected_generation=expected_generation,
        )
    print(
        "Installed kernel package smoke passed "
        f"(two fresh MCP tasks; warm Console p95 {warm_p95_ms:.3f} ms)."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-pypi", action="store_true")
    parser.add_argument("--version")
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument(
        "--upgrade-from",
        help="public version or local wheel used to create the pre-upgrade cache",
    )
    arguments = parser.parse_args()
    if arguments.from_pypi and arguments.artifact_dir is not None:
        parser.error("--from-pypi and --artifact-dir are mutually exclusive")
    with tempfile.TemporaryDirectory(prefix="kernel-smoke-build-") as name:
        target = _resolve_install_target(arguments, Path(name))
        smoke_install(
            target,
            version=arguments.version,
            upgrade_from=arguments.upgrade_from,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
