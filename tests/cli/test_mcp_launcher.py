from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


class _ExecIntercept(Exception):
    pass


def test_source_and_packaged_launchers_are_identical_and_default_to_core() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source_launcher = repo_root / "skills/codex-usage-tracker/scripts/run_mcp.py"
    packaged_launcher = (
        repo_root
        / "src/codex_usage_tracker/plugin_data/skills/codex-usage-tracker/scripts/run_mcp.py"
    )
    server = json.loads((repo_root / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"][
        "codex-usage-tracker"
    ]

    assert source_launcher.read_bytes() == packaged_launcher.read_bytes()
    assert server["env"] == {"CODEX_USAGE_TRACKER_MCP_PROFILE": "core"}


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


def test_launcher_defaults_installed_runtime_to_core_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CODEX_USAGE_TRACKER_MCP_PROFILE", raising=False)
    captured = _run_launcher(launcher=_load_launcher(), tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert captured["profile"] == "core"


@pytest.mark.parametrize("profile", ["full", "developer"])
def test_launcher_accepts_explicit_profiles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    launcher = _load_launcher()
    monkeypatch.setenv("CODEX_USAGE_TRACKER_MCP_PROFILE", profile)

    captured = _run_launcher(launcher=launcher, tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert captured["profile"] == profile


def test_invalid_profile_fails_before_runtime_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = _load_launcher()
    monkeypatch.setenv("CODEX_USAGE_TRACKER_MCP_PROFILE", "unreviewed")
    python_path = tmp_path / "plugin" / ".venv" / launcher._python_bin()
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    exec_calls: list[Path] = []
    monkeypatch.setattr(launcher, "_local_candidate_pythons", lambda _root: [python_path])
    monkeypatch.setattr(launcher, "_can_import_server", lambda _path: True)
    monkeypatch.setattr(launcher, "_can_use_runtime", lambda _path: False)
    monkeypatch.setattr(launcher, "_ensure_runtime", lambda _path: None)
    monkeypatch.setattr(launcher, "_exec_server", lambda path, *_args: exec_calls.append(path))

    result = launcher.main()

    assert result != 0
    assert exec_calls == []


@pytest.mark.parametrize("profile", ["core", "full", "developer"])
def test_profile_selection_does_not_invalidate_matching_runtime_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    launcher = _load_launcher()
    python_path = tmp_path / "runtime" / launcher._python_bin()
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    launcher._package_spec_marker(python_path).write_text(
        launcher.PACKAGE_SPEC + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("CODEX_USAGE_TRACKER_MCP_PROFILE", profile)
    monkeypatch.setattr(launcher, "_can_import_server", lambda _path: True)

    assert launcher._can_use_runtime(python_path) is True


def test_local_venv_candidate_path_is_unchanged(tmp_path: Path, monkeypatch) -> None:
    launcher = _load_launcher()
    plugin_root = tmp_path / "plugin"
    monkeypatch.delenv("CODEX_USAGE_TRACKER_MCP_PYTHON", raising=False)

    assert launcher._local_candidate_pythons(plugin_root) == [
        plugin_root / ".venv" / launcher._python_bin()
    ]


def test_windows_runtime_and_local_venv_paths_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = _load_launcher()
    runtime_root = tmp_path / "runtime"
    monkeypatch.setattr(launcher, "os", SimpleNamespace(name="nt", environ=os.environ))
    monkeypatch.setenv("CODEX_USAGE_TRACKER_RUNTIME_DIR", str(runtime_root))

    assert launcher._python_bin() == Path("Scripts/python.exe")
    assert launcher.MODULE_ARGS == ["-m", "codex_usage_tracker.interfaces.mcp.server"]
    assert launcher._runtime_python() == runtime_root / "Scripts" / "python.exe"
    assert launcher._local_candidate_pythons(tmp_path / "plugin")[-1] == (
        tmp_path / "plugin" / ".venv" / "Scripts" / "python.exe"
    )


def _run_launcher(
    *, launcher: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    python_path = tmp_path / "plugin" / ".venv" / launcher._python_bin()
    python_path.parent.mkdir(parents=True)
    python_path.write_text("", encoding="utf-8")
    captured: dict[str, object] = {}
    monkeypatch.setattr(launcher, "_local_candidate_pythons", lambda _root: [python_path])
    monkeypatch.setattr(launcher, "_can_import_server", lambda _path: True)

    def capture(path: Path, env: dict[str, str]) -> None:
        captured["path"] = path
        captured["profile"] = env.get("CODEX_USAGE_TRACKER_MCP_PROFILE")
        raise _ExecIntercept

    monkeypatch.setattr(
        launcher.os,
        "execv",
        lambda path, _argv: capture(Path(path), os.environ),
    )
    monkeypatch.setattr(
        launcher.os,
        "execve",
        lambda path, _argv, env: capture(Path(path), env),
    )
    with pytest.raises(_ExecIntercept):
        launcher.main()
    return captured


def _load_launcher() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[2]
    launcher_path = repo_root / "skills" / "codex-usage-tracker" / "scripts" / "run_mcp.py"
    spec = importlib.util.spec_from_file_location("codex_usage_tracker_run_mcp", launcher_path)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load MCP launcher")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
