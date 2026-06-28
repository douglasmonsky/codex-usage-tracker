from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_diagnostic_facts


@dataclass
class _Report:
    payload: dict[str, object]


def test_diagnostics_summary_payload_normalizes_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"ok": True})

    monkeypatch.setattr(server_diagnostic_facts, "build_diagnostics_summary_report", build_report)

    payload = server_diagnostic_facts.diagnostics_summary_payload(
        "limit=7&min_tokens=42&include_archived=true&sort=tokens&direction=asc",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
    )

    assert payload == {"ok": True}
    assert calls["limit"] == 7
    assert calls["min_tokens"] == 42
    assert calls["include_archived"] is True
    assert calls["sort"] == "tokens"
    assert calls["direction"] == "asc"


def test_diagnostics_facts_payload_applies_route_fact_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"facts": []})

    monkeypatch.setattr(server_diagnostic_facts, "build_diagnostics_facts_report", build_report)

    payload = server_diagnostic_facts.diagnostics_facts_payload(
        "fact_type=ignored&fact_name=name",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=True,
        request_path="/api/diagnostics/tools",
        fact_type="tool_call",
        fact_group="tools",
    )

    assert payload == {"facts": []}
    assert calls["fact_type"] == "tool_call"
    assert calls["fact_name"] == "name"
    assert calls["fact_group"] == "tools"
    assert calls["view"] == "tools"
    assert calls["include_archived"] is True


def test_diagnostic_fact_calls_payload_requires_fact_identity(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="fact_type and fact_name are required"):
        server_diagnostic_facts.diagnostic_fact_calls_payload(
            "fact_type=tool_call",
            db_path=tmp_path / "usage.sqlite3",
            include_archived_default=False,
            privacy_mode="normal",
        )


def test_diagnostic_fact_calls_payload_forwards_paging_and_privacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"calls": []})

    monkeypatch.setattr(
        server_diagnostic_facts,
        "build_diagnostics_fact_calls_report",
        build_report,
    )

    payload = server_diagnostic_facts.diagnostic_fact_calls_payload(
        "fact_type=tool_call&fact_name=exec_command&limit=11&offset=3",
        db_path=tmp_path / "usage.sqlite3",
        include_archived_default=False,
        privacy_mode="strict",
    )

    assert payload == {"calls": []}
    assert calls["fact_type"] == "tool_call"
    assert calls["fact_name"] == "exec_command"
    assert calls["limit"] == 11
    assert calls["offset"] == 3
    assert calls["sort"] == "tokens"
    assert calls["privacy_mode"] == "strict"
