from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

import pytest

from codex_usage_tracker.server import dedupe as server_dedupe


def test_dedupe_payload_normalizes_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}

    def build(**kwargs: object) -> dict[str, object]:
        calls.update(kwargs)
        return {"schema": "codex-usage-tracker-dedupe-diagnostics-v1"}

    monkeypatch.setattr(server_dedupe, "build_dedupe_diagnostics", build)

    payload = server_dedupe.dedupe_payload("limit=25", db_path=tmp_path / "usage.sqlite3")

    assert payload["schema"] == "codex-usage-tracker-dedupe-diagnostics-v1"
    assert calls["limit"] == 25


def test_handle_dedupe_request_sends_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[HTTPStatus, dict[str, object]]] = []
    monkeypatch.setattr(
        server_dedupe,
        "dedupe_payload",
        lambda query, **kwargs: {"query": query},
    )

    server_dedupe.handle_dedupe_request(
        "limit=10",
        db_path=tmp_path / "usage.sqlite3",
        send_exception=lambda prefix, exc: None,
        send_json=lambda status, payload: sent.append((status, payload)),
    )

    assert sent == [(HTTPStatus.OK, {"query": "limit=10"})]
