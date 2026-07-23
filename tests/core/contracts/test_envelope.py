from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from codex_usage_tracker.core.contracts import (
    AccountingContextV1,
    FreshnessV1,
    NextActionV1,
    ScopeV1,
)
from codex_usage_tracker.core.contracts.envelope import McpEnvelopeV1, envelope_payload
from codex_usage_tracker.core.contracts.serialization import (
    PayloadBudgetError,
    enforce_payload_budget,
    payload_mapping,
    serialized_size,
)


def _scope() -> ScopeV1:
    return ScopeV1(
        since=None,
        until=None,
        history="active",
        privacy_mode="strict",
        filters={"model": "gpt-5.6"},
    )


def _freshness() -> FreshnessV1:
    return FreshnessV1(
        latest_indexed_event_at="2026-07-21T12:00:00Z",
        source_revision="revision-1",
        refresh_completed_at="2026-07-21T12:00:01Z",
        state="fresh",
        reason="Refresh completed.",
        threshold_seconds=300,
        recommended_refresh_action=None,
    )


def _accounting() -> AccountingContextV1:
    return AccountingContextV1(
        physical_rows=10,
        canonical_rows=9,
        copied_rows_excluded=1,
        pricing_coverage=0.9,
        credit_coverage=None,
        service_tier_coverage=0.8,
        history_scope="active",
        privacy_mode="strict",
    )


def test_envelope_generates_utc_time_request_id_and_sorted_mapping() -> None:
    payload = envelope_payload(
        tool="usage_status",
        result_schema="codex-usage-tracker.status.v1",
        result={"zeta": 2, "alpha": 1},
        scope=_scope(),
        freshness=_freshness(),
        accounting=_accounting(),
        data_class="aggregate",
        next_actions=(
            NextActionV1(
                code="open.evidence",
                label="Open evidence",
                tool="usage_evidence",
                arguments={"evidence_id": "evidence-1"},
            ),
        ),
    )

    assert list(payload) == sorted(payload)
    assert re.fullmatch(r"req-[0-9a-f]{32}", payload["request_id"])
    generated_at = datetime.fromisoformat(str(payload["generated_at"]).replace("Z", "+00:00"))
    assert generated_at.tzinfo == timezone.utc
    assert payload["source_revision"] == "revision-1"
    assert list(payload["result"]) == ["alpha", "zeta"]


def test_recursive_non_finite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        envelope_payload(
            tool="usage_query",
            result_schema="codex-usage-tracker.query.v1",
            result={"rows": [{"tokens": float("nan")}]},
            scope=_scope(),
            freshness=_freshness(),
            accounting=_accounting(),
            data_class="aggregate",
        )


def test_envelope_snapshots_nested_result_and_dashboard_targets() -> None:
    result = {"rows": [{"tokens": 1200}]}
    dashboard_targets = [{"relative_url": "/calls", "filters": {"ids": ["call-1"]}}]
    envelope = McpEnvelopeV1(
        tool="usage_query",
        request_id="req-00000000000000000000000000000000",
        generated_at="2026-07-21T12:00:02Z",
        source_revision="revision-1",
        freshness=_freshness(),
        scope=_scope(),
        data_class="aggregate",
        accounting=_accounting(),
        warnings=(),
        limitations=(),
        result_schema="codex-usage-tracker.query.v1",
        result=result,
        dashboard_targets=dashboard_targets,  # type: ignore[arg-type]
        next_actions=(),
    )
    expected = payload_mapping(envelope)

    result["rows"][0]["tokens"] = 2400
    dashboard_targets[0]["filters"]["ids"].append("call-2")

    assert payload_mapping(envelope) == expected


def test_serialized_size_is_utf8_and_budget_error_reports_actual_and_maximum() -> None:
    payload = {"message": "évidence"}
    expected = len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode(
            "utf-8"
        )
    )

    assert serialized_size(payload) == expected
    with pytest.raises(PayloadBudgetError) as exc_info:
        enforce_payload_budget(payload, maximum=expected - 1, name="status")

    assert exc_info.value.actual == expected
    assert exc_info.value.maximum == expected - 1
    assert f"actual={expected}" in str(exc_info.value)
    assert f"maximum={expected - 1}" in str(exc_info.value)
