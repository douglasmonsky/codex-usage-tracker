from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codex_usage_tracker.cli.plugin_installer import install_plugin
from codex_usage_tracker.server import status as server_status


class _RouteSenders:
    def __init__(self) -> None:
        self.exceptions: list[tuple[str, BaseException]] = []
        self.json_payloads: list[tuple[HTTPStatus, dict[str, object]]] = []

    def send_exception(self, prefix: str, exc: BaseException) -> None:
        self.exceptions.append((prefix, exc))

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.json_payloads.append((status, payload))


def test_handle_status_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_status,
        "status_payload",
        lambda query, **kwargs: {"query": query, "archived": kwargs["include_archived_default"]},
    )

    server_status.handle_status_request(
        "include_archived=true",
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=False,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.exceptions == []
    assert senders.json_payloads == [
        (HTTPStatus.OK, {"query": "include_archived=true", "archived": False}),
    ]


def test_handle_status_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def status_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(server_status, "status_payload", status_payload)

    server_status.handle_status_request(
        "",
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=True,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading status"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_status_payload_normalizes_include_archived_and_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {"status": [], "observed": []}
    codex_home = tmp_path / ".codex"
    install_plugin(
        plugin_dir=codex_home.parent / "plugins" / "codex-usage-tracker",
        marketplace_path=tmp_path / "marketplace.json",
    )
    real_readiness = server_status.conversational_readiness
    readiness_homes: list[Path] = []

    def capture_readiness(*, codex_home: Path) -> dict[str, object]:
        readiness_homes.append(codex_home)
        return real_readiness(codex_home=codex_home)

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["status"].append(kwargs)
        timestamp = "2026-06-01T00:00:00Z" if kwargs["include_archived"] else "2026-05-31T00:00:00Z"
        return {"total_events": 4, "max_event_timestamp": timestamp}

    def query_observed(**kwargs: Any) -> dict[str, object]:
        calls["observed"].append(kwargs)
        return {"weekly_percent": 37 if kwargs["include_archived"] else 31}

    monkeypatch.setattr(server_status, "query_usage_status", query_status)
    monkeypatch.setattr(server_status, "conversational_readiness", capture_readiness)
    monkeypatch.setattr(server_status, "query_latest_observed_usage", query_observed)
    monkeypatch.setattr(
        server_status,
        "query_dedupe_diagnostics",
        lambda **kwargs: {"summary": {"excluded_copied_rows": 2}},
    )
    monkeypatch.setattr(
        server_status,
        "refresh_metadata",
        lambda db_path: {
            "latest_refresh_at": "2026-06-01T01:00:00Z",
            "parser_adapter": "jsonl",
            "parser_skipped_events": "3",
            "parser_duplicate_events": "0",
        },
    )
    def home_summary(**kwargs: Any) -> dict[str, object]:
        calls["home"] = kwargs
        return {"schema": "codex-usage-tracker-home-summary-v1"}

    monkeypatch.setattr(server_status, "home_summary_payload", home_summary)

    payload = server_status.status_payload(
        "include_archived=true",
        codex_home=codex_home,
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=False,
    )

    assert [call["include_archived"] for call in calls["status"]] == [True, False]
    assert [call["include_archived"] for call in calls["observed"]] == [True, False]
    assert calls["home"]["latest_event_at"] == "2026-05-31T00:00:00Z"
    assert calls["home"]["observed_usage"] == {"weekly_percent": 31}
    assert payload["schema"] == "codex-usage-tracker-status-v1"
    assert payload["latest_refresh_at"] == "2026-06-01T01:00:00Z"
    assert payload["max_event_timestamp"] == "2026-06-01T00:00:00Z"
    assert payload["observed_usage"] == {"weekly_percent": 37}
    assert payload["parser_adapter"] == "jsonl"
    assert payload["parser_diagnostics"] == {"skipped_events": 3}
    assert payload["dedupe"] == {"excluded_copied_rows": 2}
    assert payload["conversational_analysis"]["state"] == "ready"
    assert readiness_homes == [codex_home]
    assert str(codex_home) not in str(payload["conversational_analysis"])


def test_status_payload_uses_include_archived_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {"include_archived": []}

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["include_archived"].append(kwargs["include_archived"])
        return {}

    monkeypatch.setattr(server_status, "query_usage_status", query_status)
    monkeypatch.setattr(server_status, "query_latest_observed_usage", lambda **kwargs: {})
    monkeypatch.setattr(
        server_status,
        "query_dedupe_diagnostics",
        lambda **kwargs: {"summary": {"excluded_copied_rows": 0}},
    )
    monkeypatch.setattr(server_status, "refresh_metadata", lambda db_path: {})
    monkeypatch.setattr(
        server_status,
        "home_summary_payload",
        lambda **kwargs: {"schema": "codex-usage-tracker-home-summary-v1"},
    )

    payload = server_status.status_payload(
        "",
        codex_home=tmp_path / ".codex",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=True,
    )

    assert calls["include_archived"] == [True, False]
    assert payload["include_archived"] is True
    assert payload["parser_diagnostics"] == {}


def test_home_summary_payload_is_active_only_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}
    recommendation_rows = [
        {
            "record_id": f"record-{index}",
            "fact_primary_recommendation_key": "context-bloat",
            "fact_recommendations_json": (
                '[{"key":"context-bloat","severity":"high","title":"High context",'
                '"why":"Context is near the limit.","action":"Start a fresh task."}]'
            ),
        }
        for index in range(5)
    ]
    recent_rows = [
        {
            "record_id": f"recent-{index}",
            "event_timestamp": f"2026-07-21T0{index}:00:00Z",
            "thread_name": f"Thread {index}",
            "model": "gpt-5",
            "total_tokens": 1_000 + index,
        }
        for index in range(8)
    ]

    def query_findings(**kwargs: Any) -> list[dict[str, object]]:
        calls["findings"] = kwargs
        return recommendation_rows

    def query_recent(**kwargs: Any) -> list[dict[str, object]]:
        calls["recent"] = kwargs
        return recent_rows

    monkeypatch.setattr(server_status, "query_home_finding_rows", query_findings)
    monkeypatch.setattr(server_status, "query_home_recent_evidence_rows", query_recent)
    monkeypatch.setattr(server_status, "current_source_revision", lambda _path: "generation:9")
    monkeypatch.setattr(
        server_status,
        "load_pricing_config",
        lambda _path: SimpleNamespace(
            loaded=True,
            error=None,
            models={"gpt-5": {}, "gpt-5-mini": {}},
            estimated_models={"gpt-5-mini"},
        ),
    )
    monkeypatch.setattr(
        server_status,
        "load_allowance_config",
        lambda _path, **kwargs: SimpleNamespace(
            loaded=True,
            error=None,
            windows=[SimpleNamespace(
                key="weekly",
                label="Weekly",
                total_credits=100,
                remaining_credits=63,
                remaining_percent=63,
                reset_at=None,
                captured_at=None,
            )],
        ),
    )

    payload = server_status.home_summary_payload(
        db_path=tmp_path / "usage.sqlite3",
        metadata={"latest_refresh_at": "2026-07-21T10:00:00Z"},
        dedupe={"physical_rows": 8, "canonical_rows": 7, "excluded_copied_rows": 1},
        latest_event_at="2026-07-21T09:00:00Z",
        observed_usage={"available": True, "windows": [{"used_percent": 37}]},
    )

    assert calls["findings"] == {
        "db_path": tmp_path / "usage.sqlite3",
        "min_score": 80,
        "limit": 3,
    }
    assert calls["recent"] == {
        "db_path": tmp_path / "usage.sqlite3",
        "limit": 5,
    }
    assert payload["schema"] == "codex-usage-tracker-home-summary-v1"
    assert payload["source_revision"] == "generation:9"
    assert payload["pricing"] == {
        "configured": True,
        "model_count": 2,
        "estimated_model_count": 1,
        "error": None,
    }
    assert payload["allowance"]["configured"] is True
    assert payload["allowance"]["observed_usage"]["windows"] == [{"used_percent": 37}]
    assert payload["allowance"]["windows"][0]["remaining_percent"] == 63
    assert len(payload["findings"]) == 3
    assert len(payload["recent_evidence"]) == 5
    assert payload["findings"][0]["evidence"] == {
        "kind": "call",
        "record_id": "record-0",
    }
    assert payload["recent_evidence"][0]["record_id"] == "recent-0"
    assert "raw" not in str(payload).lower()
