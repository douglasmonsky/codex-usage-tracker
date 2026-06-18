from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_dashboard_url_state_round_trips() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for dashboard_state.js round-trip test")
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / "dashboard_state.js"
    script = f"""
const fs = require('fs');
const vm = require('vm');
const code = fs.readFileSync({json.dumps(str(script_path))}, 'utf8');
const context = {{
  URL,
  URLSearchParams,
  window: {{
    location: {{
      href: 'http://127.0.0.1:8877/dashboard.html?external=keep#details',
      search: '?external=keep',
      hash: '#details',
    }},
    history: {{ replaceState: () => {{}} }},
  }},
  navigator: {{}},
  document: {{}},
}};
vm.createContext(context);
vm.runInContext(code, context);

const manager = context.window.CodexUsageDashboardState;
const expected = {{
  view: 'threads',
  search: 'Thread Alpha',
  model: 'gpt-5.5',
  effort: 'high',
  confidence: 'estimated',
  datePreset: 'last-7-days',
  dateStart: '2026-06-01',
  dateEnd: '2026-06-07',
  historyScope: 'all',
  sort: 'usage',
  direction: 'desc',
  preset: 'context-bloat',
  page: 3,
  record: 'record-123',
  thread: 'Thread Alpha',
  expand: 'thread-123',
  expandedThreads: ['Thread Alpha', 'Subagent Child'],
}};
const url = manager.urlFor(expected);
const parsed = new URL(url);
const actual = manager.read(parsed.searchParams);
const external = parsed.searchParams.get('external');
const defaultUrl = manager.urlFor({{
  view: 'calls',
  search: '',
  model: '',
  effort: '',
  confidence: '',
  datePreset: 'all',
  dateStart: '',
  dateEnd: '',
  historyScope: 'active',
  sort: 'time',
  direction: 'desc',
  preset: '',
  page: 1,
  record: '',
  thread: '',
  expand: '',
  expandedThreads: [],
}});
const defaultParsed = new URL(defaultUrl);
console.log(JSON.stringify({{ actual, external, hash: parsed.hash, defaultSearch: defaultParsed.search }}));
"""
    result = subprocess.run(
        [node, "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["external"] == "keep"
    assert payload["hash"] == "#details"
    assert payload["defaultSearch"] == "?external=keep"
    assert payload["actual"] == {
        "view": "threads",
        "search": "Thread Alpha",
        "model": "gpt-5.5",
        "effort": "high",
        "confidence": "estimated",
        "datePreset": "last-7-days",
        "dateStart": "2026-06-01",
        "dateEnd": "2026-06-07",
        "historyScope": "all",
        "sort": "usage",
        "direction": "desc",
        "preset": "context-bloat",
        "page": 3,
        "record": "record-123",
        "thread": "Thread Alpha",
        "expand": "thread-123",
        "expandedThreads": ["Thread Alpha", "Subagent Child"],
    }
