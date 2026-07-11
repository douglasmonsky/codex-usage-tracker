from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.context.api import load_call_context
from codex_usage_tracker.store.api import query_session_usage, refresh_usage_index
from tests.store_dashboard_helpers import SESSION_ID, _make_codex_home


def test_context_loading_uses_one_source_scan_for_evidence_and_serialized_estimate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = _make_codex_home(tmp_path)
    db_path = tmp_path / "usage.sqlite3"
    refresh_usage_index(codex_home=codex_home, db_path=db_path)
    row = query_session_usage(db_path=db_path, session_id=SESSION_ID)[0]
    source_file = Path(str(row["source_file"]))
    open_count = 0
    real_open = Path.open

    def counting_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ):
        nonlocal open_count
        if path == source_file:
            open_count += 1
        return real_open(path, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, "open", counting_open)

    context = load_call_context(row["record_id"], db_path=db_path, diagnostics=True)

    assert open_count == 1
    assert any(entry["label"] == "message / user" for entry in context["entries"])
    assert context["include_tool_output"] is False
    assert context["context_mode"] == "quick"
    assert context["serialized_evidence"]["available"] is True
    assert context["serialized_evidence"]["deferred_buckets"] is True
    assert "call_anchors" not in context
    assert "thread_anchors" not in context
    assert context["diagnostics"]["source_scan_ms"] >= 0
    assert context["diagnostics"]["serialized_estimate_ms"] >= 0
