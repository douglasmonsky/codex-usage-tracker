"""Compact public payload contracts for Compression Lab tools."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from codex_usage_tracker.compression.detector_registry import DETECTOR_SET_VERSION
from codex_usage_tracker.compression.estimators import ESTIMATOR_POLICY_V1
from codex_usage_tracker.compression.request import COMPRESSION_SCHEMA_VERSION

COMPRESSION_API_SCHEMA = "codex-usage-tracker-compression-api-v1"
STATUS_BUDGET_BYTES = 4 * 1024
PROFILE_BUDGET_BYTES = 8 * 1024
CANDIDATE_PAGE_BUDGET_BYTES = 16 * 1024
CANDIDATE_DETAIL_BUDGET_BYTES = 24 * 1024
_ACTIVE_STATUSES = frozenset({"pending", "running"})
_DEFAULT_CAVEATS = [
    "Savings are heuristic ranges, not an OpenAI usage ledger.",
    "Observed exposure is not automatically avoidable waste.",
]


def compression_status_payload(run: Mapping[str, Any]) -> dict[str, Any]:
    payload = compression_envelope(run, kind="status")
    payload.update(
        {
            "progress": _status_progress(run),
            "error": dict(run.get("error_summary") or {}) or None,
            "next": _status_next(run),
        }
    )
    _trim_status_payload(payload)
    return payload


def compression_profile_payload(run: Mapping[str, Any]) -> dict[str, Any]:
    payload = compression_envelope(run, kind="profile")
    profile = dict(run.get("public_profile") or {})
    payload["profile"] = profile
    canonical_run_id = str(profile.get("run_id") or run.get("run_id") or "")
    if canonical_run_id != str(run.get("run_id") or ""):
        payload["result_run_id"] = canonical_run_id
    payload["next"] = {
        "tool": "usage_compression_candidates",
        "arguments": {"run_id": canonical_run_id},
    }
    return _trim_profile(payload)


def compression_candidate_page_payload(
    run: Mapping[str, Any],
    page: Mapping[str, Any],
    *,
    max_bytes: int | None,
) -> dict[str, Any]:
    payload = compression_envelope(run, kind="candidate_page")
    source_rows = [dict(row) for row in page.get("rows") or []]
    source_count = len(source_rows)
    payload["candidates"] = [dict(row) for row in source_rows]
    payload["pagination"] = _candidate_pagination(page, source_count)
    arguments = {"candidate_id": source_rows[0]["candidate_id"]} if source_rows else {}
    payload["next"] = {"tool": "usage_compression_candidate_detail", "arguments": arguments}
    if max_bytes is not None:
        _enforce_candidate_budget(payload, source_rows, max_bytes)
    _finalize_candidate_pagination(payload, page, source_count)
    return payload


def compression_candidate_detail_payload(
    run: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    evidence_mode: str,
    claims: Sequence[Mapping[str, Any]],
    evidence: Sequence[Mapping[str, Any]],
    max_bytes: int = CANDIDATE_DETAIL_BUDGET_BYTES,
) -> dict[str, Any]:
    payload = compression_envelope(run, kind="candidate_detail")
    compact_candidate = {
        key: value for key, value in candidate.items() if key not in {"claims", "evidence_handles"}
    }
    evidence_rows = [dict(row) for row in evidence]
    payload.update(
        {
            "candidate": compact_candidate,
            "evidence_mode": evidence_mode,
            "claims": [dict(row) for row in claims],
            "evidence": evidence_rows,
            "evidence_pagination": {
                "requested": len(evidence_rows),
                "returned": len(evidence_rows),
                "truncated": False,
            },
            "payload_truncated": bool(payload.get("payload_truncated")),
            "next": {
                "tool": "usage_compression_candidates",
                "arguments": {"run_id": str(run.get("run_id") or "")},
            },
        }
    )
    payload.update(_detail_content_flags(evidence_mode, evidence_rows))
    original_evidence = len(evidence_rows)
    _trim_rows_to_budget(payload, "evidence", max_bytes)
    _trim_rows_to_budget(payload, "claims", max_bytes)
    _finalize_candidate_detail(payload, compact_candidate, original_evidence, max_bytes)
    return payload


def _status_progress(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "percent": float(run.get("progress_percent") or 0),
        "stage": str(run.get("stage") or run.get("status") or "pending"),
        "current_detector": run.get("current_detector"),
        "completed_detectors": int(run.get("completed_detectors") or 0),
        "total_detectors": int(run.get("total_detectors") or 0),
        "records_examined": int(run.get("records_examined") or 0),
        "candidate_count": int(
            _public_profile(run).get("candidate_count") or run.get("candidate_count") or 0
        ),
    }


def _trim_status_payload(payload: dict[str, Any]) -> None:
    if _json_size(payload) > STATUS_BUDGET_BYTES:
        payload["warnings"] = payload["warnings"][:3]
        payload["caveats"] = payload["caveats"][:2]
        payload["payload_truncated"] = True


def _candidate_pagination(page: Mapping[str, Any], source_count: int) -> dict[str, Any]:
    return {
        "total": int(page.get("total") or 0),
        "offset": int(page.get("offset") or 0),
        "requested_limit": page.get("limit"),
        "returned": source_count,
        "truncated": bool(page.get("truncated")),
        "next_offset": None,
    }


def _enforce_candidate_budget(
    payload: dict[str, Any],
    source_rows: Sequence[Mapping[str, Any]],
    max_bytes: int,
) -> None:
    _trim_rows_to_budget(payload, "candidates", max_bytes)
    if source_rows and not payload["candidates"]:
        payload["candidates"] = [_compact_candidate(source_rows[0])]
        if _json_size(payload) > max_bytes:
            candidate_id = str(source_rows[0].get("candidate_id") or "")
            payload["candidates"] = [{"candidate_id": candidate_id}]
        if _json_size(payload) > max_bytes:
            payload["candidates"] = []


def _finalize_candidate_pagination(
    payload: dict[str, Any], page: Mapping[str, Any], source_count: int
) -> None:
    pagination = payload["pagination"]
    returned = len(payload["candidates"])
    truncated = bool(page.get("truncated")) or returned < source_count
    consumed = returned or (1 if source_count else 0)
    pagination["returned"] = returned
    pagination["truncated"] = truncated
    pagination["next_offset"] = pagination["offset"] + consumed if truncated else None
    if returned < source_count:
        payload["payload_truncated"] = True


def _detail_content_flags(
    evidence_mode: str, evidence_rows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    if evidence_mode == "excerpts":
        return {
            "content_mode": "excerpts",
            "includes_indexed_content": bool(evidence_rows),
            "includes_raw_fragments": any(
                bool(row.get("includes_raw_fragment")) for row in evidence_rows
            ),
        }
    return {
        "content_mode": evidence_mode,
        "includes_indexed_content": False,
        "includes_raw_fragments": False,
    }


def _finalize_candidate_detail(
    payload: dict[str, Any],
    compact_candidate: Mapping[str, Any],
    original_evidence: int,
    max_bytes: int,
) -> None:
    returned = len(payload["evidence"])
    payload["evidence_pagination"] = {
        "requested": original_evidence,
        "returned": returned,
        "truncated": returned < original_evidence,
    }
    if _json_size(payload) <= max_bytes:
        return
    payload["candidate"] = {
        key: compact_candidate[key]
        for key in (
            "candidate_id",
            "run_id",
            "family",
            "rank",
            "confidence",
            "observed_exposure_tokens",
            "gross_estimate",
            "adjusted_estimate",
        )
        if key in compact_candidate
    }
    payload["payload_truncated"] = True


def compression_error_payload(
    *,
    kind: str,
    code: str,
    message: str,
    next_tool: str,
    next_arguments: Mapping[str, Any] | None = None,
    run: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if run is not None:
        payload = compression_envelope(run, kind=kind)
        payload["status"] = "error"
    else:
        payload = {
            "schema": COMPRESSION_API_SCHEMA,
            "kind": kind,
            "versions": {
                "compression_schema": COMPRESSION_SCHEMA_VERSION,
                "detector_set": DETECTOR_SET_VERSION,
                "estimator": ESTIMATOR_POLICY_V1.version,
            },
            "run_id": None,
            "status": "error",
            "source_revision": "",
            "scope": {},
            "filters": {},
            "include_archived": False,
            "coverage": {},
            "timing": {},
            "cache": {"reused": False, "mode": None, "request_reused": "none"},
            "content_mode": "none",
            "includes_indexed_content": False,
            "includes_raw_fragments": False,
            "warnings": [],
            "caveats": list(_DEFAULT_CAVEATS),
            "payload_truncated": False,
        }
    payload["error"] = {"code": code, "message": message, **dict(details or {})}
    payload["next"] = {"tool": next_tool, "arguments": dict(next_arguments or {})}
    return payload


def compression_envelope(run: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    """Build the stable common envelope shared by Compression Lab responses."""
    public_profile = _public_profile(run)
    raw_mappings, compact_mappings = _envelope_mappings(run, public_profile)
    payload = {
        "schema": COMPRESSION_API_SCHEMA,
        "kind": kind,
        **_run_metadata(run),
        "scope": compact_mappings["scope"],
        "filters": compact_mappings["filters"],
        "include_archived": bool(compact_mappings["scope"].get("include_archived")),
        "coverage": compact_mappings["coverage"],
        "timing": compact_mappings["timing"],
        "cache": _cache_payload(run, public_profile),
        **_public_metadata(public_profile),
        "includes_raw_fragments": False,
    }
    payload["payload_truncated"] = any(
        compact_mappings[key] != raw_value for key, raw_value in raw_mappings.items()
    )
    return payload


def _run_metadata(run: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "versions": {
            "compression_schema": int(run.get("compression_schema_version") or 1),
            "detector_set": str(run.get("detector_set_version") or ""),
            "estimator": str(run.get("estimator_version") or ""),
        },
        "run_id": str(run.get("run_id") or ""),
        "status": str(run.get("status") or "unknown"),
        "source_revision": str(run.get("source_revision") or ""),
    }


def _envelope_mappings(
    run: Mapping[str, Any],
    public_profile: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    raw_mappings = {
        "scope": dict(run.get("scope") or {}),
        "filters": dict(run.get("filters") or {}),
        "coverage": dict(public_profile.get("coverage") or run.get("coverage") or {}),
        "timing": dict(run.get("timing") or {}),
    }
    compact_mappings = {key: _compact_mapping(value) for key, value in raw_mappings.items()}
    return raw_mappings, compact_mappings


def _cache_payload(run: Mapping[str, Any], public_profile: Mapping[str, Any]) -> dict[str, Any]:
    cache = public_profile.get("cache")
    cache_mapping = cache if isinstance(cache, Mapping) else {}
    return {
        "reused": bool(
            run.get("cache_reused")
            or cache_mapping.get("reused")
            or run.get("request_reused") in {"active", "completed"}
        ),
        "mode": cache_mapping.get("mode"),
        "request_reused": str(run.get("request_reused") or "none"),
    }


def _public_metadata(public_profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "content_mode": str(public_profile.get("content_mode") or "aggregate"),
        "includes_indexed_content": bool(public_profile.get("includes_indexed_content")),
        "warnings": [_compact_mapping(dict(row)) for row in public_profile.get("warnings") or []][
            :10
        ],
        "caveats": [
            _bounded_text(value) for value in public_profile.get("caveats") or _DEFAULT_CAVEATS
        ][:10],
    }


def _status_next(run: Mapping[str, Any]) -> dict[str, Any]:
    run_id = str(run.get("run_id") or "")
    status = str(run.get("status") or "")
    if status in _ACTIVE_STATUSES:
        return {
            "tool": "usage_compression_status",
            "arguments": {"run_id": run_id},
            "poll_after_ms": int(run.get("next_poll_ms") or 250),
        }
    if status in {"completed", "completed_with_warnings"}:
        return {"tool": "usage_compression_profile", "arguments": {"run_id": run_id}}
    return {"tool": "usage_compression_start", "arguments": {}}


def _trim_profile(payload: dict[str, Any]) -> dict[str, Any]:
    if _json_size(payload) <= PROFILE_BUDGET_BYTES:
        return payload
    profile = payload.get("profile")
    if not isinstance(profile, dict):
        return payload
    for key in ("top_candidate_ids", "families", "warnings", "caveats"):
        value = profile.get(key)
        if not isinstance(value, list):
            continue
        while value and _json_size(payload) > PROFILE_BUDGET_BYTES:
            value.pop()
            payload["payload_truncated"] = True
    if _json_size(payload) > PROFILE_BUDGET_BYTES:
        payload["profile"] = {
            key: profile[key]
            for key in (
                "schema",
                "run_id",
                "status",
                "candidate_count",
                "observed_exposure",
                "portfolio_estimate",
                "cache",
                "duration_ms",
                "content_mode",
                "includes_indexed_content",
                "includes_raw_fragments",
            )
            if key in profile
        }
        payload["payload_truncated"] = True
    return payload


def _trim_rows_to_budget(payload: dict[str, Any], key: str, max_bytes: int) -> None:
    rows = payload.get(key)
    if not isinstance(rows, list):
        return
    while rows and _json_size(payload) > max_bytes:
        rows.pop()


def _compact_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: candidate[key]
        for key in (
            "candidate_id",
            "run_id",
            "family",
            "rank",
            "confidence_grade",
            "confidence_score",
            "observed_exposure_tokens",
            "gross_estimate",
            "adjusted_estimate",
        )
        if key in candidate
    }


def _json_size(payload: Mapping[str, Any]) -> int:
    return len(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _public_profile(run: Mapping[str, Any]) -> Mapping[str, Any]:
    profile = run.get("public_profile")
    return profile if isinstance(profile, Mapping) else {}


def _compact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        _bounded_text(key, max_chars=64): _compact_value(item, depth=1)
        for key, item in list(value.items())[:16]
    }


def _compact_value(value: Any, *, depth: int) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _bounded_text(value)
    if isinstance(value, Mapping) and depth < 2:
        return {
            _bounded_text(key, max_chars=64): _compact_value(item, depth=depth + 1)
            for key, item in list(value.items())[:16]
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_compact_value(item, depth=depth + 1) for item in list(value)[:16]]
    return _bounded_text(value)


def _bounded_text(value: Any, *, max_chars: int = 256) -> str:
    text = str(value)
    return text if len(text) <= max_chars else f"{text[: max_chars - 3]}..."
