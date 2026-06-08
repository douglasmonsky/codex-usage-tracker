from __future__ import annotations

import json
from pathlib import Path

from codex_usage_tracker.adapters.claude_code_jsonl import (
    CLAUDE_CODE_DIAGNOSTIC_KEYS,
    ClaudeCodeJsonlAdapter,
    compact_claude_diagnostics,
)


def test_claude_adapter_parses_aggregate_usage_without_text(tmp_path: Path) -> None:
    claude_home = _make_claude_home(tmp_path)
    adapter = ClaudeCodeJsonlAdapter()
    logs = adapter.discover_logs(claude_home)

    stats: dict[str, int] = {}
    events = adapter.parse_file(logs[0], stats=stats)

    assert len(events) == 2
    first = events[0]
    assert first.source_provider == "anthropic"
    assert first.source_app == "claude-code"
    assert first.source_format == "claude-code-jsonl-v1"
    assert first.provider_request_id == "msg-001"
    assert first.session_id == "claude-session-1"
    assert first.model == "claude-sonnet-4-20250514"
    assert first.cwd == "/tmp/claude-project"
    assert first.input_tokens == 170
    assert first.cached_input_tokens == 50
    assert first.cache_creation_input_tokens == 20
    assert first.uncached_input_tokens == 120
    assert first.output_tokens == 30
    assert first.total_tokens == 200
    assert first.cumulative_total_tokens == 200
    assert events[1].cumulative_total_tokens == 310
    assert "SECRET CLAUDE TEXT" not in json.dumps([event.to_row() for event in events])
    assert compact_claude_diagnostics(stats) == {}
    assert CLAUDE_CODE_DIAGNOSTIC_KEYS[-1] == "skipped_events"


def test_claude_adapter_reports_diagnostics_and_continues(tmp_path: Path) -> None:
    log_path = tmp_path / ".claude" / "projects" / "project-a" / "session.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        "\n".join(
            [
                "{not json}",
                json.dumps({"type": "assistant", "message": {"usage": None}}),
                json.dumps(_assistant_entry("msg-good", input_tokens=10, output_tokens=5)),
                json.dumps(_assistant_entry("msg-bad", input_tokens="bad", output_tokens=5)),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    adapter = ClaudeCodeJsonlAdapter()
    stats: dict[str, int] = {}

    events = adapter.parse_file(log_path, stats=stats)

    assert len(events) == 1
    assert events[0].provider_request_id == "msg-good"
    assert stats["invalid_json"] == 1
    assert stats["missing_usage"] == 1
    assert stats["invalid_integer"] == 1
    assert stats["skipped_events"] == 2


def test_claude_log_discovery_uses_projects_tree(tmp_path: Path) -> None:
    claude_home = _make_claude_home(tmp_path)
    adapter = ClaudeCodeJsonlAdapter()

    logs = adapter.discover_logs(claude_home)

    assert [path.name for path in logs] == ["session.jsonl"]


def _make_claude_home(tmp_path: Path) -> Path:
    claude_home = tmp_path / ".claude"
    log_path = claude_home / "projects" / "project-a" / "session.jsonl"
    log_path.parent.mkdir(parents=True)
    rows = [
        {
            "type": "user",
            "message": {"role": "user", "content": "SECRET CLAUDE TEXT"},
        },
        _assistant_entry(
            "msg-001",
            input_tokens=100,
            cache_creation_input_tokens=20,
            cache_read_input_tokens=50,
            output_tokens=30,
        ),
        _assistant_entry(
            "msg-002",
            input_tokens=40,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=10,
            output_tokens=60,
        ),
    ]
    log_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return claude_home


def _assistant_entry(
    message_id: str,
    *,
    input_tokens: object,
    output_tokens: object,
    cache_creation_input_tokens: object = 0,
    cache_read_input_tokens: object = 0,
) -> dict[str, object]:
    return {
        "type": "assistant",
        "timestamp": "2026-06-08T12:00:00.000Z",
        "sessionId": "claude-session-1",
        "cwd": "/tmp/claude-project",
        "message": {
            "id": message_id,
            "role": "assistant",
            "model": "claude-sonnet-4-20250514",
            "content": [{"type": "text", "text": "SECRET CLAUDE TEXT"}],
            "usage": {
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "output_tokens": output_tokens,
            },
        },
    }
