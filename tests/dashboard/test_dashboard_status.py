from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def _run_dashboard_status_script(script: str) -> dict[str, object]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard status helper tests")
    repo_root = Path(__file__).resolve().parents[2]
    script_path = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_status.js"
    )
    wrapped = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{
  window: {{ location: {{ protocol: 'http:' }} }},
  console,
}};
vm.createContext(context);
vm.runInContext(code, context);
const factory = context.window.CodexUsageDashboardStatus;
{script}
"""
    result = subprocess.run(
        [node, "-e", wrapped],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_dashboard_status_hides_duplicate_only_parser_diagnostics() -> None:
    payload = _run_dashboard_status_script(
        """
let diagnostics = { duplicate_cumulative_total: 3 };
let tooltip = 'unset';
const parserDiagnosticsElement = {
  hidden: false,
  textContent: 'Parser warnings',
  dataset: {},
};
const runtime = factory.create({
  getParserDiagnostics: () => diagnostics,
  number: new Intl.NumberFormat('en-US'),
  parserDiagnosticsElement,
  setFastTooltip: (_el, text) => { tooltip = text; },
  t: key => key,
  tf: (key, values = {}) => `${key}:${JSON.stringify(values)}`,
});
runtime.updateParserDiagnosticsLine();
const duplicateOnly = {
  hidden: parserDiagnosticsElement.hidden,
  textContent: parserDiagnosticsElement.textContent,
  tooltip,
};
diagnostics = {
  duplicate_cumulative_total: 3,
  missing_total_token_usage: 2,
};
runtime.updateParserDiagnosticsLine();
console.log(JSON.stringify({
  duplicateOnly,
  mixedHidden: parserDiagnosticsElement.hidden,
  mixedText: parserDiagnosticsElement.textContent,
  mixedTooltip: tooltip,
}));
"""
    )

    assert payload["duplicateOnly"]["hidden"] is True
    assert payload["duplicateOnly"]["textContent"] == ""
    assert payload["duplicateOnly"]["tooltip"] == ""
    assert payload["mixedHidden"] is False
    assert payload["mixedText"] == "badge.parser_warnings"
    assert "missing_total_token_usage=2" in payload["mixedTooltip"]
    assert "duplicate_cumulative_total" not in payload["mixedTooltip"]
