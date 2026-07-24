"""Secondary import checks for the product-layer rules enforced by Tach."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).parents[2] / "src" / "codex_usage_tracker"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id in {"__import__", "import_module"}
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
        ):
            imported.add(node.args[0].value)
    return imported


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


@pytest.mark.parametrize(
    ("domain", "forbidden"),
    [
        (
            "store",
            (
                "codex_usage_tracker.application",
                "codex_usage_tracker.interfaces",
                "codex_usage_tracker.mcp_server",
                "codex_usage_tracker.cli.mcp",
            ),
        ),
        (
            "analytics",
            (
                "codex_usage_tracker.cli",
                "codex_usage_tracker.interfaces",
                "codex_usage_tracker.mcp_server",
                "codex_usage_tracker.server",
            ),
        ),
        (
            "application",
            (
                "codex_usage_tracker.cli",
                "codex_usage_tracker.interfaces",
                "codex_usage_tracker.mcp_server",
                "codex_usage_tracker.server",
            ),
        ),
        (
            "interfaces/mcp",
            (
                "codex_usage_tracker.cli",
                "codex_usage_tracker.interfaces.http",
            ),
        ),
        (
            "interfaces/http",
            (
                "codex_usage_tracker.interfaces.mcp",
                "codex_usage_tracker.mcp_server",
            ),
        ),
    ],
)
def test_forbidden_dependency_directions(
    domain: str,
    forbidden: tuple[str, ...],
) -> None:
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} -> {module}"
        for path in sorted((PACKAGE_ROOT / domain).rglob("*.py"))
        for module in sorted(_imports(path))
        if any(_matches(module, prefix) for prefix in forbidden)
    ]
    assert not violations, "\n".join(violations)


def test_core_imports_only_core_modules() -> None:
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} -> {module}"
        for path in sorted((PACKAGE_ROOT / "core").rglob("*.py"))
        for module in sorted(_imports(path))
        if _matches(module, "codex_usage_tracker")
        and not _matches(module, "codex_usage_tracker.core")
    ]
    assert not violations, "\n".join(violations)


def test_stable_domains_do_not_import_compatibility_package() -> None:
    stable_domains = (
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
    )
    violations = [
        f"{path.relative_to(PACKAGE_ROOT)} -> {module}"
        for domain in stable_domains
        for path in sorted((PACKAGE_ROOT / domain).rglob("*.py"))
        for module in sorted(_imports(path))
        if _matches(module, "codex_usage_tracker.compatibility")
    ]
    assert not violations, "\n".join(violations)
