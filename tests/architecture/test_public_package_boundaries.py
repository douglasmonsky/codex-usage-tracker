"""Configuration and compatibility checks for public Python package boundaries."""

from __future__ import annotations

import importlib
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib

import codex_usage_tracker
from codex_usage_tracker.allowance_intelligence.materialization import (
    materialize_allowance_intelligence as domain_materialize_allowance,
)
from codex_usage_tracker.application.query_models import QueryFilters as ApplicationQueryFilters
from codex_usage_tracker.core.requests import QueryFilters as CoreQueryFilters
from codex_usage_tracker.core.version import __version__ as core_version
from codex_usage_tracker.store.allowance_materialization import (
    materialize_allowance_intelligence as compatibility_materialize_allowance,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
PACKAGE_ROOT = REPOSITORY_ROOT / "src" / "codex_usage_tracker"
REQUIRED_DOMAINS = (
    "core",
    "ingest",
    "store",
    "analytics",
    "evidence",
    "jobs",
    "application",
    "interfaces",
    "dashboard",
    "plugin",
    "compatibility",
)
ROOT_COMPATIBILITY_ALIASES = {
    "codex_usage_tracker.allowance": "codex_usage_tracker.pricing.allowance",
    "codex_usage_tracker.mcp_server": "codex_usage_tracker.cli.mcp_server",
    "codex_usage_tracker.plugin_installer": "codex_usage_tracker.cli.plugin_installer",
    "codex_usage_tracker.support": "codex_usage_tracker.reports.support",
}
ROOT_COMPATIBILITY_DEPENDENCIES = {
    "codex_usage_tracker.allowance": "codex_usage_tracker.pricing",
    "codex_usage_tracker.mcp_server": "codex_usage_tracker.cli",
    "codex_usage_tracker.plugin_installer": "codex_usage_tracker.cli",
    "codex_usage_tracker.support": "codex_usage_tracker.reports",
}


def _tach_config() -> dict[str, object]:
    with (REPOSITORY_ROOT / "tach.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_strict_tach_policy_is_enabled() -> None:
    config = _tach_config()
    assert config["root_module"] == "forbid"
    assert config["forbid_circular_dependencies"] is True
    assert config["layers_explicit_depends_on"] is True


def test_required_product_domains_have_local_tach_contracts() -> None:
    missing = [
        domain
        for domain in REQUIRED_DOMAINS
        if not (PACKAGE_ROOT / domain / "tach.domain.toml").is_file()
    ]
    assert not missing


def test_every_source_module_has_a_tach_owner() -> None:
    configured_root_modules = {
        module["path"]
        for module in _tach_config()["modules"]  # type: ignore[index]
    }
    unowned: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if any(
            (parent / "tach.domain.toml").is_file()
            for parent in (path.parent, *path.parents)
            if parent == PACKAGE_ROOT or PACKAGE_ROOT in parent.parents
        ):
            continue
        relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
        module = "codex_usage_tracker." + ".".join(relative.parts)
        if relative.name == "__init__":
            module = module.removesuffix(".__init__")
        if module not in configured_root_modules:
            unowned.append(str(relative))
    assert not unowned


def test_moved_contracts_preserve_public_import_identity() -> None:
    assert ApplicationQueryFilters is CoreQueryFilters
    assert compatibility_materialize_allowance is domain_materialize_allowance


def test_public_and_core_version_contracts_match() -> None:
    assert codex_usage_tracker.__version__ == core_version


def test_legacy_cli_helper_paths_alias_interface_modules() -> None:
    for name in (
        "help_i18n",
        "parser_data",
        "parser_diagnostics",
        "parser_lifecycle",
        "parser_reports",
    ):
        legacy = importlib.import_module(f"codex_usage_tracker.cli.{name}")
        interface = importlib.import_module(f"codex_usage_tracker.interfaces.cli.{name}")
        assert legacy is interface


def test_root_compatibility_aliases_have_explicit_tach_edges() -> None:
    configured = {
        module["path"]: module["depends_on"]
        for module in _tach_config()["modules"]  # type: ignore[index]
    }
    for alias, target in ROOT_COMPATIBILITY_ALIASES.items():
        assert importlib.import_module(alias) is importlib.import_module(target)
        assert configured[alias] == [ROOT_COMPATIBILITY_DEPENDENCIES[alias]]
    assert configured["codex_usage_tracker.store.api"] == [
        "codex_usage_tracker.allowance_intelligence",
        "codex_usage_tracker.core",
        "codex_usage_tracker.store",
    ]
