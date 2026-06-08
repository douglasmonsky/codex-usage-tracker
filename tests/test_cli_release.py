from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker.cli import _COMMAND_HANDLERS
from codex_usage_tracker.json_contracts import known_json_schemas


def test_module_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codex_usage_tracker", "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )

    assert "codex-usage-tracker 0.2.0" in result.stdout


def test_release_check_script_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_release.py"],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
        env=_subprocess_env(),
    )

    assert "Release readiness checks passed." in result.stdout


def test_readme_codex_usage_tracker_commands_reference_known_subcommands() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme = repo_root / "README.md"
    commands = set(_COMMAND_HANDLERS)
    documented: set[str] = set()
    unresolved: list[str] = []

    for raw_line in readme.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("codex-usage-tracker"):
            continue
        tokens = shlex.split(line)
        command = next((token for token in tokens[1:] if token in commands), None)
        if command:
            documented.add(command)
        elif "--version" not in tokens:
            unresolved.append(line)

    assert not unresolved
    assert {
        "setup",
        "serve-dashboard",
        "dashboard",
        "query",
        "summary",
        "session",
        "export",
        "support-bundle",
        "parse-allowance",
    } <= documented


def test_cli_json_schema_doc_lists_tracked_contracts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = (repo_root / "docs" / "cli-json-schemas.md").read_text(encoding="utf-8")

    missing = [schema for schema in known_json_schemas() if schema not in docs]

    assert not missing


def test_docs_mention_claude_source_support() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = "\n".join(
        [
            (repo_root / "README.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "cli-reference.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "privacy.md").read_text(encoding="utf-8"),
        ]
    )

    assert "AI Usage Tracker" in docs
    assert "--source claude-code" in docs
    assert "~/.claude/projects" in docs
    assert "Claude Code" in docs


def test_synthetic_history_benchmark_script_smoke(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_synthetic_history.py",
            "--rows",
            "100",
            "--batch-size",
            "25",
            "--db-dir",
            str(tmp_path),
            "--json",
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=repo_root,
        env=_subprocess_env(),
    )
    payload = json.loads(result.stdout)

    assert payload["benchmarks"][0]["rows"] == 100
    assert payload["benchmarks"][0]["filtered_rows"] <= 50
    assert "idx_usage_model_effort" in payload["benchmarks"][0]["query_plan"]


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[1]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
        if env.get("PYTHONPATH")
        else src_path
    )
    return env
