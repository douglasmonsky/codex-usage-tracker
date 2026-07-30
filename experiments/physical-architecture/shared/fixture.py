from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from .canonical import canonical_sha256, load_canonical_object
from .crash import CRASH_BOUNDARIES

FIXTURE_SCHEMA = "codex-usage-tracker.synthetic-fixture-manifest.v1"
ORACLE_SCHEMA = "codex-usage-tracker.synthetic-oracle-bundle.v1"
FIXTURE_REVISION = "agent-kernel-structural-v1"
_SOURCE_TIME_CONFIDENCE = frozenset(
    {"trusted", "uncertain", "unavailable"}
)
_SOURCE_TIME_INVENTORY_CONTRACT = {
    "confidence_values": ["trusted", "uncertain", "unavailable"],
    "hint_interval": "half_open_utc_microseconds",
    "selection_policy": "skip_nonoverlapping_trusted_only",
    "version": 1,
}
REQUIRED_VERTICAL_SLICES = (
    "context_deterioration",
    "workflow_sequence_first_mutation",
    "allowance_interval_accounting",
    "parent_subagent_aggregation",
    "evidence_source_lifecycle",
)
REQUIRED_SLICE_QUESTION_IDS = (
    "Q-ACC-05",
    "Q-ALW-01",
    "Q-ALW-02",
    "Q-ALW-03",
    "Q-CTX-01",
    "Q-CTX-02",
    "Q-CTX-04",
    "Q-DEL-01",
    "Q-OPS-03",
    "Q-OPS-04",
    "Q-WF-01",
    "Q-WF-02",
    "Q-WF-03",
    "Q-WF-05",
)


class FixtureContractError(ValueError):
    pass


@dataclass(frozen=True)
class SourceArtifact:
    relative_path: PurePosixPath
    absolute_path: Path
    byte_count: int
    record_count: int
    sha256: str
    state: str
    manifestation_id: str
    revision: str
    adapter_version: str
    time_range_hint: tuple[int, int] | None
    time_range_confidence: str


@dataclass(frozen=True)
class PhaseArtifact:
    relative_path: PurePosixPath
    absolute_path: Path
    byte_count: int
    record_count: int
    sha256: str
    group: str
    phase: str
    phase_id: str
    revision: str


@dataclass(frozen=True)
class FixtureBundle:
    root: Path
    profile: str
    seed: int
    fixture_revision: str
    manifest_digest: str
    oracle_digest: str
    manifest: Mapping[str, Any]
    oracle: Mapping[str, Any]
    sources: tuple[SourceArtifact, ...]
    phases: tuple[PhaseArtifact, ...]
    vertical_slices: tuple[str, ...]
    question_ids: frozenset[str]

    @property
    def source_bytes(self) -> int:
        return sum(source.byte_count for source in self.sources)

    def crash_expectation(self, boundary: str) -> Mapping[str, Any]:
        states = self.oracle.get("crash_states")
        if not isinstance(states, Sequence) or isinstance(states, (str, bytes)):
            raise FixtureContractError("oracle crash state matrix is missing")
        for state in states:
            if isinstance(state, Mapping) and state.get("boundary") == boundary:
                return MappingProxyType(dict(state))
        raise FixtureContractError(f"oracle has no crash expectation for {boundary!r}")


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _object_field(artifact: Mapping[str, Any], field: str, *, label: str) -> Mapping[str, Any]:
    value = artifact.get(field)
    if not isinstance(value, Mapping):
        raise FixtureContractError(f"{label} {field} must be an object")
    return value


def _require_exact_contract(
    manifest: Mapping[str, Any],
    oracle: Mapping[str, Any],
) -> None:
    if manifest.get("schema") != FIXTURE_SCHEMA:
        raise FixtureContractError("fixture manifest schema is not CK-03 v1")
    if oracle.get("schema") != ORACLE_SCHEMA:
        raise FixtureContractError("fixture oracle schema is not CK-03 v1")
    for artifact_name, artifact in (("manifest", manifest), ("oracle", oracle)):
        if artifact.get("fixture_revision") != FIXTURE_REVISION:
            raise FixtureContractError(f"{artifact_name} fixture revision is not frozen CK-03 v1")
        if artifact.get("version") != 1:
            raise FixtureContractError(f"{artifact_name} version must be 1")
    for field in ("profile", "seed", "fixture_revision"):
        if manifest.get(field) != oracle.get(field):
            raise FixtureContractError(f"manifest and oracle disagree on {field}")
    if (
        _object_field(manifest, "format_policy", label="manifest").get("content_bodies")
        is not False
    ):
        raise FixtureContractError("fixture manifest does not forbid content bodies")
    if _object_field(oracle, "format_policy", label="oracle").get("content_bodies") != "forbidden":
        raise FixtureContractError("fixture oracle does not forbid content bodies")


def _safe_relative_path(value: object) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise FixtureContractError("relative source path must be a non-empty string")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        raise FixtureContractError(f"invalid relative source path: {value!r}")
    return relative


def _source_stats(path: Path) -> tuple[int, int, str, tuple[int, int] | None]:
    digest = hashlib.sha256()
    byte_count = 0
    record_count = 0
    last_byte = b""
    time_range_start_us: int | None = None
    time_range_end_us: int | None = None
    try:
        with path.open("rb") as source:
            for line in source:
                digest.update(line)
                byte_count += len(line)
                record_count += line.count(b"\n")
                last_byte = line[-1:]
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(record, dict) and type(record.get("event_at_us")) is int:
                    event_at_us = record["event_at_us"]
                    time_range_start_us = (
                        event_at_us
                        if time_range_start_us is None
                        else min(time_range_start_us, event_at_us)
                    )
                    event_end_us = event_at_us + 1
                    time_range_end_us = (
                        event_end_us
                        if time_range_end_us is None
                        else max(time_range_end_us, event_end_us)
                    )
    except OSError as error:
        raise FixtureContractError(f"persisted source cannot be read: {path.name}") from error
    if byte_count and last_byte != b"\n":
        raise FixtureContractError(f"persisted source lacks final LF: {path.name}")
    time_range = (
        None
        if time_range_start_us is None or time_range_end_us is None
        else (time_range_start_us, time_range_end_us)
    )
    return byte_count, record_count, digest.hexdigest(), time_range


def _verified_artifact_path(
    root: Path,
    relative: PurePosixPath,
) -> Path:
    artifact_path = root.joinpath(*relative.parts)
    if (
        artifact_path.is_symlink()
        or not artifact_path.is_file()
        or not artifact_path.resolve().is_relative_to(root)
    ):
        raise FixtureContractError(f"persisted artifact is missing: {relative.as_posix()}")
    return artifact_path


def _source_time_range(
    entry: Mapping[str, Any],
) -> tuple[tuple[int, int] | None, str]:
    if (
        "time_range_confidence" not in entry
        or "time_range_hint" not in entry
    ):
        raise FixtureContractError("source time range fields are required")
    confidence = entry["time_range_confidence"]
    if (
        not isinstance(confidence, str)
        or confidence not in _SOURCE_TIME_CONFIDENCE
    ):
        raise FixtureContractError("source time range confidence is invalid")
    hint = entry["time_range_hint"]
    if hint is None:
        if confidence != "unavailable":
            raise FixtureContractError(
                "source time range hint is required when available"
            )
        return None, confidence
    if confidence == "unavailable":
        raise FixtureContractError(
            "unavailable source time range cannot include a hint"
        )
    if not isinstance(hint, dict) or set(hint) != {"end_us", "start_us"}:
        raise FixtureContractError("source time range hint is invalid")
    start_us = hint["start_us"]
    end_us = hint["end_us"]
    if (
        type(start_us) is not int
        or type(end_us) is not int
        or start_us >= end_us
    ):
        raise FixtureContractError(
            "source time range must be a non-empty half-open interval"
        )
    return (start_us, end_us), confidence


def _load_sources(root: Path, manifest: Mapping[str, Any]) -> tuple[SourceArtifact, ...]:
    if manifest.get("source_time_inventory") != _SOURCE_TIME_INVENTORY_CONTRACT:
        raise FixtureContractError("source time range contract is invalid")
    source_entries = manifest.get("sources")
    if not isinstance(source_entries, list):
        raise FixtureContractError("manifest sources must be a list")
    artifacts: list[SourceArtifact] = []
    seen_paths: set[PurePosixPath] = set()
    for entry in source_entries:
        if not isinstance(entry, dict):
            raise FixtureContractError("manifest source entry must be an object")
        time_range_hint, time_range_confidence = _source_time_range(entry)
        if entry.get("persisted_when_requested") is not True:
            continue
        relative = _safe_relative_path(entry.get("path"))
        if relative in seen_paths:
            raise FixtureContractError(f"duplicate persisted source path: {relative.as_posix()}")
        seen_paths.add(relative)
        source_path = _verified_artifact_path(root, relative)
        expected_bytes = entry.get("bytes")
        expected_records = entry.get("records")
        expected_digest = entry.get("content_sha256")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise FixtureContractError(f"invalid byte count for {relative.as_posix()}")
        if not isinstance(expected_records, int) or expected_records < 0:
            raise FixtureContractError(f"invalid record count for {relative.as_posix()}")
        actual_bytes, actual_records, actual_digest, actual_time_range = _source_stats(
            source_path
        )
        if actual_bytes != expected_bytes:
            raise FixtureContractError(f"source byte count mismatch: {relative.as_posix()}")
        if actual_records != expected_records:
            raise FixtureContractError(f"source record count mismatch: {relative.as_posix()}")
        if expected_digest != actual_digest:
            raise FixtureContractError(f"source digest mismatch: {relative.as_posix()}")
        if actual_time_range is None and time_range_hint is not None:
            raise FixtureContractError(
                f"source time range hint has no persisted timestamps: {relative.as_posix()}"
            )
        if actual_time_range is not None and time_range_hint is None:
            raise FixtureContractError(
                f"source time range hint missing persisted timestamps: {relative.as_posix()}"
            )
        if (
            actual_time_range is not None
            and time_range_hint is not None
            and (
                time_range_hint[0] > actual_time_range[0]
                or time_range_hint[1] < actual_time_range[1]
            )
        ):
            raise FixtureContractError(
                f"source time range hint excludes persisted timestamps: "
                f"{relative.as_posix()}"
            )
        artifacts.append(
            SourceArtifact(
                relative_path=relative,
                absolute_path=source_path,
                byte_count=expected_bytes,
                record_count=expected_records,
                sha256=actual_digest,
                state=str(entry.get("state")),
                manifestation_id=str(entry.get("manifestation_id")),
                revision=str(entry.get("revision")),
                adapter_version=str(entry.get("adapter_version")),
                time_range_hint=time_range_hint,
                time_range_confidence=time_range_confidence,
            )
        )
    return tuple(artifacts)


def _load_phases(root: Path, manifest: Mapping[str, Any]) -> tuple[PhaseArtifact, ...]:
    phase_entries = manifest.get("lifecycle_phases")
    if not isinstance(phase_entries, list):
        raise FixtureContractError("manifest lifecycle phases must be a list")
    artifacts: list[PhaseArtifact] = []
    seen_paths: set[PurePosixPath] = set()
    for entry in phase_entries:
        if not isinstance(entry, dict):
            raise FixtureContractError("manifest lifecycle phase must be an object")
        relative = _safe_relative_path(entry.get("path"))
        if relative in seen_paths:
            raise FixtureContractError(f"duplicate lifecycle phase path: {relative.as_posix()}")
        seen_paths.add(relative)
        phase_path = _verified_artifact_path(root, relative)
        expected_bytes = entry.get("bytes")
        expected_records = entry.get("records")
        if not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise FixtureContractError(f"invalid phase byte count for {relative.as_posix()}")
        if not isinstance(expected_records, int) or expected_records < 0:
            raise FixtureContractError(f"invalid phase record count for {relative.as_posix()}")
        actual_bytes, actual_records, actual_digest, _ = _source_stats(phase_path)
        if actual_bytes != expected_bytes or actual_records != expected_records:
            raise FixtureContractError(f"lifecycle phase size mismatch: {relative.as_posix()}")
        if actual_digest != entry.get("content_sha256"):
            raise FixtureContractError(f"lifecycle phase digest mismatch: {relative.as_posix()}")
        text_fields = ("group", "phase", "phase_id", "revision")
        if any(not isinstance(entry.get(field), str) or not entry[field] for field in text_fields):
            raise FixtureContractError(
                f"lifecycle phase metadata is invalid: {relative.as_posix()}"
            )
        artifacts.append(
            PhaseArtifact(
                relative_path=relative,
                absolute_path=phase_path,
                byte_count=actual_bytes,
                record_count=actual_records,
                sha256=actual_digest,
                group=str(entry["group"]),
                phase=str(entry["phase"]),
                phase_id=str(entry["phase_id"]),
                revision=str(entry["revision"]),
            )
        )
    return tuple(artifacts)


def _question_ids(
    manifest: Mapping[str, Any],
    oracle: Mapping[str, Any],
) -> frozenset[str]:
    questions = oracle.get("questions")
    if not isinstance(questions, dict):
        raise FixtureContractError("oracle questions must be an object")
    manifest_oracle_ids = manifest.get("question_oracle_ids")
    if (
        not isinstance(manifest_oracle_ids, list)
        or len(manifest_oracle_ids) != 80
        or any(not isinstance(item, str) for item in manifest_oracle_ids)
        or manifest_oracle_ids != sorted(manifest_oracle_ids)
        or set(manifest_oracle_ids) != set(questions)
    ):
        raise FixtureContractError("manifest and oracle question variants are inconsistent")
    result: set[str] = set()
    for oracle_id, question in questions.items():
        if isinstance(question, dict):
            if question.get("oracle_id") != oracle_id:
                raise FixtureContractError(f"oracle question key mismatch: {oracle_id}")
            question_id = question.get("question_id")
            if isinstance(question_id, str):
                result.add(question_id)
    missing = set(REQUIRED_SLICE_QUESTION_IDS) - result
    if missing:
        raise FixtureContractError(f"oracle omits required bake-off questions: {sorted(missing)}")
    return frozenset(result)


def _validate_oracle_reconciliation(oracle: Mapping[str, Any]) -> None:
    reconciliation = _object_field(
        oracle,
        "source_to_oracle_reconciliation",
        label="oracle",
    )
    if reconciliation.get("question_cases") != 80:
        raise FixtureContractError("oracle reconciliation question count is not CK-03 complete")
    if reconciliation.get("formula_failures") != {}:
        raise FixtureContractError("oracle reconciliation contains formula failures")
    states = oracle.get("crash_states")
    if not isinstance(states, list) or [
        state.get("boundary") if isinstance(state, dict) else None for state in states
    ] != list(CRASH_BOUNDARIES):
        raise FixtureContractError("oracle crash boundary matrix is incomplete")


def load_fixture_bundle(root: Path) -> FixtureBundle:
    """Load and byte-verify one persisted CK-03 fixture and oracle bundle."""
    resolved = root.resolve()
    try:
        manifest_payload = (resolved / "manifest.json").read_bytes()
        oracle_payload = (resolved / "oracle-bundle.json").read_bytes()
    except OSError as error:
        raise FixtureContractError("fixture manifest and oracle must both exist") from error
    try:
        manifest = load_canonical_object(manifest_payload, artifact="fixture manifest")
        oracle = load_canonical_object(oracle_payload, artifact="fixture oracle")
    except ValueError as error:
        raise FixtureContractError(str(error)) from error

    declared_manifest_digest = manifest.get("manifest_digest")
    unsigned_manifest = dict(manifest)
    unsigned_manifest.pop("manifest_digest", None)
    actual_manifest_digest = canonical_sha256(unsigned_manifest)
    if declared_manifest_digest != actual_manifest_digest:
        raise FixtureContractError("fixture manifest digest does not match canonical bytes")
    actual_oracle_digest = hashlib.sha256(oracle_payload).hexdigest()
    if manifest.get("oracle_sha256") != actual_oracle_digest:
        raise FixtureContractError("fixture oracle digest does not match manifest")

    _require_exact_contract(manifest, oracle)
    _validate_oracle_reconciliation(oracle)
    vertical_slice_map = oracle.get("vertical_slices")
    expected_slice_map = {
        f"V{index}": name for index, name in enumerate(REQUIRED_VERTICAL_SLICES, start=1)
    }
    if vertical_slice_map != expected_slice_map:
        raise FixtureContractError("oracle does not contain the five frozen vertical slices")
    sources = _load_sources(resolved, manifest)
    phases = _load_phases(resolved, manifest)
    declared_source_bytes = _object_field(
        manifest,
        "source_layout",
        label="manifest",
    ).get("source_bytes")
    if declared_source_bytes != sum(source.byte_count for source in sources):
        raise FixtureContractError("manifest persisted source byte total is inconsistent")

    return FixtureBundle(
        root=resolved,
        profile=str(manifest["profile"]),
        seed=int(manifest["seed"]),
        fixture_revision=str(manifest["fixture_revision"]),
        manifest_digest=actual_manifest_digest,
        oracle_digest=actual_oracle_digest,
        manifest=_deep_freeze(manifest),
        oracle=_deep_freeze(oracle),
        sources=sources,
        phases=phases,
        vertical_slices=tuple(expected_slice_map.values()),
        question_ids=_question_ids(manifest, oracle),
    )
