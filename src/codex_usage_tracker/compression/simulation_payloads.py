"""Compact public payload for overlap-aware Compression Lab simulations."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from codex_usage_tracker.compression.payloads import compression_envelope
from codex_usage_tracker.compression.simulator import SimulationResult

SIMULATION_BUDGET_BYTES = 16 * 1024


def compression_simulation_payload(
    run: Mapping[str, Any],
    result: SimulationResult,
    *,
    max_bytes: int = SIMULATION_BUDGET_BYTES,
) -> dict[str, Any]:
    """Build a bounded simulation payload while preserving portfolio totals."""
    result_payload = result.as_dict()
    groups = list(result_payload.pop("groups"))
    verification_plan = list(result_payload.pop("verification_plan"))
    payload = compression_envelope(run, kind="simulation")
    payload.update(
        {
            "stale": False,
            "content_mode": "aggregate",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "simulation": result_payload,
            "calculation_trace": _trace_page(groups),
            "verification_plan": _page(verification_plan),
            "next": _simulation_next(result.selected_candidate_ids),
        }
    )
    _trim_simulation_payload(payload, max_bytes)
    return payload


def _trim_simulation_payload(payload: dict[str, Any], max_bytes: int) -> None:
    for key in ("calculation_trace", "verification_plan"):
        page = payload[key]
        rows = page["rows"]
        while rows and _json_size(payload) > max_bytes:
            rows.pop()
        _finalize_page(page)
    candidates = payload["simulation"]["candidates"]
    requested = len(candidates)
    payload["simulation"]["candidate_results"] = {
        "requested": requested,
        "returned": requested,
        "truncated": False,
    }
    while candidates and _json_size(payload) > max_bytes:
        candidates.pop()
    payload["simulation"]["candidate_results"].update(
        returned=len(candidates),
        truncated=len(candidates) < requested,
    )
    payload["payload_truncated"] = bool(
        payload.get("payload_truncated")
        or payload["calculation_trace"]["truncated"]
        or payload["verification_plan"]["truncated"]
        or len(candidates) < requested
    )


def _page(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "returned": len(rows),
        "truncated": False,
        "rows": rows,
    }


def _trace_page(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_groups": len(rows),
        "returned_groups": len(rows),
        "truncated": False,
        "rows": rows,
    }


def _finalize_page(page: dict[str, Any]) -> None:
    if "total_groups" in page:
        page["returned_groups"] = len(page["rows"])
        page["truncated"] = page["returned_groups"] < page["total_groups"]
        return
    page["returned"] = len(page["rows"])
    page["truncated"] = page["returned"] < page["total"]


def _simulation_next(candidate_ids: tuple[str, ...]) -> dict[str, Any]:
    arguments = {"candidate_id": candidate_ids[0]} if candidate_ids else {}
    return {"tool": "usage_compression_candidate_detail", "arguments": arguments}


def _json_size(payload: Mapping[str, Any]) -> int:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
