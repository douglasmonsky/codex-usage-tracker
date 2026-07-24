from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codex_usage_tracker.application import status
from codex_usage_tracker.application.context import RequestContext
from codex_usage_tracker.application.requests import RequestScope, StatusRequest
from codex_usage_tracker.core.contracts import FreshnessV1
from codex_usage_tracker.dashboard_service import DashboardServiceStatus
from codex_usage_tracker.diagnostics.conversational_readiness import conversational_readiness

CORE_TOOLS = [
    "usage_status",
    "usage_refresh",
    "usage_analyze",
    "usage_query",
    "usage_evidence",
    "usage_allowance",
    "usage_job_status",
]


def _context(*, state: str, rows: int = 1) -> RequestContext:
    timestamp = None
    if rows:
        age = timedelta(minutes=10) if state == "stale" else timedelta(seconds=10)
        timestamp = (datetime.now(timezone.utc) - age).isoformat().replace("+00:00", "Z")
    return RequestContext(
        source_revision="generation:test" if rows else None,
        freshness=FreshnessV1(
            latest_indexed_event_at=timestamp,
            source_revision="generation:test" if rows else None,
            refresh_completed_at=timestamp,
            state=state,  # type: ignore[arg-type]
            reason=f"index is {state}",
            threshold_seconds=300,
            recommended_refresh_action=None if state == "fresh" else "usage_refresh",
        ),
        scope=RequestScope().to_contract(),
        physical_rows=rows,
        canonical_rows=rows,
        copied_rows_excluded=0,
        pricing_coverage=1.0 if rows else None,
        credit_coverage=1.0 if rows else None,
        service_tier_coverage=1.0 if rows else None,
    )


def _install_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    context: RequestContext,
    readiness_state: str = "ready",
) -> None:
    monkeypatch.setattr(status, "build_request_context", lambda **_kwargs: context)
    monkeypatch.setattr(
        status,
        "conversational_readiness",
        lambda **_kwargs: {
            "schema": "codex-usage-tracker-conversational-readiness-v1",
            "state": readiness_state,
            "summary": "Local checks passed; current task tool exposure is not verified.",
            "next_action": "Restart Codex." if readiness_state == "restart-required" else None,
            "evidence": ["synthetic"],
        },
    )
    monkeypatch.setattr(
        status,
        "dashboard_service_status",
        lambda **_kwargs: DashboardServiceStatus(False, False, False, 47821, "not installed"),
    )


def _request(
    tmp_path: Path, *, profile: str = "core", threshold_seconds: int = 300
) -> StatusRequest:
    pricing_path = tmp_path / "pricing.json"
    pricing_path.write_text(
        json.dumps({"models": {}, "billing_basis": "unknown"}), encoding="utf-8"
    )
    return StatusRequest(
        db_path=tmp_path / "usage.sqlite3",
        pricing_path=pricing_path,
        codex_home=tmp_path / ".codex",
        home=tmp_path,
        mcp_profile=profile,  # type: ignore[arg-type]
        freshness_threshold_seconds=threshold_seconds,
    )


def test_empty_install_returns_bounded_status_and_refresh_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_dependencies(monkeypatch, context=_context(state="empty", rows=0))

    result = status.get_status(_request(tmp_path))

    assert result["schema"] == "codex-usage-tracker.status.v2"
    assert result["index"]["state"] == "empty"  # type: ignore[index]
    assert result["sources"]["canonical_rows"] == 0  # type: ignore[index]
    assert result["persistent_service"]["detail"] == "not installed"  # type: ignore[index]
    assert result["next_action"]["tool"] == "usage_refresh"  # type: ignore[index]


@pytest.mark.parametrize("state", ["fresh", "stale"])
def test_index_freshness_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    _install_dependencies(monkeypatch, context=_context(state=state))

    result = status.get_status(_request(tmp_path))

    assert result["index"]["state"] == state  # type: ignore[index]
    expected = None if state == "fresh" else "usage_refresh"
    assert result["index"]["recommended_refresh_action"] == expected  # type: ignore[index]


@pytest.mark.parametrize(
    ("threshold_seconds", "expected_state"),
    [(5, "stale"), (900, "fresh")],
)
def test_custom_whole_second_threshold_controls_result_and_returned_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    threshold_seconds: int,
    expected_state: str,
) -> None:
    _install_dependencies(monkeypatch, context=_context(state="stale"))

    result, context = status._build_status(_request(tmp_path, threshold_seconds=threshold_seconds))

    assert result["index"]["state"] == expected_state  # type: ignore[index]
    assert result["index"]["threshold_seconds"] == threshold_seconds  # type: ignore[index]
    assert context.freshness.state == expected_state
    assert context.freshness.threshold_seconds == threshold_seconds
    assert result["index"] == status.payload_mapping(context.freshness)


def test_unavailable_pricing_is_explicit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install_dependencies(monkeypatch, context=_context(state="fresh"))
    request = _request(tmp_path)
    request.pricing_path.unlink()

    result = status.get_status(request)

    assert result["pricing"]["state"] == "unavailable"  # type: ignore[index]
    assert result["pricing"]["coverage"] == 1.0  # type: ignore[index]


def test_restart_required_mcp_is_preserved_without_exposure_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_dependencies(
        monkeypatch,
        context=_context(state="fresh"),
        readiness_state="restart-required",
    )

    result = status.get_status(_request(tmp_path))

    assert result["conversational_readiness"]["state"] == "restart-required"  # type: ignore[index]
    assert result["mcp"]["current_task_exposure"] == "not-verified"  # type: ignore[index]
    assert "not verified" in json.dumps(result).lower()


def test_core_profile_reports_exact_stable_catalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_dependencies(monkeypatch, context=_context(state="fresh"))

    result = status.get_status(_request(tmp_path, profile="core"))

    assert result["mcp"] == {
        "active_profile": "core",
        "core_tools": CORE_TOOLS,
        "current_task_exposure": "not-verified",
    }


def test_malformed_pricing_configuration_is_bounded_and_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_dependencies(monkeypatch, context=_context(state="fresh"))
    request = _request(tmp_path)
    request.pricing_path.write_text("{", encoding="utf-8")

    result = status.get_status(request)

    assert result["pricing"]["state"] == "malformed"  # type: ignore[index]
    assert result["pricing"]["error"]  # type: ignore[index]
    assert result["next_action"]["code"] == "fix_pricing_config"  # type: ignore[index]


def test_malformed_mcp_configuration_never_claims_current_task_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        status,
        "build_request_context",
        lambda **_kwargs: _context(state="fresh"),
    )
    monkeypatch.setattr(
        status,
        "dashboard_service_status",
        lambda **_kwargs: DashboardServiceStatus(False, False, False, 47821, "not installed"),
    )
    request = _request(tmp_path)
    plugin_root = tmp_path / "plugins" / "codex-usage-tracker"
    (plugin_root / ".codex-plugin").mkdir(parents=True)
    (plugin_root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps({"name": "codex-usage-tracker"}), encoding="utf-8"
    )
    (plugin_root / ".mcp.json").write_text("{", encoding="utf-8")

    result = status.get_status(request, readiness_provider=conversational_readiness)

    assert result["conversational_readiness"]["state"] == "unavailable"  # type: ignore[index]
    assert result["mcp"]["current_task_exposure"] == "not-verified"  # type: ignore[index]
    assert result["next_action"]["code"] == "setup_plugin"  # type: ignore[index]
