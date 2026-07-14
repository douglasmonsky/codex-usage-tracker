from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.recommendation_engine import query as recommendation_query
from codex_usage_tracker.server import recommendations as server_recommendations
from codex_usage_tracker.server.query_cache import AggregateQueryCache


@dataclass
class _Report:
    payload: dict[str, object]


class _RouteSenders:
    def __init__(self) -> None:
        self.errors: list[tuple[HTTPStatus, str]] = []
        self.exceptions: list[tuple[str, BaseException]] = []
        self.json_payloads: list[tuple[HTTPStatus, dict[str, object]]] = []

    def send_error(self, status: HTTPStatus, message: str) -> None:
        self.errors.append((status, message))

    def send_exception(self, prefix: str, exc: BaseException) -> None:
        self.exceptions.append((prefix, exc))

    def send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        self.json_payloads.append((status, payload))


def test_server_uses_recommendation_query_orchestrator() -> None:
    assert (
        server_recommendations.build_recommendations_report
        is recommendation_query.build_recommendations_report
    )


def test_handle_recommendations_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    monkeypatch.setattr(
        server_recommendations,
        "recommendations_payload",
        lambda query, **_kwargs: {"query": query},
    )

    server_recommendations.handle_recommendations_request(
        "limit=2",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == []
    assert senders.json_payloads == [(HTTPStatus.OK, {"query": "limit=2"})]


def test_handle_recommendations_request_sends_sqlite_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def recommendations_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(
        server_recommendations,
        "recommendations_payload",
        recommendations_payload,
    )

    server_recommendations.handle_recommendations_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Database error while reading recommendations"
    assert str(senders.exceptions[0][1]) == "database is locked"


def test_handle_recommendations_request_requires_refresh_for_stale_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def recommendations_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise recommendation_query.RecommendationFactsUnavailableError("refresh required")

    monkeypatch.setattr(
        server_recommendations,
        "recommendations_payload",
        recommendations_payload,
    )

    server_recommendations.handle_recommendations_request(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
        send_error=senders.send_error,
        send_exception=senders.send_exception,
        send_json=senders.send_json,
    )

    assert senders.errors == [(HTTPStatus.SERVICE_UNAVAILABLE, "refresh required")]
    assert senders.exceptions == []
    assert senders.json_payloads == []


def test_handle_recommendations_request_reuses_generation_keyed_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    calls = 0

    def recommendations_payload(query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"query": query, "rows": []}

    monkeypatch.setattr(
        server_recommendations,
        "recommendations_payload",
        recommendations_payload,
    )

    for query in ("limit=20&model=gpt-5", "model=gpt-5&limit=20"):
        server_recommendations.handle_recommendations_request(
            query,
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=tmp_path / "pricing.json",
            allowance_path=tmp_path / "allowance.json",
            projects_path=tmp_path / "projects.json",
            privacy_mode="normal",
            query_cache=cache,
            send_error=senders.send_error,
            send_exception=senders.send_exception,
            send_json=senders.send_json,
        )

    assert calls == 1
    assert [_cache_metadata(payload)["status"] for _, payload in senders.json_payloads] == [
        "miss",
        "hit",
    ]


def test_handle_recommendations_request_invalidates_all_semantic_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=4, max_payload_bytes=1_024)
    calls = 0
    rate_card_path = tmp_path / "rate-card.json"
    thresholds_path = tmp_path / "thresholds.json"

    def recommendations_payload(_query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"rows": [], "build": calls}

    monkeypatch.setattr(
        server_recommendations,
        "recommendations_payload",
        recommendations_payload,
    )
    request: dict[str, Any] = {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": rate_card_path,
        "thresholds_path": thresholds_path,
        "projects_path": tmp_path / "projects.json",
        "privacy_mode": "normal",
        "query_cache": cache,
        "send_error": senders.send_error,
        "send_exception": senders.send_exception,
        "send_json": senders.send_json,
    }

    server_recommendations.handle_recommendations_request("limit=20", **request)
    server_recommendations.handle_recommendations_request("limit=20", **request)
    thresholds_path.write_text('{"high_cost_usd": 2.0}\n', encoding="utf-8")
    server_recommendations.handle_recommendations_request("limit=20", **request)
    rate_card_path.write_text('{"models": {}}\n', encoding="utf-8")
    server_recommendations.handle_recommendations_request("limit=20", **request)

    assert calls == 3
    assert [_cache_metadata(payload)["status"] for _, payload in senders.json_payloads] == [
        "miss",
        "hit",
        "miss",
        "miss",
    ]


def test_handle_recommendations_request_bypasses_explicit_large_payload_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    cache = AggregateQueryCache(max_entries=2, max_payload_bytes=1_024)
    calls = 0

    def recommendations_payload(_query: str, **_kwargs: Any) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return {"rows": [], "build": calls}

    monkeypatch.setattr(
        server_recommendations,
        "recommendations_payload",
        recommendations_payload,
    )
    request: dict[str, Any] = {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
        "projects_path": tmp_path / "projects.json",
        "privacy_mode": "normal",
        "query_cache": cache,
        "send_error": senders.send_error,
        "send_exception": senders.send_exception,
        "send_json": senders.send_json,
    }

    server_recommendations.handle_recommendations_request("limit=0", **request)
    server_recommendations.handle_recommendations_request("limit=0", **request)

    assert calls == 2
    assert all(
        _cache_metadata(payload)["status"] == "bypass" for _, payload in senders.json_payloads
    )


def _cache_metadata(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload["query_cache"]
    assert isinstance(metadata, dict)
    return metadata


def test_recommendations_payload_normalizes_query_filters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({"schema": "codex-usage-tracker-recommendations-v1"})

    monkeypatch.setattr(server_recommendations, "build_recommendations_report", build_report)
    rate_card_path = tmp_path / "rate-card.json"
    thresholds_path = tmp_path / "thresholds.json"

    payload = server_recommendations.recommendations_payload(
        "limit=7&min_score=0.25&model=gpt-5.5&project=tracker",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=rate_card_path,
        thresholds_path=thresholds_path,
        projects_path=tmp_path / "projects.json",
        privacy_mode="redacted",
    )

    assert payload["schema"] == "codex-usage-tracker-recommendations-v1"
    assert payload["raw_context_included"] is False
    assert calls["limit"] == 7
    assert calls["min_score"] == 0.25
    assert calls["model"] == "gpt-5.5"
    assert calls["project"] == "tracker"
    assert calls["privacy_mode"] == "redacted"
    assert calls["rate_card_path"] == rate_card_path
    assert calls["thresholds_path"] == thresholds_path


def test_recommendations_payload_uses_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def build_report(**kwargs: Any) -> _Report:
        calls.update(kwargs)
        return _Report({})

    monkeypatch.setattr(server_recommendations, "build_recommendations_report", build_report)

    payload = server_recommendations.recommendations_payload(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        projects_path=tmp_path / "projects.json",
        privacy_mode="normal",
    )

    assert payload == {"raw_context_included": False}
    assert calls["limit"] == 20
    assert calls["min_score"] is None


def test_recommendations_payload_rejects_invalid_min_score(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="min_score must be a number"):
        server_recommendations.recommendations_payload(
            "min_score=not-a-number",
            db_path=tmp_path / "usage.sqlite3",
            pricing_path=tmp_path / "pricing.json",
            allowance_path=tmp_path / "allowance.json",
            projects_path=tmp_path / "projects.json",
            privacy_mode="normal",
        )
