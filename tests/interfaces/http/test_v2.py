from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from codex_usage_tracker.interfaces.http.serialization import HttpRequestError, decode_json_object
from codex_usage_tracker.interfaces.http.v2 import HTTP_V2_ROUTES, HttpV2Facade, HttpV2Response


@dataclass
class RecordingServices:
    calls: list[tuple[str, object]] = field(default_factory=list)

    def status(self, request: object) -> object:
        return self._record("status", request)

    def refresh(self, request: object) -> object:
        return self._record("refresh", request)

    def analyze(self, request: object) -> object:
        return self._record("analyze", request)

    def query(self, request: object) -> object:
        return self._record("query", request)

    def evidence(self, request: object) -> object:
        return self._record("evidence", request)

    def allowance(self, request: object) -> object:
        return self._record("allowance", request)

    def job_status(self, request: object) -> object:
        return self._record("job_status", request)

    def capabilities(self) -> object:
        return self._record("capabilities", None)

    def _record(self, name: str, request: object) -> dict[str, object]:
        self.calls.append((name, request))
        return {"schema": f"test.{name}.v1", "operation": name}


def _request(
    facade: HttpV2Facade,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    *,
    query: str = "",
    authorized: bool = True,
    content_type: str = "application/json",
) -> HttpV2Response:
    body = b"" if payload is None else json.dumps(payload).encode()
    return facade.handle(
        method=method,
        path=path,
        query=query,
        body=body,
        content_type=content_type,
        authorized=authorized,
    )


def test_v2_route_contract_is_exact_and_versioned() -> None:
    assert {
        ("GET", "/api/v2/status"),
        ("POST", "/api/v2/refresh"),
        ("POST", "/api/v2/analyze"),
        ("POST", "/api/v2/query"),
        ("POST", "/api/v2/evidence"),
        ("POST", "/api/v2/allowance"),
        ("GET", "/api/v2/jobs/{job_id}"),
        ("GET", "/api/v2/capabilities"),
    } == HTTP_V2_ROUTES


@pytest.mark.parametrize(
    ("path", "payload", "service"),
    [
        ("/api/v2/refresh", {"history": "all", "execution": "sync"}, "refresh"),
        ("/api/v2/analyze", {"goal": "token_waste", "evidence_limit": 4}, "analyze"),
        ("/api/v2/query", {"entity": "model", "measures": ["tokens"]}, "query"),
        (
            "/api/v2/evidence",
            {"selector_kind": "call", "selector_id": "record-7"},
            "evidence",
        ),
        ("/api/v2/allowance", {"operation": "status"}, "allowance"),
    ],
)
def test_post_routes_decode_typed_requests(
    path: str, payload: dict[str, object], service: str
) -> None:
    services = RecordingServices()
    response = _request(HttpV2Facade(services), "POST", path, payload)

    assert response.status == 200
    assert response.payload["operation"] == service
    assert services.calls[-1][0] == service


def test_get_routes_decode_query_and_path_parameters() -> None:
    services = RecordingServices()
    facade = HttpV2Facade(services)

    status = _request(
        facade,
        "GET",
        "/api/v2/status",
        query="history=all&freshness_threshold_seconds=60",
    )
    job = _request(
        facade,
        "GET",
        "/api/v2/jobs/job_123",
        query="include_result=1",
    )
    capabilities = _request(facade, "GET", "/api/v2/capabilities")

    assert [status.status, job.status, capabilities.status] == [200, 200, 200]
    assert [name for name, _request_value in services.calls] == [
        "status",
        "job_status",
        "capabilities",
    ]
    assert services.calls[0][1].scope.history == "all"
    assert services.calls[1][1].job_id == "job_123"
    assert services.calls[1][1].include_result is True


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/v2/refresh", {"history": "active", "surprise": True}),
        ("/api/v2/analyze", {"goal": "token_waste", "surprise": True}),
        ("/api/v2/query", {"entity": "model", "measures": ["tokens"], "surprise": True}),
        (
            "/api/v2/evidence",
            {"selector_kind": "call", "selector_id": "record-7", "surprise": True},
        ),
        ("/api/v2/allowance", {"operation": "status", "surprise": True}),
    ],
)
def test_post_routes_reject_unknown_top_level_fields(
    path: str, payload: dict[str, object]
) -> None:
    response = _request(HttpV2Facade(RecordingServices()), "POST", path, payload)

    assert response.status == 400
    assert response.payload == {
        "schema": "codex-usage-tracker.error.v1",
        "error": {"code": "invalid_request", "message": "unsupported field: surprise"}
    }


def test_json_decoder_rejects_wrong_content_type_malformed_and_oversized_bodies() -> None:
    with pytest.raises(HttpRequestError, match="application/json"):
        decode_json_object(b"{}", content_type="text/plain", max_bytes=16)
    with pytest.raises(HttpRequestError, match="valid JSON"):
        decode_json_object(b"{", content_type="application/json", max_bytes=16)
    with pytest.raises(HttpRequestError, match="JSON object"):
        decode_json_object(b"[]", content_type="application/json", max_bytes=16)
    with pytest.raises(HttpRequestError, match="exceeds 16 bytes"):
        decode_json_object(b'{"value":"too large"}', content_type="application/json", max_bytes=16)


@pytest.mark.parametrize("body", [b'{"value":NaN}', b'{"value":1,"value":2}'])
def test_json_decoder_rejects_non_standard_numbers_and_duplicate_fields(body: bytes) -> None:
    with pytest.raises(HttpRequestError, match="valid JSON"):
        decode_json_object(body, content_type="application/json", max_bytes=64)


@pytest.mark.parametrize(
    "path",
    ["/api/v2/refresh", "/api/v2/analyze", "/api/v2/allowance"],
)
def test_mutating_or_expensive_routes_require_the_local_api_token(path: str) -> None:
    payloads: dict[str, dict[str, Any]] = {
        "/api/v2/refresh": {"history": "active"},
        "/api/v2/analyze": {"goal": "token_waste"},
        "/api/v2/allowance": {"operation": "analysis"},
    }
    response = _request(
        HttpV2Facade(RecordingServices()),
        "POST",
        path,
        payloads[path],
        authorized=False,
    )

    assert response.status == 403
    assert response.payload["error"] == {
        "code": "forbidden",
        "message": "Valid local API token required",
    }


def test_routes_reject_wrong_methods_and_unknown_paths() -> None:
    facade = HttpV2Facade(RecordingServices())

    wrong_method = _request(facade, "GET", "/api/v2/query")
    missing = _request(facade, "GET", "/api/v2/not-real")

    assert wrong_method.status == 405
    assert wrong_method.headers["Allow"] == "POST"
    assert missing.status == 404
