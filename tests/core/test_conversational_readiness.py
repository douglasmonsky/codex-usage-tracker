from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

from codex_usage_tracker import __version__
from codex_usage_tracker.core.conversational_readiness import conversational_readiness

PLUGIN_NAME = "codex-usage-tracker"


def _plugin_root(codex_home: Path) -> Path:
    return codex_home.parent / "plugins" / PLUGIN_NAME


def _write_wrapper(codex_home: Path, server: dict[str, object]) -> Path:
    root = _plugin_root(codex_home)
    (root / ".codex-plugin").mkdir(parents=True)
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": PLUGIN_NAME}), encoding="utf-8"
    )
    (root / ".mcp.json").write_text(
        json.dumps({"mcpServers": {PLUGIN_NAME: server}}), encoding="utf-8"
    )
    return root


def _write_runtime_python(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_fresh_bootstrap_install_requires_restart(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    root = _write_wrapper(
        codex_home,
        {
            "command": "python3",
            "args": ["skills/codex-usage-tracker/scripts/run_mcp.py"],
        },
    )
    launcher = root / "skills" / "codex-usage-tracker" / "scripts" / "run_mcp.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# launcher\n", encoding="utf-8")

    result = conversational_readiness(codex_home=codex_home)

    assert result["state"] == "restart-required"
    assert "restart" in (result["next_action"] or "").lower()


def test_bootstrap_runtime_with_matching_marker_and_import_is_ready(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    runtime = tmp_path / ".cache" / "codex-usage-tracker" / "mcp-runtime" / __version__
    root = _write_wrapper(
        codex_home,
        {
            "command": "python3",
            "args": ["skills/codex-usage-tracker/scripts/run_mcp.py"],
        },
    )
    launcher = root / "skills" / "codex-usage-tracker" / "scripts" / "run_mcp.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# launcher\n", encoding="utf-8")
    runtime_python = runtime / "bin" / "python"
    _write_runtime_python(runtime_python)
    (runtime / ".codex-usage-tracker-package-spec").write_text(
        f"codex-usage-tracking=={__version__}\n", encoding="utf-8"
    )

    result = conversational_readiness(codex_home=codex_home)

    assert result["state"] == "ready", result["evidence"]
    assert "current task" in result["summary"].lower()


def test_bootstrap_runtime_wrong_marker_or_failed_import_requires_restart(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    runtime = tmp_path / "runtime"
    root = _write_wrapper(
        codex_home,
        {
            "command": "python3",
            "args": ["skills/codex-usage-tracker/scripts/run_mcp.py"],
            "env": {"CODEX_USAGE_TRACKER_RUNTIME_DIR": str(runtime)},
        },
    )
    launcher = root / "skills" / "codex-usage-tracker" / "scripts" / "run_mcp.py"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("# launcher\n", encoding="utf-8")
    runtime_python = runtime / "bin" / "python"
    _write_runtime_python(runtime_python)
    marker = runtime / ".codex-usage-tracker-package-spec"
    marker.write_text("wrong-package\n", encoding="utf-8")

    wrong_marker = conversational_readiness(codex_home=codex_home)
    marker.write_text(f"codex-usage-tracking=={__version__}\n", encoding="utf-8")
    runtime_python.unlink()
    runtime_python.symlink_to("/bin/false")
    failed_import = conversational_readiness(codex_home=codex_home)

    assert wrong_marker["state"] == "restart-required"
    assert any("marker" in item.lower() for item in wrong_marker["evidence"])
    assert failed_import["state"] == "restart-required"
    assert any("import" in item.lower() for item in failed_import["evidence"])


def test_valid_generated_wrapper_is_ready(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    _write_wrapper(
        codex_home,
        {
            "command": sys.executable,
            "args": ["-m", "codex_usage_tracker.mcp_server"],
        },
    )

    result = conversational_readiness(codex_home=codex_home)

    assert result["state"] == "ready"
    assert result["next_action"] is None
    assert "current task" in result["summary"].lower()


def test_missing_or_malformed_wrapper_is_unavailable(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    missing = conversational_readiness(codex_home=codex_home)
    root = _plugin_root(codex_home)
    root.mkdir(parents=True)
    (root / ".mcp.json").write_text("{broken", encoding="utf-8")
    malformed = conversational_readiness(codex_home=codex_home)

    assert missing["state"] == "unavailable"
    assert malformed["state"] == "unavailable"
    assert "setup" in (missing["next_action"] or "")
    assert "doctor" in (malformed["next_action"] or "")


def test_failed_direct_launcher_import_is_unavailable(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    _write_wrapper(
        codex_home,
        {
            "command": "/bin/false",
            "args": ["-m", "codex_usage_tracker.mcp_server"],
        },
    )

    result = conversational_readiness(codex_home=codex_home)

    assert result["state"] == "unavailable"
    assert any("runtime" in evidence.lower() for evidence in result["evidence"])


def test_uninspectable_state_is_unknown(tmp_path: Path) -> None:
    codex_home = tmp_path / ".codex"
    root = _write_wrapper(codex_home, {"command": "python3", "args": ["custom-server"]})
    assert root.exists()

    result = conversational_readiness(codex_home=codex_home)

    assert result["state"] == "unknown"
    assert "could not" in result["summary"].lower()
