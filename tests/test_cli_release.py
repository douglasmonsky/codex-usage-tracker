from __future__ import annotations

import ast
import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.cli import _COMMAND_HANDLERS
from codex_usage_tracker.json_contracts import known_json_schemas

STABLE_CLI_COMMANDS = {
    "setup",
    "doctor",
    "install-plugin",
    "upgrade-plugin",
    "uninstall-plugin",
    "refresh",
    "inspect-log",
    "rebuild-index",
    "reset-db",
    "summary",
    "query",
    "recommendations",
    "session",
    "context",
    "dashboard",
    "open-dashboard",
    "serve-dashboard",
    "expensive",
    "pricing-coverage",
    "export",
    "init-pricing",
    "update-pricing",
    "pin-pricing",
    "init-allowance",
    "parse-allowance",
    "update-rate-card",
    "init-thresholds",
    "init-projects",
    "support-bundle",
}


MCP_TOOL_NAMES = {
    "refresh_usage_index",
    "usage_doctor",
    "usage_summary",
    "usage_query",
    "usage_recommendations",
    "session_usage",
    "usage_call_context",
    "most_expensive_usage_calls",
    "usage_pricing_coverage",
    "generate_usage_dashboard",
    "export_usage_csv",
    "init_usage_pricing_config",
    "update_usage_pricing_config",
    "init_usage_allowance_config",
}


def test_module_cli_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "codex_usage_tracker", "--version"],
        check=True,
        capture_output=True,
        text=True,
        env=_subprocess_env(),
    )

    assert f"codex-usage-tracker {__version__}" in result.stdout


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


def test_release_check_rejects_stale_public_package_version_claims(tmp_path: Path) -> None:
    module = _load_release_check_module()
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "one-dot-oh-readiness.md").write_text(
        "Verify public install: codex-usage-tracking==0.4.0\n"
        "Smoke Docker: --from-pypi --version 0.4.0\n"
        "Verify visible as `0.4.0`.\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "development.md").write_text(
        "python scripts/smoke_installed_package.py --from-pypi --version 0.4.0\n",
        encoding="utf-8",
    )

    original_root = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        failures = module._check_public_release_doc_versions("0.4.1")
    finally:
        module.REPO_ROOT = original_root

    assert len(failures) == 4
    assert all("does not match pyproject.toml 0.4.1" in failure for failure in failures)


def test_release_check_rejects_old_pypi_package_install_docs(tmp_path: Path) -> None:
    module = _load_release_check_module()
    readme = tmp_path / "README.md"
    install_doc = tmp_path / "docs" / "install.md"
    development_doc = tmp_path / "docs" / "development.md"
    install_doc.parent.mkdir()
    readme.write_text(
        "Package naming: the PyPI distribution is `codex-usage-tracking`. "
        "The `codex-usage-tracker` PyPI name is not this project.\n"
        "pipx install codex-usage-tracker\n",
        encoding="utf-8",
    )
    install_doc.write_text(
        "Package naming: the public PyPI distribution is `codex-usage-tracking`. "
        "The `codex-usage-tracker` PyPI name is not this project.\n"
        "python -m pip install codex-usage-tracker\n",
        encoding="utf-8",
    )
    development_doc.write_text("Distribution: codex-usage-tracking\n", encoding="utf-8")

    original_root = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        failures = module._check_package_naming_docs()
    finally:
        module.REPO_ROOT = original_root

    assert {
        "README.md:2 installs codex-usage-tracker; use codex-usage-tracking",
        "docs/install.md:2 installs codex-usage-tracker; use codex-usage-tracking",
    } <= set(failures)


def test_readme_codex_usage_tracker_commands_reference_known_subcommands() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme = repo_root / "README.md"
    documented, unresolved = _documented_cli_commands(readme)

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


def test_cli_reference_documents_only_existing_stable_commands() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cli_reference = repo_root / "docs" / "cli-reference.md"
    documented, unresolved = _documented_cli_commands(cli_reference)

    assert not unresolved
    assert documented == STABLE_CLI_COMMANDS
    assert set(_COMMAND_HANDLERS) >= STABLE_CLI_COMMANDS


def test_stable_cli_commands_are_not_removed_without_a_deprecation_plan() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cli_reference = repo_root / "docs" / "cli-reference.md"
    documented, unresolved = _documented_cli_commands(cli_reference)
    current_commands = set(_COMMAND_HANDLERS)

    assert not unresolved
    missing = sorted(STABLE_CLI_COMMANDS - current_commands)
    assert not missing, f"removed stable CLI commands need a documented deprecation plan: {missing}"
    assert documented == STABLE_CLI_COMMANDS


def test_installed_package_smoke_checks_help_for_stable_commands() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "smoke_installed_package.py"
    spec = importlib.util.spec_from_file_location("smoke_installed_package", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load smoke_installed_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module.CLI_HELP_SUBCOMMANDS) == STABLE_CLI_COMMANDS


def test_mcp_tool_names_remain_documented() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = (repo_root / "docs" / "mcp.md").read_text(encoding="utf-8")
    source = repo_root / "src" / "codex_usage_tracker" / "mcp_server.py"

    actual_tools = _mcp_tool_names(source)
    documented_tools = _documented_mcp_tools(docs)

    assert actual_tools == MCP_TOOL_NAMES
    assert documented_tools == MCP_TOOL_NAMES


def test_local_config_schema_docs_reference_stable_fields() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = "\n".join(
        [
            (repo_root / "docs" / "cli-reference.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "dashboard-guide.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "pricing-and-credits.md").read_text(encoding="utf-8"),
        ]
    )

    for required in [
        "codex-usage-tracker-pricing-v1",
        "codex-usage-tracker-codex-rate-card-v1",
        "codex-usage-tracker-allowance-v1",
        "pricing.json",
        "rate-card.json",
        "allowance.json",
        "thresholds.json",
        "projects.json",
        "models",
        "credit_rates",
        "windows",
        "aliases",
        "ignored_paths",
        "tags",
        "low_cache_ratio",
    ]:
        assert required in docs


def test_known_limitations_are_documented() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    docs = "\n".join(
        [
            (repo_root / "README.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "install.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "mcp.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "pricing-and-credits.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "privacy.md").read_text(encoding="utf-8"),
        ]
    ).lower()

    for required in [
        "codex upstream log formats can change",
        "parser compatibility may require",
        "pricing and rate-card sources can change outside this project",
        "live account allowance cannot be read automatically",
        "not guaranteed to match exact billing",
        "plugin discovery limitations are separate from core python cli/dashboard support",
    ]:
        assert required in docs


def test_dashboard_history_scope_labels_remain_user_facing() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    template = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_template.html"
    ).read_text(encoding="utf-8")
    script = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard.js"
    ).read_text(encoding="utf-8")

    assert "Active sessions only" in template
    assert "All history" in template
    assert "history.active_only" in script
    assert "history.all_includes" in script

    from codex_usage_tracker.i18n import translations_for
    en_trans = translations_for("en")
    assert en_trans["history.active_only"] == "Active sessions only"
    assert "All history" in en_trans["history.all_includes"]


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


def _load_release_check_module():
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "scripts" / "check_release.py"
    spec = importlib.util.spec_from_file_location("check_release", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load check_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _documented_cli_commands(path: Path) -> tuple[set[str], list[str]]:
    commands = set(_COMMAND_HANDLERS)
    documented: set[str] = set()
    unresolved: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("codex-usage-tracker"):
            continue
        tokens = shlex.split(line)
        command = next((token for token in tokens[1:] if token in commands), None)
        if command:
            documented.add(command)
        elif "--version" not in tokens:
            unresolved.append(line)
    return documented, unresolved


def _mcp_tool_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    tools: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "tool"
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "mcp"
            ):
                tools.add(node.name)
    return tools


def _documented_mcp_tools(docs: str) -> set[str]:
    in_tools = False
    tools: set[str] = set()
    for line in docs.splitlines():
        if line == "## Tools":
            in_tools = True
            continue
        if in_tools and line.startswith("## "):
            break
        if in_tools and line.startswith("- `"):
            tools.add(line.removeprefix("- `").removesuffix("`"))
    return tools
