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
