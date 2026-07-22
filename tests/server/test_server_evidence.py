from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from codex_usage_tracker.server.evidence import evidence_payload, handle_evidence_request
from tests.evidence.test_service import seed_evidence


def test_evidence_payload_returns_shared_bounded_envelope(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)

    payload = evidence_payload(
        "selector_kind=call&selector_id=record-1",
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
    )

    assert payload["schema"] == "codex-usage-tracker.mcp-envelope.v1"
    assert payload["result_schema"] == "codex-usage-tracker.evidence-result.v1"
    assert payload["data_class"] == "aggregate"
    assert payload["result"]["selector"] == {  # type: ignore[index]
        "kind": "call",
        "id": "record-1",
        "section": "summary",
    }
    assert "raw_context" not in str(payload).lower()


def test_evidence_payload_honors_explicit_archived_scope(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)

    payload = evidence_payload(
        "selector_kind=call&selector_id=record-2&history=all",
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
    )

    assert payload["result"]["selector"]["id"] == "record-2"  # type: ignore[index]
    assert payload["scope"]["history"] == "all"  # type: ignore[index]


def test_evidence_handler_returns_recoverable_errors_for_bad_or_stale_selectors(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    seed_evidence(db_path)
    responses: list[tuple[HTTPStatus, dict[str, object]]] = []

    for query in (
        "selector_kind=call&selector_id=../unsafe",
        "selector_kind=call&selector_id=record-999",
        "selector_kind=call&selector_id=record-2",
    ):
        handle_evidence_request(
            query,
            db_path=db_path,
            pricing_path=tmp_path / "pricing.json",
            history_default="active",
            send_error=lambda status, message, **extra: responses.append(
                (status, {"error": message, **extra})
            ),
            send_exception=lambda _prefix, exc: responses.append(
                (HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            ),
            send_json=lambda status, payload: responses.append((status, payload)),
        )

    assert [status for status, _payload in responses] == [
        HTTPStatus.BAD_REQUEST,
        HTTPStatus.NOT_FOUND,
        HTTPStatus.NOT_FOUND,
    ]
    assert responses[1][1]["code"] == "evidence_not_found"
    assert responses[2][1]["code"] == "evidence_history_mismatch"
