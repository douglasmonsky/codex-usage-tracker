from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codex_usage_tracker.cli.plugin_installer import install_plugin
from codex_usage_tracker.recommendation_engine.materialization import (
    sync_recommendation_facts,
)
from codex_usage_tracker.server import status as server_status
from codex_usage_tracker.store.api import upsert_usage_events
from codex_usage_tracker.store.connection import connect
from tests.store_dashboard_helpers import _usage_event


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
        return {
            "total_rows": 4,
            "active_rows": 3,
            "total_max_event_timestamp": "2026-06-01T00:00:00Z",
            "active_max_event_timestamp": "2026-05-31T00:00:00Z",
            "physical_rows": 4,
            "canonical_rows": 2,
            "excluded_copied_rows": 2,
            "dedupe_enabled": True,
            "fingerprint_version": "usage-fingerprint-v2",
            "duplicate_fingerprint_groups": 1,
            "physical_total_tokens": 400,
            "canonical_total_tokens": 200,
            "excluded_total_tokens": 200,
            "duplicate_reasons": {"copied_usage_fingerprint": 2},
        }

    def query_observed(**kwargs: Any) -> dict[str, object]:
        calls["observed"].append(kwargs)
        return {"weekly_percent": 37 if kwargs["include_archived"] else 31}

    monkeypatch.setattr(server_status, "query_home_status_counts", query_status)
    monkeypatch.setattr(server_status, "conversational_readiness", capture_readiness)
    monkeypatch.setattr(server_status, "query_home_latest_observed_usage", query_observed)
    monkeypatch.setattr(
        server_status,
        "query_home_refresh_metadata",
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

    assert calls["status"] == [{"db_path": tmp_path / "usage.sqlite3"}]
    assert [call["include_archived"] for call in calls["observed"]] == [True, False]
    assert calls["home"]["latest_event_at"] == "2026-05-31T00:00:00Z"
    assert calls["home"]["observed_usage"] == {"weekly_percent": 31}
    assert payload["schema"] == "codex-usage-tracker-status-v1"
    assert payload["latest_refresh_at"] == "2026-06-01T01:00:00Z"
    assert payload["max_event_timestamp"] == "2026-06-01T00:00:00Z"
    assert payload["observed_usage"] == {"weekly_percent": 37}
    assert payload["parser_adapter"] == "jsonl"
    assert payload["parser_diagnostics"] == {"skipped_events": 3}
    assert payload["dedupe"] == {
        "dedupe_enabled": True,
        "fingerprint_version": "usage-fingerprint-v2",
        "physical_rows": 4,
        "canonical_rows": 2,
        "excluded_copied_rows": 2,
        "duplicate_fingerprint_groups": 1,
        "physical_total_tokens": 400,
        "canonical_total_tokens": 200,
        "excluded_total_tokens": 200,
        "duplicate_reasons": {"copied_usage_fingerprint": 2},
    }
    assert payload["conversational_analysis"]["state"] == "ready"
    assert readiness_homes == [codex_home]
    assert str(codex_home) not in str(payload["conversational_analysis"])


def test_status_payload_uses_include_archived_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {"include_archived": []}

    def query_status(**kwargs: Any) -> dict[str, object]:
        calls["include_archived"].append("single")
        return {
            "total_rows": 0,
            "active_rows": 0,
            "total_max_event_timestamp": None,
            "active_max_event_timestamp": None,
            "physical_rows": 0,
            "canonical_rows": 0,
            "excluded_copied_rows": 0,
        }

    monkeypatch.setattr(server_status, "query_home_status_counts", query_status)
    monkeypatch.setattr(
        server_status,
        "query_home_latest_observed_usage",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(server_status, "query_home_refresh_metadata", lambda db_path: {})
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

    assert calls["include_archived"] == ["single"]
    assert payload["include_archived"] is True
    assert payload["parser_diagnostics"] == {}


def test_home_summary_payload_omits_persisted_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        server_status,
        "query_home_usage_metrics",
        lambda **_kwargs: {
            "calls": 7,
            "total_tokens": 12_345,
            "pricing_coverage": 1.0,
        },
    )
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
            windows=[
                SimpleNamespace(
                    key="weekly",
                    label="Weekly",
                    total_credits=100,
                    remaining_credits=63,
                    remaining_percent=63,
                    reset_at=None,
                    captured_at=None,
                )
            ],
        ),
    )
    monkeypatch.setattr(
        server_status,
        "query_home_status_counts",
        lambda **_kwargs: {"active_max_event_timestamp": "2026-07-21T09:00:00Z"},
    )

    payload = server_status.home_summary_payload(
        db_path=tmp_path / "usage.sqlite3",
        metadata={"latest_refresh_at": "2026-07-21T10:00:00Z"},
        dedupe={"physical_rows": 8, "canonical_rows": 7, "excluded_copied_rows": 1},
        observed_usage={"available": True, "windows": [{"used_percent": 37}]},
    )

    assert payload["schema"] == "codex-usage-tracker-home-summary-v1"
    assert payload["source_revision"] == "generation:9"
    assert payload["usage_metrics"] == {
        "calls": 7,
        "total_tokens": 12_345,
        "pricing_coverage": 1.0,
    }
    assert payload["latest_event_at"] == "2026-07-21T09:00:00Z"
    assert payload["pricing"] == {
        "configured": True,
        "model_count": 2,
        "estimated_model_count": 1,
        "error": None,
    }
    assert payload["allowance"]["configured"] is True
    assert payload["allowance"]["observed_usage"]["windows"] == [{"used_percent": 37}]
    assert payload["allowance"]["windows"][0]["remaining_percent"] == 63
    assert "findings" not in payload
    assert "recent_evidence" not in payload
    assert "raw" not in str(payload).lower()


def test_status_payload_reads_committed_snapshot_while_writer_is_active(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    event = _usage_event(
        record_id="active",
        session_id="session",
        thread_key="thread:Active",
        event_timestamp="2026-07-21T08:00:00Z",
        cumulative_total_tokens=1_500,
    )
    upsert_usage_events([event], db_path=db_path)
    with connect(db_path) as conn:
        sync_recommendation_facts(conn, record_ids=[event.record_id])

    writer = sqlite3.connect(db_path)
    try:
        writer.execute("BEGIN IMMEDIATE")
        payload = server_status.status_payload(
            "include_archived=false",
            codex_home=tmp_path / ".codex",
            db_path=db_path,
            pricing_path=tmp_path / "pricing.json",
            allowance_path=tmp_path / "allowance.json",
            rate_card_path=tmp_path / "rate-card.json",
            include_archived_default=False,
        )
    finally:
        writer.rollback()
        writer.close()

    assert payload["home_summary"]["usage_metrics"]["calls"] == 1
    assert payload["dedupe"]["canonical_rows"] == 1
