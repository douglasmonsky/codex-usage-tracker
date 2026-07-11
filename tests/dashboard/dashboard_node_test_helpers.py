from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest


def _run_node_script(
    *, asset_name: str, script: str, context: str, setup: str = ""
) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard JavaScript tests")
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / asset_name
    )
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {context};
vm.createContext(context);
vm.runInContext(code, context);
{setup}
{script}
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def run_snapshot_renderer_script(script: str) -> dict[str, Any]:
    setup = """
const factory = context.window.CodexUsageDashboardDiagnosticSnapshots;
function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
"""
    return _run_node_script(
        asset_name="dashboard_diagnostics_snapshots.js",
        script=script,
        context="{ window: {}, console }",
        setup=setup,
    )


def run_dashboard_live_script(script: str) -> dict[str, Any]:
    return _run_node_script(
        asset_name="dashboard_live.js",
        script=script,
        context=(
            "{ window: { clearInterval, setInterval }, URLSearchParams, "
            "fetch: async (url, options) => globalThis.__fetch(url, options), console }"
        ),
        setup="const factory = context.window.CodexUsageDashboardLive;",
    )
