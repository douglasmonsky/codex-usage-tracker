from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pytest

from codex_usage_tracker.kernel.application import KernelApplication
from codex_usage_tracker.kernel.evidence.contracts import (
    EvidenceSelector,
    EvidenceView,
)
from codex_usage_tracker.kernel.interfaces.http.app import (
    API_PREFIX,
    ROUTES,
    validate_loopback_request,
)
from codex_usage_tracker.kernel.interfaces.http.server import create_server
from codex_usage_tracker.kernel.live.journal import JournalEvent
from codex_usage_tracker.kernel.live.stream import MAX_REPLAY, parse_last_event_id

from ..interfaces.support import active_runtime, synthetic_sources

_ROOT = Path(__file__).resolve().parents[3]
_CONTRACT_PATH = _ROOT / "config" / "kernel-overlay-adapter-v1.json"
_FIXTURE_PATH = (
    _ROOT / "tests" / "kernel" / "fixtures" / "overlay-adapter-v1.json"
)
_DOC_PATH = _ROOT / "docs" / "kernel-overlay-adapter-contract.md"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _negotiates(contract: dict, fixture: dict) -> bool:
    capabilities = {route["capability"] for route in contract["routes"]}
    return (
        fixture["protocol_version"] == contract["protocol_version"]
        and fixture["kernel_api_prefix"] == contract["kernel_api_prefix"]
        and fixture["contract_schema"] == contract["schema"]
        and set(fixture["capabilities"]) == capabilities
    )


def _snapshot_is_consistent(contract: dict, snapshot: dict) -> bool:
    before = snapshot.get("status_before")
    after = snapshot.get("status_after")
    evidence = snapshot.get("evidence_response")
    if not isinstance(before, dict) or not isinstance(after, dict) or not isinstance(evidence, dict):
        return False
    if before.get("state") not in contract["snapshot_identity"]["usable_states"]:
        return False
    identity = tuple(contract["snapshot_identity"]["required_fields"])
    before_identity = tuple(before.get(field) for field in identity)
    after_identity = tuple(after.get(field) for field in identity)
    return (
        all(value is not None for value in before_identity)
        and before_identity == after_identity
        and evidence.get("generation") == before.get("generation")
    )


def test_overlay_contract_is_an_exact_read_only_route_subset() -> None:
    contract = _load(_CONTRACT_PATH)

    assert contract["schema"] == "codex-usage-tracker.overlay-adapter-contract.v1"
    assert contract["protocol_version"] == 1
    assert contract["kernel_api_prefix"] == API_PREFIX
    routes = {
        (entry["method"], entry["path"]): entry["capability"]
        for entry in contract["routes"]
    }
    assert routes == {
        ("GET", f"{API_PREFIX}/status"): "handshake",
        ("POST", f"{API_PREFIX}/evidence"): "evidence_snapshot",
        ("GET", f"{API_PREFIX}/events"): "generation_stream",
    }
    assert set(routes) <= set(ROUTES)
    assert all(value is False for value in contract["authority"].values())
    assert contract["sidecar"] == {
        "canonical_renderer": True,
        "fallback_required": True,
        "destination_template": "/evidence/{selector}?view=timeline&live=1",
    }
    assert "config/kernel-overlay-adapter-v1.json" in (
        _ROOT / "MANIFEST.in"
    ).read_text(encoding="utf-8")
    assert not (_ROOT / "src" / "codex_usage_tracker" / "kernel" / "overlay").exists()


def test_selector_capability_and_synthetic_handshake_fail_closed() -> None:
    contract = _load(_CONTRACT_PATH)
    fixture = _load(_FIXTURE_PATH)

    assert set(contract["selectors"]) == {
        "thread",
        "turn",
        "call",
        "tool",
        "allowance",
    }
    assert set(contract["evidence_views"]) == {view.value for view in EvidenceView}
    for kind in contract["selectors"]:
        assert EvidenceSelector.parse(f"{kind}:synthetic-id").kind == kind

    validate_loopback_request(
        fixture["request"]["host"],
        fixture["request"]["origin"],
    )
    assert _negotiates(contract, fixture)
    snapshot = fixture["snapshot"]
    assert set(contract["status_required_fields"]) <= set(snapshot["status_before"])
    assert _snapshot_is_consistent(contract, snapshot)
    assert not _snapshot_is_consistent(
        contract,
        fixture["rejections"]["absent_status"],
    )
    assert not _snapshot_is_consistent(
        contract,
        fixture["rejections"]["publication_race"],
    )
    assert snapshot["evidence_response"]["coverage"]["content_included"] is False
    origin = urlsplit(fixture["request"]["origin"])
    assert origin.path in contract["origin"]["paths"]

    for key, value in (
        ("protocol_version", 2),
        ("kernel_api_prefix", "/api/kernel/v2"),
        ("contract_schema", "unknown"),
    ):
        incompatible = deepcopy(fixture)
        incompatible[key] = value
        assert not _negotiates(contract, incompatible)
    incompatible = deepcopy(fixture)
    incompatible["capabilities"].append("refresh")
    assert not _negotiates(contract, incompatible)

    with pytest.raises(ValueError, match="loopback Host"):
        validate_loopback_request("example.com", fixture["request"]["origin"])
    with pytest.raises(ValueError, match="loopback"):
        validate_loopback_request(
            fixture["request"]["host"],
            "https://example.com",
        )


def test_stream_fixture_freezes_replay_and_privacy_contract() -> None:
    contract = _load(_CONTRACT_PATH)
    fixture = _load(_FIXTURE_PATH)
    stream = fixture["stream"]
    first, gap, fresh = stream["connections"]
    committed = first["frames"][0]
    data = committed["data"]

    assert contract["stream"]["max_replay"] == MAX_REPLAY
    assert parse_last_event_id(str(first["last_event_id"])) == first["last_event_id"]
    assert committed["event"] == "generation_committed"
    assert committed["event"] in contract["stream"]["sse_event_kinds"]
    assert set(contract["stream"]["generation_committed_required_fields"]) <= set(
        data
    )
    assert set(data["payload"]) <= set(contract["stream"]["safe_payload_keys"])
    assert gap["frames"] == [
        {"event": "snapshot_required", "data": {"generation": 8}}
    ]
    assert gap["frames"][0]["event"] in contract["stream"]["sse_event_kinds"]
    assert fresh == {
        "last_event_id": None,
        "frames": [{"comment": "heartbeat"}],
    }
    assert fresh["frames"][0]["comment"] in contract["stream"]["comment_frames"]
    assert stream["reconnect"] == {
        "header": "Last-Event-ID",
        "resume_value": "41",
        "on_gap": "snapshot_required",
        "after_gap_header": None,
    }
    assert contract["stream"]["on_gap"] == {
        "event": "snapshot_required",
        "action": "resnapshot_then_reopen_without_cursor",
        "close_stale_connection": True,
        "clear_last_event_id": True,
    }
    rendered = JournalEvent(
        event_id=committed["id"],
        publication_id=data["publication_id"],
        generation=data["generation"],
        event_kind=committed["event"],
        selector=data["selector"],
        occurred_at=data["occurred_at"],
        payload=data["payload"],
    ).to_sse()
    assert rendered.startswith("id: 41\nevent: generation_committed\n")

    encoded = json.dumps(fixture, sort_keys=True)
    assert "PRIVATE_" not in encoded
    assert "/Users/" not in encoded
    assert "arguments" not in encoded
    assert "raw_content" not in encoded


def test_contract_routes_work_through_a_real_read_only_loopback_listener(
    tmp_path: Path,
) -> None:
    runtime = active_runtime(tmp_path)
    launches = []
    application = KernelApplication(
        runtime,
        worker_launcher=launches.append,
        source_provider=lambda _home: synthetic_sources(),
    )
    query = application.query(
        {
            "requests": [
                {
                    "dataset": "calls",
                    "operation": "rows",
                    "dimensions": ["call"],
                    "measures": ["total_tokens"],
                    "limit": 1,
                }
            ]
        }
    )
    selector = query["results"][0]["evidence_selectors"][0]
    operational_before = runtime.kernel.operational.read_bytes()
    analytical_before = runtime.kernel.analytical.read_bytes()
    server = create_server(application)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    host, port = server.server_address
    origin = f"http://127.0.0.1:{port}"
    headers = {"Host": f"127.0.0.1:{port}", "Origin": origin}

    try:
        with urlopen(
            Request(f"{origin}{API_PREFIX}/status", headers=headers),
            timeout=5,
        ) as response:
            status_before = json.loads(response.read())
        evidence_body = json.dumps(
            {"selector": selector, "view": "summary", "limit": 10}
        ).encode()
        with urlopen(
            Request(
                f"{origin}{API_PREFIX}/evidence",
                data=evidence_body,
                headers={**headers, "Content-Type": "application/json"},
                method="POST",
            ),
            timeout=5,
        ) as response:
            evidence = json.loads(response.read())
        with urlopen(
            Request(
                f"{origin}{API_PREFIX}/events?limit=5",
                headers={**headers, "Last-Event-ID": "0"},
            ),
            timeout=5,
        ) as response:
            stream = response.read().decode()
        with urlopen(
            Request(f"{origin}{API_PREFIX}/status", headers=headers),
            timeout=5,
        ) as response:
            status_after = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

    contract = _load(_CONTRACT_PATH)
    assert _snapshot_is_consistent(
        contract,
        {
            "status_before": status_before,
            "evidence_response": evidence,
            "status_after": status_after,
        },
    )
    assert "event: generation_committed" in stream
    assert evidence["coverage"]["content_included"] is False
    assert runtime.kernel.operational.read_bytes() == operational_before
    assert runtime.kernel.analytical.read_bytes() == analytical_before
    assert launches == []


def test_contract_documentation_preserves_future_decision_boundary() -> None:
    document = _DOC_PATH.read_text(encoding="utf-8")

    for statement in (
        "does not authorize overlay implementation",
        "Sidecar remains canonical renderer",
        "No credentials",
        "No DOM capture",
        "Unknown protocol, API version, Host, or Origin fails closed",
    ):
        assert statement in document
