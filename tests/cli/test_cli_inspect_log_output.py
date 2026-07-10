from __future__ import annotations

import argparse
import importlib

cli_main = importlib.import_module("codex_usage_tracker.cli.main")


def test_inspect_log_text_output_handles_shape_drift(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_main, "load_session_index", lambda _codex_home: {})
    monkeypatch.setattr(
        cli_main,
        "inspect_log",
        lambda _path, *, session_index: {
            "path": "/tmp/example.jsonl",
            "adapter": "codex-jsonl-v2",
            "file_session_id": None,
            "event_count": 0,
            "session_ids": "unexpected-scalar",
            "models": None,
            "diagnostics": ["unexpected-list"],
        },
    )

    result = cli_main._run_inspect_log(
        argparse.Namespace(path="/tmp/example.jsonl", codex_home=None, as_json=False)
    )

    assert result == 0
    assert capsys.readouterr().out.splitlines() == [
        "Log: /tmp/example.jsonl",
        "Adapter: codex-jsonl-v2",
        "File session id: unknown",
        "Parsed events: 0",
        "Diagnostics: none",
    ]


def test_inspect_log_text_output_normalizes_collection_values(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_main, "load_session_index", lambda _codex_home: {})
    monkeypatch.setattr(
        cli_main,
        "inspect_log",
        lambda _path, *, session_index: {
            "path": "/tmp/example.jsonl",
            "adapter": "codex-jsonl-v2",
            "file_session_id": "session-a",
            "event_count": 2,
            "session_ids": ("session-a", 7),
            "models": ["gpt-5.6", 5],
            "diagnostics": {"partial_field_count": 1},
        },
    )

    result = cli_main._run_inspect_log(
        argparse.Namespace(path="/tmp/example.jsonl", codex_home=None, as_json=False)
    )

    assert result == 0
    assert "Sessions: session-a, 7" in capsys.readouterr().out
