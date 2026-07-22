"""Bounded local checks for conversational dashboard analysis readiness."""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - bounded local runtime probe; no shell is invoked.
from pathlib import Path
from typing import Literal, TypedDict

from codex_usage_tracker import __version__
from codex_usage_tracker.diagnostics.mcp import check_mcp_config, check_mcp_runtime

PLUGIN_NAME = "codex-usage-tracker"
SCHEMA = "codex-usage-tracker-conversational-readiness-v1"
SETUP_ACTION = "Run `codex-usage-tracker setup`, then `codex-usage-tracker doctor`."
PACKAGE_SPEC_MARKER = ".codex-usage-tracker-package-spec"
MODULE_CHECK = (
    "import importlib.metadata; "
    "importlib.metadata.version('codex-usage-tracking'); "
    "importlib.metadata.version('mcp')"
)


class ConversationalReadiness(TypedDict):
    schema: Literal["codex-usage-tracker-conversational-readiness-v1"]
    state: Literal["ready", "restart-required", "unavailable", "unknown"]
    summary: str
    next_action: str | None
    configured_profile: str
    runtime_version_matches: bool
    evidence: list[str]


def conversational_readiness(*, codex_home: Path) -> ConversationalReadiness:
    """Report what can be proven from one explicitly selected local Codex home."""
    plugin_root = codex_home.expanduser().parent / "plugins" / PLUGIN_NAME
    server = _configured_server(plugin_root)
    configured_profile = _configured_profile(server)
    if not _looks_like_plugin_wrapper(plugin_root):
        return _result(
            "unavailable",
            "Conversational analysis is not locally configured.",
            SETUP_ACTION,
            ["Generated plugin wrapper: missing or invalid"],
            configured_profile=configured_profile,
        )

    if configured_profile not in {"core", "full", "developer"}:
        return _result(
            "unavailable",
            "Conversational analysis has an invalid MCP profile configuration.",
            SETUP_ACTION,
            [f"Configured MCP profile: invalid ({configured_profile})"],
            configured_profile=configured_profile,
        )

    config = check_mcp_config(plugin_root)
    runtime = check_mcp_runtime(plugin_root)
    evidence = [
        f"Configured MCP profile: {configured_profile}",
        f"{config.name}: {config.status}",
        f"{runtime.name}: {runtime.status}",
    ]
    if config.status == "fail" or runtime.status == "fail":
        return _result(
            "unavailable",
            "Conversational analysis failed a local configuration or launcher check.",
            SETUP_ACTION,
            evidence,
            configured_profile=configured_profile,
        )
    if config.status != "pass" or runtime.status != "pass":
        return _result(
            "unknown",
            "Conversational analysis readiness could not be determined from local files.",
            "Run `codex-usage-tracker doctor` for a bounded diagnosis.",
            evidence,
            configured_profile=configured_profile,
        )
    if _uses_bootstrap_launcher(plugin_root):
        runtime_ready, version_matches, runtime_evidence = _bootstrap_runtime_ready(
            plugin_root=plugin_root,
            codex_home=codex_home,
        )
        evidence.extend(runtime_evidence)
        if runtime_ready:
            return _result(
                "ready",
                "Local installation and launcher checks passed; current task tool exposure is not verified.",
                None,
                evidence,
                configured_profile=configured_profile,
                runtime_version_matches=version_matches,
            )
        return _result(
            "restart-required",
            "The local launcher is installed; a fresh Codex task is required for discovery.",
            "Restart Codex and open a fresh task to load the plugin tools.",
            evidence,
            configured_profile=configured_profile,
            runtime_version_matches=version_matches,
        )
    return _result(
        "ready",
        "Local installation and launcher checks passed; current task tool exposure is not verified.",
        None,
        evidence,
        configured_profile=configured_profile,
        runtime_version_matches=True,
    )


def _looks_like_plugin_wrapper(plugin_root: Path) -> bool:
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    config_path = plugin_root / ".mcp.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(manifest, dict) and manifest.get("name") == PLUGIN_NAME and config_path.exists()
    )


def _uses_bootstrap_launcher(plugin_root: Path) -> bool:
    try:
        data = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
        server = data["mcpServers"][PLUGIN_NAME]
        args = server["args"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False
    return isinstance(args, list) and any(
        isinstance(arg, str) and arg.endswith("skills/codex-usage-tracker/scripts/run_mcp.py")
        for arg in args
    )


def _bootstrap_runtime_ready(
    *, plugin_root: Path, codex_home: Path
) -> tuple[bool, bool, list[str]]:
    server = _configured_server(plugin_root)
    configured_env = server.get("env")
    env = (
        {str(key): value for key, value in configured_env.items() if isinstance(value, str)}
        if isinstance(configured_env, dict)
        else {}
    )
    configured_runtime = env.get("CODEX_USAGE_TRACKER_RUNTIME_DIR")
    if configured_runtime and Path(configured_runtime).is_absolute():
        runtime_dir = Path(configured_runtime)
    else:
        runtime_dir = (
            codex_home.expanduser().parent
            / ".cache"
            / "codex-usage-tracker"
            / "mcp-runtime"
            / __version__
        )
    expected_spec = env.get(
        "CODEX_USAGE_TRACKER_PACKAGE_SPEC",
        f"codex-usage-tracking=={__version__}",
    )
    marker = runtime_dir / PACKAGE_SPEC_MARKER
    try:
        marker_matches = marker.read_text(encoding="utf-8").strip() == expected_spec
    except OSError:
        marker_matches = False
    if not marker_matches:
        return False, False, ["Bootstrap runtime marker: missing or mismatched"]

    runtime_python = runtime_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        probe_env = os.environ.copy()
        probe_env.update(env)
        result = subprocess.run(  # nosec B603 - fixed argv and bounded local runtime probe.
            [str(runtime_python), "-c", MODULE_CHECK],
            cwd=plugin_root,
            env=probe_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, True, ["Bootstrap runtime marker: pass", "Bootstrap runtime import: fail"]
    if result.returncode:
        return False, True, ["Bootstrap runtime marker: pass", "Bootstrap runtime import: fail"]
    return True, True, ["Bootstrap runtime marker: pass", "Bootstrap runtime import: pass"]


def _configured_server(plugin_root: Path) -> dict[str, object]:
    try:
        data = json.loads((plugin_root / ".mcp.json").read_text(encoding="utf-8"))
        server = data["mcpServers"][PLUGIN_NAME]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return {}
    return dict(server) if isinstance(server, dict) else {}


def _configured_profile(server: dict[str, object]) -> str:
    configured_env = server.get("env")
    if isinstance(configured_env, dict):
        value = configured_env.get("CODEX_USAGE_TRACKER_MCP_PROFILE")
        if isinstance(value, str):
            return value
    args = server.get("args")
    if isinstance(args, list) and "codex_usage_tracker.mcp_server" in args:
        return "full"
    return "core"


def _result(
    state: Literal["ready", "restart-required", "unavailable", "unknown"],
    summary: str,
    next_action: str | None,
    evidence: list[str],
    *,
    configured_profile: str,
    runtime_version_matches: bool = False,
) -> ConversationalReadiness:
    return {
        "schema": SCHEMA,
        "state": state,
        "summary": summary,
        "next_action": next_action,
        "configured_profile": configured_profile,
        "runtime_version_matches": runtime_version_matches,
        "evidence": evidence,
    }
