"""Bounded HTTP adapter for the canonical evidence application service."""

from __future__ import annotations

from collections.abc import Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs

from codex_usage_tracker.application.context import build_request_context
from codex_usage_tracker.application.evidence import get_evidence
from codex_usage_tracker.application.requests import HistoryScope, RequestScope
from codex_usage_tracker.core.contracts import enforce_payload_budget, envelope_payload
from codex_usage_tracker.evidence.models import (
    EvidenceAmbiguityError,
    EvidenceHistoryMismatchError,
    EvidenceNotFoundError,
    EvidenceRequest,
)
from codex_usage_tracker.jobs.service import JobService

MAX_EVIDENCE_PAYLOAD_BYTES = 128 * 1024
_ALLOWED_PARAMS = {
    "selector_kind",
    "selector_id",
    "section",
    "limit",
    "cursor",
    "history",
    "analysis_id",
}


def _one(params: dict[str, list[str]], name: str, default: str | None = None) -> str | None:
    values = params.get(name)
    if values is None:
        return default
    if len(values) != 1 or not values[0]:
        raise ValueError(f"{name} must be provided exactly once")
    return values[0]


def evidence_payload(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    history_default: str = "active",
    job_service: JobService | None = None,
) -> dict[str, object]:
    """Resolve one exact selector into the shared bounded evidence envelope."""
    params = parse_qs(query, keep_blank_values=True)
    unsupported = sorted(set(params) - _ALLOWED_PARAMS)
    if unsupported:
        raise ValueError(f"unsupported evidence parameter: {unsupported[0]}")
    selector_kind = _one(params, "selector_kind")
    selector_id = _one(params, "selector_id")
    if selector_kind is None or selector_id is None:
        raise ValueError("selector_kind and selector_id are required")
    limit_value = _one(params, "limit", "20")
    assert limit_value is not None
    try:
        limit = int(limit_value)
    except ValueError as exc:
        raise ValueError("limit must be an integer") from exc
    history = _one(params, "history", history_default)
    assert history is not None
    request = EvidenceRequest(
        selector_kind=cast(Any, selector_kind),
        selector_id=selector_id,
        section=_one(params, "section", "summary") or "summary",
        limit=limit,
        cursor=_one(params, "cursor"),
        history=cast(Any, history),
        analysis_id=_one(params, "analysis_id"),
    )
    scope = RequestScope(
        history=cast(HistoryScope, request.history),
        thread_key=request.selector_id if request.selector_kind == "thread" else None,
    )
    context = build_request_context(db_path=db_path, pricing_path=pricing_path, scope=scope)
    result = get_evidence(
        request,
        db_path=db_path,
        pricing_path=pricing_path,
        job_service=job_service,
        context=context,
    )
    payload = envelope_payload(
        tool="usage_evidence",
        result_schema=result.schema,
        result=result,
        scope=context.scope,
        freshness=context.freshness,
        accounting=context.accounting,
        data_class="aggregate",
        dashboard_targets=(result.dashboard_target,),
    )
    enforce_payload_budget(payload, MAX_EVIDENCE_PAYLOAD_BYTES, "usage_evidence")
    return payload


def handle_evidence_request(
    query: str,
    *,
    db_path: Path,
    pricing_path: Path,
    history_default: str,
    send_error: Callable[..., None],
    send_exception: Callable[[str, BaseException], None],
    send_json: Callable[[HTTPStatus, dict[str, object]], None],
) -> None:
    """Send a recoverable HTTP response for an evidence request."""
    try:
        payload = evidence_payload(
            query,
            db_path=db_path,
            pricing_path=pricing_path,
            history_default=history_default,
        )
    except EvidenceHistoryMismatchError as exc:
        send_error(
            HTTPStatus.NOT_FOUND,
            str(exc),
            code="evidence_history_mismatch",
            next_action="Retry with history=all to include archived evidence.",
        )
        return
    except EvidenceNotFoundError as exc:
        send_error(HTTPStatus.NOT_FOUND, str(exc), code="evidence_not_found")
        return
    except EvidenceAmbiguityError as exc:
        send_error(HTTPStatus.CONFLICT, str(exc), code="evidence_ambiguous")
        return
    except ValueError as exc:
        send_error(HTTPStatus.BAD_REQUEST, str(exc), code="invalid_evidence_request")
        return
    except Exception as exc:  # pragma: no cover - defensive transport boundary
        send_exception("Unable to resolve evidence", exc)
        return
    send_json(HTTPStatus.OK, payload)
