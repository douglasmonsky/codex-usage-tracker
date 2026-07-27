from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.kernel.interfaces.cli.main import build_parser, main

from ..interfaces.support import active_runtime


def test_cli_exposes_explicit_content_lifecycle() -> None:
    help_text = build_parser().format_help()

    assert "content" in help_text


def test_cli_requires_privacy_confirmation_and_supports_delete(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    runtime = active_runtime(tmp_path)
    monkeypatch.setenv("CODEX_HOME", str(runtime.codex_home))
    monkeypatch.setenv("CODEX_USAGE_TRACKER_CACHE_ROOT", str(runtime.cache_root))

    assert main(["content", "enable"]) == 2
    assert "privacy confirmation" in json.loads(capsys.readouterr().err)["error"]

    assert main(
        [
            "content",
            "enable",
            "--confirm-private-content",
            "--store-redacted-fragments",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "enabled"

    assert main(["content", "index"]) == 0
    assert json.loads(capsys.readouterr().out)["indexed_generation"] == 1

    assert main(["content", "delete"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "disabled"
    assert not runtime.content.exists()
