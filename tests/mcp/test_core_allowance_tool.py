from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from codex_usage_tracker.application.allowance_models import AllowanceResult
from codex_usage_tracker.core.contracts import serialized_size
from codex_usage_tracker.core.dashboard_targets import build_limits_target_v2
from codex_usage_tracker.interfaces.mcp import core_tools
from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_allowance, usage_allowance
from tests.application.test_allowance import NOW, _seed


def test_allowance_public_signature_is_the_roadmap_contract() -> None:
    assert tuple(inspect.signature(usage_allowance).parameters) == (
        "operation",
        "window",
        "range",
        "cursor",
        "limit",
        "analysis_id",
        "execution",
    )


def test_allowance_public_adapter_forwards_every_roadmap_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(core_tools, "build_usage_allowance", capture)

    assert usage_allowance(
        operation="analysis",
        window="five_hour",
        range="7d",
        cursor="opaque",
        limit=17,
        analysis_id="snapshot-1",
        execution="async",
    ) == {"ok": True}
    assert captured == {
        "operation": "analysis",
        "window": "five_hour",
        "range_preset": "7d",
        "cursor": "opaque",
        "limit": 17,
        "analysis_id": "snapshot-1",
        "execution": "async",
    }


@pytest.mark.parametrize(
    ("operation", "result_schema"),
    (
        ("status", "codex-usage-tracker-allowance-status-v2"),
        ("series", "codex-usage-tracker-allowance-series-v2"),
        ("evidence", "codex-usage-tracker-allowance-evidence-v2"),
    ),
)
def test_allowance_operations_return_bounded_envelopes_and_limits_targets(
    tmp_path: Path, operation: str, result_schema: str
) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)

    payload = build_usage_allowance(
        operation=operation,
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
        now=NOW,
    )

    assert payload["schema"] == "codex-usage-tracker.mcp-envelope.v1"
    assert payload["result_schema"] == result_schema
    assert payload["dashboard_targets"][0]["surface"] == "limits"  # type: ignore[index]
    assert payload["dashboard_targets"][0]["evidence_kind"] == "allowance"  # type: ignore[index]
    assert serialized_size(payload) <= 128 * 1024


def test_allowance_nonterminal_job_uses_generic_poll_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = build_limits_target_v2(
        operation="analysis",
        window="weekly",
        range_preset="8w",
        since=None,
        until="2026-07-22T11:00:00+00:00",
        analysis_id="a" * 64,
    )
    result = AllowanceResult(
        payload={
            "schema": "codex-usage-tracker.job.v1",
            "job_id": "allowance_job",
            "kind": "allowance",
            "state": "queued",
        },
        result_schema="codex-usage-tracker.job.v1",
        range_start=None,
        range_end="2026-07-22T11:00:00+00:00",
        analysis_id="a" * 64,
        dashboard_target=target,
    )
    monkeypatch.setattr(core_tools, "get_allowance", lambda *_args, **_kwargs: result)

    payload = build_usage_allowance(
        operation="analysis",
        execution="async",
        db_path=tmp_path / "missing.sqlite3",
        pricing_path=tmp_path / "pricing.json",
    )

    assert payload["result_schema"] == "codex-usage-tracker.job.v1"
    assert payload["next_actions"] == [
        {
            "schema": "codex-usage-tracker.next-action.v1",
            "code": "job.poll",
            "label": "Poll allowance analysis job",
            "tool": "usage_job_status",
            "arguments": {"job_id": "allowance_job", "include_result": True},
        }
    ]


def test_allowance_final_envelope_budget_rejects_oversized_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = build_limits_target_v2(
        operation="status",
        window="weekly",
        range_preset="8w",
        since=None,
        until=None,
    )
    result = AllowanceResult(
        payload={"schema": "synthetic.v1", "aggregate": "x" * (130 * 1024)},
        result_schema="synthetic.v1",
        range_start=None,
        range_end=None,
        dashboard_target=target,
    )
    monkeypatch.setattr(core_tools, "get_allowance", lambda *_args, **_kwargs: result)

    with pytest.raises(ValueError, match="payload budget"):
        build_usage_allowance(
            operation="status",
            db_path=tmp_path / "missing.sqlite3",
            pricing_path=tmp_path / "pricing.json",
        )
