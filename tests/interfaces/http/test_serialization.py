from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from codex_usage_tracker.interfaces.http.serialization import serialize_http_payload


@dataclass(frozen=True)
class _ImmutablePayload:
    values: object


def test_serialize_http_payload_handles_immutable_dataclass_mappings() -> None:
    payload = _ImmutablePayload(
        values=MappingProxyType({"nested": MappingProxyType({"count": 2})})
    )

    assert serialize_http_payload(payload) == {
        "values": {"nested": {"count": 2}}
    }
