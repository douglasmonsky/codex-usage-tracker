from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_PACKAGE = _ROOT / "src" / "codex_usage_tracker" / "interfaces" / "mcp"
_IMPLEMENTATION_MODULES = tuple(
    f"codex_usage_tracker.interfaces.mcp.{path.stem}"
    for path in sorted(_PACKAGE.glob("*.py"))
    if path.stem != "__init__"
)

_COMPATIBILITY_MODULES = (
    "codex_usage_tracker.cli.mcp_allowance",
    "codex_usage_tracker.cli.mcp_compression",
    "codex_usage_tracker.cli.mcp_dashboard",
    "codex_usage_tracker.cli.mcp_discovery",
    "codex_usage_tracker.cli.mcp_dogfood",
    "codex_usage_tracker.cli.mcp_investigations",
    "codex_usage_tracker.cli.mcp_server",
    "codex_usage_tracker.cli.mcp_subagents",
    "codex_usage_tracker.cli.mcp_visualization",
    "codex_usage_tracker.cli.mcp_compression_router",
    "codex_usage_tracker.cli.mcp_compression_router_payloads",
)


def test_importing_mcp_modules_creates_no_global_server() -> None:
    module_names = (
        "codex_usage_tracker.interfaces.mcp.runtime",
        *_IMPLEMENTATION_MODULES,
        *_COMPATIBILITY_MODULES,
    )
    script = f"""
import importlib
import json
from mcp.server.fastmcp import FastMCP

events = {{"constructed": 0, "registered": 0}}
original_init = FastMCP.__init__
original_add_tool = FastMCP.add_tool
original_tool = FastMCP.tool

def counted_init(self, *args, **kwargs):
    events["constructed"] += 1
    return original_init(self, *args, **kwargs)

def counted_add_tool(self, *args, **kwargs):
    events["registered"] += 1
    return original_add_tool(self, *args, **kwargs)

def counted_tool(self, *args, **kwargs):
    decorator = original_tool(self, *args, **kwargs)
    def counted_decorator(handler):
        events["registered"] += 1
        return decorator(handler)
    return counted_decorator

FastMCP.__init__ = counted_init
FastMCP.add_tool = counted_add_tool
FastMCP.tool = counted_tool

for module_name in {module_names!r}:
    importlib.import_module(module_name)

print(json.dumps(events, sort_keys=True))
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join((str(_ROOT / "src"), str(_ROOT)))
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {"constructed": 0, "registered": 0}


def test_interface_implementations_have_no_decorator_registration() -> None:
    for module_name in _IMPLEMENTATION_MODULES:
        path = _PACKAGE / f"{module_name.rsplit('.', maxsplit=1)[-1]}.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module == "codex_usage_tracker.cli.mcp_runtime"
            for node in ast.walk(tree)
        ), module_name
        assert not any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "tool"
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            for decorator in node.decorator_list
        ), module_name


def test_legacy_module_paths_reexport_the_extracted_handlers() -> None:
    module_pairs = (
        ("mcp_allowance", "mcp_allowance"),
        ("mcp_compression", "mcp_compression"),
        ("mcp_discovery", "mcp_discovery"),
        ("mcp_dogfood", "mcp_dogfood"),
        ("mcp_investigations", "mcp_investigations"),
        ("mcp_server", "mcp_server_tools"),
        ("mcp_subagents", "mcp_subagents"),
        ("mcp_visualization", "mcp_visualization"),
        ("mcp_compression_router", "mcp_compression_router"),
        (
            "mcp_compression_router_payloads",
            "mcp_compression_router_payloads",
        ),
    )
    for legacy_name, implementation_name in module_pairs:
        legacy = import_module(f"codex_usage_tracker.cli.{legacy_name}")
        implementation = import_module(f"codex_usage_tracker.interfaces.mcp.{implementation_name}")
        assert legacy is implementation

    dashboard = import_module("codex_usage_tracker.cli.mcp_dashboard")
    assert callable(dashboard.usage_status)
    assert callable(dashboard.generate_usage_dashboard)
