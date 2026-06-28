from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_summary


@dataclass
class _Report:
    value: dict[str, object]

    def payload(self) -> dict[str, object]:
        return dict(self.value)


def test_summary_payload_normalizes_query_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"schema": "codex-usage-tracker-summary-v1"})

    monkeypatch.setattr(server_summary, "build_summary_report", build_report)

    payload = server_summary.summary_payload(
        "group_by=model&limit=9&preset=by-subagent-role&since=2026-06-01",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="strict",
    )

    assert payload["schema"] == "codex-usage-tracker-summary-v1"
    assert payload["raw_context_included"] is False
    assert calls["group_by"] == "model"
    assert calls["limit"] == 9
    assert calls["preset"] == "by-subagent-role"
    assert calls["since"] == "2026-06-01"
    assert calls["privacy_mode"] == "strict"


def test_summary_payload_uses_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({})

    monkeypatch.setattr(server_summary, "build_summary_report", build_report)

    payload = server_summary.summary_payload(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
    )

    assert payload == {"raw_context_included": False}
    assert calls["group_by"] == "thread"
    assert calls["limit"] == 20
    assert calls["preset"] is None
