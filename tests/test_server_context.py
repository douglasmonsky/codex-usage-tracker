from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_context


def test_context_payload_normalizes_query_parameters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def load_context(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"record_id": kwargs["record_id"]}

    monkeypatch.setattr(server_context, "load_call_context", load_context)

    payload = server_context.context_payload(
        (
            "record_id=rec-1&max_chars=123&max_entries=4&include_tool_output=true"
            "&include_compaction_history=1&diagnostics=yes&mode=FULL"
        ),
        db_path=tmp_path / "usage.sqlite3",
        default_context_chars=20_000,
    )

    assert payload == {"record_id": "rec-1"}
    assert calls["record_id"] == "rec-1"
    assert calls["max_chars"] == 123
    assert calls["max_entries"] == 4
    assert calls["include_tool_output"] is True
    assert calls["include_compaction_history"] is True
    assert calls["diagnostics"] is True
    assert calls["mode"] == "full"


def test_context_payload_uses_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def load_context(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {}

    monkeypatch.setattr(server_context, "load_call_context", load_context)

    payload = server_context.context_payload(
        "record_id=rec-1",
        db_path=tmp_path / "usage.sqlite3",
        default_context_chars=999,
    )

    assert payload == {}
    assert calls["max_chars"] == 999
    assert calls["max_entries"] == server_context.DEFAULT_CONTEXT_ENTRIES
    assert calls["include_tool_output"] is False
    assert calls["include_compaction_history"] is False
    assert calls["diagnostics"] is False
    assert calls["mode"] == "quick"


def test_context_payload_requires_record_id(tmp_path: Path) -> None:
    with pytest.raises(server_context.ContextRequestError, match="record_id required"):
        server_context.context_payload(
            "",
            db_path=tmp_path / "usage.sqlite3",
            default_context_chars=20_000,
        )


def test_context_payload_rejects_invalid_mode(tmp_path: Path) -> None:
    with pytest.raises(server_context.ContextRequestError, match="mode must be one of"):
        server_context.context_payload(
            "record_id=rec-1&mode=slow",
            db_path=tmp_path / "usage.sqlite3",
            default_context_chars=20_000,
        )
