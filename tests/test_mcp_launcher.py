from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType


def test_runtime_cache_requires_matching_package_spec(tmp_path: Path, monkeypatch) -> None:
    launcher = _load_launcher()
    python_path = tmp_path / "runtime" / "bin" / "python"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(launcher, "PACKAGE_SPEC", "package@new")
    monkeypatch.setattr(launcher, "_can_import_server", lambda path: True)

    assert launcher._can_use_runtime(python_path) is False

    launcher._package_spec_marker(python_path).write_text("package@old\n", encoding="utf-8")
    assert launcher._can_use_runtime(python_path) is False

    launcher._package_spec_marker(python_path).write_text("package@new\n", encoding="utf-8")
    assert launcher._can_use_runtime(python_path) is True


def test_ensure_runtime_writes_package_spec_marker(tmp_path: Path, monkeypatch) -> None:
    launcher = _load_launcher()
    python_path = tmp_path / "runtime" / "bin" / "python"
    calls: list[list[str]] = []
    monkeypatch.setattr(launcher, "PACKAGE_SPEC", "package@abc123")

    def fake_run(command, **kwargs):  # noqa: ANN001 - mirrors subprocess.run's flexible API.
        calls.append([str(part) for part in command])
        if command[1:3] == ["-m", "venv"]:
            python_path.parent.mkdir(parents=True)
            python_path.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    launcher._ensure_runtime(python_path)

    assert any(call[1:3] == ["-m", "venv"] for call in calls)
    assert any(call[-4:] == ["pip", "install", "--upgrade", "package@abc123"] for call in calls)
    assert launcher._package_spec_marker(python_path).read_text(encoding="utf-8") == (
        "package@abc123\n"
    )


def _load_launcher() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[1]
    launcher_path = repo_root / "skills" / "codex-usage-tracker" / "scripts" / "run_mcp.py"
    spec = importlib.util.spec_from_file_location("codex_usage_tracker_run_mcp", launcher_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load MCP launcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
