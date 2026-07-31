from __future__ import annotations

from decimal import Decimal

import pytest

from codex_usage_tracker.agent_kernel.evidence.cursors import (
    CursorBinding,
    CursorCodec,
    CursorError,
    CursorExpiredError,
    CursorMismatchError,
    CursorTamperedError,
)

SECRET = b"ck08-synthetic-cursor-secret-32-bytes"


def _binding(**changes: object) -> CursorBinding:
    values = {
        "kind": "query",
        "plan_id": "top_sessions",
        "plan_version": 1,
        "publication_id": "publication:synthetic",
        "request_digest": "a" * 64,
        "order": (Decimal("10.500"), "session:stable"),
        "issued_at_us": 100,
        "expires_at_us": 200,
    }
    values.update(changes)
    return CursorBinding(**values)  # type: ignore[arg-type]


def _decode(codec: CursorCodec, token: str, **changes: object) -> CursorBinding:
    values = {
        "expected_kind": "query",
        "expected_plan_id": "top_sessions",
        "expected_plan_version": 1,
        "expected_publication_id": "publication:synthetic",
        "expected_request_digest": "a" * 64,
    }
    values.update(changes)
    return codec.decode(token, **values)  # type: ignore[arg-type]


def test_cursor_round_trips_canonical_keyset_and_is_deterministic() -> None:
    codec = CursorCodec(SECRET, clock=lambda: 150)
    binding = _binding()

    first = codec.encode(binding)
    second = codec.encode(binding)
    decoded = _decode(codec, first)

    assert first == second
    assert decoded.order == ("10.5", "session:stable")
    assert "10.5" not in first


def test_cursor_rejects_tampering_malformed_payload_and_short_secret() -> None:
    codec = CursorCodec(SECRET, clock=lambda: 150)
    token = codec.encode(_binding())
    replacement = "A" if token[-1] != "A" else "B"

    with pytest.raises(CursorTamperedError):
        _decode(codec, token[:-1] + replacement)
    with pytest.raises(CursorTamperedError):
        _decode(codec, "v1.not-base64.not-base64")
    with pytest.raises(CursorError, match="32 bytes"):
        CursorCodec(b"short", clock=lambda: 0)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_plan_id", "current_usage"),
        ("expected_plan_version", 2),
        ("expected_publication_id", "publication:replacement"),
        ("expected_request_digest", "b" * 64),
    ],
)
def test_cursor_rejects_request_plan_and_publication_mismatches(
    field: str,
    value: object,
) -> None:
    codec = CursorCodec(SECRET, clock=lambda: 150)
    token = codec.encode(_binding())

    with pytest.raises(CursorMismatchError, match="restart"):
        _decode(codec, token, **{field: value})


def test_cursor_rejects_expiry_and_evidence_view_mismatch() -> None:
    expired = CursorCodec(SECRET, clock=lambda: 201)
    token = expired.encode(_binding())
    with pytest.raises(CursorExpiredError, match="restart"):
        _decode(expired, token)

    codec = CursorCodec(SECRET, clock=lambda: 150)
    evidence = _binding(kind="evidence", view="timeline")
    evidence_token = codec.encode(evidence)
    with pytest.raises(CursorMismatchError):
        _decode(
            codec,
            evidence_token,
            expected_kind="evidence",
            expected_view="calls",
        )


def test_cursor_forbids_offsets_empty_order_and_nonfinite_values() -> None:
    with pytest.raises(CursorError, match="non-empty"):
        _binding(order=())
    with pytest.raises(CursorError, match="non-finite"):
        _binding(order=(Decimal("NaN"),))
    with pytest.raises(CursorError, match="unsupported"):
        _binding(order=({"offset": object()},))
