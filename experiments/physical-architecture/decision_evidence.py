"""Strict, bounded CK-04 physical-architecture decision evidence.

The decision manifest is intentionally an aggregate of canonical evidence, not
raw qualification output.  It records exact hashes and enough typed
measurements to reproduce the elimination, scoring, and sensitivity decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import shared

MANIFEST_SCHEMA = "codex-usage-tracker.ck04-decision-evidence.v2"
PRODUCTION_SCHEMA_CONTRACT_SHA256 = (
    "eecff68062a8d0cba0619058a6e660f565d9a96c2575ab0dc93d72b987f31543"
)
CANDIDATE_A_SCHEMA_SHA256 = "31b33e9efe24c458a528f2cc6930379028cd3bf40e9df0b79825290d61d85f09"
MAX_MANIFEST_BYTES = 512 * 1024
MAX_ARTIFACTS_PER_DIRECTION = 256
MAX_QUALIFICATION_RUNS = 128
MAX_QUERY_PLANS = 256
MAX_CRASH_OBSERVATIONS = 256
MAX_LIMITATIONS = 32
MAX_TEXT_LENGTH = 2_048

_CANDIDATE_IDS = ("A", "C", "D")
_SCALE_ORDER = ("standard", "production", "growth")
_SCALE_MODEL_CALLS = {
    "standard": 100_000,
    "production": 1_316_864,
    "growth": 2_500_000,
}
_SCORE_DIMENSIONS = tuple(sorted(dimension.value for dimension in shared.ScoreDimension))
_REQUIRED_QUESTION_IDS = frozenset(shared.P1_QUESTION_IDS) | frozenset(
    shared.REQUIRED_SLICE_QUESTION_IDS
)
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_SYMBOL = re.compile(r"[A-Za-z_][A-Za-z0-9_.:<>\-]{0,255}\Z")
_ENVIRONMENT_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_QUESTION_ID = re.compile(r"Q-[A-Z]+-[0-9]{2}\Z")
_PACKET_ID = re.compile(r"CK-[0-9]{2}\Z")
_DECIMAL_TEXT = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?\Z")
_PRIVATE_PATH = re.compile(
    r"(?:^|[\s=:(])(?:/(?:Users|home|root|private|tmp|var/folders)/|"
    r"[A-Za-z]:\\|~[/\\]|file://)",
    re.IGNORECASE,
)
_SECRET_VALUE = re.compile(
    r"(?:-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b|"
    r"\bgh[opusr]_[A-Za-z0-9]{20,}\b|"
    r"\bsk-[A-Za-z0-9_-]{16,}\b|"
    r"\b(?:api[_ -]?key|password|passwd|secret|access[_ -]?token|bearer)"
    r"\s*[:=]\s*\S+)",
    re.IGNORECASE,
)
_SECRET_ENVIRONMENT_PARTS = ("CREDENTIAL", "KEY", "PASSWORD", "SECRET", "TOKEN")
_SHELL_PROGRAMS = frozenset({"bash", "dash", "fish", "sh", "zsh"})
_WORKLOAD_PLACEHOLDERS = frozenset({"{python}", "{fixture_root}", "{output_root}"})
_PLAN_COUNTER_FIELDS = frozenset(
    {"automatic_indexes", "full_scans", "sql_statements", "temporary_sorts"}
)

_ARTIFACT_SPECS = {
    "fixture_manifest": ("input", "canonical_json"),
    "fixture_oracle": ("input", "canonical_json"),
    "workload_matrix": ("input", "canonical_json"),
    "qualification_invocation": ("input", "canonical_json"),
    "agent_perf_workload": ("input", "canonical_json"),
    "dbhub_invocation": ("input", "canonical_json"),
    "qualification_measurements": ("output", "canonical_jsonl"),
    "qualification_summary": ("output", "canonical_json"),
    "score_result": ("output", "canonical_json"),
    "query_plan_measurements": ("output", "canonical_json"),
    "crash_measurements": ("output", "canonical_json"),
    "agent_perf_measurements": ("output", "canonical_json"),
    "dbhub_measurements": ("output", "canonical_json"),
}
_REQUIRED_ARTIFACT_KINDS = {
    "input": frozenset(
        {
            "fixture_manifest",
            "fixture_oracle",
            "workload_matrix",
            "qualification_invocation",
            "agent_perf_workload",
            "dbhub_invocation",
        }
    ),
    "output": frozenset(
        {
            "qualification_measurements",
            "qualification_summary",
            "score_result",
            "query_plan_measurements",
            "crash_measurements",
            "agent_perf_measurements",
            "dbhub_measurements",
        }
    ),
}
_FAILURE_METRICS = {
    "automatic_index_count": ("integer", "lte"),
    "database_bytes": ("integer", "lte"),
    "full_scan_count": ("integer", "lte"),
    "oracle_equivalent": ("boolean", "eq"),
    "prior_publication_survived": ("boolean", "eq"),
    "process_termination_observed": ("boolean", "eq"),
    "projection_fanout": ("integer", "lte"),
    "queryable_reader_latency_ns": ("integer", "lte"),
    "raw_content_absent": ("boolean", "eq"),
    "response_bytes": ("integer", "lte"),
    "selector_pages_gap_free": ("boolean", "eq"),
    "temporary_sort_count": ("integer", "lte"),
    "tracker_calls": ("integer", "lte"),
    "wall_time_ns": ("integer", "lte"),
    "wal_bytes": ("integer", "lte"),
}
_FAILURE_GATES = frozenset(
    {
        "correctness",
        "data_handling",
        "evidence_stability",
        "performance",
        "publication_recovery",
    }
)


class DecisionEvidenceContractError(ValueError):
    """The aggregate manifest is incomplete, unsafe, or non-canonical."""


@dataclass(frozen=True)
class DecisionEvidenceBuild:
    """A validated manifest and its exact canonical representation."""

    payload: dict[str, Any]
    canonical_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class _Artifact:
    artifact_id: str
    direction: str
    kind: str
    encoding: str
    canonical_sha256: str
    record_count: int


class _ArtifactIndex:
    def __init__(self, artifacts: Mapping[str, _Artifact]) -> None:
        self.artifacts = dict(artifacts)
        self.used: set[str] = set()

    def use(
        self,
        artifact_id: object,
        *,
        context: str,
        direction: str,
        kinds: frozenset[str],
    ) -> _Artifact:
        identifier = _identifier(artifact_id, f"{context}.artifact_id")
        artifact = self.artifacts.get(identifier)
        if artifact is None:
            raise DecisionEvidenceContractError(
                f"{context} references unknown artifact {identifier!r}"
            )
        if artifact.direction != direction or artifact.kind not in kinds:
            expected = ", ".join(sorted(kinds))
            raise DecisionEvidenceContractError(
                f"{context} must reference {direction} artifact kind {expected}"
            )
        self.used.add(identifier)
        return artifact

    def require_all_used(self) -> None:
        unused = sorted(set(self.artifacts) - self.used)
        if unused:
            raise DecisionEvidenceContractError(
                f"canonical artifacts contain unreferenced IDs: {', '.join(unused)}"
            )


@dataclass(frozen=True)
class _FixtureIdentity:
    fixture_id: str
    manifest_sha256: str
    oracle_sha256: str


@dataclass(frozen=True)
class _QualificationRun:
    run_id: str
    candidate_ids: tuple[str, ...]
    fixture_id: str
    case_ids: frozenset[str]


@dataclass(frozen=True)
class _WorkloadIdentity:
    case_count: int
    matrix_sha256: str


@dataclass(frozen=True)
class _CandidateEvidence:
    candidate_id: str
    eligible: bool
    failure_ids: tuple[str, ...]
    score_inputs: Mapping[str, shared.CandidateScoreInput]
    score_results: Mapping[str, Mapping[str, Any]]


def build_manifest(payload: Mapping[str, object]) -> DecisionEvidenceBuild:
    """Validate a structured draft and return canonical bytes plus SHA-256."""

    if not isinstance(payload, dict):
        raise DecisionEvidenceContractError("decision evidence must be one JSON object")
    _scan_json_value(payload, context="$")
    _validate_manifest(payload)
    canonical_bytes = shared.canonical_json_bytes(payload)
    if len(canonical_bytes) > MAX_MANIFEST_BYTES:
        raise DecisionEvidenceContractError(
            f"decision evidence exceeds {MAX_MANIFEST_BYTES} canonical bytes"
        )
    decoded = json.loads(canonical_bytes)
    if not isinstance(decoded, dict):
        raise DecisionEvidenceContractError("decision evidence canonicalization failed")
    return DecisionEvidenceBuild(
        payload=decoded,
        canonical_bytes=canonical_bytes,
        sha256=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def validate_manifest_bytes(payload: bytes) -> DecisionEvidenceBuild:
    """Require exact canonical encoding, then validate the manifest contract."""

    if len(payload) > MAX_MANIFEST_BYTES:
        raise DecisionEvidenceContractError(f"decision evidence exceeds {MAX_MANIFEST_BYTES} bytes")
    decoded = _decode_json_object(payload, artifact="decision evidence")
    build = build_manifest(decoded)
    if payload != build.canonical_bytes:
        raise DecisionEvidenceContractError("decision evidence is not canonical JSON")
    return build


def validate_manifest_path(path: Path) -> DecisionEvidenceBuild:
    """Read and validate one existing canonical manifest."""

    try:
        payload = path.read_bytes()
    except OSError as error:
        raise DecisionEvidenceContractError(
            f"cannot read decision evidence {path.name!r}"
        ) from error
    return validate_manifest_bytes(payload)


def write_manifest(
    payload: Mapping[str, object],
    destination: Path,
    *,
    replace: bool = False,
) -> DecisionEvidenceBuild:
    """Atomically write validated canonical evidence.

    Existing files are refused unless the caller explicitly selects ``replace``.
    """

    build = build_manifest(payload)
    if destination.is_symlink():
        raise DecisionEvidenceContractError("decision evidence destination cannot be a symlink")
    destination = destination.resolve()
    if not destination.parent.is_dir():
        raise DecisionEvidenceContractError("decision evidence parent directory is missing")
    if destination.exists() and not replace:
        raise DecisionEvidenceContractError("decision evidence destination already exists")

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as output:
            output.write(build.canonical_bytes)
            output.flush()
            os.fsync(output.fileno())
        if destination.exists() and not replace:
            raise DecisionEvidenceContractError("decision evidence destination already exists")
        os.replace(temporary_path, destination)
        if destination.read_bytes() != build.canonical_bytes:
            raise DecisionEvidenceContractError("canonical decision evidence changed after write")
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return build


def _validate_manifest(payload: Mapping[str, object]) -> None:
    document = _object(
        payload,
        "$",
        {
            "agent_perf",
            "candidates",
            "canonical_artifacts",
            "code_commit",
            "crash_observations",
            "dbhub",
            "decision_date",
            "decision_id",
            "environment",
            "fixtures",
            "limitations",
            "qualification_runs",
            "query_plans",
            "schema",
            "schema_identity",
            "selected_candidate",
            "sensitivity",
            "workload",
        },
    )
    if document["schema"] != MANIFEST_SCHEMA:
        raise DecisionEvidenceContractError(f"schema must be {MANIFEST_SCHEMA}")
    if document["decision_id"] != "CK-04":
        raise DecisionEvidenceContractError("decision_id must be CK-04")
    _date_text(document["decision_date"], "$.decision_date")
    code_commit = _commit(document["code_commit"], "$.code_commit")
    selected_candidate = _candidate_id(document["selected_candidate"], "$.selected_candidate")
    _validate_schema_identity(
        document["schema_identity"],
        selected_candidate=selected_candidate,
    )

    artifacts = _validate_artifacts(document["canonical_artifacts"])
    environment = _validate_environment(document["environment"])
    fixtures = _validate_fixtures(document["fixtures"], artifacts)
    workload = _validate_workload(document["workload"], artifacts, environment)
    qualification_runs = _validate_qualification_runs(
        document["qualification_runs"],
        artifacts,
        fixtures,
        workload_case_count=workload.case_count,
    )
    candidates, rankings = _validate_candidates(
        document["candidates"],
        artifacts,
        fixtures,
        qualification_runs,
        code_commit=code_commit,
        selected_candidate=selected_candidate,
    )
    _validate_sensitivity(
        document["sensitivity"],
        rankings=rankings,
        selected_candidate=selected_candidate,
    )
    _validate_query_plans(
        document["query_plans"],
        artifacts,
        fixtures,
        qualification_runs,
    )
    _validate_crash_observations(
        document["crash_observations"],
        artifacts,
        candidates,
        qualification_runs,
    )
    _validate_agent_perf(
        document["agent_perf"],
        artifacts,
        fixtures,
        qualification_runs,
        workload_matrix_sha256=workload.matrix_sha256,
        selected_candidate=selected_candidate,
    )
    dbhub_tokens_unavailable = _validate_dbhub(
        document["dbhub"],
        artifacts,
        qualification_runs,
    )
    _validate_limitations(
        document["limitations"],
        artifacts,
        require_dbhub_token_limitation=dbhub_tokens_unavailable,
    )
    artifacts.require_all_used()


def _validate_schema_identity(value: object, *, selected_candidate: str) -> None:
    identity = _object(
        value,
        "$.schema_identity",
        {
            "production_contract_id",
            "production_contract_sha256",
            "selected_candidate_schema_id",
            "selected_candidate_schema_sha256",
        },
    )
    if identity["production_contract_id"] != "codex-usage-tracker.agent-kernel.schema-contract.v1":
        raise DecisionEvidenceContractError("production schema contract identity is unsupported")
    expected_candidate_id = (
        f"codex-usage-tracker.physical-bakeoff.candidate-{selected_candidate.lower()}.v1"
    )
    if identity["selected_candidate_schema_id"] != expected_candidate_id:
        raise DecisionEvidenceContractError(
            "selected candidate schema identity differs from decision"
        )
    production_digest = _sha256(
        identity["production_contract_sha256"],
        "$.schema_identity.production_contract_sha256",
    )
    if production_digest != PRODUCTION_SCHEMA_CONTRACT_SHA256:
        raise DecisionEvidenceContractError("production schema contract SHA-256 is stale")
    candidate_digest = _sha256(
        identity["selected_candidate_schema_sha256"],
        "$.schema_identity.selected_candidate_schema_sha256",
    )
    if selected_candidate == "A" and candidate_digest != CANDIDATE_A_SCHEMA_SHA256:
        raise DecisionEvidenceContractError("Candidate A physical schema SHA-256 is stale")


def _validate_artifacts(value: object) -> _ArtifactIndex:
    section = _object(value, "$.canonical_artifacts", {"inputs", "outputs"})
    artifacts: dict[str, _Artifact] = {}
    kinds_by_direction: dict[str, set[str]] = {"input": set(), "output": set()}
    for field_name, direction in (("inputs", "input"), ("outputs", "output")):
        rows = _list(
            section[field_name],
            f"$.canonical_artifacts.{field_name}",
            minimum=1,
            maximum=MAX_ARTIFACTS_PER_DIRECTION,
        )
        identifiers: list[str] = []
        for index, row in enumerate(rows):
            context = f"$.canonical_artifacts.{field_name}[{index}]"
            artifact = _object(
                row,
                context,
                {
                    "artifact_id",
                    "canonical_sha256",
                    "encoding",
                    "kind",
                    "record_count",
                },
            )
            artifact_id = _identifier(artifact["artifact_id"], f"{context}.artifact_id")
            kind = _text(artifact["kind"], f"{context}.kind", maximum=64)
            encoding = _text(artifact["encoding"], f"{context}.encoding", maximum=32)
            expected = _ARTIFACT_SPECS.get(kind)
            if expected != (direction, encoding):
                raise DecisionEvidenceContractError(
                    f"{context} has unsupported {direction} artifact kind/encoding"
                )
            if artifact_id in artifacts:
                raise DecisionEvidenceContractError(
                    f"canonical artifact ID duplicated: {artifact_id}"
                )
            record_count = _integer(
                artifact["record_count"],
                f"{context}.record_count",
                minimum=1,
                maximum=10_000_000,
            )
            if encoding == "canonical_json" and record_count != 1:
                raise DecisionEvidenceContractError(
                    f"{context} canonical_json artifact must contain one record"
                )
            artifacts[artifact_id] = _Artifact(
                artifact_id=artifact_id,
                direction=direction,
                kind=kind,
                encoding=encoding,
                canonical_sha256=_sha256(
                    artifact["canonical_sha256"],
                    f"{context}.canonical_sha256",
                ),
                record_count=record_count,
            )
            identifiers.append(artifact_id)
            kinds_by_direction[direction].add(kind)
        _require_ordered_unique(identifiers, f"$.canonical_artifacts.{field_name}")

    for direction, required in _REQUIRED_ARTIFACT_KINDS.items():
        missing = sorted(required - kinds_by_direction[direction])
        if missing:
            raise DecisionEvidenceContractError(
                f"canonical {direction} artifacts missing kinds: {', '.join(missing)}"
            )
    return _ArtifactIndex(artifacts)


def _validate_environment(value: object) -> Mapping[str, Any]:
    environment = _object(
        value,
        "$.environment",
        {"environment_id", "fingerprint_sha256", "identity"},
    )
    _identifier(environment["environment_id"], "$.environment.environment_id")
    identity = _object(
        environment["identity"],
        "$.environment.identity",
        {
            "analyze_state",
            "compiler_flags",
            "cpu_model",
            "filesystem",
            "filesystem_cache_state",
            "logical_cores",
            "memory_bytes",
            "operating_system",
            "physical_cores",
            "python_version",
            "sqlite_settings",
            "sqlite_version",
            "storage_model",
        },
    )
    for field_name in (
        "analyze_state",
        "cpu_model",
        "filesystem",
        "operating_system",
        "python_version",
        "sqlite_version",
        "storage_model",
    ):
        _text(identity[field_name], f"$.environment.identity.{field_name}", maximum=512)
    if identity["filesystem_cache_state"] not in {"cold", "uncontrolled", "warm"}:
        raise DecisionEvidenceContractError(
            "$.environment.identity.filesystem_cache_state is unsupported"
        )
    physical_cores = _integer(
        identity["physical_cores"],
        "$.environment.identity.physical_cores",
        minimum=1,
        maximum=1_024,
    )
    _integer(
        identity["logical_cores"],
        "$.environment.identity.logical_cores",
        minimum=physical_cores,
        maximum=2_048,
    )
    _integer(
        identity["memory_bytes"],
        "$.environment.identity.memory_bytes",
        minimum=1,
    )
    compiler_flags = _string_list(
        identity["compiler_flags"],
        "$.environment.identity.compiler_flags",
        minimum=1,
        maximum=32,
        item_maximum=512,
    )
    _require_ordered_unique(compiler_flags, "$.environment.identity.compiler_flags")
    settings = _list(
        identity["sqlite_settings"],
        "$.environment.identity.sqlite_settings",
        minimum=7,
        maximum=7,
    )
    setting_names: list[str] = []
    for index, row in enumerate(settings):
        context = f"$.environment.identity.sqlite_settings[{index}]"
        setting = _object(row, context, {"name", "value"})
        setting_names.append(_identifier(setting["name"], f"{context}.name"))
        _text(setting["value"], f"{context}.value", maximum=128)
    _require_ordered_unique(setting_names, "$.environment.identity.sqlite_settings")
    required_settings = {
        "cache_size",
        "journal_mode",
        "mmap_size",
        "page_size",
        "synchronous",
        "temp_store",
        "wal_autocheckpoint",
    }
    if set(setting_names) != required_settings:
        raise DecisionEvidenceContractError(
            "$.environment.identity.sqlite_settings must contain the pinned seven settings"
        )
    expected_digest = shared.canonical_sha256(identity)
    if (
        _sha256(
            environment["fingerprint_sha256"],
            "$.environment.fingerprint_sha256",
        )
        != expected_digest
    ):
        raise DecisionEvidenceContractError("environment fingerprint SHA-256 is stale")
    return identity


def _validate_fixtures(
    value: object,
    artifacts: _ArtifactIndex,
) -> Mapping[str, _FixtureIdentity]:
    rows = _list(value, "$.fixtures", minimum=3, maximum=3)
    fixture_ids: list[str] = []
    fixtures: dict[str, _FixtureIdentity] = {}
    for index, row in enumerate(rows):
        context = f"$.fixtures[{index}]"
        fixture = _object(
            row,
            context,
            {
                "fixture_id",
                "fixture_revision",
                "manifest_input_id",
                "model_calls",
                "oracle_input_id",
                "source_bytes",
                "source_records",
            },
        )
        fixture_id = _identifier(fixture["fixture_id"], f"{context}.fixture_id")
        fixture_ids.append(fixture_id)
        if fixture_id not in _SCALE_MODEL_CALLS:
            raise DecisionEvidenceContractError(f"{context}.fixture_id is unsupported")
        if fixture["fixture_revision"] != shared.FIXTURE_REVISION:
            raise DecisionEvidenceContractError(
                f"{context}.fixture_revision must be {shared.FIXTURE_REVISION}"
            )
        if (
            _integer(
                fixture["model_calls"],
                f"{context}.model_calls",
                minimum=1,
            )
            != _SCALE_MODEL_CALLS[fixture_id]
        ):
            raise DecisionEvidenceContractError(
                f"{context}.model_calls does not match the required scale"
            )
        _integer(fixture["source_records"], f"{context}.source_records", minimum=1)
        _integer(fixture["source_bytes"], f"{context}.source_bytes", minimum=1)
        manifest = artifacts.use(
            fixture["manifest_input_id"],
            context=f"{context}.manifest_input_id",
            direction="input",
            kinds=frozenset({"fixture_manifest"}),
        )
        oracle = artifacts.use(
            fixture["oracle_input_id"],
            context=f"{context}.oracle_input_id",
            direction="input",
            kinds=frozenset({"fixture_oracle"}),
        )
        fixtures[fixture_id] = _FixtureIdentity(
            fixture_id=fixture_id,
            manifest_sha256=manifest.canonical_sha256,
            oracle_sha256=oracle.canonical_sha256,
        )
    if tuple(fixture_ids) != _SCALE_ORDER:
        raise DecisionEvidenceContractError(
            "$.fixtures must be ordered standard, production, growth"
        )
    return fixtures


def _validate_workload(
    value: object,
    artifacts: _ArtifactIndex,
    environment: Mapping[str, Any],
) -> _WorkloadIdentity:
    workload = _object(
        value,
        "$.workload",
        {
            "case_count",
            "contract_version",
            "matrix_input_id",
            "physical_cores",
            "workload_id",
        },
    )
    _identifier(workload["workload_id"], "$.workload.workload_id")
    if workload["contract_version"] != shared.CANDIDATE_ADAPTER_CONTRACT_VERSION:
        raise DecisionEvidenceContractError("workload contract version is unsupported")
    matrix_artifact = artifacts.use(
        workload["matrix_input_id"],
        context="$.workload.matrix_input_id",
        direction="input",
        kinds=frozenset({"workload_matrix"}),
    )
    physical_cores = _integer(
        workload["physical_cores"],
        "$.workload.physical_cores",
        minimum=1,
        maximum=1_024,
    )
    if physical_cores != environment["physical_cores"]:
        raise DecisionEvidenceContractError(
            "workload physical cores differ from environment identity"
        )
    return _WorkloadIdentity(
        case_count=_integer(
            workload["case_count"],
            "$.workload.case_count",
            minimum=1,
            maximum=512,
        ),
        matrix_sha256=matrix_artifact.canonical_sha256,
    )


def _validate_qualification_runs(
    value: object,
    artifacts: _ArtifactIndex,
    fixtures: Mapping[str, _FixtureIdentity],
    *,
    workload_case_count: int,
) -> Mapping[str, _QualificationRun]:
    rows = _list(
        value,
        "$.qualification_runs",
        minimum=1,
        maximum=MAX_QUALIFICATION_RUNS,
    )
    run_ids: list[str] = []
    runs: dict[str, _QualificationRun] = {}
    all_case_ids: set[str] = set()
    for index, row in enumerate(rows):
        context = f"$.qualification_runs[{index}]"
        run = _object(
            row,
            context,
            {
                "candidate_ids",
                "case_ids",
                "case_ids_sha256",
                "fixture_id",
                "invocation_input_id",
                "measurements_output_id",
                "profiled",
                "repetitions",
                "run_id",
                "speed_claim",
                "summary_output_id",
            },
        )
        run_id = _identifier(run["run_id"], f"{context}.run_id")
        run_ids.append(run_id)
        candidate_ids = tuple(
            _string_list(
                run["candidate_ids"],
                f"{context}.candidate_ids",
                minimum=1,
                maximum=3,
                item_maximum=1,
            )
        )
        if any(candidate_id not in _CANDIDATE_IDS for candidate_id in candidate_ids):
            raise DecisionEvidenceContractError(f"{context}.candidate_ids is unsupported")
        _require_ordered_unique(candidate_ids, f"{context}.candidate_ids")
        fixture_id = _identifier(run["fixture_id"], f"{context}.fixture_id")
        if fixture_id not in fixtures:
            raise DecisionEvidenceContractError(f"{context}.fixture_id is unknown")
        case_ids = _string_list(
            run["case_ids"],
            f"{context}.case_ids",
            minimum=1,
            maximum=512,
            item_maximum=128,
        )
        for case_id in case_ids:
            _identifier(case_id, f"{context}.case_ids")
        _require_ordered_unique(case_ids, f"{context}.case_ids")
        if _sha256(run["case_ids_sha256"], f"{context}.case_ids_sha256") != (
            shared.canonical_sha256(case_ids)
        ):
            raise DecisionEvidenceContractError(f"{context}.case_ids_sha256 is stale")
        repetitions = _integer(
            run["repetitions"],
            f"{context}.repetitions",
            minimum=1,
            maximum=100,
        )
        profiled = _boolean(run["profiled"], f"{context}.profiled")
        speed_claim = _boolean(run["speed_claim"], f"{context}.speed_claim")
        if speed_claim and (profiled or repetitions < 5):
            raise DecisionEvidenceContractError(
                f"{context} speed claim must use five unprofiled repetitions"
            )
        artifacts.use(
            run["invocation_input_id"],
            context=f"{context}.invocation_input_id",
            direction="input",
            kinds=frozenset({"qualification_invocation"}),
        )
        artifacts.use(
            run["measurements_output_id"],
            context=f"{context}.measurements_output_id",
            direction="output",
            kinds=frozenset({"qualification_measurements"}),
        )
        artifacts.use(
            run["summary_output_id"],
            context=f"{context}.summary_output_id",
            direction="output",
            kinds=frozenset({"qualification_summary"}),
        )
        runs[run_id] = _QualificationRun(
            run_id=run_id,
            candidate_ids=candidate_ids,
            fixture_id=fixture_id,
            case_ids=frozenset(case_ids),
        )
        all_case_ids.update(case_ids)
    _require_ordered_unique(run_ids, "$.qualification_runs")
    if len(all_case_ids) > workload_case_count:
        raise DecisionEvidenceContractError(
            "qualification runs name more cases than the workload matrix"
        )
    return runs


def _validate_candidates(
    value: object,
    artifacts: _ArtifactIndex,
    fixtures: Mapping[str, _FixtureIdentity],
    qualification_runs: Mapping[str, _QualificationRun],
    *,
    code_commit: str,
    selected_candidate: str,
) -> tuple[Mapping[str, _CandidateEvidence], Mapping[str, tuple[str, ...]]]:
    rows = _list(value, "$.candidates", minimum=3, maximum=3)
    candidate_ids: list[str] = []
    failure_ids_seen: set[str] = set()
    candidates: dict[str, _CandidateEvidence] = {}
    for index, row in enumerate(rows):
        context = f"$.candidates[{index}]"
        candidate = _object(
            row,
            context,
            {
                "candidate_id",
                "eligible",
                "failures",
                "qualification_run_ids",
                "score_inputs",
                "score_results",
            },
        )
        candidate_id = _candidate_id(candidate["candidate_id"], f"{context}.candidate_id")
        candidate_ids.append(candidate_id)
        eligible = _boolean(candidate["eligible"], f"{context}.eligible")
        run_ids = _string_list(
            candidate["qualification_run_ids"],
            f"{context}.qualification_run_ids",
            minimum=1,
            maximum=MAX_QUALIFICATION_RUNS,
            item_maximum=128,
        )
        _require_ordered_unique(run_ids, f"{context}.qualification_run_ids")
        candidate_case_ids: set[str] = set()
        for run_id in run_ids:
            run = qualification_runs.get(run_id)
            if run is None or candidate_id not in run.candidate_ids:
                raise DecisionEvidenceContractError(
                    f"{context} references qualification run not containing candidate"
                )
            candidate_case_ids.update(run.case_ids)
        failure_ids = _validate_failures(
            candidate["failures"],
            artifacts,
            context=f"{context}.failures",
            eligible=eligible,
            candidate_case_ids=candidate_case_ids,
            global_ids=failure_ids_seen,
        )
        score_inputs = _validate_score_inputs(
            candidate["score_inputs"],
            fixtures,
            candidate_id=candidate_id,
            code_commit=code_commit,
            candidate_case_ids=candidate_case_ids,
            context=f"{context}.score_inputs",
        )
        score_results = _validate_score_results(
            candidate["score_results"],
            artifacts,
            score_inputs=score_inputs,
            failure_ids=failure_ids,
            eligible=eligible,
            context=f"{context}.score_results",
        )
        candidates[candidate_id] = _CandidateEvidence(
            candidate_id=candidate_id,
            eligible=eligible,
            failure_ids=failure_ids,
            score_inputs=score_inputs,
            score_results=score_results,
        )
    if tuple(candidate_ids) != _CANDIDATE_IDS:
        raise DecisionEvidenceContractError("$.candidates must be ordered A, C, D")
    if not candidates[selected_candidate].eligible:
        raise DecisionEvidenceContractError("selected candidate is not eligible")

    rankings: dict[str, tuple[str, ...]] = {}
    eligible_candidates = tuple(
        candidate for candidate in candidates.values() if candidate.eligible
    )
    if not eligible_candidates:
        raise DecisionEvidenceContractError("at least one candidate must be eligible")
    for scale in _SCALE_ORDER:
        ranked = shared.rank_candidates(
            candidate.score_inputs[scale] for candidate in eligible_candidates
        )
        rankings[scale] = tuple(result.candidate_id for result in ranked)
        for rank, result in enumerate(ranked, start=1):
            recorded = candidates[result.candidate_id].score_results[scale]
            if recorded["status"] != "ranked":
                raise DecisionEvidenceContractError(
                    f"eligible candidate {result.candidate_id} lacks ranked score result"
                )
            if recorded["rank"] != rank:
                raise DecisionEvidenceContractError(
                    f"candidate {result.candidate_id} {scale} rank is stale"
                )
            expected_score = _canonical_decimal(result.weighted_score)
            if recorded["weighted_score"] != expected_score:
                raise DecisionEvidenceContractError(
                    f"candidate {result.candidate_id} {scale} weighted score is stale"
                )
    return candidates, rankings


def _validate_failures(
    value: object,
    artifacts: _ArtifactIndex,
    *,
    context: str,
    eligible: bool,
    candidate_case_ids: set[str],
    global_ids: set[str],
) -> tuple[str, ...]:
    rows = _list(value, context, minimum=0, maximum=32)
    failure_ids: list[str] = []
    for index, row in enumerate(rows):
        item_context = f"{context}[{index}]"
        failure = _object(
            row,
            item_context,
            {
                "case_id",
                "comparison",
                "detail_code",
                "failure_id",
                "gate",
                "metric",
                "observed",
                "output_artifact_id",
                "required",
            },
        )
        failure_id = _identifier(failure["failure_id"], f"{item_context}.failure_id")
        if failure_id in global_ids:
            raise DecisionEvidenceContractError(f"failure ID duplicated: {failure_id}")
        global_ids.add(failure_id)
        failure_ids.append(failure_id)
        case_id = _identifier(failure["case_id"], f"{item_context}.case_id")
        if case_id not in candidate_case_ids:
            raise DecisionEvidenceContractError(
                f"{item_context}.case_id is absent from candidate qualification runs"
            )
        if failure["gate"] not in _FAILURE_GATES:
            raise DecisionEvidenceContractError(f"{item_context}.gate is unsupported")
        _identifier(failure["detail_code"], f"{item_context}.detail_code")
        metric = _text(failure["metric"], f"{item_context}.metric", maximum=64)
        metric_contract = _FAILURE_METRICS.get(metric)
        if metric_contract is None:
            raise DecisionEvidenceContractError(f"{item_context}.metric is unsupported")
        metric_type, comparison = metric_contract
        if failure["comparison"] != comparison:
            raise DecisionEvidenceContractError(
                f"{item_context}.comparison is incompatible with metric"
            )
        if metric_type == "boolean":
            observed_boolean = _boolean(
                failure["observed"],
                f"{item_context}.observed",
            )
            required_boolean = _boolean(
                failure["required"],
                f"{item_context}.required",
            )
            failed = observed_boolean != required_boolean
        else:
            observed_integer = _integer(
                failure["observed"],
                f"{item_context}.observed",
                minimum=0,
            )
            required_integer = _integer(
                failure["required"],
                f"{item_context}.required",
                minimum=0,
            )
            failed = observed_integer > required_integer
        if not failed:
            raise DecisionEvidenceContractError(
                f"{item_context} does not describe an actual hard-gate failure"
            )
        artifacts.use(
            failure["output_artifact_id"],
            context=f"{item_context}.output_artifact_id",
            direction="output",
            kinds=frozenset(
                {
                    "crash_measurements",
                    "qualification_measurements",
                    "qualification_summary",
                    "query_plan_measurements",
                }
            ),
        )
    _require_ordered_unique(failure_ids, context)
    if eligible and failure_ids:
        raise DecisionEvidenceContractError(f"{context} must be empty for eligible candidate")
    if not eligible and not failure_ids:
        raise DecisionEvidenceContractError(f"{context} must name why eliminated candidate failed")
    return tuple(failure_ids)


def _validate_score_inputs(
    value: object,
    fixtures: Mapping[str, _FixtureIdentity],
    *,
    candidate_id: str,
    code_commit: str,
    candidate_case_ids: set[str],
    context: str,
) -> Mapping[str, shared.CandidateScoreInput]:
    rows = _list(value, context, minimum=3, maximum=3)
    scales: list[str] = []
    score_inputs: dict[str, shared.CandidateScoreInput] = {}
    for index, row in enumerate(rows):
        item_context = f"{context}[{index}]"
        score = _object(
            row,
            item_context,
            {"dimensions", "fixture_id", "input_sha256", "scale"},
        )
        scale = _identifier(score["scale"], f"{item_context}.scale")
        fixture_id = _identifier(score["fixture_id"], f"{item_context}.fixture_id")
        if scale not in _SCALE_ORDER or fixture_id != scale:
            raise DecisionEvidenceContractError(
                f"{item_context} scale and fixture_id must identify the same required scale"
            )
        scales.append(scale)
        dimensions = _list(
            score["dimensions"],
            f"{item_context}.dimensions",
            minimum=len(_SCORE_DIMENSIONS),
            maximum=len(_SCORE_DIMENSIONS),
        )
        dimension_names: list[str] = []
        costs: list[shared.DimensionCost] = []
        for dimension_index, row_value in enumerate(dimensions):
            dimension_context = f"{item_context}.dimensions[{dimension_index}]"
            dimension = _object(
                row_value,
                dimension_context,
                {"dimension", "source_case_ids", "value"},
            )
            dimension_name = _text(
                dimension["dimension"],
                f"{dimension_context}.dimension",
                maximum=96,
            )
            if dimension_name not in _SCORE_DIMENSIONS:
                raise DecisionEvidenceContractError(f"{dimension_context}.dimension is unsupported")
            dimension_names.append(dimension_name)
            source_case_ids = _string_list(
                dimension["source_case_ids"],
                f"{dimension_context}.source_case_ids",
                minimum=1,
                maximum=64,
                item_maximum=128,
            )
            for case_id in source_case_ids:
                _identifier(case_id, f"{dimension_context}.source_case_ids")
                if case_id not in candidate_case_ids:
                    raise DecisionEvidenceContractError(
                        f"{dimension_context} cites an unqualified source case"
                    )
            _require_ordered_unique(
                source_case_ids,
                f"{dimension_context}.source_case_ids",
            )
            decimal_value = _decimal(
                dimension["value"],
                f"{dimension_context}.value",
                minimum=Decimal(0),
            )
            costs.append(
                shared.DimensionCost(
                    dimension=shared.ScoreDimension(dimension_name),
                    value=decimal_value,
                    source_case_ids=tuple(source_case_ids),
                )
            )
        if tuple(dimension_names) != _SCORE_DIMENSIONS:
            raise DecisionEvidenceContractError(
                f"{item_context}.dimensions must use canonical dimension ordering"
            )
        fixture = fixtures[fixture_id]
        score_input = shared.CandidateScoreInput(
            candidate_id=candidate_id,
            fixture_manifest_digest=fixture.manifest_sha256,
            fixture_oracle_digest=fixture.oracle_sha256,
            code_commit=code_commit,
            scale=scale,
            costs=tuple(costs),
        )
        if _sha256(score["input_sha256"], f"{item_context}.input_sha256") != (score_input.digest):
            raise DecisionEvidenceContractError(f"{item_context}.input_sha256 is stale")
        score_inputs[scale] = score_input
    if tuple(scales) != _SCALE_ORDER:
        raise DecisionEvidenceContractError(
            f"{context} must be ordered standard, production, growth"
        )
    return score_inputs


def _validate_score_results(
    value: object,
    artifacts: _ArtifactIndex,
    *,
    score_inputs: Mapping[str, shared.CandidateScoreInput],
    failure_ids: tuple[str, ...],
    eligible: bool,
    context: str,
) -> Mapping[str, Mapping[str, Any]]:
    rows = _list(value, context, minimum=3, maximum=3)
    scales: list[str] = []
    results: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        item_context = f"{context}[{index}]"
        if not isinstance(row, dict):
            raise DecisionEvidenceContractError(f"{item_context} must be an object")
        status = row.get("status")
        if status == "ranked":
            result = _object(
                row,
                item_context,
                {
                    "input_sha256",
                    "output_artifact_id",
                    "rank",
                    "scale",
                    "status",
                    "weighted_score",
                },
            )
            if not eligible:
                raise DecisionEvidenceContractError(
                    f"{item_context} eliminated candidate cannot be ranked"
                )
            result["rank"] = _integer(
                result["rank"],
                f"{item_context}.rank",
                minimum=1,
                maximum=3,
            )
            result["weighted_score"] = _canonical_decimal(
                _decimal(
                    result["weighted_score"],
                    f"{item_context}.weighted_score",
                    minimum=Decimal(0),
                    maximum=Decimal(100),
                )
            )
        elif status == "eliminated":
            result = _object(
                row,
                item_context,
                {
                    "elimination_failure_ids",
                    "input_sha256",
                    "output_artifact_id",
                    "scale",
                    "status",
                },
            )
            if eligible:
                raise DecisionEvidenceContractError(
                    f"{item_context} eligible candidate cannot be eliminated"
                )
            recorded_failure_ids = _string_list(
                result["elimination_failure_ids"],
                f"{item_context}.elimination_failure_ids",
                minimum=1,
                maximum=32,
                item_maximum=128,
            )
            if tuple(recorded_failure_ids) != failure_ids:
                raise DecisionEvidenceContractError(
                    f"{item_context}.elimination_failure_ids is stale"
                )
        else:
            raise DecisionEvidenceContractError(f"{item_context}.status is unsupported")
        scale = _identifier(result["scale"], f"{item_context}.scale")
        if scale not in score_inputs:
            raise DecisionEvidenceContractError(f"{item_context}.scale is unsupported")
        scales.append(scale)
        if _sha256(result["input_sha256"], f"{item_context}.input_sha256") != (
            score_inputs[scale].digest
        ):
            raise DecisionEvidenceContractError(
                f"{item_context}.input_sha256 does not match score input"
            )
        artifacts.use(
            result["output_artifact_id"],
            context=f"{item_context}.output_artifact_id",
            direction="output",
            kinds=frozenset({"score_result"}),
        )
        results[scale] = result
    if tuple(scales) != _SCALE_ORDER:
        raise DecisionEvidenceContractError(
            f"{context} must be ordered standard, production, growth"
        )
    return results


def _validate_sensitivity(
    value: object,
    *,
    rankings: Mapping[str, tuple[str, ...]],
    selected_candidate: str,
) -> None:
    rows = _list(value, "$.sensitivity", minimum=3, maximum=3)
    scales: list[str] = []
    for index, row in enumerate(rows):
        context = f"$.sensitivity[{index}]"
        sensitivity = _object(
            row,
            context,
            {
                "model_calls",
                "ranked_candidate_ids",
                "scale",
                "selected_candidate",
                "selection_survives",
            },
        )
        scale = _identifier(sensitivity["scale"], f"{context}.scale")
        if scale not in rankings:
            raise DecisionEvidenceContractError(f"{context}.scale is unsupported")
        scales.append(scale)
        if (
            _integer(sensitivity["model_calls"], f"{context}.model_calls", minimum=1)
            != _SCALE_MODEL_CALLS[scale]
        ):
            raise DecisionEvidenceContractError(
                f"{context}.model_calls does not match sensitivity scale"
            )
        ranked = tuple(
            _string_list(
                sensitivity["ranked_candidate_ids"],
                f"{context}.ranked_candidate_ids",
                minimum=1,
                maximum=3,
                item_maximum=1,
            )
        )
        if ranked != rankings[scale]:
            raise DecisionEvidenceContractError(f"{context}.ranked_candidate_ids is stale")
        if sensitivity["selected_candidate"] != selected_candidate:
            raise DecisionEvidenceContractError(
                f"{context}.selected_candidate differs from decision"
            )
        if ranked[0] != selected_candidate:
            raise DecisionEvidenceContractError(f"{context} does not rank selected candidate first")
        if (
            _boolean(
                sensitivity["selection_survives"],
                f"{context}.selection_survives",
            )
            is not True
        ):
            raise DecisionEvidenceContractError(
                f"{context} must prove selection survives sensitivity"
            )
    if tuple(scales) != _SCALE_ORDER:
        raise DecisionEvidenceContractError(
            "$.sensitivity must be ordered standard, production, growth"
        )


def _validate_query_plans(
    value: object,
    artifacts: _ArtifactIndex,
    fixtures: Mapping[str, _FixtureIdentity],
    qualification_runs: Mapping[str, _QualificationRun],
) -> None:
    rows = _list(value, "$.query_plans", minimum=1, maximum=MAX_QUERY_PLANS)
    case_ids: list[str] = []
    question_ids: set[str] = set()
    for index, row in enumerate(rows):
        context = f"$.query_plans[{index}]"
        query = _object(
            row,
            context,
            {
                "answer_correct",
                "approved_plan_counts",
                "fixture_id",
                "mcp_latency_p95_ns",
                "observed_plan_counts",
                "oracle_equivalent",
                "output_artifact_id",
                "performance_class",
                "plan_id",
                "qualification_run_id",
                "query_case_id",
                "question_id",
                "repetitions",
                "response_bytes_max",
                "selector_pages_gap_free",
                "sql_latency_p95_ns",
            },
        )
        case_id = _identifier(query["query_case_id"], f"{context}.query_case_id")
        case_ids.append(case_id)
        question_id = _text(query["question_id"], f"{context}.question_id", maximum=16)
        if not _QUESTION_ID.fullmatch(question_id) or question_id not in _REQUIRED_QUESTION_IDS:
            raise DecisionEvidenceContractError(f"{context}.question_id is unsupported")
        question_ids.add(question_id)
        plan_id = _identifier(query["plan_id"], f"{context}.plan_id")
        performance_class = _text(
            query["performance_class"],
            f"{context}.performance_class",
            maximum=4,
        )
        expected_plan, expected_class = shared.QUESTION_WORKLOAD_CONTRACTS[question_id]
        if (plan_id, performance_class) != (expected_plan, expected_class):
            raise DecisionEvidenceContractError(
                f"{context} plan identity differs from frozen question workload"
            )
        fixture_id = _identifier(query["fixture_id"], f"{context}.fixture_id")
        if fixture_id not in fixtures:
            raise DecisionEvidenceContractError(f"{context}.fixture_id is unknown")
        run = _qualification_case(
            query["qualification_run_id"],
            case_id,
            qualification_runs,
            context=f"{context}.qualification_run_id",
        )
        if run.fixture_id != fixture_id:
            raise DecisionEvidenceContractError(f"{context} fixture differs from qualification run")
        _validate_plan_counts(
            query["approved_plan_counts"],
            query["observed_plan_counts"],
            context=context,
        )
        _integer(query["repetitions"], f"{context}.repetitions", minimum=5, maximum=100)
        _integer(
            query["sql_latency_p95_ns"],
            f"{context}.sql_latency_p95_ns",
            minimum=0,
        )
        _integer(
            query["mcp_latency_p95_ns"],
            f"{context}.mcp_latency_p95_ns",
            minimum=0,
        )
        _integer(
            query["response_bytes_max"],
            f"{context}.response_bytes_max",
            minimum=0,
        )
        for field_name in (
            "answer_correct",
            "oracle_equivalent",
            "selector_pages_gap_free",
        ):
            if _boolean(query[field_name], f"{context}.{field_name}") is not True:
                raise DecisionEvidenceContractError(f"{context}.{field_name} must be proven true")
        artifacts.use(
            query["output_artifact_id"],
            context=f"{context}.output_artifact_id",
            direction="output",
            kinds=frozenset({"query_plan_measurements"}),
        )
    _require_ordered_unique(case_ids, "$.query_plans")
    missing = sorted(_REQUIRED_QUESTION_IDS - question_ids)
    if missing:
        raise DecisionEvidenceContractError(
            f"query plan evidence missing required question IDs: {', '.join(missing)}"
        )


def _validate_plan_counts(approved: object, observed: object, *, context: str) -> None:
    approved_counts = _object(
        approved,
        f"{context}.approved_plan_counts",
        _PLAN_COUNTER_FIELDS,
    )
    observed_counts = _object(
        observed,
        f"{context}.observed_plan_counts",
        _PLAN_COUNTER_FIELDS,
    )
    for field_name in sorted(_PLAN_COUNTER_FIELDS):
        limit = _integer(
            approved_counts[field_name],
            f"{context}.approved_plan_counts.{field_name}",
            minimum=0,
            maximum=1_000_000,
        )
        actual = _integer(
            observed_counts[field_name],
            f"{context}.observed_plan_counts.{field_name}",
            minimum=0,
            maximum=1_000_000,
        )
        if actual > limit:
            raise DecisionEvidenceContractError(
                f"{context}.observed_plan_counts.{field_name} exceeds approval"
            )


def _validate_crash_observations(
    value: object,
    artifacts: _ArtifactIndex,
    candidates: Mapping[str, _CandidateEvidence],
    qualification_runs: Mapping[str, _QualificationRun],
) -> None:
    rows = _list(
        value,
        "$.crash_observations",
        minimum=1,
        maximum=MAX_CRASH_OBSERVATIONS,
    )
    observation_ids: list[str] = []
    candidate_cases: dict[str, set[str]] = {candidate_id: set() for candidate_id in _CANDIDATE_IDS}
    for index, row in enumerate(rows):
        context = f"$.crash_observations[{index}]"
        observation = _object(
            row,
            context,
            {
                "boundary",
                "candidate_id",
                "case_id",
                "fault",
                "mode",
                "observation_id",
                "output_artifact_id",
                "process",
                "qualification_run_id",
                "recovery",
            },
        )
        observation_id = _identifier(
            observation["observation_id"],
            f"{context}.observation_id",
        )
        observation_ids.append(observation_id)
        candidate_id = _candidate_id(observation["candidate_id"], f"{context}.candidate_id")
        case_id = _identifier(observation["case_id"], f"{context}.case_id")
        if case_id in candidate_cases[candidate_id]:
            raise DecisionEvidenceContractError(
                f"crash case duplicated for candidate {candidate_id}: {case_id}"
            )
        candidate_cases[candidate_id].add(case_id)
        _qualification_case(
            observation["qualification_run_id"],
            case_id,
            qualification_runs,
            context=f"{context}.qualification_run_id",
            candidate_id=candidate_id,
        )
        mode = observation["mode"]
        if mode == "process_termination":
            boundary = _text(observation["boundary"], f"{context}.boundary", maximum=64)
            if boundary not in shared.CRASH_BOUNDARIES or observation["fault"] is not None:
                raise DecisionEvidenceContractError(
                    f"{context} process termination boundary/fault is invalid"
                )
            if case_id != f"crash.terminate.{boundary}":
                raise DecisionEvidenceContractError(
                    f"{context}.case_id differs from termination boundary"
                )
            _validate_process_termination(observation["process"], context=context)
        elif mode == "injected_fault":
            fault = _text(observation["fault"], f"{context}.fault", maximum=64)
            if fault not in shared.CRASH_FAULTS or observation["boundary"] is not None:
                raise DecisionEvidenceContractError(
                    f"{context} injected fault boundary/fault is invalid"
                )
            if case_id != f"crash.fault.{fault}":
                raise DecisionEvidenceContractError(
                    f"{context}.case_id differs from injected fault"
                )
            process = _object(
                observation["process"],
                f"{context}.process",
                {"status"},
            )
            if process["status"] != "not_applicable":
                raise DecisionEvidenceContractError(
                    f"{context}.process must be not_applicable for injected fault"
                )
        else:
            raise DecisionEvidenceContractError(f"{context}.mode is unsupported")
        _validate_recovery(observation["recovery"], context=context)
        artifacts.use(
            observation["output_artifact_id"],
            context=f"{context}.output_artifact_id",
            direction="output",
            kinds=frozenset({"crash_measurements"}),
        )
    _require_ordered_unique(observation_ids, "$.crash_observations")

    required_cases = {
        *(f"crash.terminate.{boundary}" for boundary in shared.CRASH_BOUNDARIES),
        *(f"crash.fault.{fault}" for fault in shared.CRASH_FAULTS),
    }
    for candidate_id, candidate in candidates.items():
        if candidate.eligible and candidate_cases[candidate_id] != required_cases:
            missing = sorted(required_cases - candidate_cases[candidate_id])
            extra = sorted(candidate_cases[candidate_id] - required_cases)
            raise DecisionEvidenceContractError(
                f"eligible candidate {candidate_id} crash matrix incomplete; "
                f"missing={missing}, extra={extra}"
            )


def _validate_process_termination(value: object, *, context: str) -> None:
    process = _object(
        value,
        f"{context}.process",
        {
            "boundary_reached",
            "exit_kind",
            "return_code",
            "signal",
            "status",
            "termination_observed",
            "worker_pid",
            "worker_started",
        },
    )
    if process["status"] != "observed":
        raise DecisionEvidenceContractError(f"{context}.process.status must be observed")
    if _boolean(process["worker_started"], f"{context}.process.worker_started") is not True:
        raise DecisionEvidenceContractError(f"{context}.process worker start was not observed")
    if (
        _boolean(
            process["boundary_reached"],
            f"{context}.process.boundary_reached",
        )
        is not True
    ):
        raise DecisionEvidenceContractError(f"{context}.process boundary was not observed")
    if (
        _boolean(
            process["termination_observed"],
            f"{context}.process.termination_observed",
        )
        is not True
    ):
        raise DecisionEvidenceContractError(
            f"{context}.process termination was asserted rather than observed"
        )
    _integer(process["worker_pid"], f"{context}.process.worker_pid", minimum=1)
    return_code = _integer(
        process["return_code"],
        f"{context}.process.return_code",
        minimum=-255,
        maximum=255,
    )
    if return_code == 0:
        raise DecisionEvidenceContractError(
            f"{context}.process return code does not prove termination"
        )
    exit_kind = process["exit_kind"]
    if exit_kind == "signal":
        if process["signal"] not in {"SIGKILL", "SIGTERM"}:
            raise DecisionEvidenceContractError(f"{context}.process signal is unsupported")
    elif exit_kind == "forced_exit":
        if process["signal"] is not None:
            raise DecisionEvidenceContractError(
                f"{context}.process forced_exit cannot claim a signal"
            )
    else:
        raise DecisionEvidenceContractError(f"{context}.process exit_kind is unsupported")


def _validate_recovery(value: object, *, context: str) -> None:
    recovery = _object(
        value,
        f"{context}.recovery",
        {
            "abandoned_artifact_disposition",
            "candidate_publication_committed",
            "post_recovery_query_sha256",
            "prior_publication_queryable",
            "prior_publication_sha256",
            "rollback_available",
            "rollback_publication_sha256",
            "sidecar_terminal_state",
            "subsequent_operation_succeeds",
        },
    )
    for field_name in (
        "prior_publication_queryable",
        "rollback_available",
        "subsequent_operation_succeeds",
    ):
        if _boolean(recovery[field_name], f"{context}.recovery.{field_name}") is not True:
            raise DecisionEvidenceContractError(
                f"{context}.recovery.{field_name} must be proven true"
            )
    _boolean(
        recovery["candidate_publication_committed"],
        f"{context}.recovery.candidate_publication_committed",
    )
    for field_name in (
        "post_recovery_query_sha256",
        "prior_publication_sha256",
        "rollback_publication_sha256",
    ):
        _sha256(recovery[field_name], f"{context}.recovery.{field_name}")
    if recovery["prior_publication_sha256"] != recovery["rollback_publication_sha256"]:
        raise DecisionEvidenceContractError(
            f"{context}.recovery rollback does not identify prior publication"
        )
    _identifier(
        recovery["sidecar_terminal_state"],
        f"{context}.recovery.sidecar_terminal_state",
    )
    _identifier(
        recovery["abandoned_artifact_disposition"],
        f"{context}.recovery.abandoned_artifact_disposition",
    )


def _validate_agent_perf(
    value: object,
    artifacts: _ArtifactIndex,
    fixtures: Mapping[str, _FixtureIdentity],
    qualification_runs: Mapping[str, _QualificationRun],
    *,
    workload_matrix_sha256: str,
    selected_candidate: str,
) -> None:
    rows = _list(value, "$.agent_perf", minimum=1, maximum=3)
    candidate_ids: list[str] = []
    run_ids: set[str] = set()
    for index, row in enumerate(rows):
        context = f"$.agent_perf[{index}]"
        evidence = _object(
            row,
            context,
            {
                "candidate_id",
                "hotspots",
                "measurements_output_id",
                "profiled_run",
                "profiler",
                "qualification_run_id",
                "unprofiled_runs",
                "workload",
                "workload_input_id",
            },
        )
        candidate_id = _candidate_id(evidence["candidate_id"], f"{context}.candidate_id")
        candidate_ids.append(candidate_id)
        run = _qualification_case(
            evidence["qualification_run_id"],
            "agent_perf.standard_cpu_attribution",
            qualification_runs,
            context=f"{context}.qualification_run_id",
            candidate_id=candidate_id,
        )
        if run.fixture_id != "standard":
            raise DecisionEvidenceContractError(f"{context} must use standard fixture")
        workload = _validate_agent_perf_workload(
            evidence["workload"],
            fixtures=fixtures,
            artifacts=artifacts,
            workload_input_id=evidence["workload_input_id"],
            candidate_id=candidate_id,
            workload_matrix_sha256=workload_matrix_sha256,
            context=f"{context}.workload",
        )
        profiler = _object(
            evidence["profiler"],
            f"{context}.profiler",
            {"name", "version"},
        )
        if profiler["name"] != "agent-perf":
            raise DecisionEvidenceContractError(f"{context}.profiler.name must be agent-perf")
        _identifier(profiler["version"], f"{context}.profiler.version")
        profiled_run = _object(
            evidence["profiled_run"],
            f"{context}.profiled_run",
            {"process_cpu_ns", "run_id", "wall_time_ns"},
        )
        profiled_run_id = _identifier(
            profiled_run["run_id"],
            f"{context}.profiled_run.run_id",
        )
        if profiled_run_id in run_ids:
            raise DecisionEvidenceContractError(f"Agent Perf run ID duplicated: {profiled_run_id}")
        run_ids.add(profiled_run_id)
        _integer(
            profiled_run["wall_time_ns"],
            f"{context}.profiled_run.wall_time_ns",
            minimum=1,
        )
        _integer(
            profiled_run["process_cpu_ns"],
            f"{context}.profiled_run.process_cpu_ns",
            minimum=1,
        )
        unprofiled = _list(
            evidence["unprofiled_runs"],
            f"{context}.unprofiled_runs",
            minimum=int(workload["minimum_unprofiled_runs"]),
            maximum=100,
        )
        unprofiled_ids: list[str] = []
        for run_index, run_value in enumerate(unprofiled):
            run_context = f"{context}.unprofiled_runs[{run_index}]"
            sample = _object(run_value, run_context, {"run_id", "wall_time_ns"})
            sample_id = _identifier(sample["run_id"], f"{run_context}.run_id")
            if sample_id in run_ids:
                raise DecisionEvidenceContractError(f"Agent Perf run ID duplicated: {sample_id}")
            run_ids.add(sample_id)
            unprofiled_ids.append(sample_id)
            _integer(sample["wall_time_ns"], f"{run_context}.wall_time_ns", minimum=1)
        _require_ordered_unique(unprofiled_ids, f"{context}.unprofiled_runs")
        _validate_hotspots(evidence["hotspots"], context=f"{context}.hotspots")
        artifacts.use(
            evidence["measurements_output_id"],
            context=f"{context}.measurements_output_id",
            direction="output",
            kinds=frozenset({"agent_perf_measurements"}),
        )
    _require_ordered_unique(candidate_ids, "$.agent_perf")
    if selected_candidate not in candidate_ids:
        raise DecisionEvidenceContractError("Agent Perf evidence must include selected candidate")


def _validate_agent_perf_workload(
    value: object,
    *,
    fixtures: Mapping[str, _FixtureIdentity],
    artifacts: _ArtifactIndex,
    workload_input_id: object,
    candidate_id: str,
    workload_matrix_sha256: str,
    context: str,
) -> Mapping[str, Any]:
    workload = _object(
        value,
        context,
        {
            "candidate_id",
            "command_argv",
            "environment",
            "fixture_manifest_digest",
            "fixture_oracle_digest",
            "fixture_profile",
            "fixture_revision",
            "minimum_unprofiled_runs",
            "profile_is_attribution_only",
            "schema",
            "synthetic_only",
            "version",
            "workload_id",
            "workload_matrix_digest",
        },
    )
    if workload["schema"] != shared.AGENT_PERF_WORKLOAD_SCHEMA or workload["version"] != 1:
        raise DecisionEvidenceContractError(f"{context} schema/version is unsupported")
    if workload["candidate_id"] != candidate_id:
        raise DecisionEvidenceContractError(f"{context}.candidate_id differs from evidence")
    if (
        workload["fixture_profile"] != "standard"
        or workload["fixture_revision"] != shared.FIXTURE_REVISION
        or workload["workload_id"] != "build.scale.standard"
    ):
        raise DecisionEvidenceContractError(f"{context} must use exact CK-04 standard workload")
    standard = fixtures["standard"]
    if (
        workload["fixture_manifest_digest"] != standard.manifest_sha256
        or workload["fixture_oracle_digest"] != standard.oracle_sha256
    ):
        raise DecisionEvidenceContractError(f"{context} fixture digests are stale")
    if (
        _sha256(
            workload["workload_matrix_digest"],
            f"{context}.workload_matrix_digest",
        )
        != workload_matrix_sha256
    ):
        raise DecisionEvidenceContractError(
            f"{context}.workload_matrix_digest differs from decision workload"
        )
    if _boolean(workload["synthetic_only"], f"{context}.synthetic_only") is not True:
        raise DecisionEvidenceContractError(f"{context} must be synthetic only")
    if (
        _boolean(
            workload["profile_is_attribution_only"],
            f"{context}.profile_is_attribution_only",
        )
        is not True
    ):
        raise DecisionEvidenceContractError(f"{context} profile must be attribution only")
    _integer(
        workload["minimum_unprofiled_runs"],
        f"{context}.minimum_unprofiled_runs",
        minimum=5,
        maximum=100,
    )
    _validate_agent_perf_command(workload["command_argv"], context=context)
    environment = _object_mapping(workload["environment"], f"{context}.environment")
    for name, item in environment.items():
        if not _ENVIRONMENT_NAME.fullmatch(name):
            raise DecisionEvidenceContractError(
                f"{context}.environment contains invalid key {name!r}"
            )
        if any(part in name for part in _SECRET_ENVIRONMENT_PARTS):
            raise DecisionEvidenceContractError(
                f"{context}.environment contains secret-like key {name!r}"
            )
        _text(item, f"{context}.environment.{name}", maximum=512)
    artifact = artifacts.use(
        workload_input_id,
        context=f"{context}.workload_input_id",
        direction="input",
        kinds=frozenset({"agent_perf_workload"}),
    )
    if artifact.canonical_sha256 != shared.canonical_sha256(workload):
        raise DecisionEvidenceContractError(
            f"{context} canonical workload hash differs from input artifact"
        )
    return workload


def _validate_agent_perf_command(value: object, *, context: str) -> None:
    command = _string_list(
        value,
        f"{context}.command_argv",
        minimum=1,
        maximum=32,
        item_maximum=512,
    )
    if Path(command[0]).name in _SHELL_PROGRAMS or "-c" in command:
        raise DecisionEvidenceContractError(f"{context}.command_argv invokes a shell")
    if any(
        argument.startswith(("/", "~"))
        or any(operator in argument for operator in ("&&", "||", "$(", "`"))
        for argument in command
    ):
        raise DecisionEvidenceContractError(
            f"{context}.command_argv contains unsafe path or shell token"
        )
    placeholders = {argument for argument in command if argument.startswith("{")}
    if placeholders != _WORKLOAD_PLACEHOLDERS:
        raise DecisionEvidenceContractError(
            f"{context}.command_argv must use exact workload placeholders"
        )


def _validate_hotspots(value: object, *, context: str) -> None:
    rows = _list(value, context, minimum=1, maximum=50)
    symbols: set[str] = set()
    for index, row in enumerate(rows):
        item_context = f"{context}[{index}]"
        hotspot = _object(
            row,
            item_context,
            {"python_cpu_percent", "rank", "source", "symbol"},
        )
        rank = _integer(hotspot["rank"], f"{item_context}.rank", minimum=1, maximum=50)
        if rank != index + 1:
            raise DecisionEvidenceContractError(f"{context} ranks must be contiguous")
        symbol = _text(hotspot["symbol"], f"{item_context}.symbol", maximum=256)
        if not _SYMBOL.fullmatch(symbol):
            raise DecisionEvidenceContractError(
                f"{item_context}.symbol must be a safe Python symbol"
            )
        if symbol in symbols:
            raise DecisionEvidenceContractError(f"{context} contains duplicate symbol")
        symbols.add(symbol)
        source = _text(hotspot["source"], f"{item_context}.source", maximum=256)
        if source.startswith(("/", "~")) or ".." in Path(source).parts:
            raise DecisionEvidenceContractError(
                f"{item_context}.source must be a safe repository-relative path"
            )
        _decimal(
            hotspot["python_cpu_percent"],
            f"{item_context}.python_cpu_percent",
            minimum=Decimal(0),
            maximum=Decimal(100),
        )


def _validate_dbhub(
    value: object,
    artifacts: _ArtifactIndex,
    qualification_runs: Mapping[str, _QualificationRun],
) -> bool:
    dbhub = _object(
        value,
        "$.dbhub",
        {
            "engine_level_read_only",
            "input_artifact_id",
            "output_artifact_id",
            "package",
            "package_integrity",
            "snapshot_sha256_after",
            "snapshot_sha256_before",
            "tool_level_read_only",
            "trials",
            "version",
        },
    )
    if (
        dbhub["package"] != shared.DBHUB_PACKAGE
        or dbhub["version"] != shared.DBHUB_VERSION
        or dbhub["package_integrity"] != shared.DBHUB_NPM_INTEGRITY
    ):
        raise DecisionEvidenceContractError("DBHub package identity is not pinned 0.24.0")
    before = _sha256(dbhub["snapshot_sha256_before"], "$.dbhub.snapshot_sha256_before")
    after = _sha256(dbhub["snapshot_sha256_after"], "$.dbhub.snapshot_sha256_after")
    if before != after:
        raise DecisionEvidenceContractError("DBHub disposable snapshot changed")
    if _boolean(dbhub["tool_level_read_only"], "$.dbhub.tool_level_read_only") is not True:
        raise DecisionEvidenceContractError("DBHub tool-level read-only proof is missing")
    if _boolean(dbhub["engine_level_read_only"], "$.dbhub.engine_level_read_only") is not False:
        raise DecisionEvidenceContractError(
            "DBHub 0.24.0 cannot claim engine-level read-only SQLite access"
        )
    artifacts.use(
        dbhub["input_artifact_id"],
        context="$.dbhub.input_artifact_id",
        direction="input",
        kinds=frozenset({"dbhub_invocation"}),
    )
    artifacts.use(
        dbhub["output_artifact_id"],
        context="$.dbhub.output_artifact_id",
        direction="output",
        kinds=frozenset({"dbhub_measurements"}),
    )
    trials = _list(dbhub["trials"], "$.dbhub.trials", minimum=4, maximum=4)
    trial_ids: list[str] = []
    combinations: set[tuple[str, str]] = set()
    sample_ids_seen: set[str] = set()
    result_identity: tuple[int, str] | None = None
    tokens_unavailable = False
    for index, row in enumerate(trials):
        context = f"$.dbhub.trials[{index}]"
        trial = _object(
            row,
            context,
            {
                "correct_route",
                "mode",
                "model_class",
                "model_tokens",
                "qualification_run_id",
                "samples",
                "selected_tool",
                "trial_id",
            },
        )
        trial_id = _identifier(trial["trial_id"], f"{context}.trial_id")
        trial_ids.append(trial_id)
        model_class = _text(trial["model_class"], f"{context}.model_class", maximum=32)
        mode = _text(trial["mode"], f"{context}.mode", maximum=32)
        combination = (model_class, mode)
        if (
            model_class not in shared.DBHUB_MODEL_CLASSES
            or mode not in shared.DBHUB_TRIAL_MODES
            or combination in combinations
        ):
            raise DecisionEvidenceContractError(f"{context} model/mode is unsupported or duplicate")
        combinations.add(combination)
        case_id = f"dbhub.{mode}.{model_class}"
        _qualification_case(
            trial["qualification_run_id"],
            case_id,
            qualification_runs,
            context=f"{context}.qualification_run_id",
        )
        _identifier(trial["selected_tool"], f"{context}.selected_tool")
        if _boolean(trial["correct_route"], f"{context}.correct_route") is not True:
            raise DecisionEvidenceContractError(f"{context}.correct_route must be true")
        samples = _list(trial["samples"], f"{context}.samples", minimum=5, maximum=100)
        sample_ids: list[str] = []
        for sample_index, sample_value in enumerate(samples):
            sample_context = f"{context}.samples[{sample_index}]"
            sample = _object(
                sample_value,
                sample_context,
                {
                    "correct",
                    "mcp_calls",
                    "process_cpu_ns",
                    "response_bytes",
                    "result_rows",
                    "result_sha256",
                    "sample_id",
                    "scanned_rows",
                    "sql_statements",
                    "wall_time_ns",
                },
            )
            sample_id = _identifier(sample["sample_id"], f"{sample_context}.sample_id")
            if sample_id in sample_ids_seen:
                raise DecisionEvidenceContractError(f"DBHub sample ID duplicated: {sample_id}")
            sample_ids_seen.add(sample_id)
            sample_ids.append(sample_id)
            _integer(sample["wall_time_ns"], f"{sample_context}.wall_time_ns", minimum=1)
            _integer(
                sample["process_cpu_ns"],
                f"{sample_context}.process_cpu_ns",
                minimum=1,
            )
            _integer(sample["scanned_rows"], f"{sample_context}.scanned_rows", minimum=0)
            _integer(
                sample["sql_statements"],
                f"{sample_context}.sql_statements",
                minimum=1,
            )
            expected_calls = 2 if mode == "generic" else 1
            if (
                _integer(sample["mcp_calls"], f"{sample_context}.mcp_calls", minimum=1)
                != expected_calls
            ):
                raise DecisionEvidenceContractError(
                    f"{sample_context}.mcp_calls differs from DBHub route contract"
                )
            _integer(sample["response_bytes"], f"{sample_context}.response_bytes", minimum=1)
            result_rows = _integer(
                sample["result_rows"],
                f"{sample_context}.result_rows",
                minimum=1,
                maximum=shared.DBHUB_MAX_ROW_CAP,
            )
            result_sha256 = _sha256(
                sample["result_sha256"],
                f"{sample_context}.result_sha256",
            )
            if _boolean(sample["correct"], f"{sample_context}.correct") is not True:
                raise DecisionEvidenceContractError(f"{sample_context}.correct must be true")
            current_identity = (result_rows, result_sha256)
            if result_identity is None:
                result_identity = current_identity
            elif current_identity != result_identity:
                raise DecisionEvidenceContractError(
                    "DBHub routes did not return identical correct result"
                )
        _require_ordered_unique(sample_ids, f"{context}.samples")
        tokens_unavailable = (
            _validate_model_tokens(trial["model_tokens"], context=f"{context}.model_tokens")
            or tokens_unavailable
        )
    _require_ordered_unique(trial_ids, "$.dbhub.trials")
    expected_combinations = {
        (model_class, mode)
        for model_class in shared.DBHUB_MODEL_CLASSES
        for mode in shared.DBHUB_TRIAL_MODES
    }
    if combinations != expected_combinations:
        raise DecisionEvidenceContractError("DBHub four-trial matrix is incomplete")
    return tokens_unavailable


def _validate_model_tokens(value: object, *, context: str) -> bool:
    if not isinstance(value, dict):
        raise DecisionEvidenceContractError(f"{context} must be an object")
    status = value.get("status")
    if status == "available":
        tokens = _object(
            value,
            context,
            {
                "cached_input_tokens",
                "input_tokens",
                "output_tokens",
                "reasoning_tokens",
                "status",
            },
        )
        for field_name in (
            "cached_input_tokens",
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
        ):
            _integer(tokens[field_name], f"{context}.{field_name}", minimum=0)
        return False
    if status == "unavailable":
        unavailable = _object(value, context, {"reason_code", "status"})
        if unavailable["reason_code"] not in {
            "host_does_not_report",
            "telemetry_not_exposed",
            "tooling_does_not_report",
        }:
            raise DecisionEvidenceContractError(f"{context}.reason_code is unsupported")
        return True
    raise DecisionEvidenceContractError(f"{context}.status is unsupported")


def _validate_limitations(
    value: object,
    artifacts: _ArtifactIndex,
    *,
    require_dbhub_token_limitation: bool,
) -> None:
    rows = _list(value, "$.limitations", minimum=1, maximum=MAX_LIMITATIONS)
    limitation_ids: list[str] = []
    dbhub_token_limitation = False
    for index, row in enumerate(rows):
        context = f"$.limitations[{index}]"
        limitation = _object(
            row,
            context,
            {
                "area",
                "category",
                "evidence_output_ids",
                "limitation_id",
                "owner_packet_ids",
                "summary",
            },
        )
        limitation_id = _identifier(
            limitation["limitation_id"],
            f"{context}.limitation_id",
        )
        limitation_ids.append(limitation_id)
        area = _identifier(limitation["area"], f"{context}.area")
        if limitation["category"] not in {
            "durability",
            "implementation_seam",
            "measurement",
            "resource_usage",
            "telemetry_unavailable",
            "variance",
        }:
            raise DecisionEvidenceContractError(f"{context}.category is unsupported")
        _text(limitation["summary"], f"{context}.summary", maximum=500)
        packet_ids = _string_list(
            limitation["owner_packet_ids"],
            f"{context}.owner_packet_ids",
            minimum=1,
            maximum=12,
            item_maximum=5,
        )
        if any(not _PACKET_ID.fullmatch(packet_id) for packet_id in packet_ids):
            raise DecisionEvidenceContractError(
                f"{context}.owner_packet_ids contains invalid packet"
            )
        _require_ordered_unique(packet_ids, f"{context}.owner_packet_ids")
        output_ids = _string_list(
            limitation["evidence_output_ids"],
            f"{context}.evidence_output_ids",
            minimum=1,
            maximum=32,
            item_maximum=128,
        )
        _require_ordered_unique(output_ids, f"{context}.evidence_output_ids")
        for output_id in output_ids:
            artifacts.use(
                output_id,
                context=f"{context}.evidence_output_ids",
                direction="output",
                kinds=frozenset(_REQUIRED_ARTIFACT_KINDS["output"]),
            )
        if area == "dbhub.model_tokens" and limitation["category"] == "telemetry_unavailable":
            dbhub_token_limitation = True
    _require_ordered_unique(limitation_ids, "$.limitations")
    if require_dbhub_token_limitation and not dbhub_token_limitation:
        raise DecisionEvidenceContractError(
            "unavailable DBHub model tokens require explicit limitation"
        )


def _qualification_case(
    run_id_value: object,
    case_id: str,
    qualification_runs: Mapping[str, _QualificationRun],
    *,
    context: str,
    candidate_id: str | None = None,
) -> _QualificationRun:
    run_id = _identifier(run_id_value, context)
    run = qualification_runs.get(run_id)
    if run is None or case_id not in run.case_ids:
        raise DecisionEvidenceContractError(
            f"{context} does not identify a run containing {case_id}"
        )
    if candidate_id is not None and candidate_id not in run.candidate_ids:
        raise DecisionEvidenceContractError(
            f"{context} run does not contain candidate {candidate_id}"
        )
    return run


def _scan_json_value(value: object, *, context: str) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise DecisionEvidenceContractError(f"{context} contains non-string key")
            _scan_json_value(item, context=f"{context}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _scan_json_value(item, context=f"{context}[{index}]")
        return
    if isinstance(value, str):
        if len(value) > MAX_TEXT_LENGTH:
            raise DecisionEvidenceContractError(f"{context} string is oversized")
        if any(ord(character) < 32 for character in value):
            raise DecisionEvidenceContractError(f"{context} contains raw/control text")
        if _PRIVATE_PATH.search(value):
            raise DecisionEvidenceContractError(f"{context} contains absolute/private path")
        if _SECRET_VALUE.search(value):
            raise DecisionEvidenceContractError(f"{context} contains secret-like string")
        return
    if value is None or type(value) in {bool, int}:
        return
    raise DecisionEvidenceContractError(
        f"{context} contains unsupported JSON telemetry type {type(value).__name__}"
    )


def _decode_json_object(payload: bytes, *, artifact: str) -> dict[str, Any]:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DecisionEvidenceContractError(
                    f"{artifact} contains duplicate object key {key!r}"
                )
            result[key] = value
        return result

    try:
        decoded = json.loads(payload, object_pairs_hook=reject_duplicate_keys)
    except DecisionEvidenceContractError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DecisionEvidenceContractError(f"{artifact} is not valid UTF-8 JSON") from error
    if not isinstance(decoded, dict):
        raise DecisionEvidenceContractError(f"{artifact} must contain one JSON object")
    return decoded


def _object(
    value: object,
    context: str,
    fields: set[str] | frozenset[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionEvidenceContractError(f"{context} must be an object")
    expected = set(fields)
    actual = set(value)
    missing = sorted(expected - actual)
    unsupported = sorted(actual - expected)
    if missing or unsupported:
        raise DecisionEvidenceContractError(
            f"{context} fields differ; missing={missing}, unsupported={unsupported}"
        )
    return value


def _object_mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DecisionEvidenceContractError(f"{context} must be an object")
    if len(value) > 64:
        raise DecisionEvidenceContractError(f"{context} contains too many fields")
    return value


def _list(
    value: object,
    context: str,
    *,
    minimum: int,
    maximum: int,
) -> list[Any]:
    if not isinstance(value, list):
        raise DecisionEvidenceContractError(f"{context} must be an array")
    if not minimum <= len(value) <= maximum:
        raise DecisionEvidenceContractError(
            f"{context} must contain between {minimum} and {maximum} items"
        )
    return value


def _string_list(
    value: object,
    context: str,
    *,
    minimum: int,
    maximum: int,
    item_maximum: int,
) -> list[str]:
    rows = _list(value, context, minimum=minimum, maximum=maximum)
    return [
        _text(item, f"{context}[{index}]", maximum=item_maximum) for index, item in enumerate(rows)
    ]


def _text(value: object, context: str, *, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise DecisionEvidenceContractError(
            f"{context} must be a non-empty string at most {maximum} characters"
        )
    return value


def _identifier(value: object, context: str) -> str:
    text = _text(value, context, maximum=128)
    if not _SAFE_ID.fullmatch(text):
        raise DecisionEvidenceContractError(f"{context} must be a safe identifier")
    return text


def _candidate_id(value: object, context: str) -> str:
    candidate_id = _text(value, context, maximum=1)
    if candidate_id not in _CANDIDATE_IDS:
        raise DecisionEvidenceContractError(f"{context} must be A, C, or D")
    return candidate_id


def _commit(value: object, context: str) -> str:
    commit = _text(value, context, maximum=40)
    if not _HEX_40.fullmatch(commit):
        raise DecisionEvidenceContractError(f"{context} must be full lowercase SHA-1")
    return commit


def _sha256(value: object, context: str) -> str:
    digest = _text(value, context, maximum=64)
    if not _HEX_64.fullmatch(digest):
        raise DecisionEvidenceContractError(f"{context} must be lowercase SHA-256")
    return digest


def _integer(
    value: object,
    context: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if type(value) is not int:
        raise DecisionEvidenceContractError(f"{context} must be an integer")
    admitted_maximum = (2**63) - 1 if maximum is None else maximum
    if value < minimum or value > admitted_maximum:
        raise DecisionEvidenceContractError(f"{context} integer is outside admitted bounds")
    return value


def _boolean(value: object, context: str) -> bool:
    if type(value) is not bool:
        raise DecisionEvidenceContractError(f"{context} must be a boolean")
    return value


def _decimal(
    value: object,
    context: str,
    *,
    minimum: Decimal,
    maximum: Decimal | None = None,
) -> Decimal:
    text = _text(value, context, maximum=64)
    if not _DECIMAL_TEXT.fullmatch(text):
        raise DecisionEvidenceContractError(f"{context} must be canonical decimal text")
    try:
        number = Decimal(text)
    except InvalidOperation as error:
        raise DecisionEvidenceContractError(f"{context} decimal is invalid") from error
    if text != _canonical_decimal(number):
        raise DecisionEvidenceContractError(f"{context} decimal text is not canonical")
    if number < minimum or (maximum is not None and number > maximum):
        raise DecisionEvidenceContractError(f"{context} decimal is outside admitted bounds")
    return number


def _canonical_decimal(value: Decimal) -> str:
    if value == value.to_integral():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")


def _date_text(value: object, context: str) -> str:
    text = _text(value, context, maximum=10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise DecisionEvidenceContractError(f"{context} must be ISO date") from error
    if parsed.isoformat() != text:
        raise DecisionEvidenceContractError(f"{context} must be canonical ISO date")
    return text


def _require_ordered_unique(values: Sequence[str], context: str) -> None:
    if len(set(values)) != len(values):
        raise DecisionEvidenceContractError(f"{context} contains duplicate IDs")
    if list(values) != sorted(values):
        raise DecisionEvidenceContractError(f"{context} is not canonically ordered")


def _load_draft(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise DecisionEvidenceContractError(f"cannot read draft {path.name!r}") from error
    if len(payload) > MAX_MANIFEST_BYTES * 2:
        raise DecisionEvidenceContractError("decision evidence draft is oversized")
    return _decode_json_object(payload, artifact="decision evidence draft")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate or canonically write CK-04 aggregate decision evidence."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate an existing canonical manifest")
    validate.add_argument("manifest", type=Path)
    write = commands.add_parser("write", help="validate a JSON draft and write canonical output")
    write.add_argument("--input", required=True, type=Path)
    write.add_argument("--output", required=True, type=Path)
    write.add_argument("--replace", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "validate":
            build = validate_manifest_path(arguments.manifest)
        else:
            build = write_manifest(
                _load_draft(arguments.input),
                arguments.output,
                replace=arguments.replace,
            )
    except DecisionEvidenceContractError as error:
        parser.error(str(error))
    print(build.sha256)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
