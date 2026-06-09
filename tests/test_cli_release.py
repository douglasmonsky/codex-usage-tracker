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

    assert "codex-usage-tracker 0.3.2" in result.stdout


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


def test_usage_skills_prefer_live_dashboard_for_open_requests() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    skill_paths = [
        repo_root / "skills" / "codex-usage-api" / "SKILL.md",
        repo_root / "skills" / "codex-usage-tracker" / "SKILL.md",
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "skills"
        / "codex-usage-api"
        / "SKILL.md",
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "skills"
        / "codex-usage-tracker"
        / "SKILL.md",
    ]

    for skill_path in skill_paths:
        skill_text = skill_path.read_text(encoding="utf-8")
        live_command_index = skill_text.find("serve-dashboard --context-api explicit --open")
        static_command_index = skill_text.find("open-dashboard")

        assert live_command_index != -1, skill_path
        assert static_command_index != -1, skill_path
        assert live_command_index < static_command_index, skill_path
        assert "Refresh is the default" in skill_text
        assert "Live requires `serve-dashboard`" in skill_text


def test_dashboard_launch_commands_refresh_by_default() -> None:
    from codex_usage_tracker.cli import _build_parser

    parser = _build_parser()

    assert parser.parse_args(["open-dashboard"]).refresh is True
    assert parser.parse_args(["open-dashboard", "--refresh"]).refresh is True
    assert parser.parse_args(["open-dashboard", "--no-refresh"]).refresh is False
    assert parser.parse_args(["serve-dashboard"]).refresh is True
    assert parser.parse_args(["serve-dashboard", "--refresh"]).refresh is True
    assert parser.parse_args(["serve-dashboard", "--no-refresh"]).refresh is False


def test_cli_json_schema_doc_lists_tracked_contracts() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = (repo_root / "docs" / "cli-json-schemas.md").read_text(encoding="utf-8")

    missing = [schema for schema in known_json_schemas() if schema not in docs]

    assert not missing


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
            "--enforce-thresholds",
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
    assert payload["benchmarks"][0]["threshold_status"] == "pass"
    assert payload["benchmarks"][0]["threshold_failures"] == []
    assert {
        "populate_seconds",
        "active_dashboard_query_seconds",
        "all_history_dashboard_query_seconds",
        "since_until_query_seconds",
        "filtered_query_seconds",
        "filtered_count_seconds",
        "dashboard_payload_active_seconds",
        "thread_summary_seconds",
        "recommendations_report_seconds",
        "pricing_coverage_seconds",
        "project_summary_seconds",
    } <= set(payload["benchmarks"][0]["timings"])


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
