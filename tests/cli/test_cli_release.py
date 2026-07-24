from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol, cast

from codex_usage_tracker import __version__
from codex_usage_tracker.cli.main import _COMMAND_HANDLERS
from codex_usage_tracker.core.json_contracts import known_json_schemas
from codex_usage_tracker.interfaces.cli.namespaces import STABLE_TOP_LEVEL_COMMANDS
from codex_usage_tracker.interfaces.mcp.registry import tool_specs
from tests.release_catalog import (
    ALL_MCP_TOOL_NAMES,
    FORBIDDEN_CONSTELLATION_PATHS,
    FORBIDDEN_DASHBOARD_DEPENDENCIES,
    MAX_INITIAL_DASHBOARD_JS_KIB,
    STABLE_CLI_COMMANDS,
)


class _ReleaseCheckModule(Protocol):
    REPO_ROOT: Path
    CLI_HELP_SUBCOMMANDS: Iterable[str]
    REQUIRED_FILES: Iterable[str]
    SDIST_REQUIRED_MEMBERS: Iterable[str]
    WHEEL_REQUIRED_MEMBERS: Iterable[str]

    def _check_dashboard_asset_sync(self) -> list[str]: ...

    def _check_package_naming_docs(self) -> list[str]: ...

    def _check_public_release_doc_versions(self, version: str) -> list[str]: ...

    def _check_react_dashboard_privacy_artifacts(self) -> list[str]: ...

    def _check_ci_workflow(self) -> list[str]: ...

    def _check_tracked_files_for_secrets(self) -> list[str]: ...


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
        cwd=Path(__file__).resolve().parents[2],
        env=_subprocess_env(),
    )

    assert "Release readiness checks passed." in result.stdout


def test_dashboard_release_excludes_three_and_constellation_artifacts() -> None:
    root = Path(__file__).resolve().parents[2]
    dashboard_package = json.loads(
        (root / "frontend" / "dashboard" / "package.json").read_text(encoding="utf-8")
    )
    declared = set(dashboard_package["dependencies"]) | set(dashboard_package["devDependencies"])
    assert declared.isdisjoint(FORBIDDEN_DASHBOARD_DEPENDENCIES)

    lock_packages = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    assert not any(
        package.removeprefix("node_modules/") in FORBIDDEN_DASHBOARD_DEPENDENCIES
        for package in lock_packages
    )
    assert not any((root / path).exists() for path in FORBIDDEN_CONSTELLATION_PATHS)

    assets = root / "src" / "codex_usage_tracker" / "plugin_data" / "dashboard" / "react" / "assets"
    assert not any("UsageConstellation" in path.name for path in assets.iterdir())


def test_dashboard_main_bundle_budget_is_ratcheted_after_constellation_removal() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "check-dashboard-bundles.mjs"
    ).read_text(encoding="utf-8")
    match = re.search(r"currentInitialJs:\s*(\d+)\s*\*\s*1024", script)
    assert match is not None
    assert int(match.group(1)) <= MAX_INITIAL_DASHBOARD_JS_KIB


def test_release_check_accepts_setup_node_v7(tmp_path: Path) -> None:
    module = _load_release_check_module()
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci.yml").write_text(
        """name: CI

jobs:
  package:
    name: Build package
    steps:
      - uses: actions/setup-node@v7.0.0
        with:
          node-version: "22"
      - run: npm ci
      - run: npm run dashboard:assets:check
      - run: python -m build
      - run: python -m twine check dist/*
      - run: python scripts/check_release.py --dist
      - run: python scripts/smoke_installed_package.py
""",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "dashboard:assets:check": (
                        "npm run dashboard:build && python3 "
                        "scripts/check_release.py --dashboard-assets"
                    )
                }
            }
        ),
        encoding="utf-8",
    )
    module.REPO_ROOT = tmp_path

    assert module._check_ci_workflow() == []


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

    assert len(failures) == 1
    assert failures[0].startswith("docs/development.md public release version 0.4.0")
    assert all("does not match pyproject.toml 0.4.1" in failure for failure in failures)


def test_release_check_requires_current_release_docs_and_packaged_launcher() -> None:
    module = _load_release_check_module()
    wheel_launcher = "codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py"
    sdist_launcher = f"src/{wheel_launcher}"

    assert {
        "docs/releases/0.22.0.md",
        "docs/upgrading-to-0.22.0.md",
        "docs/releases/0.23.0.md",
        "docs/upgrading-to-0.23.0.md",
        "docs/evidence-console-route-migration.md",
    } <= set(module.REQUIRED_FILES)
    assert wheel_launcher in module.WHEEL_REQUIRED_MEMBERS
    assert sdist_launcher in module.SDIST_REQUIRED_MEMBERS


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


def test_release_check_rejects_raw_context_in_react_dashboard_artifacts(tmp_path: Path) -> None:
    module = _load_release_check_module()
    safe_file = tmp_path / "frontend" / "dashboard" / "src" / "safeFixture.ts"
    leak_file = (
        tmp_path
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "react"
        / "assets"
        / "dashboard-react.js"
    )
    safe_file.parent.mkdir(parents=True)
    leak_file.parent.mkdir(parents=True)
    safe_file.write_text(
        "export const fixture = { raw_context_included: false, note: 'aggregate-only synthetic fixture' };\n",
        encoding="utf-8",
    )
    leak_file.write_text(
        'window.__BOOT__ = {"raw_context_persisted": true, "source": "/tmp/.codex/sessions/private.jsonl"};\n',
        encoding="utf-8",
    )
    original_root = module.REPO_ROOT
    module.REPO_ROOT = tmp_path
    try:
        failures = module._check_react_dashboard_privacy_artifacts()
    finally:
        module.REPO_ROOT = original_root

    assert any("raw context persisted" in failure for failure in failures)
    assert any("local Codex session JSONL path" in failure for failure in failures)
    assert not any("safeFixture.ts" in failure for failure in failures)


def test_release_secret_scan_ignores_tracked_files_deleted_in_worktree(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_release_check_module()
    monkeypatch.setattr(module, "_tracked_files", lambda: [tmp_path / "deleted-bundle.js"])

    assert module._check_tracked_files_for_secrets() == []


def test_readme_codex_usage_tracker_commands_reference_known_subcommands() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    readme = repo_root / "README.md"
    documented, unresolved = _documented_cli_commands(readme)

    assert not unresolved
    assert {
        "setup",
        "analyze",
        "query",
        "open",
        "export",
        "config",
        "service",
        "admin",
    } <= documented


def test_cli_reference_documents_only_existing_stable_commands() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cli_reference = repo_root / "docs" / "cli-reference.md"
    documented, unresolved = _documented_cli_commands(cli_reference)

    assert not unresolved
    assert documented >= STABLE_CLI_COMMANDS
    assert set(STABLE_TOP_LEVEL_COMMANDS) == STABLE_CLI_COMMANDS


def test_stable_cli_commands_are_not_removed_without_a_deprecation_plan() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    cli_reference = repo_root / "docs" / "cli-reference.md"
    documented, unresolved = _documented_cli_commands(cli_reference)
    current_commands = set(_COMMAND_HANDLERS) | {"config", "service", "admin"}

    assert not unresolved
    missing = sorted(STABLE_CLI_COMMANDS - current_commands)
    assert not missing, f"removed stable CLI commands need a documented deprecation plan: {missing}"
    assert documented >= STABLE_CLI_COMMANDS


def test_cli_deprecations_use_the_program_compatibility_ledger() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    deprecations = (repo_root / "docs" / "deprecations.md").read_text(encoding="utf-8")

    assert "CLI command or alias" in deprecations
    assert "No CLI compatibility surface may be removed before its removal release" in deprecations


def test_installed_package_smoke_checks_help_for_stable_commands() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "smoke_installed_package.py"
    spec = importlib.util.spec_from_file_location("smoke_installed_package", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load smoke_installed_package.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module.CLI_HELP_SUBCOMMANDS) == STABLE_CLI_COMMANDS


def test_release_pipeline_rebuilds_dashboard_assets_and_smokes_installed_wheel() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    package = json.loads((repo_root / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["dashboard:assets:check"] == (
        "npm run dashboard:build && python3 scripts/check_release.py --dashboard-assets"
    )

    workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    package_job = workflow.split("\n  package:\n", maxsplit=1)[1]
    required_in_order = [
        ("actions/setup-node@v6.4.0", "actions/setup-node@v7.0.0"),
        ('node-version: "22"',),
        ("run: npm ci",),
        ("run: npm run dashboard:assets:check",),
        ("run: python -m build",),
        ("run: python scripts/check_release.py --dist",),
        ("run: python scripts/smoke_installed_package.py",),
    ]
    positions = [
        next(
            (package_job.find(item) for item in alternatives if item in package_job),
            -1,
        )
        for alternatives in required_in_order
    ]
    assert -1 not in positions
    assert positions == sorted(positions)

    smoke = (repo_root / "scripts/smoke_installed_package.py").read_text(encoding="utf-8")
    served = (repo_root / "scripts/smoke_dashboard_server.py").read_text(encoding="utf-8")
    assert "smoke_served_dashboard(" in smoke
    assert "REACT_ASSET_PATTERN" in smoke
    assert 'dashboard_path = temp_dir / "dashboard.html"' in smoke
    for path in (
        "/react-dashboard.html",
        "/react/assets/dashboard-react.js",
        "/react/assets/index.css",
    ):
        assert path in served


def test_dashboard_asset_sync_rejects_untracked_generated_chunk(tmp_path: Path) -> None:
    module = _load_release_check_module()
    module.REPO_ROOT = tmp_path
    asset_dir = tmp_path / "src/codex_usage_tracker/plugin_data/dashboard/react/assets"
    asset_dir.mkdir(parents=True)
    (asset_dir / "dashboard-react.js").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "--", "."], cwd=tmp_path, check=True)
    omitted_chunk = asset_dir / "omitted-new-chunk.js"
    omitted_chunk.write_text("untracked", encoding="utf-8")

    failures = module._check_dashboard_asset_sync()

    assert failures == [
        "dashboard React assets include untracked generated files: "
        "src/codex_usage_tracker/plugin_data/dashboard/react/assets/omitted-new-chunk.js"
    ]


def test_mcp_tool_names_remain_documented() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    docs = (repo_root / "docs" / "mcp.md").read_text(encoding="utf-8")

    actual_tools = {tool.name for tool in tool_specs()}
    documented_tools = _documented_mcp_tools(docs)

    assert actual_tools == ALL_MCP_TOOL_NAMES
    assert documented_tools == ALL_MCP_TOOL_NAMES


def test_mcp_dashboard_evidence_targets_are_documented_as_additive() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    docs = (repo_root / "docs" / "mcp.md").read_text(encoding="utf-8")

    assert "additive `dashboard_target`" in docs
    assert "Thread annotation never" in docs
    assert "substitutes a display name" in docs
    assert "findings do not encode an ordinal Investigator route" in docs
    assert "history=all" in docs
    assert "does not upgrade conversational readiness" in docs
    assert "codex-usage-tracker serve-dashboard --open" in docs


def test_usage_skills_are_packaged_byte_for_byte_with_evidence_target_guidance() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for name in ("codex-usage-tracker", "codex-usage-api"):
        source = repo_root / "skills" / name / "SKILL.md"
        packaged = (
            repo_root / "src" / "codex_usage_tracker" / "plugin_data" / "skills" / name / "SKILL.md"
        )
        assert packaged.read_bytes() == source.read_bytes()
        text = source.read_text(encoding="utf-8")
        assert "absolute_url" in text
        assert "relative_url" in text
        assert "fallback_instruction" in text
        assert "Never infer task-level MCP availability" in text


def test_local_config_schema_docs_reference_stable_fields() -> None:
    repo_root = Path(__file__).resolve().parents[2]
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
    repo_root = Path(__file__).resolve().parents[2]
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
    repo_root = Path(__file__).resolve().parents[2]
    template = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_template.html"
    ).read_text(encoding="utf-8")
    live_runtime = (
        repo_root
        / "src"
        / "codex_usage_tracker"
        / "plugin_data"
        / "dashboard"
        / "dashboard_live.js"
    ).read_text(encoding="utf-8")

    assert "Active sessions only" in template
    assert "All history" in template
    assert "history.active_only" in live_runtime
    assert "history.all_includes" in live_runtime

    from codex_usage_tracker.core.i18n import translations_for

    en_trans = translations_for("en")
    assert en_trans["history.active_only"] == "Active sessions only"
    assert "All history" in en_trans["history.all_includes"]


def test_usage_skills_prefer_live_dashboard_for_open_requests() -> None:
    repo_root = Path(__file__).resolve().parents[2]
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
    from codex_usage_tracker.cli.parser import build_parser

    parser = build_parser()

    assert parser.parse_args(["open-dashboard"]).refresh is True
    assert parser.parse_args(["open-dashboard", "--refresh"]).refresh is True
    assert parser.parse_args(["open-dashboard", "--no-refresh"]).refresh is False
    assert parser.parse_args(["serve-dashboard"]).refresh is True
    assert parser.parse_args(["serve-dashboard", "--refresh"]).refresh is True
    assert parser.parse_args(["serve-dashboard", "--no-refresh"]).refresh is False


def test_public_schema_docs_list_tracked_contracts() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    docs = "\n".join(
        [
            (repo_root / "docs" / "cli-json-schemas.md").read_text(encoding="utf-8"),
            (repo_root / "docs" / "contracts.md").read_text(encoding="utf-8"),
        ]
    )

    missing = [schema for schema in known_json_schemas() if schema not in docs]

    assert not missing


def _subprocess_env() -> dict[str, str]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[2]
    src_path = str(repo_root / "src")
    env["PYTHONPATH"] = (
        f"{src_path}{os.pathsep}{env['PYTHONPATH']}" if env.get("PYTHONPATH") else src_path
    )
    return env


def _load_release_check_module() -> _ReleaseCheckModule:
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_release.py"
    spec = importlib.util.spec_from_file_location("check_release", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load check_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast(_ReleaseCheckModule, module)


def _documented_cli_commands(path: Path) -> tuple[set[str], list[str]]:
    commands = set(_COMMAND_HANDLERS) | set(STABLE_TOP_LEVEL_COMMANDS)
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
