from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker import server_call_detail


def test_call_detail_payload_includes_annotated_adjacent_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        "previous": {"record_id": "previous"},
        "current": {
            "record_id": "current",
            "previous_record_id": "previous",
            "next_record_id": "next",
        },
        "next": {"record_id": "next"},
    }
    calls: list[str] = []

    def query_record(**kwargs: Any) -> dict[str, object] | None:
        calls.append(kwargs["record_id"])
        return rows.get(kwargs["record_id"])

    def annotate_rows(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
        return [candidate | {"annotated": True} for candidate in candidates]

    monkeypatch.setattr(server_call_detail, "query_usage_record", query_record)

    payload = server_call_detail.call_detail_payload(
        "record=current",
        db_path=tmp_path / "usage.sqlite3",
        annotate_rows=annotate_rows,
    )

    assert calls == ["current", "previous", "next"]
    assert payload["schema"] == "codex-usage-tracker-call-v1"
    assert payload["record"] == rows["current"] | {"annotated": True}
    assert payload["previous_record"] == rows["previous"] | {"annotated": True}
    assert payload["next_record"] == rows["next"] | {"annotated": True}
    assert payload["adjacent_records"] == [
        rows["previous"] | {"annotated": True},
        rows["current"] | {"annotated": True},
        rows["next"] | {"annotated": True},
    ]
    assert payload["previous_record_id"] == "previous"
    assert payload["next_record_id"] == "next"
    assert payload["raw_context_included"] is False


def test_call_detail_payload_requires_record_id(tmp_path: Path) -> None:
    with pytest.raises(server_call_detail.MissingRecordIdError, match="record_id required"):
        server_call_detail.call_detail_payload(
            "",
            db_path=tmp_path / "usage.sqlite3",
            annotate_rows=lambda rows: rows,
        )


def test_call_detail_payload_raises_when_record_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_call_detail, "query_usage_record", lambda **kwargs: None)

    with pytest.raises(server_call_detail.UsageRecordNotFoundError, match="missing"):
        server_call_detail.call_detail_payload(
            "record_id=missing",
            db_path=tmp_path / "usage.sqlite3",
            annotate_rows=lambda rows: rows,
        )
