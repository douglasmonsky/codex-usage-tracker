"""Persistent incremental-cache helpers for Compression Lab runs."""

from __future__ import annotations

import hashlib
import zlib
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Protocol, TypeVar, cast

from codex_usage_tracker.compression.evidence import (
    CallEvidence,
    CommandRunEvidence,
    CompressionEvidenceSnapshot,
    ContentFragmentEvidence,
    FileEventEvidence,
    ToolCallEvidence,
    TurnEvidence,
)
from codex_usage_tracker.compression.identifiers import (
    stable_candidate_id,
    stable_scope_hash,
)
from codex_usage_tracker.compression.models import (
    COMPONENT_NAMES,
    CandidateDraft,
    ComponentClaim,
    ComponentExposure,
    ComponentName,
    CompressionScope,
    EstimateRange,
)
from codex_usage_tracker.store.compression_candidates import (
    get_compression_candidate,
    list_compression_candidates,
)
from codex_usage_tracker.store.compression_runs import get_compression_run
from codex_usage_tracker.store.connection import connect
from codex_usage_tracker.store.schema import init_db


class _RecordEvidence(Protocol):
    @property
    def record_id(self) -> str: ...


_RecordEvidenceT = TypeVar("_RecordEvidenceT", bound=_RecordEvidence)
_HASH_MODULUS = 1 << 256


def incremental_inputs(
    db_path: Path,
    *,
    snapshot: CompressionEvidenceSnapshot,
    current_manifest: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    scope: CompressionScope,
) -> tuple[list[CandidateDraft], CompressionEvidenceSnapshot, str]:
    """Reuse unaffected drafts and scope detector work to changed threads."""
    if previous is None:
        return [], snapshot, "cold"
    old_manifest = _mapping(previous.get("aggregate_profile")).get("_cache_manifest")
    if not isinstance(old_manifest, Mapping):
        return [], snapshot, "cold"
    changed_records, affected_threads = _affected_scope(old_manifest, current_manifest)
    previous_drafts = _load_previous_drafts(
        db_path,
        run_id=str(previous["run_id"]),
        source_revision=snapshot.source_revision,
        scope=scope,
    )
    reused = [
        draft
        for draft in previous_drafts
        if set(draft.record_ids).isdisjoint(changed_records)
        and set(draft.thread_keys).isdisjoint(affected_threads)
    ]
    return reused, _subset_snapshot(snapshot, changed_records, affected_threads), "incremental"


def latest_compatible_run(
    db_path: Path,
    *,
    scope_hash: str,
    detector_set_version: str,
    estimator_version: str,
    schema_version: int,
) -> dict[str, Any] | None:
    """Return the newest cache-compatible run regardless of source revision."""
    with connect(db_path) as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT run_id FROM compression_runs
            WHERE scope_hash = ? AND detector_set_version = ?
                AND estimator_version = ? AND compression_schema_version = ?
                AND status IN ('completed', 'completed_with_warnings')
            ORDER BY completed_at DESC, created_at DESC LIMIT 1
            """,
            (scope_hash, detector_set_version, estimator_version, int(schema_version)),
        ).fetchone()
    if row is None:
        return None
    return get_compression_run(db_path, run_id=str(row["run_id"]))


class RecordManifestBuilder:
    """Accumulate the existing order-independent manifest without retaining events."""

    def __init__(self) -> None:
        self._threads: dict[str, str] = {}
        self._accumulators: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        self._metadata: dict[str, dict[str, str]] = {}

    def add_call(self, call: CallEvidence) -> None:
        self._threads[call.record_id] = call.thread_key
        manifest_key = _manifest_key(call.record_id, call.thread_key)
        self._metadata[manifest_key] = {
            "thread_key": call.thread_key,
            "record_id": "",
        }
        _accumulate(self._accumulators[manifest_key], "call", call)

    def add_event(self, kind: str, event: Any) -> None:
        self.add_identity(kind, str(event.record_id), _revision_identity(event))

    def add_identity(self, kind: str, record_id: str, identity: Any) -> None:
        thread_key = self._threads.get(record_id, "")
        manifest_key = _manifest_key(record_id, thread_key)
        self._metadata.setdefault(
            manifest_key,
            {
                "thread_key": thread_key,
                "record_id": record_id if not thread_key else "",
            },
        )
        _accumulate(
            self._accumulators[manifest_key],
            kind,
            identity,
        )

    def build(self) -> dict[str, dict[str, str]]:
        return {
            key: {**self._metadata[key], "revision": _manifest_hash(accumulator)}
            for key, accumulator in sorted(self._accumulators.items())
        }


def record_manifest(
    snapshot: CompressionEvidenceSnapshot,
) -> dict[str, dict[str, str]]:
    """Hash bounded evidence metadata per thread for incremental invalidation."""
    builder = RecordManifestBuilder()
    for call in snapshot.calls:
        builder.add_call(call)
    for kind, events in (
        ("tool", snapshot.tool_calls),
        ("turn", snapshot.turns),
        ("command", snapshot.command_runs),
        ("file", snapshot.file_events),
        ("fragment", snapshot.content_fragments),
    ):
        for event in events:
            builder.add_event(kind, event)
    return builder.build()


def _load_previous_drafts(
    db_path: Path,
    *,
    run_id: str,
    source_revision: str,
    scope: CompressionScope,
) -> list[CandidateDraft]:
    page = list_compression_candidates(db_path, run_id=run_id, limit=None)
    details = (
        get_compression_candidate(db_path, candidate_id=str(row["candidate_id"]))
        for row in page["rows"]
    )
    return [
        _draft_from_stored(detail, source_revision=source_revision, scope=scope)
        for detail in details
        if detail is not None
    ]


def _draft_from_stored(
    payload: Mapping[str, Any],
    *,
    source_revision: str,
    scope: CompressionScope,
) -> CandidateDraft:
    claims = tuple(_claim(row) for row in _mapping_rows(payload.get("claims")))
    estimator = _mapping(payload.get("estimator"))
    confidence = _mapping(payload.get("confidence"))
    detector_version = str(payload["detector_version"])
    estimator_version = str(estimator["version"])
    pattern_key = str(payload["pattern_key"])
    family = str(payload["family"])
    return CandidateDraft(
        candidate_id=stable_candidate_id(
            source_revision=source_revision,
            scope_hash=stable_scope_hash(scope),
            family=family,
            pattern_key=pattern_key,
            detector_version=detector_version,
            estimator_version=estimator_version,
        ),
        family=family,
        pattern=str(payload["pattern"]),
        pattern_key=pattern_key,
        detector_version=detector_version,
        estimator_version=estimator_version,
        record_ids=tuple(sorted({claim.record_id for claim in claims})),
        thread_keys=tuple(sorted(str(row) for row in payload.get("thread_keys", []))),
        observation_count=int(payload["observation_count"]),
        observed_exposure=_exposure(payload.get("observed_exposure")),
        claims=claims,
        gross_estimate=_estimate(payload.get("gross_estimate")),
        confidence_grade=str(confidence["grade"]),
        confidence_score=float(confidence["score"]),
        confidence_reasons=tuple(str(row) for row in payload.get("confidence_reasons", [])),
        estimator_tier=str(estimator["tier"]),
        estimator_name=str(estimator["name"]),
        estimator_assumptions=tuple(str(row) for row in estimator.get("assumptions", [])),
        evidence_handles=tuple(_mapping_rows(payload.get("evidence_handles"))),
        intervention=_mapping(payload.get("intervention")),
        verification=_mapping(payload.get("verification")),
        first_seen=_optional_text(payload.get("first_seen")),
        last_seen=_optional_text(payload.get("last_seen")),
        data_quality_warnings=tuple(str(row) for row in payload.get("data_quality_warnings", [])),
    )


def _revision_identity(event: Any) -> Any:
    if isinstance(
        event,
        (
            CallEvidence,
            TurnEvidence,
            ToolCallEvidence,
            CommandRunEvidence,
            FileEventEvidence,
            ContentFragmentEvidence,
        ),
    ):
        return event.revision_identity()
    return event


def _manifest_key(record_id: str, thread_key: str) -> str:
    return f"thread:{thread_key}" if thread_key else f"record:{record_id}"


def _accumulate(accumulator: list[int], *parts: Any) -> None:
    encoded = "\x1f".join(repr(part) for part in parts).encode("utf-8")
    value = (zlib.crc32(encoded) << 32) | zlib.adler32(encoded)
    accumulator[0] += 1
    accumulator[1] = (accumulator[1] + value) % _HASH_MODULUS
    accumulator[2] ^= value


def _manifest_hash(accumulator: list[int]) -> str:
    encoded = f"{accumulator[0]}:{accumulator[1]:064x}:{accumulator[2]:064x}".encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def _affected_scope(
    previous: Mapping[str, Any],
    current: Mapping[str, Mapping[str, str]],
) -> tuple[set[str], set[str]]:
    manifest_keys = set(previous).union(current)
    changed_keys = {
        key
        for key in manifest_keys
        if _manifest_revision(previous.get(key)) != _manifest_revision(current.get(key))
    }
    threads = {
        thread
        for key in changed_keys
        for thread in (
            _manifest_thread(previous.get(key)),
            _manifest_thread(current.get(key)),
        )
        if thread
    }
    records = {
        record_id
        for key in changed_keys
        for record_id in (
            _manifest_record(previous.get(key)),
            _manifest_record(current.get(key)),
        )
        if record_id
    }
    return records, threads


def _subset_snapshot(
    snapshot: CompressionEvidenceSnapshot,
    changed_records: set[str],
    affected_threads: set[str],
) -> CompressionEvidenceSnapshot:
    record_ids = {
        call.record_id
        for call in snapshot.calls
        if call.record_id in changed_records or call.thread_key in affected_threads
    }
    return replace(
        snapshot,
        calls=_matching_records(snapshot.calls, record_ids),
        turns=_matching_records(snapshot.turns, record_ids),
        tool_calls=_matching_records(snapshot.tool_calls, record_ids),
        command_runs=_matching_records(snapshot.command_runs, record_ids),
        file_events=_matching_records(snapshot.file_events, record_ids),
        content_fragments=_matching_records(snapshot.content_fragments, record_ids),
        compactions=_matching_records(snapshot.compactions, record_ids),
        content_exposure_by_record={
            record_id: exposure
            for record_id, exposure in snapshot.content_exposure_by_record.items()
            if record_id in record_ids
        },
        content_exposure_by_turn={
            key: exposure
            for key, exposure in snapshot.content_exposure_by_turn.items()
            if key[0] in record_ids
        },
        tool_output_exposure_by_record={
            record_id: exposure
            for record_id, exposure in snapshot.tool_output_exposure_by_record.items()
            if record_id in record_ids
        },
    )


def _matching_records(
    rows: tuple[_RecordEvidenceT, ...],
    record_ids: set[str],
) -> tuple[_RecordEvidenceT, ...]:
    return tuple(row for row in rows if row.record_id in record_ids)


def _claim(payload: Mapping[str, Any]) -> ComponentClaim:
    component_text = str(payload["component"])
    if component_text not in COMPONENT_NAMES:
        raise ValueError(f"unknown stored compression component: {component_text}")
    return ComponentClaim(
        record_id=str(payload["record_id"]),
        component=cast(ComponentName, component_text),
        exposure_tokens=int(payload["exposure_tokens"]),
        estimate=_estimate(payload.get("estimate")),
    )


def _estimate(payload: Any) -> EstimateRange:
    value = _mapping(payload)
    return EstimateRange(int(value["low"]), int(value["likely"]), int(value["high"]))


def _exposure(payload: Any) -> ComponentExposure:
    value = _mapping(payload)
    return ComponentExposure(
        **{component: int(value.get(component, 0)) for component in COMPONENT_NAMES}
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _mapping_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [_mapping(row) for row in value if isinstance(row, Mapping)]


def _optional_text(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _manifest_revision(value: Any) -> str:
    return str(value.get("revision") or "") if isinstance(value, Mapping) else ""


def _manifest_thread(value: Any) -> str:
    return str(value.get("thread_key") or "") if isinstance(value, Mapping) else ""


def _manifest_record(value: Any) -> str:
    return str(value.get("record_id") or "") if isinstance(value, Mapping) else ""
