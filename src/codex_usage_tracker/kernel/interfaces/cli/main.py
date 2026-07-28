"""Operational CLI over the shared kernel application."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ... import __version__
from ...application import RuntimePaths, build_application, default_runtime_paths
from ...application.codec import json_value
from ...application.service import run_refresh_worker
from ...content import ContextComposition
from ...database import initialize_analytical_database
from ...hydration import HydrationPreset
from ...operational import (
    initialize_operational_database,
    load_cutover_control,
    rollback_cutover,
)
from ..http.app import API_PREFIX
from ..http.server import create_server

COMMANDS = (
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-usage-tracker",
        description="Exact local Codex usage facts and evidence.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup", help="initialize the kernel cache")
    subparsers.add_parser("status", help="show committed generation status")
    refresh = subparsers.add_parser("refresh", help="start or join refresh")
    refresh.add_argument("--wait", type=float, default=0, metavar="SECONDS")
    refresh.add_argument(
        "--preset",
        choices=tuple(item.value for item in HydrationPreset),
    )
    for name in ("query", "export"):
        command = subparsers.add_parser(name, help=f"run bounded {name}")
        command.add_argument("--request", required=True, help="JSON request")
        if name == "export":
            command.add_argument("--output", type=Path, required=True)
    open_command = subparsers.add_parser(
        "open",
        help="open the local Evidence Console",
    )
    open_command.add_argument("--host", default="127.0.0.1")
    open_command.add_argument("--port", type=int, default=8765)
    open_command.add_argument("--selector")
    open_command.add_argument("--no-browser", action="store_true")
    service = subparsers.add_parser("service", help="run local HTTP service")
    service_subparsers = service.add_subparsers(dest="service_command", required=True)
    serve = service_subparsers.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    subparsers.add_parser("config", help="show resolved local paths")
    content = subparsers.add_parser(
        "content",
        help="manage optional context-composition metadata",
    )
    content_subparsers = content.add_subparsers(
        dest="content_command",
        required=True,
    )
    content_subparsers.add_parser("status", help="show content capability status")
    enable_content = content_subparsers.add_parser(
        "enable",
        help="enable private local content indexing",
    )
    enable_content.add_argument(
        "--confirm-private-content",
        action="store_true",
        help="confirm that bounded private content may be processed locally",
    )
    enable_content.add_argument(
        "--store-redacted-fragments",
        action="store_true",
        help="retain bounded redacted fragments in the isolated content database",
    )
    content_subparsers.add_parser(
        "index",
        help="consume the latest committed kernel generation",
    )
    content_subparsers.add_parser("disable", help="disable content indexing")
    content_subparsers.add_parser(
        "delete",
        help="delete the isolated content database",
    )
    repair = subparsers.add_parser("repair", help="validate or roll back cache")
    repair.add_argument("--rollback", action="store_true")
    subparsers.add_parser("package", help="show package identity")
    subparsers.add_parser("_mcp", help=argparse.SUPPRESS)
    subparsers.add_parser("_refresh-worker", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "_mcp":
        from ..mcp.server import run_stdio

        run_stdio()
        return 0
    try:
        result = _run(arguments)
    except sqlite3.Error:
        print(
            json.dumps({"error": "kernel cache is unavailable"}),
            file=sys.stderr,
        )
        return 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    if result is not None:
        print(json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def _run(arguments: argparse.Namespace) -> dict[str, Any] | None:
    runtime = default_runtime_paths()
    application = build_application(runtime)
    if arguments.command == "setup":
        initialize_analytical_database(runtime.kernel.analytical)
        initialize_operational_database(runtime.kernel.operational)
        return {"cache_root": str(runtime.cache_root), "state": "absent"}
    if arguments.command == "status":
        return application.status()
    if arguments.command == "refresh":
        return application.refresh(
            wait_seconds=arguments.wait,
            hydration_preset=(
                HydrationPreset(arguments.preset)
                if arguments.preset is not None
                else None
            ),
        )
    if arguments.command in {"query", "export"}:
        result = application.query(_request_payload(arguments.request))
        if arguments.command == "export":
            payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
            arguments.output.write_text(payload, encoding="utf-8")
            return {"output": str(arguments.output), "rows": _row_count(result)}
        return result
    if arguments.command == "open":
        url = _console_url(
            arguments.host,
            arguments.port,
            arguments.selector,
        )
        if not arguments.no_browser:
            webbrowser.open(url)
        return {"url": url}
    if arguments.command == "service":
        server = create_server(
            application,
            host=arguments.host,
            port=arguments.port,
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return None
    if arguments.command == "config":
        return {
            "codex_home": str(runtime.codex_home),
            "cache_root": str(runtime.cache_root),
            "content_database": str(runtime.content),
            "http_prefix": API_PREFIX,
        }
    if arguments.command == "content":
        return _run_content(arguments, runtime)
    if arguments.command == "repair":
        if not runtime.kernel.operational.is_file():
            raise ValueError("kernel cache is absent")
        control = (
            rollback_cutover(runtime.kernel.operational)
            if arguments.rollback
            else load_cutover_control(runtime.kernel.operational)
        )
        return json_value(control)
    if arguments.command == "package":
        return {"name": "codex-usage-tracking", "version": __version__}
    if arguments.command == "_refresh-worker":
        return run_refresh_worker(runtime)
    raise ValueError("unknown command")


def _run_content(
    arguments: argparse.Namespace,
    runtime: RuntimePaths,
) -> dict[str, Any]:
    content = ContextComposition(
        runtime.content,
        runtime.kernel.operational,
    )
    handlers = {
        "status": content.status,
        "enable": lambda: content.enable(
            privacy_confirmed=arguments.confirm_private_content,
            store_redacted_fragments=arguments.store_redacted_fragments,
        ),
        "index": content.index,
        "disable": content.disable,
        "delete": content.delete,
    }
    try:
        handler = handlers[arguments.content_command]
    except KeyError as exc:
        raise ValueError("unknown content command") from exc
    return handler()


def _request_payload(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("request must be a JSON object")
    return payload


def _console_url(host: str, port: int, selector: str | None) -> str:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("open host must be loopback")
    if not 1 <= port <= 65_535:
        raise ValueError("open port is invalid")
    base = f"http://{host}:{port}/"
    return (
        f"{base}live"
        if selector is None
        else f"{base}evidence/{quote(selector, safe='')}?view=summary"
    )


def _row_count(result: dict[str, Any]) -> int:
    return sum(
        len(item.get("rows", []))
        for item in result.get("results", [])
        if isinstance(item, dict)
    )


if __name__ == "__main__":
    raise SystemExit(main())
