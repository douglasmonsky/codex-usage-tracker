from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.application.refresh import RefreshPlan, refresh_usage
from codex_usage_tracker.application.requests import RefreshRequest
from codex_usage_tracker.core.models import RefreshResult
from codex_usage_tracker.interfaces.mcp.core_tools import build_usage_query
from codex_usage_tracker.interfaces.mcp.models import WorkProofContract
from codex_usage_tracker.interfaces.mcp.registry import tool_specs
from codex_usage_tracker.interfaces.mcp.work_proof import CONSTANT_STATUS, WORK_PROOFS
from tests.application.test_query import _seed


def _field(payload: dict[str, object], path: str) -> object:
    value: object = payload
    for part in path.split("."):
        assert isinstance(value, dict), f"{path!r} does not resolve through a mapping"
        value = value[part]
    return value


def _set_field(payload: dict[str, object], path: str, value: object) -> None:
    target: dict[str, object] = payload
    parts = path.split(".")
    for part in parts[:-1]:
        nested = target[part]
        assert isinstance(nested, dict)
        target = nested
    target[parts[-1]] = value


def _units(value: object) -> int:
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, (str, list, tuple, dict, set)):
        return len(value)
    return 1


def _proves_work(contract: WorkProofContract, payload: dict[str, object]) -> bool:
    if contract.kind == "constant":
        return contract.minimum_when_applicable == 0
    if (
        contract.applicability_field is not None
        and _units(_field(payload, contract.applicability_field)) == 0
    ):
        return True
    assert contract.processed_field is not None
    return _units(_field(payload, contract.processed_field)) >= contract.minimum_when_applicable


def _contract(name: str) -> WorkProofContract:
    return next(spec.work_proof for spec in tool_specs() if spec.name == name)


def test_every_mcp_tool_declares_valid_work_proof() -> None:
    specs = tool_specs()

    assert specs
    assert set(WORK_PROOFS) == {spec.name for spec in specs}
    assert all(
        spec.work_proof.kind in {"constant", "rows", "sources", "evidence", "job"} for spec in specs
    )
    assert all(spec.work_proof.minimum_when_applicable >= 0 for spec in specs)
    assert {name for name, contract in WORK_PROOFS.items() if contract == CONSTANT_STATUS} == {
        "usage_status",
        "usage_doctor",
        "usage_dedupe_diagnostics",
        "usage_allowance_status",
    }


@pytest.mark.parametrize(
    ("name", "payload"),
    [
        ("usage_evidence", {"result": {"records": [{"evidence_id": "call:1"}]}}),
        ("usage_job_status", {"result": {"job_id": "job-1"}}),
        ("usage_calls", {"total_matched_rows": 1, "rows": [{"record_id": "call-1"}]}),
        ("usage_source_coverage", {"source_file_count": 1, "rows": [{"source": "cli"}]}),
        (
            "usage_compression_candidates",
            {"pagination": {"total": 1}, "candidates": [{"candidate_id": "candidate-1"}]},
        ),
        (
            "usage_visualization_render",
            {"evidence": {"row_count": 1, "rows": [{"record_id": "call-1"}]}},
        ),
        ("generate_usage_dashboard", {"dashboard_path": "/tmp/dashboard.html"}),
        ("export_usage_csv", {"rows": 1, "csv_path": "/tmp/usage.csv"}),
        ("update_usage_pricing_config", {"model_count": 1}),
        ("usage_dogfood_result", {"schema": "codex-usage-tracker-agentic-dogfood-v1"}),
    ],
)
def test_semantic_family_contracts_match_real_json_shapes(
    name: str,
    payload: dict[str, object],
) -> None:
    contract = _contract(name)

    assert _proves_work(contract, payload)
    assert contract.processed_field is not None
    false_green = deepcopy(payload)
    _set_field(false_green, contract.processed_field, 0)
    assert not _proves_work(contract, false_green)


def test_query_over_known_rows_cannot_claim_zero_matched_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)
    payload = build_usage_query(
        entity="call",
        measures=["tokens"],
        limit=1,
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
    )
    contract = _contract("usage_query")

    assert _proves_work(contract, payload)
    false_green = deepcopy(payload)
    result = false_green["result"]
    assert isinstance(result, dict)
    assert int(result["total_matched"]) > 0
    result["rows"] = []
    assert not _proves_work(contract, false_green)


def test_refresh_with_changed_source_cannot_claim_zero_scanned_files(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text("{}\n", encoding="utf-8")
    db_path = tmp_path / "usage.sqlite3"
    _seed(db_path)

    def planner(*_args: object, **_kwargs: object) -> RefreshPlan:
        assert source.exists()
        return RefreshPlan("sync", "untracked_source", 1, source.stat().st_size)

    def refresh_fn(**_kwargs: Any) -> RefreshResult:
        return RefreshResult(
            scanned_files=1,
            parsed_events=1,
            inserted_or_updated_events=1,
            db_path=str(db_path),
        )

    outcome = refresh_usage(
        RefreshRequest(execution="sync"),
        codex_home=tmp_path / ".codex",
        db_path=db_path,
        pricing_path=tmp_path / "pricing.json",
        refresh_fn=refresh_fn,
        planner=planner,
    )
    payload: dict[str, object] = {"result": outcome.result or {}}
    contract = _contract("usage_refresh")

    assert _proves_work(contract, payload)
    false_green = deepcopy(payload)
    result = false_green["result"]
    assert isinstance(result, dict)
    refresh = result["refresh"]
    assert isinstance(refresh, dict)
    refresh["scanned_files"] = 0
    assert not _proves_work(contract, false_green)


def test_status_allows_constant_size_work() -> None:
    assert _proves_work(_contract("usage_status"), {"result": {}})
