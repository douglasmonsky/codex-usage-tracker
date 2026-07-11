from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol, TypedDict

from codex_usage_tracker.server import usage_refresh as server_usage_refresh


class _MonkeyPatch(Protocol):
    def setattr(self, target: object, name: str, value: object) -> None: ...


@dataclass
class _RefreshResult:
    scanned_files: int = 2
    parsed_events: int = 3
    skipped_events: int = 4
    inserted_or_updated_events: int = 5
    db_path: Path = Path("usage.sqlite3")
    parser_diagnostics: dict[str, int] | None = None


class _FakeLock:
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    def __enter__(self) -> _FakeLock:
        self.entered += 1
        return self

    def __exit__(self, *_exc: object) -> None:
        self.exited += 1


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


def test_refresh_usage_payload_returns_aggregate_refresh_metadata(
    tmp_path: Path,
    monkeypatch: _MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def refresh_usage_index(**kwargs: Any) -> _RefreshResult:
        calls.update(kwargs)
        return _RefreshResult(
            db_path=kwargs["db_path"],
            parser_diagnostics={"duplicate_records": 1},
        )

    monkeypatch.setattr(server_usage_refresh, "refresh_usage_index", refresh_usage_index)
    lock = _FakeLock()
    db_path = tmp_path / "usage.sqlite3"

    payload, refresh_ms = server_usage_refresh.refresh_usage_payload(
        codex_home=tmp_path / "codex-home",
        db_path=db_path,
        include_archived=True,
        refresh_lock=lock,
    )

    assert calls == {
        "codex_home": tmp_path / "codex-home",
        "db_path": db_path,
        "include_archived": True,
    }
    assert lock.entered == 1
    assert lock.exited == 1
    assert payload == {
        "scanned_files": 2,
        "parsed_events": 3,
        "skipped_events": 4,
        "inserted_or_updated_events": 5,
        "db_path": db_path,
        "parser_diagnostics": {"duplicate_records": 1},
        "include_archived": True,
    }
    assert isinstance(refresh_ms, float)


class _UsageBaseKwargs(TypedDict):
    db_path: Path
    pricing_path: Path
    allowance_path: Path
    rate_card_path: Path
    thresholds_path: Path
    projects_path: Path
    privacy_mode: str
    since: str | None
    api_token: str
    context_api_enabled: bool
    include_archived_default: bool
    language_default: str
    limit_default: int
    codex_home: Path
    refresh_lock: _FakeLock


class _UsageKwargs(_UsageBaseKwargs):
    refresh_allowed: bool


class _HandleUsageKwargs(_UsageBaseKwargs):
    has_valid_api_token: server_usage_refresh.TokenValidator
    send_error: server_usage_refresh.ErrorSender
    send_exception: server_usage_refresh.ExceptionSender
    send_json: server_usage_refresh.JsonSender


def _usage_base_kwargs(tmp_path: Path) -> _UsageBaseKwargs:
    return {
        "db_path": tmp_path / "usage.sqlite3",
        "pricing_path": tmp_path / "pricing.json",
        "allowance_path": tmp_path / "allowance.json",
        "rate_card_path": tmp_path / "rate-card.json",
        "thresholds_path": tmp_path / "thresholds.json",
        "projects_path": tmp_path / "projects.json",
        "privacy_mode": "normal",
        "since": None,
        "api_token": "token",
        "context_api_enabled": True,
        "include_archived_default": True,
        "language_default": "en",
        "limit_default": 500,
        "codex_home": tmp_path / "codex-home",
        "refresh_lock": _FakeLock(),
    }


def _usage_kwargs(tmp_path: Path) -> _UsageKwargs:
    return {**_usage_base_kwargs(tmp_path), "refresh_allowed": False}


def _handle_usage_kwargs(
    tmp_path: Path,
    senders: _RouteSenders,
    *,
    has_valid_api_token: server_usage_refresh.TokenValidator = lambda _params: True,
) -> _HandleUsageKwargs:
    return {
        **_usage_base_kwargs(tmp_path),
        "has_valid_api_token": has_valid_api_token,
        "send_error": senders.send_error,
        "send_exception": senders.send_exception,
        "send_json": senders.send_json,
    }


def test_handle_usage_request_sends_payload(
    tmp_path: Path,
    monkeypatch: _MonkeyPatch,
) -> None:
    senders = _RouteSenders()
    seen: dict[str, Any] = {}

    def usage_payload(query: str, **kwargs: Any) -> dict[str, object]:
        seen["query"] = query
        seen["refresh_allowed"] = kwargs["refresh_allowed"]
        return {"query": query}

    monkeypatch.setattr(server_usage_refresh, "usage_payload", usage_payload)

    server_usage_refresh.handle_usage_request(
        "refresh=1&api_token=ok",
        **_handle_usage_kwargs(
            tmp_path,
            senders,
            has_valid_api_token=lambda params: params.get("api_token") == ["ok"],
        ),
    )

    assert seen == {"query": "refresh=1&api_token=ok", "refresh_allowed": True}
    assert senders.errors == []
    assert senders.json_payloads == [
        (HTTPStatus.OK, {"query": "refresh=1&api_token=ok"}),
    ]


def test_handle_usage_request_sends_refresh_auth_error(tmp_path: Path) -> None:
    senders = _RouteSenders()

    server_usage_refresh.handle_usage_request(
        "refresh=1",
        **_handle_usage_kwargs(
            tmp_path,
            senders,
            has_valid_api_token=lambda _params: False,
        ),
    )

    assert senders.errors == [
        (HTTPStatus.FORBIDDEN, "Valid API token is required for refresh"),
    ]
    assert senders.json_payloads == []


def test_usage_payload_forwards_request_window_without_refreshing(
    tmp_path: Path,
    monkeypatch: _MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    def dashboard_payload(**kwargs: Any) -> dict[str, object]:
        seen.update(kwargs)
        return {"rows": [], "load_window": kwargs["load_window"]}

    monkeypatch.setattr(server_usage_refresh, "dashboard_payload", dashboard_payload)

    payload = server_usage_refresh.usage_payload(
        "limit=0&since=2026-07-04T10%3A15%3A00.000Z&load_window=week",
        **_usage_kwargs(tmp_path),
    )

    assert seen["limit"] is None
    assert seen["since"] == "2026-07-04T10:15:00.000Z"
    assert seen["load_window"] == "week"
    assert payload["load_window"] == "week"


def test_usage_payload_rejects_unknown_load_window(tmp_path: Path) -> None:
    try:
        server_usage_refresh.usage_payload(
            "load_window=forever",
            **_usage_kwargs(tmp_path),
        )
    except ValueError as exc:
        assert str(exc) == "load_window must be one of: day, week, rows, all"
    else:
        raise AssertionError("unknown load window should fail")


def test_handle_usage_request_sends_os_error(
    tmp_path: Path,
    monkeypatch: _MonkeyPatch,
) -> None:
    senders = _RouteSenders()

    def usage_payload(*_args: Any, **_kwargs: Any) -> dict[str, object]:
        raise OSError("cannot read")

    monkeypatch.setattr(server_usage_refresh, "usage_payload", usage_payload)

    server_usage_refresh.handle_usage_request(
        "",
        **_handle_usage_kwargs(tmp_path, senders),
    )

    assert senders.json_payloads == []
    assert senders.exceptions[0][0] == "Could not read aggregate dashboard data"
    assert str(senders.exceptions[0][1]) == "cannot read"


def test_usage_payload_forwards_query_options_to_dashboard_payload(
    tmp_path: Path,
    monkeypatch: _MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def dashboard_payload(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"rows": [{"record_id": "r1"}]}

    monkeypatch.setattr(server_usage_refresh, "dashboard_payload", dashboard_payload)
    monkeypatch.setattr(server_usage_refresh, "utc_now", lambda: "now")

    payload = server_usage_refresh.usage_payload(
        "limit=all&offset=4&include_archived=false&shell=1",
        **_usage_kwargs(tmp_path),
    )

    assert payload["refreshed_at"] == "now"
    assert payload["refresh_result"] is None
    assert calls["limit"] is None
    assert calls["offset"] == 4
    assert calls["include_archived"] is False
    assert calls["include_rows"] is False
    assert calls["context_api_enabled"] is True


def test_usage_payload_rejects_refresh_without_valid_token(tmp_path: Path) -> None:
    try:
        server_usage_refresh.usage_payload(
            "refresh=1",
            **_usage_kwargs(tmp_path),
        )
    except server_usage_refresh.UsageRefreshAuthError as exc:
        assert "Valid API token" in str(exc)
    else:
        raise AssertionError("Expected refresh authentication to fail")


def test_usage_payload_adds_refresh_diagnostics(
    tmp_path: Path,
    monkeypatch: _MonkeyPatch,
) -> None:
    def dashboard_payload(**_kwargs: Any) -> dict[str, object]:
        return {"rows": [{"record_id": "r1"}, {"record_id": "r2"}]}

    def refresh_usage_payload(**_kwargs: Any) -> tuple[dict[str, object], float]:
        return {"parsed_events": 7}, 12.5

    monkeypatch.setattr(server_usage_refresh, "dashboard_payload", dashboard_payload)
    monkeypatch.setattr(server_usage_refresh, "refresh_usage_payload", refresh_usage_payload)
    monkeypatch.setattr(server_usage_refresh, "utc_now", lambda: "now")
    kwargs = _usage_kwargs(tmp_path)
    kwargs["refresh_allowed"] = True

    payload = server_usage_refresh.usage_payload(
        "refresh=1&diagnostics=1&limit=25&offset=3",
        **kwargs,
    )

    assert payload["refresh_result"] == {"parsed_events": 7}
    diagnostics = payload["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["rows_returned"] == 2
    assert diagnostics["refresh_ms"] == 12.5
    assert diagnostics["limit"] == 25
    assert diagnostics["offset"] == 3
