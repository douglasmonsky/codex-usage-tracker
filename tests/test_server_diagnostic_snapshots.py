from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_diagnostic_snapshots


@dataclass
class _Report:
    payload: dict[str, object]


class _FakeLock:
    def __init__(self) -> None:
        self.entered = 0
        self.exited = 0

    def __enter__(self) -> _FakeLock:
        self.entered += 1
        return self

    def __exit__(self, *_exc: object) -> None:
        self.exited += 1


def test_refresh_all_diagnostic_snapshots_payload_uses_refresh_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def refresh_diagnostic_snapshots(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        server_diagnostic_snapshots,
        "refresh_diagnostic_snapshots",
        refresh_diagnostic_snapshots,
    )
    lock = _FakeLock()

    payload = server_diagnostic_snapshots.refresh_all_diagnostic_snapshots_payload(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived=True,
        refresh_lock=lock,
    )

    assert payload == {"ok": True}
    assert lock.entered == 1
    assert lock.exited == 1
    assert calls["include_archived"] is True
    assert calls["db_path"] == tmp_path / "usage.sqlite3"


def test_diagnostic_refresh_payload_uses_include_archived_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def refresh_diagnostic_snapshots(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        server_diagnostic_snapshots,
        "refresh_diagnostic_snapshots",
        refresh_diagnostic_snapshots,
    )
    lock = _FakeLock()

    payload = server_diagnostic_snapshots.diagnostic_refresh_payload(
        "",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=True,
        refresh_lock=lock,
    )

    assert payload == {"ok": True}
    assert calls["include_archived"] is True
    assert lock.entered == 1
    assert lock.exited == 1


def test_diagnostic_refresh_payload_allows_query_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, Any] = {}

    def refresh_diagnostic_snapshots(**kwargs: Any) -> dict[str, object]:
        calls.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        server_diagnostic_snapshots,
        "refresh_diagnostic_snapshots",
        refresh_diagnostic_snapshots,
    )

    server_diagnostic_snapshots.diagnostic_refresh_payload(
        "include_archived=false",
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived_default=True,
        refresh_lock=_FakeLock(),
    )

    assert calls["include_archived"] is False


def test_diagnostic_snapshot_payload_refreshes_under_lock(tmp_path: Path) -> None:
    lock = _FakeLock()
    calls: list[dict[str, Any]] = []

    def build_report(**kwargs: Any) -> _Report:
        calls.append(kwargs)
        return _Report({"refresh": kwargs["refresh"]})

    payload = server_diagnostic_snapshots.diagnostic_snapshot_payload(
        db_path=tmp_path / "usage.sqlite3",
        include_archived=False,
        refresh=True,
        refresh_lock=lock,
        build_report=build_report,
    )

    assert payload == {"refresh": True}
    assert lock.entered == 1
    assert lock.exited == 1
    assert calls == [
        {
            "db_path": tmp_path / "usage.sqlite3",
            "include_archived": False,
            "refresh": True,
        },
    ]


def test_diagnostic_snapshot_payload_read_does_not_lock(tmp_path: Path) -> None:
    lock = _FakeLock()

    def build_report(**kwargs: Any) -> _Report:
        return _Report({"refresh": kwargs["refresh"]})

    payload = server_diagnostic_snapshots.diagnostic_snapshot_payload(
        db_path=tmp_path / "usage.sqlite3",
        include_archived=True,
        refresh=False,
        refresh_lock=lock,
        build_report=build_report,
    )

    assert payload == {"refresh": False}
    assert lock.entered == 0
    assert lock.exited == 0


def test_usage_drain_snapshot_payload_forwards_pricing_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def build_report(**kwargs: Any) -> _Report:
        calls.append(kwargs)
        return _Report({"section": "usage-drain", "refresh": kwargs["refresh"]})

    monkeypatch.setattr(
        server_diagnostic_snapshots,
        "build_diagnostic_usage_drain_report",
        build_report,
    )
    lock = _FakeLock()

    payload = server_diagnostic_snapshots.usage_drain_snapshot_payload(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=tmp_path / "pricing.json",
        allowance_path=tmp_path / "allowance.json",
        rate_card_path=tmp_path / "rate-card.json",
        include_archived=True,
        refresh=True,
        refresh_lock=lock,
    )

    assert payload == {"section": "usage-drain", "refresh": True}
    assert lock.entered == 1
    assert lock.exited == 1
    assert calls == [
        {
            "db_path": tmp_path / "usage.sqlite3",
            "pricing_path": tmp_path / "pricing.json",
            "allowance_path": tmp_path / "allowance.json",
            "rate_card_path": tmp_path / "rate-card.json",
            "include_archived": True,
            "refresh": True,
        },
    ]
