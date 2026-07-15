from __future__ import annotations

from pathlib import Path

import pytest

from codex_usage_tracker.cli import mcp_dashboard


def test_usage_dedupe_diagnostics_uses_shared_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    calls: dict[str, object] = {}

    def build(**kwargs: object) -> dict[str, object]:
        calls.update(kwargs)
        return {"schema": "codex-usage-tracker-dedupe-diagnostics-v1"}

    monkeypatch.setattr(mcp_dashboard, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(mcp_dashboard, "build_dedupe_diagnostics", build)

    payload = mcp_dashboard.usage_dedupe_diagnostics(limit=25)

    assert payload["schema"] == "codex-usage-tracker-dedupe-diagnostics-v1"
    assert calls == {"db_path": db_path, "limit": 25}
