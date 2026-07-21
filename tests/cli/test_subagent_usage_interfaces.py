from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from codex_usage_tracker.cli import commands_reports, mcp_subagents
from codex_usage_tracker.cli.parser import build_parser
from codex_usage_tracker.core.paths import DEFAULT_DB_PATH, DEFAULT_PRICING_PATH


@dataclass(frozen=True)
class FakeReport:
    def payload(self) -> dict[str, object]:
        return {
            "schema_id": "codex-usage-tracker.subagent-usage.v1",
            "summary": {"observed_spawns": 2},
        }

    def render(self) -> str:
        return "2 observed subagent spawns"


def test_mcp_json_returns_shared_report_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_subagents, "build_subagent_usage_report", lambda **kwargs: FakeReport())

    assert mcp_subagents.subagent_usage(response_format="json") == FakeReport().payload()


def test_cli_parser_defaults_match_mcp_contract() -> None:
    args = build_parser().parse_args(["subagents", "--json"])

    assert args.command == "subagents"
    assert args.limit == 10
    assert args.include_archived is False
    assert args.as_json is True


def test_cli_forwards_all_filters_and_prints_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def build_report(**kwargs: object) -> FakeReport:
        captured.update(kwargs)
        return FakeReport()

    monkeypatch.setattr(commands_reports, "build_subagent_usage_report", build_report)
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    args = build_parser().parse_args(
        [
            "--db",
            str(db_path),
            "--pricing",
            str(pricing_path),
            "--privacy-mode",
            "strict",
            "subagents",
            "--since",
            "2026-07-01T00:00:00Z",
            "--parent-thread",
            "parent-a",
            "--agent-role",
            "test_runner",
            "--subagent-type",
            "thread_spawn",
            "--include-archived",
            "--limit",
            "7",
            "--json",
        ]
    )

    assert commands_reports._run_subagents(args) == 0
    assert captured == {
        "db_path": db_path,
        "pricing_path": pricing_path,
        "since": "2026-07-01T00:00:00Z",
        "parent_thread": "parent-a",
        "agent_role": "test_runner",
        "subagent_type": "thread_spawn",
        "include_archived": True,
        "limit": 7,
        "privacy_mode": "strict",
    }
    assert json.loads(capsys.readouterr().out) == FakeReport().payload()


def test_mcp_forwards_all_filters_and_renders_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def build_report(**kwargs: object) -> FakeReport:
        captured.update(kwargs)
        return FakeReport()

    monkeypatch.setattr(mcp_subagents, "build_subagent_usage_report", build_report)

    result = mcp_subagents.subagent_usage(
        since="2026-07-01T00:00:00Z",
        parent_thread="parent-a",
        agent_role="test_runner",
        subagent_type="thread_spawn",
        include_archived=True,
        limit=7,
        response_format="markdown",
        privacy_mode="strict",
    )

    assert result == "2 observed subagent spawns"
    assert captured == {
        "db_path": DEFAULT_DB_PATH,
        "pricing_path": DEFAULT_PRICING_PATH,
        "since": "2026-07-01T00:00:00Z",
        "parent_thread": "parent-a",
        "agent_role": "test_runner",
        "subagent_type": "thread_spawn",
        "include_archived": True,
        "limit": 7,
        "privacy_mode": "strict",
    }


def test_mcp_rejects_invalid_response_format_before_building(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_builder(**kwargs: object) -> FakeReport:
        raise AssertionError(f"builder should not be called: {kwargs}")

    monkeypatch.setattr(mcp_subagents, "build_subagent_usage_report", unexpected_builder)

    with pytest.raises(ValueError, match="response_format must be markdown or json"):
        mcp_subagents.subagent_usage(response_format="yaml")


def test_cli_and_mcp_json_outputs_are_identical(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def build_report(**kwargs: object) -> FakeReport:
        return FakeReport()

    monkeypatch.setattr(commands_reports, "build_subagent_usage_report", build_report)
    monkeypatch.setattr(mcp_subagents, "build_subagent_usage_report", build_report)
    args = build_parser().parse_args(["subagents", "--json"])

    assert commands_reports._run_subagents(args) == 0
    cli_payload = json.loads(capsys.readouterr().out)
    mcp_payload = mcp_subagents.subagent_usage(response_format="json")

    assert cli_payload == mcp_payload == FakeReport().payload()
