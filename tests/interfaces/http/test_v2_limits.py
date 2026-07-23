from __future__ import annotations

from io import BytesIO
from pathlib import Path

from codex_usage_tracker.evidence.models import EvidenceNotFoundError
from codex_usage_tracker.interfaces.http.v2 import ApplicationHttpV2Services, HttpV2Facade
from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_status
from tests.interfaces.http.test_v2 import RecordingServices, _request


def test_stream_dispatch_requires_and_enforces_declared_content_length() -> None:
    facade = HttpV2Facade(RecordingServices())
    missing = facade.handle_stream(
        method="POST",
        path="/api/v2/query",
        query="",
        stream=BytesIO(b"{}"),
        content_length=None,
        content_type="application/json",
        authorized=True,
    )
    oversized = facade.handle_stream(
        method="POST",
        path="/api/v2/refresh",
        query="",
        stream=BytesIO(b""),
        content_length=str(4 * 1024 + 1),
        content_type="application/json",
        authorized=True,
    )

    assert missing.status == 411
    assert oversized.status == 413


def test_job_starts_return_accepted_and_output_limits_are_enforced() -> None:
    class Services(RecordingServices):
        def analyze(self, request: object) -> object:
            return {"schema": "codex-usage-tracker.job.v1", "job_id": "analysis-1"}

        def query(self, request: object) -> object:
            return {"schema": "codex-usage-tracker.query.v2", "rows": ["x" * (256 * 1024)]}

    facade = HttpV2Facade(Services())
    accepted = _request(facade, "POST", "/api/v2/analyze", {"goal": "token_waste"})
    too_large = _request(
        facade,
        "POST",
        "/api/v2/query",
        {"entity": "model", "measures": ["tokens"]},
    )

    assert accepted.status == 202
    assert too_large.status == 500
    assert too_large.payload["error"]["code"] == "response_too_large"  # type: ignore[index]


def test_evidence_lookup_errors_have_stable_http_status_and_code() -> None:
    class MissingEvidence(RecordingServices):
        def evidence(self, request: object) -> object:
            raise EvidenceNotFoundError("call evidence not found: record-9")

    response = _request(
        HttpV2Facade(MissingEvidence()),
        "POST",
        "/api/v2/evidence",
        {"selector_kind": "call", "selector_id": "record-9"},
    )

    assert response.status == 404
    assert response.payload["error"]["code"] == "evidence_not_found"  # type: ignore[index]


def test_http_status_uses_the_same_result_schema_and_shape_as_mcp(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    pricing_path = tmp_path / "pricing.json"
    codex_home = tmp_path / ".codex"
    response = _request(
        HttpV2Facade(
            ApplicationHttpV2Services(
                db_path=db_path,
                pricing_path=pricing_path,
                codex_home=codex_home,
            )
        ),
        "GET",
        "/api/v2/status",
    )
    mcp = build_usage_status(
        db_path=db_path,
        pricing_path=pricing_path,
        codex_home=codex_home,
        home=tmp_path,
    )

    assert response.payload["schema"] == mcp["result_schema"]
    assert set(response.payload) == set(mcp["result"])  # type: ignore[arg-type]
