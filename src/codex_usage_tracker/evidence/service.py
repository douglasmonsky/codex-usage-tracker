"""Pure canonical evidence selection over an injected aggregate repository."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from typing import Protocol

from codex_usage_tracker.core.contracts import EvidenceV1
from codex_usage_tracker.core.dashboard_targets import build_dashboard_target_v2
from codex_usage_tracker.evidence.models import (
    EvidenceAmbiguityError,
    EvidenceNotFoundError,
    EvidenceRequest,
    EvidenceResult,
)


class EvidenceRepository(Protocol):
    def source_revision(self) -> str | None: ...
    def call(self, selector_id: str, history: str) -> EvidenceV1 | None: ...
    def thread_summary(self, selector_id: str, history: str) -> EvidenceV1 | None: ...
    def thread_calls(
        self, selector_id: str, history: str, limit: int, cursor: str | None
    ) -> tuple[tuple[EvidenceV1, ...], str | None]: ...
    def allowance(self, selector_id: str, history: str) -> EvidenceV1 | None: ...
    def completed_analyses(self) -> tuple[Mapping[str, object], ...]: ...


def resolve_evidence(request: EvidenceRequest, repository: EvidenceRepository) -> EvidenceResult:
    """Resolve one exact selector without fabricating records for a miss."""
    analysis_id: str | None = None
    subject: Mapping[str, object] | None = None
    if request.selector_kind == "call":
        _no_cursor(request)
        record = repository.call(request.selector_id, request.history)
        records, cursor = (() if record is None else (record,)), None
    elif request.selector_kind == "thread" and request.section == "summary":
        _no_cursor(request)
        record = repository.thread_summary(request.selector_id, request.history)
        records, cursor = (() if record is None else (record,)), None
    elif request.selector_kind == "thread":
        records, cursor = repository.thread_calls(
            request.selector_id, request.history, request.limit, request.cursor
        )
    elif request.selector_kind == "allowance":
        _no_cursor(request)
        record = repository.allowance(request.selector_id, request.history)
        records, cursor = (() if record is None else (record,)), None
    else:
        records, cursor, analysis_id, subject = _analysis_records(
            request, repository.completed_analyses(), repository.source_revision()
        )
    if not records:
        raise EvidenceNotFoundError(
            f"{request.selector_kind} evidence not found: {request.selector_id}"
        )
    target = build_dashboard_target_v2(
        evidence_kind=request.selector_kind,
        selector_id=request.selector_id,
        history=request.history,
        analysis_id=analysis_id,
    )
    selector = {
        "kind": request.selector_kind,
        "id": request.selector_id,
        "section": request.section,
    }
    if request.selector_kind == "finding" and analysis_id is not None:
        selector["analysis_id"] = analysis_id
    return EvidenceResult(
        selector=selector,
        records=tuple(records[: request.limit]),
        next_cursor=cursor,
        dashboard_target=target,
        subject=subject,
    )


def _analysis_records(
    request: EvidenceRequest,
    reports: tuple[Mapping[str, object], ...],
    source_revision: str | None,
) -> tuple[
    tuple[EvidenceV1, ...],
    str | None,
    str | None,
    Mapping[str, object] | None,
]:
    matches = [report for report in reports if _matches(report, request)]
    if len(matches) > 1:
        raise EvidenceAmbiguityError(
            "finding evidence matches multiple analyses; provide an exact analysis_id"
        )
    if not matches:
        return (), None, None, None
    report = matches[0]
    raw_evidence = report.get("evidence")
    if not isinstance(raw_evidence, (list, tuple)):
        return (), None, None, None
    allowed = None
    if request.selector_kind == "finding":
        allowed = _finding_evidence_ids(report, request.selector_id)
    records = sorted(
        (
            item
            for item in raw_evidence
            if isinstance(item, EvidenceV1) and (allowed is None or item.evidence_id in allowed)
        ),
        key=lambda item: item.evidence_id,
    )
    last_id = _decode_cursor(request, source_revision) if request.cursor else None
    if last_id is not None:
        records = [item for item in records if item.evidence_id > last_id]
    page = tuple(records[: request.limit])
    next_cursor = (
        _encode_cursor(request, source_revision, page[-1].evidence_id)
        if len(records) > request.limit and page
        else None
    )
    analysis_id = report.get("analysis_id")
    resolved_analysis_id = analysis_id if isinstance(analysis_id, str) else None
    return (
        page,
        next_cursor,
        resolved_analysis_id,
        _analysis_subject(report, request, resolved_analysis_id),
    )


def _analysis_subject(
    report: Mapping[str, object],
    request: EvidenceRequest,
    analysis_id: str | None,
) -> Mapping[str, object] | None:
    if request.selector_kind == "finding":
        findings = report.get("findings")
        if not isinstance(findings, (list, tuple)):
            return None
        for item in findings:
            if isinstance(item, Mapping) and item.get("finding_id") == request.selector_id:
                return {**item, "analysis_id": analysis_id}
        return None
    if request.selector_kind == "analysis":
        return {
            key: report[key]
            for key in ("analysis_id", "goal", "summary", "methodology")
            if key in report
        }
    return None


def _matches(report: Mapping[str, object], request: EvidenceRequest) -> bool:
    if request.selector_kind == "analysis":
        return report.get("analysis_id") == request.selector_id
    if request.analysis_id is not None and report.get("analysis_id") != request.analysis_id:
        return False
    return bool(_finding_evidence_ids(report, request.selector_id))


def _finding_evidence_ids(report: Mapping[str, object], finding_id: str) -> set[str]:
    findings = report.get("findings")
    if not isinstance(findings, (list, tuple)):
        return set()
    for item in findings:
        if isinstance(item, Mapping) and item.get("finding_id") == finding_id:
            ids = item.get("evidence_ids")
            return {str(value) for value in ids} if isinstance(ids, (list, tuple)) else set()
    return set()


def _no_cursor(request: EvidenceRequest) -> None:
    if request.cursor is not None:
        raise ValueError(f"cursor is not supported for {request.selector_kind} evidence")


def _cursor_fingerprint(request: EvidenceRequest) -> str:
    payload = {
        "kind": request.selector_kind,
        "id": request.selector_id,
        "section": request.section,
        "history": request.history,
        "limit": request.limit,
        "analysis_id": request.analysis_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _encode_cursor(request: EvidenceRequest, revision: str | None, evidence_id: str) -> str:
    payload = {"v": 1, "f": _cursor_fingerprint(request), "r": revision, "i": evidence_id}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def _decode_cursor(request: EvidenceRequest, revision: str | None) -> str:
    if request.cursor is None:
        raise ValueError("cursor is required")
    try:
        padding = "=" * (-len(request.cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(request.cursor + padding))
    except Exception as exc:  # noqa: BLE001 - transport gets a concise cursor error.
        raise ValueError("cursor is malformed") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("v") != 1
        or not isinstance(payload.get("i"), str)
    ):
        raise ValueError("cursor is malformed")
    if payload.get("f") != _cursor_fingerprint(request):
        raise ValueError("cursor does not match evidence scope")
    if payload.get("r") != revision:
        raise ValueError("cursor is stale for the current source revision")
    return str(payload["i"])
