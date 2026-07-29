from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import platform
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import sysconfig
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import shared

INVOCATION_SCHEMA = "codex-usage-tracker.physical-bakeoff-invocation.v1"
SUMMARY_SCHEMA = "codex-usage-tracker.physical-bakeoff-summary.v1"
DETAIL_SCHEMA = "codex-usage-tracker.physical-bakeoff-detail.v1"
MEASUREMENT_FILE = "measurements.jsonl"
DETAIL_FILE = "details.jsonl"
INVOCATION_FILE = "invocation.json"
SUMMARY_FILE = "summary.json"
MAX_SUMMARY_CASES = 512
MAX_DETAIL_RECORDS = 4_096
MAX_DETAIL_FILE_BYTES = 64 * 1024 * 1024
MAX_DETAIL_RECORD_BYTES = 96 * 1024
MAX_ORACLE_RESULT_BYTES = 64 * 1024
MAX_DETAIL_DEPTH = 12
MAX_DETAIL_NODES = 20_000
MAX_DETAIL_CONTAINER_ITEMS = 1_024
MAX_DETAIL_STRING_BYTES = 16 * 1024

CANDIDATE_IDS = ("A", "C", "D")
ROUTINE_CASE_IDS = (
    "build.scale.tiny",
    "query.q-acc-01.warm_first_page",
    "query.q-acc-05.warm_first_page",
    "query.q-alw-01.warm_first_page",
    "query.q-ctx-01.warm_first_page",
    "query.q-ops-04.warm_first_page",
    "query.q-wf-01.warm_first_page",
)

_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX_64 = re.compile(r"[0-9a-f]{64}\Z")
_ABSOLUTE_PATH = re.compile(r"(?:\A(?:/|~/|\\\\|file:///)|\A[A-Za-z]:[\\/])")
_SECRET_VALUE = re.compile(
    r"(?:\A(?:sk-|ghp_|github_pat_|xox[baprs]-|Bearer\s+|AKIA[0-9A-Z]{12})"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
)
_FORBIDDEN_ORACLE_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "client_secret",
        "command_body",
        "command_text",
        "content_body",
        "cookie",
        "credential",
        "credentials",
        "id_token",
        "password",
        "passwd",
        "patch",
        "private_key",
        "prompt",
        "raw_content",
        "reasoning_text",
        "refresh_token",
        "response_text",
        "secret",
        "set_cookie",
        "tool_output",
        "tool_output_body",
    }
)
_DETAIL_FIELDS = frozenset(
    {
        "schema",
        "invocation_digest",
        "execution_index",
        "measurement_identity",
        "measurement_identity_digest",
        "measurement_record_digest",
        "outcome",
        "partial",
        "stop_decision",
        "detail_code",
        "oracle_results",
        "detail_digest",
    }
)
_MEASUREMENT_IDENTITY_FIELDS = frozenset(
    {
        "run_id",
        "candidate_id",
        "case_id",
        "fixture_profile",
        "fixture_manifest_digest",
        "fixture_oracle_digest",
        "repetition",
        "profiled",
        "code_commit",
        "workload_matrix_digest",
        "environment_digest",
        "qualification_model",
    }
)
_RESEARCH_GROUPS = frozenset({shared.WorkloadGroup.DBHUB, shared.WorkloadGroup.AGENT_PERF})
_SQLITE_SETTINGS = (
    ("cache_size", "-20000"),
    ("journal_mode", "wal"),
    ("mmap_size", "0"),
    ("page_size", "4096"),
    ("synchronous", "normal"),
    ("temp_store", "memory"),
    ("wal_autocheckpoint", "1000"),
)

AdapterLoader = Callable[[str], shared.CandidateAdapter]
CollectorFactory = Callable[[Path], shared.MeasurementCollector]


class QualificationContractError(ValueError):
    """The requested bake-off invocation is not exact or safe to execute."""


class QualificationRunFailed(RuntimeError):
    """A recorded candidate run reached a non-admissible outcome."""

    def __init__(self, artifact: QualificationArtifact) -> None:
        super().__init__(f"physical bake-off run {artifact.run_id} failed")
        self.artifact = artifact


@dataclass(frozen=True)
class QualificationConfig:
    fixture_root: Path
    output_root: Path
    run_id: str
    code_commit: str
    candidates: tuple[str, ...] = CANDIDATE_IDS
    case_ids: tuple[str, ...] = ()
    group_ids: tuple[shared.WorkloadGroup, ...] = ()
    repetitions: int = 1
    speed_claim: bool = False
    profiled: bool = False
    allow_large_fixture: bool = False
    all_compatible_cases: bool = False
    include_research: bool = False
    qualification_model: str | None = None
    filesystem_cache_state: str = "uncontrolled"
    retain_run_artifacts: bool = False

    def __post_init__(self) -> None:
        if not _RUN_ID.fullmatch(self.run_id):
            raise QualificationContractError("run ID must be a safe relative path component")
        if not _HEX_40.fullmatch(self.code_commit):
            raise QualificationContractError("code commit must be one full lowercase SHA-1")
        if not self.candidates or len(set(self.candidates)) != len(self.candidates):
            raise QualificationContractError("candidate selection must be nonempty and unique")
        if any(candidate not in CANDIDATE_IDS for candidate in self.candidates):
            raise QualificationContractError("candidate selection must contain only A, C, or D")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise QualificationContractError("case selection must be unique")
        if any(not _CASE_ID.fullmatch(case_id) for case_id in self.case_ids):
            raise QualificationContractError("case IDs must be safe relative path components")
        if len(set(self.group_ids)) != len(self.group_ids):
            raise QualificationContractError("group selection must be unique")
        if any(not isinstance(group, shared.WorkloadGroup) for group in self.group_ids):
            raise QualificationContractError("group selection contains an unknown workload group")
        if self.group_ids and (self.case_ids or self.all_compatible_cases):
            raise QualificationContractError(
                "group selection cannot be combined with explicit cases or all-compatible selection"
            )
        if self.all_compatible_cases and self.case_ids:
            raise QualificationContractError(
                "all-compatible selection cannot be combined with explicit cases"
            )
        if self.repetitions < 1:
            raise QualificationContractError("repetitions must be positive")
        if self.speed_claim and self.repetitions < 5:
            raise QualificationContractError("speed claims require at least five repetitions")
        if self.speed_claim and self.profiled:
            raise QualificationContractError("speed claims must use unprofiled repetitions")
        if self.qualification_model is not None and not self.qualification_model.strip():
            raise QualificationContractError("qualification model cannot be blank")
        if self.filesystem_cache_state not in {"cold", "warm", "uncontrolled"}:
            raise QualificationContractError("filesystem cache state is not recognized")


@dataclass(frozen=True)
class QualificationArtifact:
    run_id: str
    invocation_root: Path
    invocation_path: Path
    measurements_path: Path
    details_path: Path
    summary_path: Path
    status: str
    records: tuple[shared.MeasurementRecord, ...]
    summary: Mapping[str, Any]

    @property
    def successful(self) -> bool:
        return self.status == "passed"


@dataclass(frozen=True)
class _PreparedRun:
    fixture: shared.FixtureBundle
    matrix: shared.WorkloadMatrix
    environment: shared.EnvironmentFingerprint
    candidates: tuple[str, ...]
    cases: tuple[shared.WorkloadCase, ...]


def make_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"qualification-{timestamp}-{secrets.token_hex(4)}"


def discover_code_commit(repository_root: Path) -> str:
    root = repository_root.resolve()
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=normal")
    if status:
        raise QualificationContractError(
            "qualification requires a clean worktree so code_commit is exact"
        )
    commit = _git(root, "rev-parse", "HEAD")
    if not _HEX_40.fullmatch(commit):
        raise QualificationContractError("Git did not return one full commit SHA")
    return commit


def build_environment_fingerprint(
    run_root: Path,
    *,
    filesystem_cache_state: str,
) -> shared.EnvironmentFingerprint:
    resolved = run_root.resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    logical_cores = os.cpu_count() or 1
    physical_cores = min(logical_cores, _physical_core_count(logical_cores))
    compiler_flags = tuple(
        value
        for value in (
            f"implementation={platform.python_implementation()}",
            f"compiler={platform.python_compiler()}",
            f"config_args={sysconfig.get_config_var('CONFIG_ARGS') or 'unknown'}",
            f"optimize={sys.flags.optimize}",
        )
        if value
    )
    return shared.EnvironmentFingerprint(
        python_version=platform.python_version(),
        sqlite_version=sqlite3.sqlite_version,
        operating_system=platform.platform(),
        filesystem=_filesystem_type(resolved),
        cpu_model=_cpu_model(),
        physical_cores=physical_cores,
        logical_cores=logical_cores,
        memory_bytes=_memory_bytes(),
        storage_model=f"device:{resolved.stat().st_dev}:{platform.machine()}",
        compiler_flags=compiler_flags,
        sqlite_settings=_SQLITE_SETTINGS,
        analyze_state="candidate-owned",
        filesystem_cache_state=filesystem_cache_state,
    )


def load_candidate_adapter(candidate_id: str) -> shared.CandidateAdapter:
    if candidate_id not in CANDIDATE_IDS:
        raise QualificationContractError(f"unknown candidate {candidate_id!r}")
    module_name = f"candidate_{candidate_id.lower()}"
    module = importlib.import_module(module_name)
    module_path_text = getattr(module, "__file__", None)
    if not isinstance(module_path_text, str):
        raise QualificationContractError(f"candidate {candidate_id} module has no source path")
    experiment_root = Path(__file__).resolve().parent
    expected_root = (experiment_root / module_name).resolve()
    if not Path(module_path_text).resolve().is_relative_to(expected_root):
        raise QualificationContractError(f"candidate {candidate_id} loaded outside experiment root")
    adapter_type = getattr(module, "Adapter", None)
    if not isinstance(adapter_type, type):
        raise QualificationContractError(f"candidate {candidate_id} has no Adapter type")
    adapter = adapter_type()
    if not isinstance(adapter, shared.CandidateAdapter):
        raise QualificationContractError(f"candidate {candidate_id} violates the adapter protocol")
    if adapter.candidate_id != candidate_id:
        raise QualificationContractError(f"candidate {candidate_id} adapter ID is inconsistent")
    return adapter


def run_qualification(
    config: QualificationConfig,
    *,
    environment: shared.EnvironmentFingerprint | None = None,
    adapter_loader: AdapterLoader = load_candidate_adapter,
    collector_factory: CollectorFactory = shared.MeasurementCollector,
) -> QualificationArtifact:
    prepared = _prepare_run(config, environment=environment)
    planned_executions = len(prepared.candidates) * len(prepared.cases) * config.repetitions
    if planned_executions > MAX_DETAIL_RECORDS:
        raise QualificationContractError("selected matrix exceeds bounded detail capacity")
    adapters = {candidate_id: adapter_loader(candidate_id) for candidate_id in prepared.candidates}
    invocation_root = _create_invocation_root(config.output_root, config.run_id)
    invocation_path = invocation_root / INVOCATION_FILE
    measurements_path = invocation_root / MEASUREMENT_FILE
    details_path = invocation_root / DETAIL_FILE
    summary_path = invocation_root / SUMMARY_FILE
    invocation = _invocation_payload(config, prepared)
    _write_canonical_new(invocation_path, invocation)
    _verify_canonical_file(invocation_path, invocation)
    _create_empty_stream(details_path)
    collector = collector_factory(measurements_path)

    expected_identities: list[shared.MeasurementIdentity] = []
    failure: tuple[str, str, str] | None = None
    optional_skips = 0
    execution_index = 0
    for candidate_id in prepared.candidates:
        adapter = adapters[candidate_id]
        for case in prepared.cases:
            for repetition in range(config.repetitions):
                run_root = _create_case_root(
                    invocation_root,
                    candidate_id=candidate_id,
                    case_id=case.case_id,
                    repetition=repetition,
                )
                identity = _measurement_identity(
                    config,
                    prepared,
                    candidate_id=candidate_id,
                    case=case,
                    repetition=repetition,
                )
                expected_identities.append(identity)
                request = shared.CandidateRequest(
                    case=case,
                    fixture=prepared.fixture,
                    run_root=run_root,
                    repetition=repetition,
                    stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
                )
                measurement_offset = (
                    measurements_path.stat().st_size if measurements_path.exists() else 0
                )
                try:
                    result = shared.execute_measured_candidate(
                        adapter,
                        request,
                        collector,
                        identity,
                    )
                    measurement_payload = _read_appended_measurement(
                        measurements_path,
                        offset=measurement_offset,
                        expected_identity=identity,
                    )
                    detail = _detail_payload(
                        invocation=invocation,
                        execution_index=execution_index,
                        result=result,
                        measurement=measurement_payload,
                    )
                    _append_detail(details_path, detail)
                    execution_index += 1
                except shared.CandidateContractError as error:
                    raise QualificationContractError(
                        f"candidate {candidate_id} violated {case.case_id}: {error}"
                    ) from error
                finally:
                    if not config.retain_run_artifacts:
                        shutil.rmtree(run_root)
                if result.outcome in {shared.RunOutcome.FAILED, shared.RunOutcome.STOPPED}:
                    failure = (
                        candidate_id,
                        case.case_id,
                        result.detail_code or result.outcome.value,
                    )
                    break
                if result.outcome is shared.RunOutcome.UNSUPPORTED:
                    if case.candidate_capability is None:
                        raise QualificationContractError(
                            f"mandatory case {case.case_id} was unsupported"
                        )
                    optional_skips += config.repetitions - repetition - 1
                    break
            if failure is not None:
                break
        if failure is not None:
            break

    records = shared.load_measurements(measurements_path)
    _validate_measurements(
        records,
        expected_identities=tuple(expected_identities),
        config=config,
        prepared=prepared,
    )
    detail_records = load_execution_details(
        details_path,
        measurements_path=measurements_path,
        expected_records=len(records),
    )
    summary = _summary_payload(
        config,
        prepared,
        invocation=invocation,
        records=records,
        failure=failure,
        optional_skips=optional_skips,
        measurements_path=measurements_path,
        details_path=details_path,
        detail_records=detail_records,
    )
    _write_canonical_new(summary_path, summary)
    _verify_canonical_file(summary_path, summary)
    artifact = QualificationArtifact(
        run_id=config.run_id,
        invocation_root=invocation_root,
        invocation_path=invocation_path,
        measurements_path=measurements_path,
        details_path=details_path,
        summary_path=summary_path,
        status=str(summary["status"]),
        records=records,
        summary=summary,
    )
    if failure is not None:
        raise QualificationRunFailed(artifact)
    return artifact


def _prepare_run(
    config: QualificationConfig,
    *,
    environment: shared.EnvironmentFingerprint | None,
) -> _PreparedRun:
    fixture = shared.load_fixture_bundle(config.fixture_root)
    if fixture.profile != "tiny" and not config.allow_large_fixture:
        raise QualificationContractError(
            "non-tiny fixture requires the explicit allow-large-fixture gate"
        )
    if fixture.profile != "tiny" and not (
        config.case_ids or config.group_ids or config.all_compatible_cases
    ):
        raise QualificationContractError(
            "non-tiny fixture requires explicit cases or all-compatible selection"
        )
    fingerprint = environment or build_environment_fingerprint(
        config.output_root,
        filesystem_cache_state=config.filesystem_cache_state,
    )
    if fingerprint.filesystem_cache_state != config.filesystem_cache_state:
        raise QualificationContractError("environment cache state differs from invocation")
    matrix = shared.build_workload_matrix(physical_cores=fingerprint.physical_cores)
    cases = _select_cases(config, fixture=fixture, matrix=matrix)
    candidates = tuple(candidate for candidate in CANDIDATE_IDS if candidate in config.candidates)
    if len(candidates) * len(cases) > MAX_SUMMARY_CASES:
        raise QualificationContractError("selected matrix exceeds bounded summary capacity")
    return _PreparedRun(
        fixture=fixture,
        matrix=matrix,
        environment=fingerprint,
        candidates=candidates,
        cases=cases,
    )


def _select_cases(
    config: QualificationConfig,
    *,
    fixture: shared.FixtureBundle,
    matrix: shared.WorkloadMatrix,
) -> tuple[shared.WorkloadCase, ...]:
    requested = set(config.case_ids)
    if requested:
        unknown = requested - {case.case_id for case in matrix.cases}
        if unknown:
            raise QualificationContractError(f"unknown workload cases: {sorted(unknown)!r}")
        cases = tuple(case for case in matrix.cases if case.case_id in requested)
    elif config.group_ids:
        selected_groups = frozenset(config.group_ids)
        cases = tuple(
            case
            for case in matrix.cases
            if case.group in selected_groups and _case_matches_fixture(case, fixture.profile)
        )
    elif config.all_compatible_cases:
        cases = tuple(
            case
            for case in matrix.cases
            if _case_matches_fixture(case, fixture.profile)
            and (config.include_research or case.group not in _RESEARCH_GROUPS)
        )
    else:
        if fixture.profile != "tiny":
            raise QualificationContractError("routine mode requires the tiny fixture")
        cases = tuple(case for case in matrix.cases if case.case_id in ROUTINE_CASE_IDS)

    if not cases:
        raise QualificationContractError("case selection is empty")
    for case in cases:
        if not _case_matches_fixture(case, fixture.profile):
            declared = case.parameter("profile")
            raise QualificationContractError(
                f"case {case.case_id} requires fixture profile {declared!r}, "
                f"not {fixture.profile!r}"
            )
        if case.group in _RESEARCH_GROUPS and not config.include_research:
            raise QualificationContractError(
                f"research case {case.case_id} requires include-research"
            )
        if config.speed_claim and config.repetitions < max(5, case.minimum_repetitions):
            raise QualificationContractError(
                f"speed claim for {case.case_id} has too few repetitions"
            )
    return cases


def _case_matches_fixture(case: shared.WorkloadCase, fixture_profile: str) -> bool:
    declared = case.parameter("profile")
    return declared is None or declared == fixture_profile


def _invocation_payload(
    config: QualificationConfig,
    prepared: _PreparedRun,
) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": INVOCATION_SCHEMA,
        "run_id": config.run_id,
        "code_commit": config.code_commit,
        "fixture": {
            "profile": prepared.fixture.profile,
            "fixture_revision": prepared.fixture.fixture_revision,
            "manifest_digest": prepared.fixture.manifest_digest,
            "oracle_digest": prepared.fixture.oracle_digest,
        },
        "workload_matrix_digest": prepared.matrix.digest,
        "environment": asdict(prepared.environment),
        "environment_digest": shared.canonical_sha256(asdict(prepared.environment)),
        "candidate_ids": prepared.candidates,
        "case_ids": tuple(case.case_id for case in prepared.cases),
        "group_ids": tuple(group.value for group in config.group_ids),
        "repetitions": config.repetitions,
        "speed_claim": config.speed_claim,
        "profiled": config.profiled,
        "include_research": config.include_research,
        "qualification_model": config.qualification_model,
        "retain_run_artifacts": config.retain_run_artifacts,
        "completion_marker": SUMMARY_FILE,
    }
    return {**base, "invocation_digest": shared.canonical_sha256(base)}


def _measurement_identity(
    config: QualificationConfig,
    prepared: _PreparedRun,
    *,
    candidate_id: str,
    case: shared.WorkloadCase,
    repetition: int,
) -> shared.MeasurementIdentity:
    return shared.MeasurementIdentity(
        run_id=config.run_id,
        candidate_id=candidate_id,
        case_id=case.case_id,
        fixture_profile=prepared.fixture.profile,
        fixture_manifest_digest=prepared.fixture.manifest_digest,
        fixture_oracle_digest=prepared.fixture.oracle_digest,
        repetition=repetition,
        profiled=config.profiled,
        code_commit=config.code_commit,
        workload_matrix_digest=prepared.matrix.digest,
        environment=prepared.environment,
        qualification_model=config.qualification_model,
    )


def _validate_measurements(
    records: Sequence[shared.MeasurementRecord],
    *,
    expected_identities: Sequence[shared.MeasurementIdentity],
    config: QualificationConfig,
    prepared: _PreparedRun,
) -> None:
    actual = tuple(record.identity for record in records)
    expected = tuple(expected_identities)
    if actual != expected:
        raise QualificationContractError("measurement identities differ from execution order")
    allowed_cases = {case.case_id for case in prepared.cases}
    for record in records:
        identity = record.identity
        if (
            identity.run_id != config.run_id
            or identity.code_commit != config.code_commit
            or identity.workload_matrix_digest != prepared.matrix.digest
            or identity.fixture_profile != prepared.fixture.profile
            or identity.fixture_manifest_digest != prepared.fixture.manifest_digest
            or identity.fixture_oracle_digest != prepared.fixture.oracle_digest
            or identity.environment != prepared.environment
            or identity.candidate_id not in prepared.candidates
            or identity.case_id not in allowed_cases
            or identity.repetition >= config.repetitions
        ):
            raise QualificationContractError("measurement identity escaped invocation contract")


def _summary_payload(
    config: QualificationConfig,
    prepared: _PreparedRun,
    *,
    invocation: Mapping[str, object],
    records: Sequence[shared.MeasurementRecord],
    failure: tuple[str, str, str] | None,
    optional_skips: int,
    measurements_path: Path,
    details_path: Path,
    detail_records: Sequence[Mapping[str, Any]],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for candidate_id in prepared.candidates:
        for case in prepared.cases:
            selected = tuple(
                record
                for record in records
                if record.identity.candidate_id == candidate_id
                and record.identity.case_id == case.case_id
            )
            outcomes = Counter(record.outcome.value for record in selected)
            wall_times = tuple(record.wall_time_ns for record in selected)
            distribution = _speed_distribution(
                wall_times,
                enabled=(
                    config.speed_claim
                    and len(selected) == config.repetitions
                    and all(record.outcome is shared.RunOutcome.PASSED for record in selected)
                ),
            )
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "case_id": case.case_id,
                    "mandatory": case.candidate_capability is None,
                    "candidate_capability": case.candidate_capability,
                    "repetitions_planned": config.repetitions,
                    "repetitions_recorded": len(selected),
                    "outcomes": {
                        outcome.value: outcomes[outcome.value] for outcome in shared.RunOutcome
                    },
                    "wall_time_ns_min": min(wall_times) if wall_times else None,
                    "wall_time_ns_max": max(wall_times) if wall_times else None,
                    "wall_time_distribution": distribution,
                }
            )
    measurements_sha256 = hashlib.sha256(measurements_path.read_bytes()).hexdigest()
    details_sha256 = hashlib.sha256(details_path.read_bytes()).hexdigest()
    base: dict[str, object] = {
        "schema": SUMMARY_SCHEMA,
        "status": "failed" if failure is not None else "passed",
        "run_id": config.run_id,
        "invocation_digest": invocation["invocation_digest"],
        "code_commit": config.code_commit,
        "fixture_manifest_digest": prepared.fixture.manifest_digest,
        "fixture_oracle_digest": prepared.fixture.oracle_digest,
        "workload_matrix_digest": prepared.matrix.digest,
        "environment_digest": invocation["environment_digest"],
        "measurement_file": MEASUREMENT_FILE,
        "measurement_sha256": measurements_sha256,
        "records": len(records),
        "details_file": DETAIL_FILE,
        "details_sha256": details_sha256,
        "detail_records": len(detail_records),
        "planned_executions": (len(prepared.candidates) * len(prepared.cases) * config.repetitions),
        "optional_repetitions_skipped": optional_skips,
        "retain_run_artifacts": config.retain_run_artifacts,
        "failure": (
            {
                "candidate_id": failure[0],
                "case_id": failure[1],
                "detail_code": failure[2],
            }
            if failure is not None
            else None
        ),
        "cases": rows,
    }
    return {**base, "summary_digest": shared.canonical_sha256(base)}


def _create_empty_stream(path: Path) -> None:
    try:
        with path.open("xb"):
            pass
    except FileExistsError as error:
        raise QualificationContractError(f"refusing to overwrite {path.name}") from error


def _read_appended_measurement(
    path: Path,
    *,
    offset: int,
    expected_identity: shared.MeasurementIdentity,
) -> dict[str, Any]:
    try:
        with path.open("rb") as source:
            source.seek(0, os.SEEK_END)
            final_size = source.tell()
            if offset < 0 or offset >= final_size:
                raise QualificationContractError(
                    "candidate execution did not append one measurement"
                )
            source.seek(offset)
            appended = source.read()
    except OSError as error:
        raise QualificationContractError("appended measurement cannot be read") from error
    lines = appended.splitlines(keepends=True)
    if len(lines) != 1:
        raise QualificationContractError("candidate execution appended multiple measurements")
    measurement = _load_canonical_object_line(
        lines[0],
        label="appended measurement",
    )
    if measurement.get("schema") != shared.MEASUREMENT_SCHEMA:
        raise QualificationContractError("appended measurement has wrong schema")
    actual_identity = measurement.get("identity")
    expected = json.loads(shared.canonical_json_bytes(asdict(expected_identity)))
    if actual_identity != expected:
        raise QualificationContractError("measurement identities differ from execution order")
    return measurement


def _detail_payload(
    *,
    invocation: Mapping[str, object],
    execution_index: int,
    result: shared.CandidateResult,
    measurement: Mapping[str, Any],
) -> dict[str, object]:
    measurement_identity = _measurement_identity_projection(measurement)
    fixture = invocation.get("fixture")
    if not isinstance(fixture, Mapping):
        raise QualificationContractError("invocation fixture binding is incomplete")
    expected_bindings = {
        "run_id": invocation.get("run_id"),
        "code_commit": invocation.get("code_commit"),
        "fixture_profile": fixture.get("profile"),
        "fixture_manifest_digest": fixture.get("manifest_digest"),
        "fixture_oracle_digest": fixture.get("oracle_digest"),
        "workload_matrix_digest": invocation.get("workload_matrix_digest"),
        "environment_digest": invocation.get("environment_digest"),
    }
    if any(measurement_identity[field] != value for field, value in expected_bindings.items()):
        raise QualificationContractError("measurement identity escaped invocation details")
    if (
        measurement_identity["candidate_id"] != result.candidate_id
        or measurement_identity["case_id"] != result.case_id
        or measurement.get("outcome") != result.outcome.value
        or (
            result.outcome in {shared.RunOutcome.FAILED, shared.RunOutcome.UNSUPPORTED}
            and measurement.get("detail_code") != result.detail_code
        )
    ):
        raise QualificationContractError("candidate result differs from recorded measurement")

    oracle_results = _bounded_oracle_results(result.oracle_results)
    base: dict[str, object] = {
        "schema": DETAIL_SCHEMA,
        "invocation_digest": invocation["invocation_digest"],
        "execution_index": execution_index,
        "measurement_identity": measurement_identity,
        "measurement_identity_digest": shared.canonical_sha256(measurement_identity),
        "measurement_record_digest": shared.canonical_sha256(measurement),
        "outcome": result.outcome.value,
        "partial": measurement.get("partial"),
        "stop_decision": measurement.get("stop_decision"),
        "detail_code": result.detail_code,
        "oracle_results": oracle_results,
    }
    return {**base, "detail_digest": shared.canonical_sha256(base)}


def _measurement_identity_projection(
    measurement: Mapping[str, Any],
) -> dict[str, object]:
    identity = measurement.get("identity")
    if not isinstance(identity, Mapping):
        raise QualificationContractError("measurement identity is missing")
    environment = identity.get("environment")
    if not isinstance(environment, Mapping):
        raise QualificationContractError("measurement environment is missing")
    try:
        projection: dict[str, object] = {
            "run_id": identity["run_id"],
            "candidate_id": identity["candidate_id"],
            "case_id": identity["case_id"],
            "fixture_profile": identity["fixture_profile"],
            "fixture_manifest_digest": identity["fixture_manifest_digest"],
            "fixture_oracle_digest": identity["fixture_oracle_digest"],
            "repetition": identity["repetition"],
            "profiled": identity["profiled"],
            "code_commit": identity["code_commit"],
            "workload_matrix_digest": identity["workload_matrix_digest"],
            "environment_digest": shared.canonical_sha256(environment),
            "qualification_model": identity.get("qualification_model"),
        }
    except KeyError as error:
        raise QualificationContractError("measurement identity is incomplete") from error
    _validate_projected_identity(projection)
    return projection


def _validate_projected_identity(identity: Mapping[str, Any]) -> None:
    if set(identity) != _MEASUREMENT_IDENTITY_FIELDS:
        raise QualificationContractError("detail measurement identity has unknown fields")
    if not isinstance(identity["run_id"], str) or not _RUN_ID.fullmatch(identity["run_id"]):
        raise QualificationContractError("detail run ID is invalid")
    if identity["candidate_id"] not in CANDIDATE_IDS:
        raise QualificationContractError("detail candidate ID is invalid")
    if not isinstance(identity["case_id"], str) or not _CASE_ID.fullmatch(identity["case_id"]):
        raise QualificationContractError("detail case ID is invalid")
    if not isinstance(identity["fixture_profile"], str) or not identity["fixture_profile"].strip():
        raise QualificationContractError("detail fixture profile is invalid")
    for field in (
        "fixture_manifest_digest",
        "fixture_oracle_digest",
        "workload_matrix_digest",
        "environment_digest",
    ):
        if not isinstance(identity[field], str) or not _HEX_64.fullmatch(identity[field]):
            raise QualificationContractError(f"detail {field} is invalid")
    if (
        type(identity["repetition"]) is not int
        or identity["repetition"] < 0
        or type(identity["profiled"]) is not bool
    ):
        raise QualificationContractError("detail repetition/profiled binding is invalid")
    if not isinstance(identity["code_commit"], str) or not _HEX_40.fullmatch(
        identity["code_commit"]
    ):
        raise QualificationContractError("detail code commit is invalid")
    model = identity["qualification_model"]
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise QualificationContractError("detail qualification model is invalid")


def _bounded_oracle_results(
    value: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise QualificationContractError("candidate oracle results must be an object or null")
    node_count = [0]
    normalized = _bounded_oracle_value(value, path="oracle_results", depth=0, nodes=node_count)
    if not isinstance(normalized, dict):
        raise QualificationContractError("candidate oracle results must remain an object")
    if len(shared.canonical_json_bytes(normalized)) > MAX_ORACLE_RESULT_BYTES:
        raise QualificationContractError("candidate oracle results exceed bounded capacity")
    return normalized


def _bounded_oracle_value(
    value: Any,
    *,
    path: str,
    depth: int,
    nodes: list[int],
) -> Any:
    nodes[0] += 1
    if nodes[0] > MAX_DETAIL_NODES:
        raise QualificationContractError("candidate oracle results contain too many values")
    if depth > MAX_DETAIL_DEPTH:
        raise QualificationContractError("candidate oracle results are nested too deeply")
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        if not -(1 << 63) <= value < (1 << 63):
            raise QualificationContractError(f"{path} integer exceeds signed 64-bit range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise QualificationContractError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) > MAX_DETAIL_STRING_BYTES:
            raise QualificationContractError(f"{path} string exceeds bounded capacity")
        if "\x00" in value:
            raise QualificationContractError(f"{path} contains a NUL byte")
        if _ABSOLUTE_PATH.search(value):
            raise QualificationContractError(f"{path} contains a machine-specific path")
        if _SECRET_VALUE.search(value):
            raise QualificationContractError(f"{path} contains a secret-like value")
        return value
    if isinstance(value, Mapping):
        if len(value) > MAX_DETAIL_CONTAINER_ITEMS:
            raise QualificationContractError(f"{path} object exceeds bounded capacity")
        normalized_mapping: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise QualificationContractError(f"{path} keys must be non-empty strings")
            normalized_key = key.lower().replace("-", "_")
            if normalized_key in _FORBIDDEN_ORACLE_KEYS or any(
                normalized_key.endswith(f"_{suffix}") for suffix in _FORBIDDEN_ORACLE_KEYS
            ):
                raise QualificationContractError(f"{path}.{key} is not safe structural evidence")
            if len(key.encode("utf-8")) > 256:
                raise QualificationContractError(f"{path} key exceeds bounded capacity")
            normalized_mapping[key] = _bounded_oracle_value(
                item,
                path=f"{path}.{key}",
                depth=depth + 1,
                nodes=nodes,
            )
        return normalized_mapping
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_DETAIL_CONTAINER_ITEMS:
            raise QualificationContractError(f"{path} sequence exceeds bounded capacity")
        return [
            _bounded_oracle_value(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
                nodes=nodes,
            )
            for index, item in enumerate(value)
        ]
    raise QualificationContractError(f"{path} contains a non-canonical value")


def _append_detail(path: Path, detail: Mapping[str, object]) -> None:
    execution_index = detail.get("execution_index")
    if type(execution_index) is not int:
        raise QualificationContractError("detail execution index is invalid")
    payload = shared.canonical_json_bytes(detail)
    _load_detail_line(payload, index=execution_index)
    try:
        current_size = path.stat().st_size
    except OSError as error:
        raise QualificationContractError("detail file cannot be inspected") from error
    if current_size + len(payload) > MAX_DETAIL_FILE_BYTES:
        raise QualificationContractError("detail file exceeds bounded capacity")
    try:
        with path.open("ab") as output:
            output.write(payload)
    except OSError as error:
        raise QualificationContractError("detail record cannot be appended") from error


def _load_canonical_object_line(line: bytes, *, label: str) -> dict[str, Any]:
    if not line or not line.endswith(b"\n"):
        raise QualificationContractError(f"{label} lacks a final LF")
    try:
        decoded = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualificationContractError(f"{label} is not JSON") from error
    if not isinstance(decoded, dict) or line != shared.canonical_json_bytes(decoded):
        raise QualificationContractError(f"{label} is not canonical JSON")
    return decoded


def _load_detail_line(line: bytes, *, index: int) -> dict[str, Any]:
    if len(line) > MAX_DETAIL_RECORD_BYTES:
        raise QualificationContractError(f"detail line {index + 1} exceeds bounded capacity")
    record = _load_canonical_object_line(line, label=f"detail line {index + 1}")
    if set(record) != _DETAIL_FIELDS or record.get("schema") != DETAIL_SCHEMA:
        raise QualificationContractError(f"detail line {index + 1} has wrong fields")
    if record.get("execution_index") != index:
        raise QualificationContractError(f"detail line {index + 1} is out of order")
    invocation_digest = record.get("invocation_digest")
    if not isinstance(invocation_digest, str) or not _HEX_64.fullmatch(invocation_digest):
        raise QualificationContractError(f"detail line {index + 1} has wrong invocation digest")
    unsigned = dict(record)
    detail_digest = unsigned.pop("detail_digest")
    if not isinstance(detail_digest, str) or not _HEX_64.fullmatch(detail_digest):
        raise QualificationContractError(f"detail line {index + 1} has invalid detail digest")
    if shared.canonical_sha256(unsigned) != detail_digest:
        raise QualificationContractError(f"detail line {index + 1} has wrong detail digest")

    identity = record.get("measurement_identity")
    if not isinstance(identity, Mapping):
        raise QualificationContractError(f"detail line {index + 1} has no measurement identity")
    _validate_projected_identity(identity)
    identity_digest = record.get("measurement_identity_digest")
    if (
        not isinstance(identity_digest, str)
        or not _HEX_64.fullmatch(identity_digest)
        or shared.canonical_sha256(identity) != identity_digest
    ):
        raise QualificationContractError(
            f"detail line {index + 1} has wrong measurement identity digest"
        )
    measurement_digest = record.get("measurement_record_digest")
    if not isinstance(measurement_digest, str) or not _HEX_64.fullmatch(measurement_digest):
        raise QualificationContractError(
            f"detail line {index + 1} has invalid measurement record digest"
        )
    try:
        outcome = shared.RunOutcome(str(record.get("outcome")))
    except ValueError as error:
        raise QualificationContractError(f"detail line {index + 1} has invalid outcome") from error
    partial = record.get("partial")
    stop_decision = record.get("stop_decision")
    if type(partial) is not bool or partial is not (outcome is shared.RunOutcome.STOPPED):
        raise QualificationContractError(f"detail line {index + 1} has invalid partial state")
    if partial:
        if not isinstance(stop_decision, Mapping) or set(stop_decision) != {
            "case_id",
            "maximum",
            "metric",
            "observed",
        }:
            raise QualificationContractError(f"detail line {index + 1} has invalid stop decision")
        if (
            stop_decision["case_id"] != identity["case_id"]
            or type(stop_decision["maximum"]) is not int
            or type(stop_decision["observed"]) is not int
            or not isinstance(stop_decision["metric"], str)
        ):
            raise QualificationContractError(
                f"detail line {index + 1} has invalid stop decision values"
            )
    elif stop_decision is not None:
        raise QualificationContractError(f"detail line {index + 1} has unexpected stop decision")
    detail_code = record.get("detail_code")
    if detail_code is not None and (
        not isinstance(detail_code, str)
        or not detail_code.strip()
        or len(detail_code.encode("utf-8")) > 256
    ):
        raise QualificationContractError(f"detail line {index + 1} has invalid detail code")
    if outcome in {shared.RunOutcome.FAILED, shared.RunOutcome.UNSUPPORTED} and detail_code is None:
        raise QualificationContractError(f"detail line {index + 1} omits its detail code")
    normalized_oracle = _bounded_oracle_results(record.get("oracle_results"))
    if normalized_oracle != record.get("oracle_results"):
        raise QualificationContractError(
            f"detail line {index + 1} has non-canonical oracle results"
        )
    return record


def _load_measurement_lines(path: Path) -> tuple[bytes, ...]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise QualificationContractError("measurement file cannot be read") from error
    lines = tuple(payload.splitlines(keepends=True))
    if any(not line.endswith(b"\n") for line in lines):
        raise QualificationContractError("measurement file contains an incomplete line")
    return lines


def load_execution_details(
    path: Path,
    *,
    measurements_path: Path | None = None,
    expected_sha256: str | None = None,
    expected_records: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Load and verify one bounded canonical execution-detail stream."""
    try:
        size = path.stat().st_size
        payload = path.read_bytes()
    except OSError as error:
        raise QualificationContractError("detail file cannot be read") from error
    if size != len(payload) or size > MAX_DETAIL_FILE_BYTES:
        raise QualificationContractError("detail file exceeds bounded capacity")
    if expected_sha256 is not None:
        if not _HEX_64.fullmatch(expected_sha256):
            raise QualificationContractError("expected detail SHA-256 is invalid")
        if hashlib.sha256(payload).hexdigest() != expected_sha256:
            raise QualificationContractError("detail file SHA-256 differs from summary")
    lines = payload.splitlines(keepends=True)
    if len(lines) > MAX_DETAIL_RECORDS:
        raise QualificationContractError("detail record count exceeds bounded capacity")
    if expected_records is not None and len(lines) != expected_records:
        raise QualificationContractError("detail record count differs from measurements")

    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        record = _load_detail_line(line, index=index)
        records.append(record)

    if measurements_path is not None:
        measurement_lines = _load_measurement_lines(measurements_path)
        if len(measurement_lines) != len(records):
            raise QualificationContractError("detail and measurement record counts differ")
        for index, (detail, measurement_line) in enumerate(
            zip(records, measurement_lines, strict=True)
        ):
            measurement = _load_canonical_object_line(
                measurement_line,
                label=f"measurement line {index + 1}",
            )
            if measurement.get("schema") != shared.MEASUREMENT_SCHEMA:
                raise QualificationContractError(f"measurement line {index + 1} has wrong schema")
            if hashlib.sha256(measurement_line).hexdigest() != detail["measurement_record_digest"]:
                raise QualificationContractError(
                    f"detail line {index + 1} has wrong measurement record digest"
                )
            identity = _measurement_identity_projection(measurement)
            if identity != detail["measurement_identity"]:
                raise QualificationContractError(
                    f"detail line {index + 1} has wrong measurement identity"
                )
    return tuple(records)


def _speed_distribution(
    wall_times: Sequence[int],
    *,
    enabled: bool,
) -> dict[str, object] | None:
    if not enabled:
        return None
    distribution = shared.distribution_summary(wall_times)
    return {
        "sample_count": distribution.sample_count,
        "median_ns": str(distribution.median),
        "p95_ns": str(distribution.p95),
        "maximum_ns": str(distribution.maximum),
        "coefficient_of_variation": str(distribution.coefficient_of_variation),
    }


def _create_invocation_root(output_root: Path, run_id: str) -> Path:
    resolved_output = output_root.resolve()
    resolved_output.mkdir(parents=True, exist_ok=True)
    invocation_root = resolved_output / run_id
    try:
        invocation_root.mkdir()
    except FileExistsError as error:
        raise QualificationContractError(
            f"run directory already exists for {run_id!r}; refusing stale output"
        ) from error
    return invocation_root


def _create_case_root(
    invocation_root: Path,
    *,
    candidate_id: str,
    case_id: str,
    repetition: int,
) -> Path:
    root = (
        invocation_root
        / "runs"
        / f"candidate-{candidate_id.lower()}"
        / case_id
        / f"repetition-{repetition:03d}"
    )
    root.mkdir(parents=True)
    if not root.resolve().is_relative_to(invocation_root.resolve()):
        raise QualificationContractError("candidate run root escaped invocation root")
    return root


def _write_canonical_new(path: Path, payload: Mapping[str, object]) -> None:
    try:
        with path.open("xb") as output:
            output.write(shared.canonical_json_bytes(payload))
    except FileExistsError as error:
        raise QualificationContractError(f"refusing to overwrite {path.name}") from error


def _verify_canonical_file(path: Path, expected: Mapping[str, object]) -> None:
    payload = path.read_bytes()
    if payload != shared.canonical_json_bytes(expected):
        raise QualificationContractError(f"{path.name} is not the current canonical artifact")
    decoded = json.loads(payload)
    if decoded != json.loads(shared.canonical_json_bytes(expected)):
        raise QualificationContractError(f"{path.name} changed after canonical write")


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise QualificationContractError(
            f"Git command failed: {' '.join(arguments)}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _command_text(arguments: tuple[str, ...]) -> str | None:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _physical_core_count(logical_cores: int) -> int:
    if sys.platform == "darwin":
        value = _command_text(("sysctl", "-n", "hw.physicalcpu"))
        if value is not None and value.isdigit():
            return max(1, int(value))
    if sys.platform.startswith("linux"):
        try:
            rows = Path("/proc/cpuinfo").read_text(encoding="utf-8").split("\n\n")
        except OSError:
            rows = []
        cores = {
            (
                _cpuinfo_value(row, "physical id"),
                _cpuinfo_value(row, "core id"),
            )
            for row in rows
            if _cpuinfo_value(row, "processor") is not None
        }
        cores.discard((None, None))
        if cores:
            return len(cores)
    return logical_cores


def _cpuinfo_value(block: str, name: str) -> str | None:
    prefix = f"{name}\t"
    for line in block.splitlines():
        if line.startswith(prefix) and ":" in line:
            return line.split(":", 1)[1].strip()
    return None


def _cpu_model() -> str:
    if sys.platform == "darwin":
        value = _command_text(("sysctl", "-n", "machdep.cpu.brand_string"))
        if value is not None:
            return value
    if sys.platform.startswith("linux"):
        try:
            text = Path("/proc/cpuinfo").read_text(encoding="utf-8")
        except OSError:
            text = ""
        value = _cpuinfo_value(text, "model name")
        if value is not None:
            return value
    return platform.processor() or platform.machine() or "unknown-cpu"


def _memory_bytes() -> int:
    if sys.platform == "darwin":
        value = _command_text(("sysctl", "-n", "hw.memsize"))
        if value is not None and value.isdigit() and int(value) > 0:
            return int(value)
    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        pages = int(os.sysconf("SC_PHYS_PAGES"))
    except (AttributeError, OSError, TypeError, ValueError):
        return 1
    return max(1, page_size * pages)


def _filesystem_type(path: Path) -> str:
    if sys.platform == "darwin":
        value = _command_text(("stat", "-f", "%T", str(path)))
    else:
        value = _command_text(("stat", "-f", "-c", "%T", str(path)))
    return value or f"unknown-{platform.system().lower()}"
