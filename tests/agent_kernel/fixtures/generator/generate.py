from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import shutil
import sys
import tempfile
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from tests.agent_kernel.contracts.reference.identity import semantic_id
from tests.agent_kernel.fixtures.generator.cases import (
    control_records,
    question_case_records,
    selector_anchor_records,
)
from tests.agent_kernel.fixtures.generator.profile import (
    FixtureProfile,
    load_production_shape,
    planned_distribution,
    validate_production_aggregates,
)
from tests.agent_kernel.fixtures.generator.semantic import (
    activity_record,
    allowance_record,
    boundary_records,
    compaction_record,
    history_windows,
    model_call_record,
    selected,
    selection_rank,
    state_change_record,
    tool_records,
)
from tests.agent_kernel.fixtures.generator.sources import (
    SourceSpec,
    clustered_source_index,
    source_specs,
)
from tests.agent_kernel.fixtures.oracles.bundle import build_oracle_bundle
from tests.agent_kernel.fixtures.oracles.common import canonical_json_bytes
from tests.agent_kernel.fixtures.oracles.source_ledger import SourceLedger

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CATALOG_PATH = (
    _REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json"
)
_EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
_MAX_OPEN_FILES = 768
_WINDOW_INDEPENDENT_EVENT_KINDS = frozenset(
    {
        "allowance_compatibility",
        "late_parent",
        "oracle_case",
        "selector_anchor",
        "slice_control",
        "source_revision",
    }
)
_AT_FDCWD = -100
_RENAME_EXCL = 0x00000004
_RENAME_NOREPLACE = 0x00000001
_UNSUPPORTED_RENAME_ERRNOS = {
    errno.EINVAL,
    getattr(errno, "ENOSYS", errno.EINVAL),
    getattr(errno, "ENOTSUP", errno.EINVAL),
    getattr(errno, "EOPNOTSUPP", errno.EINVAL),
}


@dataclass(frozen=True)
class GenerationResult:
    manifest_bytes: bytes
    oracle_bytes: bytes
    manifest_digest: str
    oracle_digest: str
    source_bytes: int
    source_records: int


@dataclass
class _SourceStats:
    bytes: int = 0
    records: int = 0
    digest: Any = None
    time_range_start_us: int | None = None
    time_range_end_us: int | None = None
    window_selection_uncertain: bool = False

    def __post_init__(self) -> None:
        if self.digest is None:
            self.digest = hashlib.sha256()


class _SourceSink:
    def __init__(
        self,
        root: Path,
        specs: tuple[SourceSpec, ...],
        *,
        ledger: SourceLedger,
        materialize: bool,
    ) -> None:
        self.root = root
        self.specs = specs
        self.ledger = ledger
        self.materialize = materialize
        self.stats = {spec.index: _SourceStats() for spec in specs}
        self.event_counts: Counter[str] = Counter()
        self._handles: OrderedDict[int, BinaryIO] = OrderedDict()
        if materialize:
            for spec in specs:
                if not spec.materialized:
                    continue
                path = root / spec.relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"")

    def emit_record(
        self,
        source_index: int,
        record: dict[str, Any],
        *,
        canonical: bool = True,
    ) -> None:
        self.emit_bytes(
            source_index,
            canonical_json_bytes(record),
            event_kind=str(record["type"]),
            record=record,
            canonical=canonical,
        )

    def emit_bytes(
        self,
        source_index: int,
        body: bytes,
        *,
        event_kind: str,
        record: dict[str, Any] | None = None,
        canonical: bool = True,
    ) -> None:
        stats = self.stats[source_index]
        byte_start = stats.bytes
        ordinal = stats.records
        stats.digest.update(body)
        stats.bytes += len(body)
        stats.records += 1
        self.event_counts[event_kind] += 1
        if event_kind in _WINDOW_INDEPENDENT_EVENT_KINDS:
            stats.window_selection_uncertain = True
        if record is not None and type(record.get("event_at_us")) is int:
            event_at_us = record["event_at_us"]
            if stats.time_range_start_us is None:
                stats.time_range_start_us = event_at_us
                stats.time_range_end_us = event_at_us + 1
            else:
                stats.time_range_start_us = min(
                    stats.time_range_start_us,
                    event_at_us,
                )
                assert stats.time_range_end_us is not None
                stats.time_range_end_us = max(
                    stats.time_range_end_us,
                    event_at_us + 1,
                )
        if self.materialize:
            self._handle(source_index).write(body)
        if record is not None:
            spec = self.specs[source_index]
            self.ledger.observe(
                record,
                {
                    "adapter_version": spec.adapter_version,
                    "byte_end": stats.bytes,
                    "byte_start": byte_start,
                    "manifestation_id": spec.manifestation_id,
                    "record_ordinal": ordinal,
                    "record_range": [ordinal, ordinal],
                    "revision": spec.revision,
                    "source_path": spec.relative_path,
                },
                canonical=canonical,
            )

    def _handle(self, source_index: int) -> BinaryIO:
        existing = self._handles.pop(source_index, None)
        if existing is not None:
            self._handles[source_index] = existing
            return existing
        if len(self._handles) >= _MAX_OPEN_FILES:
            _, oldest = self._handles.popitem(last=False)
            oldest.close()
        spec = self.specs[source_index]
        try:
            handle = (self.root / spec.relative_path).open("ab")
        except OSError as exc:
            if exc.errno != errno.EMFILE or not self._handles:
                raise
            for _ in range(min(32, len(self._handles))):
                _, oldest = self._handles.popitem(last=False)
                oldest.close()
            handle = (self.root / spec.relative_path).open("ab")
        self._handles[source_index] = handle
        return handle

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()


def _load_catalog() -> dict[str, Any]:
    import json

    payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("question catalog must contain one object")
    return payload


def _emit_control_stream(
    profile: FixtureProfile,
    catalog: dict[str, Any],
    sink: _SourceSink,
) -> None:
    for record in selector_anchor_records(profile):
        sink.emit_record(0, record)
    for record in control_records(profile):
        sink.emit_record(0, record)
    for record in question_case_records(profile, catalog):
        sink.emit_record(0, record)


def _generate_source_stream(
    profile: FixtureProfile,
    specs: tuple[SourceSpec, ...],
    sink: _SourceSink,
) -> None:
    distribution = planned_distribution(profile)
    active_count = sum(spec.state == "active" for spec in specs)
    archived = next(spec for spec in specs if spec.state == "archived")
    _emit_control_stream(profile, _load_catalog(), sink)

    for ordinal in range(profile.model_calls):
        source_index = clustered_source_index(
            ordinal,
            model_calls=profile.model_calls,
            active_sources=active_count,
        )
        missing_cached = selected(
            ordinal,
            profile.model_calls,
            distribution["missing_cached_input_calls"],
        )
        late = selected(
            ordinal,
            profile.model_calls,
            distribution["late_events"],
        )
        unpriced = selected(
            ordinal,
            profile.model_calls,
            distribution["unpriced_calls"],
        )
        session_start, turn_start, session_terminal = boundary_records(
            profile,
            ordinal,
        )
        for boundary in (session_start, turn_start):
            if boundary is not None:
                sink.emit_record(source_index, boundary)

        call = model_call_record(
            profile,
            ordinal,
            missing_cached=missing_cached,
            late=late,
            unpriced=unpriced,
        )
        sink.emit_record(source_index, call)
        if selected(
            ordinal,
            profile.model_calls,
            distribution["duplicate_call_occurrences"],
        ):
            sink.emit_record(archived.index, call, canonical=False)

        if selected(
            ordinal,
            profile.model_calls,
            distribution["compaction_boundaries"],
        ):
            sink.emit_record(source_index, compaction_record(profile, ordinal))

        if selected(
            ordinal,
            profile.model_calls,
            distribution["tool_invocations"],
        ):
            tool_rank = selection_rank(
                ordinal,
                profile.model_calls,
                distribution["tool_invocations"],
            )
            start, terminal = tool_records(
                profile,
                ordinal,
                tool_rank=tool_rank,
            )
            sink.emit_record(source_index, start)
            if tool_rank + 1 < distribution["tool_invocations"]:
                sink.emit_record(source_index, terminal)

        if selected(
            ordinal,
            profile.model_calls,
            distribution["activities"],
        ):
            sink.emit_record(source_index, activity_record(profile, ordinal))

        if selected(
            ordinal,
            profile.model_calls,
            distribution["state_changes"],
        ):
            sink.emit_record(source_index, state_change_record(profile, ordinal))

        if selected(
            ordinal,
            profile.model_calls,
            distribution["allowance_observations"],
        ):
            observation_rank = selection_rank(
                ordinal,
                profile.model_calls,
                distribution["allowance_observations"],
            )
            sink.emit_record(
                source_index,
                allowance_record(
                    profile,
                    ordinal,
                    observation_rank=observation_rank,
                ),
            )

        if session_terminal is not None:
            sink.emit_record(source_index, session_terminal)


def _emit_special_sources(
    profile: FixtureProfile,
    specs: tuple[SourceSpec, ...],
    sink: _SourceSink,
) -> None:
    replaced = next(spec for spec in specs if spec.state == "replaced")
    malformed = next(spec for spec in specs if spec.state == "malformed")
    sink.emit_record(
        replaced.index,
        {
            "event_at_us": profile.start_at_us,
            "event_kind_order": 0,
            "payload": {
                "content_revision": "synthetic-revision-1",
                "replacement": True,
            },
            "source_order": 0,
            "type": "source_revision",
        },
    )
    sink.emit_bytes(
        malformed.index,
        b'{"type":"malformed_fixture"\n',
        event_kind="malformed_line",
    )


def _phase_record(
    profile: FixtureProfile,
    *,
    occurrence: str,
    revision: str,
    ordinal: int,
) -> bytes:
    return canonical_json_bytes(
        {
            "event_at_us": profile.start_at_us + ordinal,
            "event_kind_order": 1,
            "payload": {
                "occurrence_id": semantic_id(
                    "call",
                    ["phase", profile.seed, occurrence],
                ),
                "revision": revision,
                "structural_case": occurrence,
            },
            "source_order": ordinal,
            "type": "source_phase_occurrence",
        }
    )


def _phase_artifacts(
    profile: FixtureProfile,
    root: Path,
    *,
    materialize: bool,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    archive = _phase_record(
        profile,
        occurrence="archive-preserved",
        revision="revision-1",
        ordinal=1,
    )
    replacement_before = _phase_record(
        profile,
        occurrence="replacement-removed",
        revision="revision-1",
        ordinal=2,
    )
    replacement_after = _phase_record(
        profile,
        occurrence="replacement-inserted",
        revision="revision-2",
        ordinal=3,
    )
    truncation_preserved = _phase_record(
        profile,
        occurrence="truncation-preserved",
        revision="revision-1",
        ordinal=4,
    )
    truncation_removed = _phase_record(
        profile,
        occurrence="truncation-removed",
        revision="revision-1",
        ordinal=5,
    )
    moving_preserved = _phase_record(
        profile,
        occurrence="moving-preserved",
        revision="revision-1",
        ordinal=6,
    )
    moving_inserted = _phase_record(
        profile,
        occurrence="moving-inserted",
        revision="revision-2",
        ordinal=7,
    )
    payloads = {
        "archive-original": archive,
        "archive-copy": archive,
        "replacement-before": replacement_before,
        "replacement-after": replacement_after,
        "truncation-before": truncation_preserved + truncation_removed,
        "truncation-after": truncation_preserved,
        "moving-tail-before": moving_preserved,
        "moving-tail-after": moving_preserved + moving_inserted,
    }
    groups = {
        "archive-original": ("archive", "before"),
        "archive-copy": ("archive", "after"),
        "replacement-before": ("replacement", "before"),
        "replacement-after": ("replacement", "after"),
        "truncation-before": ("truncation", "before"),
        "truncation-after": ("truncation", "after"),
        "moving-tail-before": ("moving_tail", "before"),
        "moving-tail-after": ("moving_tail", "after"),
    }
    entries = []
    for phase_id, body in payloads.items():
        group, phase = groups[phase_id]
        relative = f"phases/{group}/{phase}.jsonl"
        if group == "archive":
            relative = f"phases/{group}/{phase_id.rsplit('-', 1)[-1]}.jsonl"
        if materialize:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        entries.append(
            {
                "bytes": len(body),
                "content_sha256": hashlib.sha256(body).hexdigest(),
                "group": group,
                "path": relative,
                "phase": phase,
                "phase_id": phase_id,
                "records": len(body.splitlines()),
                "revision": "revision-1" if phase == "before" else "revision-2",
            }
        )
    occurrence = lambda name: semantic_id(  # noqa: E731
        "call",
        ["phase", profile.seed, name],
    )
    mappings = {
        "archive": {
            "byte_identical": True,
            "inserted": [],
            "preserved": [occurrence("archive-preserved")],
            "removed": [],
        },
        "moving_tail": {
            "inserted": [occurrence("moving-inserted")],
            "preserved": [occurrence("moving-preserved")],
            "removed": [],
        },
        "replacement": {
            "inserted": [occurrence("replacement-inserted")],
            "preserved": [],
            "removed": [occurrence("replacement-removed")],
        },
        "truncation": {
            "inserted": [],
            "preserved": [occurrence("truncation-preserved")],
            "removed": [occurrence("truncation-removed")],
        },
    }
    return entries, mappings


def _source_time_inventory(
    spec: SourceSpec,
    stats: _SourceStats,
) -> dict[str, Any]:
    if (
        stats.time_range_start_us is None
        or stats.time_range_end_us is None
    ):
        return {
            "time_range_confidence": "unavailable",
            "time_range_hint": None,
        }
    confidence = (
        "uncertain"
        if (
            spec.history_selection == "uncertain"
            or stats.window_selection_uncertain
        )
        else "trusted"
    )
    return {
        "time_range_confidence": confidence,
        "time_range_hint": {
            "end_us": stats.time_range_end_us,
            "start_us": stats.time_range_start_us,
        },
    }


def _source_manifest(
    specs: tuple[SourceSpec, ...],
    sink: _SourceSink,
) -> list[dict[str, Any]]:
    result = []
    for spec in specs:
        stats = sink.stats[spec.index]
        result.append(
            {
                "adapter_version": spec.adapter_version,
                "bytes": stats.bytes,
                "content_sha256": stats.digest.hexdigest(),
                "duplicate_of": spec.duplicate_of,
                "history_selection": spec.history_selection,
                "logical_source": spec.logical_source,
                "manifestation_id": spec.manifestation_id,
                "moving_tail": spec.moving_tail,
                "path": spec.relative_path,
                "persisted_when_requested": spec.materialized,
                "records": stats.records,
                "revision": spec.revision,
                "state": spec.state,
                **_source_time_inventory(spec, stats),
            }
        )
    return result


def _build_manifest(
    profile: FixtureProfile,
    specs: tuple[SourceSpec, ...],
    sink: _SourceSink,
    *,
    catalog: dict[str, Any],
    oracle_digest: str,
    phase_entries: list[dict[str, Any]],
    phase_mappings: dict[str, Any],
) -> dict[str, Any]:
    sources = _source_manifest(specs, sink)
    state_counts = Counter(spec.state for spec in specs)
    stream_aggregates = sink.ledger.stream_aggregates
    production_validation: dict[str, Any] | None = None
    if profile.name == "production":
        shape = load_production_shape()
        validate_production_aggregates(shape, stream_aggregates)
        if sink.ledger.cardinality_histograms != shape["cardinality_histograms"]:
            raise ValueError("production cardinality histograms differ from stream")
        production_validation = {
            "cardinality_histograms": sink.ledger.cardinality_histograms,
            "profile_schema": shape["schema"],
            "status": "exact_match",
            "stream_aggregates": stream_aggregates,
        }
    manifest: dict[str, Any] = {
        "capabilities": {
            "allowance_observation": True,
            "model_call_usage": True,
            "session_hierarchy": True,
            "source_occurrence": True,
            "state_change_observation": True,
            "tool_lifecycle": True,
            "valuation": True,
        },
        "digest_policy": {
            "algorithm": "sha256",
            "manifest": "canonical_manifest_without_manifest_digest",
            "oracle": "canonical_complete_oracle_bundle",
            "source": "exact_source_file_bytes",
        },
        "distribution": planned_distribution(profile),
        "event_kind_counts": dict(sorted(sink.event_counts.items())),
        "fixture_revision": "agent-kernel-structural-v1",
        "format_policy": {
            "absolute_paths": False,
            "content_bodies": False,
            "encoding": "canonical_json_utf8_lf",
            "source_records": "structural_metadata_only",
        },
        "history": {
            "days": profile.history_days,
            "selections": sink.ledger.history,
            "start_at_us": profile.start_at_us,
            "timezone": profile.timezone,
            "windows": sink.ledger.history_windows,
        },
        "lifecycle_phases": phase_entries,
        "oracle_sha256": oracle_digest,
        "phase_occurrence_mappings": phase_mappings,
        "production_shape_validation": production_validation,
        "profile": profile.name,
        "publication": {
            "atomic": True,
            "no_replace": True,
            "same_filesystem": True,
            "strategy": "sibling_staging_exclusive_lock_rename",
        },
        "question_oracle_ids": sorted(
            oracle_id
            for question in catalog["questions"]
            for oracle_id in question["oracle_ids"]
        ),
        "rate_card_revision": "synthetic-rate-card-v1",
        "schema": "codex-usage-tracker.synthetic-fixture-manifest.v1",
        "seed": profile.seed,
        "semantic_cases": list(profile.semantic_cases),
        "source_layout": {
            "manifestations": profile.source_manifestations,
            "moving_tails": sum(spec.moving_tail for spec in specs),
            "persisted_source_files_when_requested": sum(
                spec.materialized for spec in specs
            ),
            "source_bytes": sum(item["bytes"] for item in sources),
            "source_records": sum(item["records"] for item in sources),
            "state_counts": {
                state: state_counts[state]
                for state in (
                    "active",
                    "archived",
                    "deferred",
                    "malformed",
                    "replaced",
                    "truncated",
                )
            },
            "uncertain_sources": sum(
                spec.history_selection == "uncertain"
                for spec in specs
            ),
        },
        "source_time_inventory": {
            "confidence_values": [
                "trusted",
                "uncertain",
                "unavailable",
            ],
            "hint_interval": "half_open_utc_microseconds",
            "selection_policy": "skip_nonoverlapping_trusted_only",
            "version": 1,
        },
        "sources": sources,
        "stream_aggregates": stream_aggregates,
        "version": 1,
    }
    manifest["manifest_digest"] = hashlib.sha256(
        canonical_json_bytes(manifest)
    ).hexdigest()
    return manifest


def _generate_into(
    profile: FixtureProfile,
    root: Path,
    *,
    manifest_only: bool,
) -> GenerationResult:
    specs = source_specs(profile)
    catalog = _load_catalog()
    distribution = planned_distribution(profile)
    windows = history_windows(
        profile,
        late_event_count=distribution["late_events"],
    )
    ledger = SourceLedger(
        history_windows=windows,
        streaming=True,
        source_manifestations=profile.source_manifestations,
    )
    sink = _SourceSink(
        root,
        specs,
        ledger=ledger,
        materialize=not manifest_only,
    )
    try:
        _generate_source_stream(profile, specs, sink)
        _emit_special_sources(profile, specs, sink)
    finally:
        sink.close()
    phase_entries, phase_mappings = _phase_artifacts(
        profile,
        root,
        materialize=not manifest_only,
    )
    ledger.phase_occurrences = phase_mappings
    ledger.finish()
    oracle = build_oracle_bundle(profile, catalog, ledger=ledger)
    oracle_bytes = canonical_json_bytes(oracle)
    oracle_digest = hashlib.sha256(oracle_bytes).hexdigest()
    manifest = _build_manifest(
        profile,
        specs,
        sink,
        catalog=catalog,
        oracle_digest=oracle_digest,
        phase_entries=phase_entries,
        phase_mappings=phase_mappings,
    )
    manifest_bytes = canonical_json_bytes(manifest)
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_bytes(manifest_bytes)
    (root / "oracle-bundle.json").write_bytes(oracle_bytes)
    return GenerationResult(
        manifest_bytes=manifest_bytes,
        oracle_bytes=oracle_bytes,
        manifest_digest=manifest["manifest_digest"],
        oracle_digest=oracle_digest,
        source_bytes=manifest["source_layout"]["source_bytes"],
        source_records=manifest["source_layout"]["source_records"],
    )


def _raise_atomic_rename_error(destination: Path) -> None:
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, os.strerror(error), destination)
    if error in _UNSUPPORTED_RENAME_ERRNOS:
        raise NotImplementedError(
            f"atomic no-replace directory rename is unsupported for {sys.platform}"
        )
    raise OSError(error, os.strerror(error), destination)


def _rename_directory_no_replace(staging: Path, destination: Path) -> None:
    """Atomically publish a sibling directory without replacing any destination."""

    source_bytes = os.fsencode(staging)
    destination_bytes = os.fsencode(destination)

    if sys.platform == "darwin":
        renamex_np = getattr(ctypes.CDLL(None, use_errno=True), "renamex_np", None)
        if renamex_np is None:
            raise NotImplementedError("renamex_np is unavailable on this macOS runtime")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        ctypes.set_errno(0)
        if renamex_np(source_bytes, destination_bytes, _RENAME_EXCL) != 0:
            _raise_atomic_rename_error(destination)
        return

    if sys.platform.startswith("linux"):
        renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
        if renameat2 is None:
            raise NotImplementedError("renameat2 is unavailable on this Linux runtime")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        ctypes.set_errno(0)
        if (
            renameat2(
                _AT_FDCWD,
                source_bytes,
                _AT_FDCWD,
                destination_bytes,
                _RENAME_NOREPLACE,
            )
            != 0
        ):
            _raise_atomic_rename_error(destination)
        return

    if os.name == "nt":
        os.rename(staging, destination)
        return

    raise NotImplementedError(
        f"atomic no-replace directory rename is unsupported for {sys.platform}"
    )


def _exclusive_publish(staging: Path, destination: Path) -> None:
    lock = destination.parent / f".{destination.name}.publish-lock"
    descriptor: int | None = None
    lock_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(
            lock,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        lock_stat = os.fstat(descriptor)
        lock_identity = (lock_stat.st_dev, lock_stat.st_ino)
        if destination.exists():
            raise FileExistsError(
                f"fixture output already exists: {destination.name}"
            )
        _rename_directory_no_replace(staging, destination)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if lock_identity is not None:
            try:
                current_lock = lock.stat(follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if (current_lock.st_dev, current_lock.st_ino) == lock_identity:
                    lock.unlink()


def generate_fixture(
    profile: FixtureProfile,
    output: Path,
    *,
    manifest_only: bool = False,
) -> GenerationResult:
    """Generate in a sibling tree and atomically publish without replacement."""

    destination = output.resolve()
    if destination.exists():
        raise FileExistsError(f"fixture output already exists: {destination.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.staging-",
            dir=destination.parent,
        )
    )
    try:
        result = _generate_into(profile, staging, manifest_only=manifest_only)
        _exclusive_publish(staging, destination)
        return result
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def tree_digest(root: Path) -> str:
    """Hash exact generated bytes in relative path order."""

    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def empty_source_sha256() -> str:
    """Expose the canonical empty-source digest for hand-audit assertions."""

    return _EMPTY_SHA256
