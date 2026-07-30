from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_PACKAGE = _ROOT / "src" / "codex_usage_tracker" / "agent_kernel"
_FORBIDDEN_IMPORT = "codex_usage_tracker.kernel"
_FORBIDDEN_DATABASE_NAMES = {
    "usage.sqlite3",
    "codex-usage-tracker.sqlite3",
}


def test_agent_kernel_has_no_old_kernel_or_experiment_imports() -> None:
    for path in sorted(_PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            imported: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported = (node.module or "",)
            assert all(
                name != _FORBIDDEN_IMPORT
                and not name.startswith(f"{_FORBIDDEN_IMPORT}.")
                and not name.startswith("experiments.physical")
                for name in imported
            ), f"forbidden import in {path}"


def test_agent_kernel_never_names_an_old_database() -> None:
    for path in sorted(_PACKAGE.rglob("*")):
        if path.suffix not in {".py", ".sql"}:
            continue
        source = path.read_text(encoding="utf-8")
        assert all(name not in source for name in _FORBIDDEN_DATABASE_NAMES)
