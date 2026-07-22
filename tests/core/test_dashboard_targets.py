from __future__ import annotations

import json

import pytest

from codex_usage_tracker.core.dashboard_targets import (
    build_dashboard_target,
    build_dashboard_target_v2,
)
from codex_usage_tracker.dashboard_service import DashboardServiceStatus


@pytest.mark.parametrize("privacy_mode", ["normal", "redacted", "strict"])
def test_build_dashboard_target_normalizes_reviewed_fields(privacy_mode: str) -> None:
    target = build_dashboard_target(
        view="call",
        record_id="record-123",
        history="all",
        filters={"mode": "full", "call_q": "forbidden-fixture-value"},
        privacy_mode=privacy_mode,
        service_origin="http://127.0.0.1:47821/",
    )

    assert target == {
        "schema": "codex-usage-tracker-dashboard-target-v1",
        "view": "call",
        "record_id": "record-123",
        "filters": {"mode": "full"},
        "history": "all",
        "privacy_mode": privacy_mode,
        "relative_url": ("/react-dashboard.html?history=all&mode=full&record=record-123&view=call"),
        "absolute_url": (
            "http://127.0.0.1:47821/react-dashboard.html?"
            "history=all&mode=full&record=record-123&view=call"
        ),
        "fallback_instruction": None,
    }
    assert "forbidden-fixture-value" not in json.dumps(target)


def test_build_dashboard_target_resolves_healthy_service_then_fallback() -> None:
    healthy = DashboardServiceStatus(True, True, True, 48123, "healthy")
    target = build_dashboard_target(view="overview", service_status=healthy)
    assert target["absolute_url"] == ("http://127.0.0.1:48123/react-dashboard.html?view=overview")
    assert target["fallback_instruction"] is None

    unavailable = DashboardServiceStatus(True, True, False, 48123, "unreachable")
    target = build_dashboard_target(view="overview", service_status=unavailable)
    assert target["absolute_url"] is None
    assert target["fallback_instruction"] == "codex-usage-tracker serve-dashboard --open"


def test_v2_evidence_target_is_deterministic_and_v1_remains_compatible() -> None:
    first = build_dashboard_target_v2(evidence_kind="call", selector_id="record-123", history="all")
    second = build_dashboard_target_v2(
        evidence_kind="call", selector_id="record-123", history="all"
    )
    assert first == second
    assert first["schema"] == "codex-usage-tracker-dashboard-target-v2"
    assert first["target_id"] == "evidence:call:record-123:all"
    assert first["expires_at"] is None
    assert first["surface"] == "evidence"
    assert first["selectors"] == {"record_id": "record-123"}
    assert first["relative_url"].endswith(
        "history=all&kind=call&record_id=record-123&view=evidence"
    )
    assert build_dashboard_target(view="call", record_id="record-123")["schema"] == (
        "codex-usage-tracker-dashboard-target-v1"
    )
    finding = build_dashboard_target_v2(
        evidence_kind="finding", selector_id="finding-1", analysis_id="analysis-1"
    )
    assert finding["selectors"] == {"finding_id": "finding-1", "analysis_id": "analysis-1"}


def test_build_dashboard_target_rejects_uncataloged_inputs() -> None:
    with pytest.raises(ValueError, match="dashboard view"):
        build_dashboard_target(view="secrets")
    with pytest.raises(ValueError, match="privacy mode"):
        build_dashboard_target(view="overview", privacy_mode="local")
    with pytest.raises(ValueError, match="loopback"):
        build_dashboard_target(view="overview", service_origin="https://example.com")
    with pytest.raises(ValueError, match="credentials"):
        build_dashboard_target(view="overview", service_origin="http://secret@localhost:47821")


def test_build_dashboard_target_maps_canonical_route_selectors() -> None:
    session_key = "session:019e374d-c19f-7da3-a44f-8de043a7a64e"
    assert build_dashboard_target(view="threads", thread_key=session_key)["relative_url"] == (
        "/react-dashboard.html?thread_key=session%3A019e374d-c19f-7da3-a44f-"
        "8de043a7a64e&view=threads"
    )
    assert (
        build_dashboard_target(view="diagnostics", diagnostic_fact="activity:search_read_command")[
            "relative_url"
        ]
        == "/react-dashboard.html?diagnostic_fact=activity%3Asearch_read_command&view=diagnostics"
    )
    for diagnostic_fact in ("skill:codex-usage-tracker", "skill:brooks-test"):
        assert (
            build_dashboard_target(view="diagnostics", diagnostic_fact=diagnostic_fact)[
                "diagnostic_fact"
            ]
            == diagnostic_fact
        )
    assert (
        build_dashboard_target(view="usage-drain", limit_evidence="stable")["relative_url"]
        == "/react-dashboard.html?limit_hypothesis=stable&view=usage-drain"
    )
    assert build_dashboard_target(view="call", record_id="a" * 64)["record_id"] == "a" * 64


@pytest.mark.parametrize(
    "unsafe",
    [
        {"api_token": "forbidden-fixture-value"},
        {"raw_text": "forbidden-fixture-value"},
        {"indexed_text": "forbidden-fixture-value"},
        {"path": "/Users/private/forbidden-fixture-value"},
        {"raw_context": "forbidden-fixture-value"},
        {"q": "forbidden-fixture-value"},
    ],
)
def test_build_dashboard_target_drops_private_or_unreviewed_filters(
    unsafe: dict[str, str],
) -> None:
    target = build_dashboard_target(view="calls", filters=unsafe)
    assert target["filters"] == {}
    assert "forbidden-fixture-value" not in json.dumps(target)


@pytest.mark.parametrize("privacy_mode", ["normal", "redacted", "strict"])
@pytest.mark.parametrize(
    ("view", "selector"),
    [
        ("call", "record_id"),
        ("threads", "thread_key"),
        ("diagnostics", "diagnostic_fact"),
        ("usage-drain", "limit_evidence"),
    ],
)
@pytest.mark.parametrize(
    "unsafe_value",
    [
        "forbidden-fixture-value",
        "sk-" + "abcdefghijklmnopqrstuvwxyz123456",
        "/Users/private/project",
        "name with spaces",
        "line\nbreak",
        "folder\\name",
        "value?token=secret",
        "value#fragment",
        '{"raw":"text"}',
        "raw-context-fragment",
        "indexed-prompt-fragment",
        "project:private-label",
        "a" * 130,
        "xox" + "b-1234567890-abcdefghijklmnop",
        "summarize-my-bank-account",
        "client-acme-production",
    ],
)
def test_build_dashboard_target_rejects_unsafe_selector_values(
    privacy_mode: str,
    view: str,
    selector: str,
    unsafe_value: str,
) -> None:
    with pytest.raises(ValueError, match=selector):
        build_dashboard_target(
            view=view,
            privacy_mode=privacy_mode,
            **{selector: unsafe_value},
        )


@pytest.mark.parametrize("privacy_mode", ["normal", "redacted", "strict"])
@pytest.mark.parametrize(
    ("view", "filter_key"),
    [
        ("investigator", "finding"),
        ("calls", "explore"),
        ("calls", "detail"),
        ("calls", "source"),
        ("calls", "sort"),
        ("calls", "direction"),
        ("calls", "density"),
        ("calls", "page"),
        ("call", "return"),
        ("call", "mode"),
        ("threads", "expand"),
        ("threads", "risk"),
        ("threads", "thread_call_sort"),
        ("threads", "thread_call_page"),
        ("usage-drain", "usage_plan"),
        ("usage-drain", "usage_effort"),
        ("usage-drain", "usage_subagents"),
        ("usage-drain", "usage_sample"),
        ("usage-drain", "usage_confidence"),
        ("usage-drain", "limit_window"),
        ("diagnostics", "diagnostic_source"),
        ("reports", "report"),
    ],
)
def test_build_dashboard_target_drops_invalid_handoff_filter_values(
    privacy_mode: str,
    view: str,
    filter_key: str,
) -> None:
    target = build_dashboard_target(
        view=view,
        privacy_mode=privacy_mode,
        filters={filter_key: "forbidden-fixture-value"},
    )
    serialized = json.dumps(target)
    assert target["filters"] == {}
    assert "forbidden-fixture-value" not in serialized
    assert "forbidden-fixture-value" not in target["relative_url"]
    assert target["absolute_url"] is None


def test_build_dashboard_target_normalizes_boolean_and_numeric_filters() -> None:
    target = build_dashboard_target(
        view="usage-drain",
        filters={
            "usage_subagents": False,
            "usage_sample": 80,
            "usage_confidence": 0.55,
        },
    )

    assert target["relative_url"] == (
        "/react-dashboard.html?usage_confidence=0.55&usage_sample=80&"
        "usage_subagents=false&view=usage-drain"
    )


@pytest.mark.parametrize("privacy_mode", ["redacted", "strict"])
def test_build_dashboard_target_rejects_label_bearing_identifiers(
    privacy_mode: str,
) -> None:
    with pytest.raises(ValueError, match="thread_key"):
        build_dashboard_target(
            view="threads",
            thread_key="thread:Project Alpha",
            privacy_mode=privacy_mode,
        )


def test_normal_mode_accepts_bounded_identifier_form_without_private_expansion() -> None:
    target = build_dashboard_target(
        view="threads",
        thread_key="thread:Project Alpha",
        privacy_mode="normal",
    )

    assert target["thread_key"] == "thread:Project Alpha"


@pytest.mark.parametrize("privacy_mode", ["normal", "redacted", "strict"])
@pytest.mark.parametrize(
    "adversarial",
    [
        "xox" + "b-1234567890-abcdefghijklmnop",
        "summarize-my-bank-account",
        "client-acme-production",
    ],
)
def test_report_filter_accepts_only_cataloged_ids(
    privacy_mode: str,
    adversarial: str,
) -> None:
    target = build_dashboard_target(
        view="reports",
        privacy_mode=privacy_mode,
        filters={"report": adversarial},
    )
    assert target["filters"] == {}
    assert adversarial not in json.dumps(target)


@pytest.mark.parametrize(
    "report_id",
    [
        "fast-mode-proxy",
        "cost-curves",
        "usage-remaining",
        "allowance-change",
        "weekly-credits",
        "usage-drain-model",
    ],
)
def test_report_filter_accepts_cataloged_ids(report_id: str) -> None:
    assert build_dashboard_target(view="reports", filters={"report": report_id})["filters"] == {
        "report": report_id
    }


@pytest.mark.parametrize("privacy_mode", ["normal", "redacted", "strict"])
def test_session_thread_keys_are_safe_in_every_privacy_mode(privacy_mode: str) -> None:
    session_key = "session:019e374d-c19f-7da3-a44f-8de043a7a64e"
    assert (
        build_dashboard_target(
            view="threads",
            thread_key=session_key,
            privacy_mode=privacy_mode,
        )["thread_key"]
        == session_key
    )


@pytest.mark.parametrize(
    ("value", "serialized"),
    [(0.0, "0"), (-0.0, "0"), (1.0, "1"), (0.55, "0.55"), (1e-7, "0.0000001")],
)
def test_numeric_filter_serialization_is_canonical(value: float, serialized: str) -> None:
    target = build_dashboard_target(view="usage-drain", filters={"usage_confidence": value})
    assert target["relative_url"] == (
        f"/react-dashboard.html?usage_confidence={serialized}&view=usage-drain"
    )


@pytest.mark.parametrize("value", [-0.01, 1.01, float("inf"), float("nan")])
def test_numeric_filter_rejects_non_finite_or_out_of_range_values(value: float) -> None:
    assert (
        build_dashboard_target(view="usage-drain", filters={"usage_confidence": value})["filters"]
        == {}
    )


@pytest.mark.parametrize(
    "origin",
    ["http://localhost", "http://localhost:80", "http://localhost:65536"],
)
def test_service_origin_requires_valid_non_privileged_port(origin: str) -> None:
    with pytest.raises(ValueError):
        build_dashboard_target(view="overview", service_origin=origin)
