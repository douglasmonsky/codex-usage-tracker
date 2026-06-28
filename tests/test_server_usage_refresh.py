from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_usage_refresh


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


def test_refresh_usage_payload_returns_aggregate_refresh_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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


def _usage_kwargs(tmp_path: Path) -> dict[str, object]:
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
        "refresh_allowed": False,
    }


def test_usage_payload_forwards_query_options_to_dashboard_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    with pytest.raises(server_usage_refresh.UsageRefreshAuthError, match="Valid API token"):
        server_usage_refresh.usage_payload(
            "refresh=1",
            **_usage_kwargs(tmp_path),
        )


def test_usage_payload_adds_refresh_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    assert payload["diagnostics"]["rows_returned"] == 2
    assert payload["diagnostics"]["refresh_ms"] == 12.5
    assert payload["diagnostics"]["limit"] == 25
    assert payload["diagnostics"]["offset"] == 3
