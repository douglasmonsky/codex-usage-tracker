from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from codex_usage_tracker.kernel.interfaces.cli.main import build_parser, main

from .support import active_runtime


def test_cli_help_contains_only_retained_public_commands() -> None:
    help_text = build_parser().format_help()

    for command in (
        "setup",
        "status",
        "refresh",
        "query",
        "export",
        "open",
        "service",
        "config",
        "repair",
        "package",
    ):
        assert command in help_text
    for removed in ("analyze", "dashboard", "open-dashboard", "admin"):
        assert removed not in help_text


def test_status_is_read_only_and_setup_is_explicit(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    cache = tmp_path / "cache"
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("CODEX_USAGE_TRACKER_CACHE_ROOT", str(cache))

    assert main(["status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["state"] == "absent"
    assert not cache.exists()

    assert main(["setup"]) == 0
    setup = json.loads(capsys.readouterr().out)
    assert setup["state"] == "absent"
    assert (cache / "codex-usage-kernel-v1.sqlite3").is_file()
    assert (cache / "codex-usage-kernel-operational-v1.sqlite3").is_file()


def test_installed_style_module_help_and_query(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runtime = active_runtime(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(runtime.codex_home))
    monkeypatch.setenv("CODEX_USAGE_TRACKER_CACHE_ROOT", str(runtime.cache_root))
    request = json.dumps(
        {
            "requests": [
                {
                    "dataset": "calls",
                    "operation": "aggregate",
                    "dimensions": ["model"],
                    "measures": ["total_tokens"],
                }
            ]
        }
    )

    assert main(["query", "--request", request]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["results"][0]["generation"] == 1

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(__file__).parents[3] / "src")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "codex_usage_tracker.kernel.interfaces.cli.main",
            "--help",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert "usage_status" not in completed.stdout
    assert "service" in completed.stdout


def test_open_returns_an_encoded_stable_evidence_destination(
    capsys,
) -> None:
    assert main(
        [
            "open",
            "--no-browser",
            "--selector",
            "thread:synthetic/value",
        ]
    ) == 0

    result = json.loads(capsys.readouterr().out)

    assert result["url"] == (
        "http://127.0.0.1:8765/"
        "evidence/thread%3Asynthetic%2Fvalue?view=summary"
    )


def test_open_defaults_to_the_focused_live_console(capsys) -> None:
    assert main(["open", "--no-browser"]) == 0

    assert json.loads(capsys.readouterr().out)["url"] == (
        "http://127.0.0.1:8765/live"
    )


def test_corrupt_cache_returns_sanitized_cli_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    cache = tmp_path / "cache"
    operational = cache / "codex-usage-kernel-operational-v1.sqlite3"
    operational.parent.mkdir(parents=True)
    operational.write_bytes(b"not sqlite")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))
    monkeypatch.setenv("CODEX_USAGE_TRACKER_CACHE_ROOT", str(cache))

    assert main(["status"]) == 2

    assert json.loads(capsys.readouterr().err) == {
        "error": "kernel cache is unavailable"
    }
