"""Validated application API for overlap-aware compression simulations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from codex_usage_tracker.compression.detector_registry import DETECTOR_SET_VERSION
from codex_usage_tracker.compression.models import CompressionScope
from codex_usage_tracker.compression.payloads import compression_error_payload
from codex_usage_tracker.compression.request import prepare_compression_request
from codex_usage_tracker.compression.simulation_payloads import (
    SIMULATION_BUDGET_BYTES,
    compression_simulation_payload,
)
from codex_usage_tracker.compression.simulator import simulate_candidate_portfolio
from codex_usage_tracker.store.compression_candidates import get_compression_candidate
from codex_usage_tracker.store.compression_capacities import (
    load_record_component_capacities,
)
from codex_usage_tracker.store.compression_runs import get_compression_run

MAX_SIMULATION_CANDIDATES = 50
_COMPLETED_STATUSES = frozenset({"completed", "completed_with_warnings"})


def compression_simulate(
    db_path: Path,
    *,
    run_id: str,
    candidate_ids: Sequence[str],
    max_payload_bytes: int = SIMULATION_BUDGET_BYTES,
) -> dict[str, Any]:
    """Validate and simulate one explicit persisted candidate portfolio."""
    run = get_compression_run(db_path, run_id=run_id)
    if run is None:
        return _missing_run(run_id)
    if run["status"] not in _COMPLETED_STATUSES:
        return compression_error_payload(
            kind="simulation",
            code="compression_run_not_complete",
            message="Simulation is available after the compression run completes.",
            next_tool="usage_compression_status",
            next_arguments={"run_id": run_id},
            run=run,
        )
    selected, error = _validate_selection(candidate_ids)
    if error is not None:
        return _selection_error(run, run_id, **error)
    records, unknown_ids, foreign_ids = _load_candidates(db_path, run_id, selected)
    if unknown_ids or foreign_ids:
        return _selection_error(
            run,
            run_id,
            reason="unknown_or_foreign",
            unknown_candidate_ids=unknown_ids,
            foreign_candidate_ids=foreign_ids,
        )
    stale, refresh_arguments = _stale_state(db_path, run)
    if stale:
        return compression_error_payload(
            kind="simulation",
            code="compression_run_stale",
            message="Refresh the same compression scope before simulating candidates.",
            next_tool="usage_compression_start",
            next_arguments=refresh_arguments,
            run=run,
        )
    capacities = load_record_component_capacities(db_path, _record_ids(records))
    try:
        result = simulate_candidate_portfolio(records, capacities)
    except ValueError:
        return compression_error_payload(
            kind="simulation",
            code="compression_capacity_unavailable",
            message="Detector-ready capacity is incomplete; refresh analysis and retry.",
            next_tool="usage_compression_start",
            next_arguments=refresh_arguments,
            run=run,
        )
    return compression_simulation_payload(
        run,
        result,
        max_bytes=max_payload_bytes,
    )


def _validate_selection(
    candidate_ids: Sequence[str],
) -> tuple[tuple[str, ...], dict[str, Any] | None]:
    selected = tuple(str(candidate_id) for candidate_id in candidate_ids)
    if not selected:
        return selected, {"reason": "empty"}
    if len(selected) > MAX_SIMULATION_CANDIDATES:
        return selected, {
            "reason": "over_limit",
            "maximum_candidate_count": MAX_SIMULATION_CANDIDATES,
        }
    if len(set(selected)) != len(selected):
        return selected, {"reason": "duplicate"}
    if any(not candidate_id for candidate_id in selected):
        return selected, {"reason": "empty_id"}
    return tuple(sorted(selected)), None


def _load_candidates(
    db_path: Path,
    run_id: str,
    candidate_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    records: list[dict[str, Any]] = []
    unknown: list[str] = []
    foreign: list[str] = []
    for candidate_id in candidate_ids:
        candidate = get_compression_candidate(db_path, candidate_id=candidate_id)
        if candidate is None:
            unknown.append(candidate_id)
        elif str(candidate.get("run_id") or "") != run_id:
            foreign.append(candidate_id)
        else:
            records.append(candidate)
    return records, unknown[:16], foreign[:16]


def _selection_error(
    run: Mapping[str, Any],
    run_id: str,
    *,
    reason: str,
    **details: Any,
) -> dict[str, Any]:
    return compression_error_payload(
        kind="simulation",
        code="invalid_candidate_selection",
        message="Select unique candidates from one completed compression run.",
        next_tool="usage_compression_candidates",
        next_arguments={"run_id": run_id},
        run=run,
        details={"reason": reason, **details},
    )


def _missing_run(run_id: str) -> dict[str, Any]:
    return compression_error_payload(
        kind="simulation",
        code="compression_run_not_found",
        message="No persisted compression run matched that ID.",
        next_tool="usage_compression_start",
        next_arguments={},
        details={"requested_run_id": run_id},
    )


def _stale_state(
    db_path: Path,
    run: Mapping[str, Any],
) -> tuple[bool, dict[str, Any]]:
    known, families = _run_detector_families(run)
    refresh_arguments = _refresh_arguments(run, families)
    if not known:
        return True, refresh_arguments
    try:
        current = prepare_compression_request(
            db_path,
            _run_scope(run),
            detector_families=families,
        )
    except ValueError:
        return True, refresh_arguments
    return current.revision_key != str(run.get("revision_key") or ""), refresh_arguments


def _run_detector_families(
    run: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...] | None]:
    version = str(run.get("detector_set_version") or "")
    if version == DETECTOR_SET_VERSION:
        return True, None
    prefix = f"{DETECTOR_SET_VERSION}:"
    if not version.startswith(prefix):
        return False, None
    families = tuple(family for family in version[len(prefix) :].split(",") if family)
    return True, families


def _run_scope(run: Mapping[str, Any]) -> CompressionScope:
    scope = run.get("scope")
    values = dict(scope) if isinstance(scope, Mapping) else {}
    return CompressionScope(
        since=_optional_text(values.get("since")),
        until=_optional_text(values.get("until")),
        thread=_optional_text(values.get("thread")),
        include_archived=bool(values.get("include_archived")),
        model=_optional_text(values.get("model")),
        effort=_optional_text(values.get("effort")),
    )


def _refresh_arguments(
    run: Mapping[str, Any],
    families: tuple[str, ...] | None,
) -> dict[str, Any]:
    scope = _run_scope(run)
    arguments = {"refresh": True, **scope.as_dict()}
    if families is not None:
        arguments["detector_families"] = list(families)
    return arguments


def _record_ids(records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(claim.get("record_id") or "")
                for record in records
                for claim in record.get("claims") or []
                if isinstance(claim, Mapping) and claim.get("record_id")
            }
        )
    )


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)
