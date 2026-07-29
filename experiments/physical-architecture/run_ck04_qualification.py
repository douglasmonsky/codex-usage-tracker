from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

_EXPERIMENT_ROOT = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _EXPERIMENT_ROOT.parents[1]
if str(_EXPERIMENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENT_ROOT))

qualification = importlib.import_module("qualification")
shared = importlib.import_module("shared")

SUITE_INVOCATION_SCHEMA = "codex-usage-tracker.ck04-qualification-suite-invocation.v1"
SUITE_RESULT_SCHEMA = "codex-usage-tracker.ck04-qualification-suite-result.v1"
TIMEOUT_SCHEMA = "codex-usage-tracker.ck04-qualification-timeout.v1"
SUITE_SUMMARY_SCHEMA = "codex-usage-tracker.ck04-qualification-suite-summary.v1"

INVOCATION_FILE = "suite-invocation.json"
RESULT_STREAM_FILE = "unit-results.jsonl"
RESULT_FILE = "suite-result.json"
TIMEOUT_FILE = "timeout.json"
SUMMARY_FILE = "suite-summary.json"
_CHILD_FILES = (
    qualification.INVOCATION_FILE,
    qualification.MEASUREMENT_FILE,
    qualification.DETAIL_FILE,
    qualification.SUMMARY_FILE,
)
_PROFILES = ("tiny", "standard", "production", "growth")
_DEFAULT_GROUP_SECONDS = {
    shared.WorkloadGroup.ORDINARY_CHANGE: 30.0,
    shared.WorkloadGroup.UNSAFE_CHANGE: 120.0,
    shared.WorkloadGroup.QUERY: 30.0,
    shared.WorkloadGroup.CRASH: 60.0,
    shared.WorkloadGroup.DBHUB: 120.0,
    shared.WorkloadGroup.AGENT_PERF: 120.0,
}
_DEFAULT_PROFILE_SECONDS = {
    "tiny": 30.0,
    "standard": 120.0,
    "production": 180.0,
    "growth": 300.0,
}
_MAX_WATCHDOG_SECONDS = 3_600.0


class SuiteContractError(ValueError):
    """The requested outer qualification suite is not exact or bounded."""


class SuiteRunFailed(RuntimeError):
    """The suite stopped after retaining its canonical partial evidence."""

    def __init__(self, artifact: SuiteArtifact, message: str) -> None:
        super().__init__(message)
        self.artifact = artifact


@dataclass(frozen=True)
class FixtureSpec:
    profile: str
    path: Path | None

    def __post_init__(self) -> None:
        if self.profile not in _PROFILES:
            raise SuiteContractError(f"unsupported fixture profile {self.profile!r}")


@dataclass(frozen=True)
class Watchdog:
    seconds: float
    basis: str


@dataclass(frozen=True)
class SuiteConfig:
    output_root: Path
    code_commit: str
    fixture_specs: tuple[FixtureSpec, ...]
    candidates: tuple[str, ...] = qualification.CANDIDATE_IDS
    case_ids: tuple[str, ...] = ()
    group_ids: tuple[Any, ...] = ()
    suite_repetitions: int = 1
    runner_path: Path = _EXPERIMENT_ROOT / "run_bakeoff.py"
    watchdog_overrides: tuple[str, ...] = ()
    startup_grace_seconds: float = 10.0
    termination_grace_seconds: float = 2.0
    resume_results: tuple[Path, ...] = ()
    include_research: bool = False

    def __post_init__(self) -> None:
        if len(self.code_commit) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_commit
        ):
            raise SuiteContractError("code commit must be one full lowercase SHA-1")
        profiles = tuple(spec.profile for spec in self.fixture_specs)
        if not profiles or len(profiles) != len(set(profiles)):
            raise SuiteContractError("fixture profiles must be nonempty and unique")
        if not self.candidates or len(self.candidates) != len(set(self.candidates)):
            raise SuiteContractError("candidate selection must be nonempty and unique")
        if any(candidate not in qualification.CANDIDATE_IDS for candidate in self.candidates):
            raise SuiteContractError("candidate selection must contain only A, C, or D")
        if len(self.case_ids) != len(set(self.case_ids)):
            raise SuiteContractError("case selection must be unique")
        if len(self.group_ids) != len(set(self.group_ids)) or any(
            not isinstance(group, shared.WorkloadGroup) for group in self.group_ids
        ):
            raise SuiteContractError("group selection must contain unique workload groups")
        if bool(self.case_ids) == bool(self.group_ids):
            raise SuiteContractError("select exactly one of explicit cases or groups")
        if self.suite_repetitions < 1:
            raise SuiteContractError("suite repetitions must be positive")
        _bounded_seconds(self.startup_grace_seconds, label="startup grace", allow_zero=True)
        _bounded_seconds(
            self.termination_grace_seconds,
            label="termination grace",
            allow_zero=False,
        )
        parse_watchdog_overrides(self.watchdog_overrides)


@dataclass(frozen=True)
class SuiteArtifact:
    output_root: Path
    invocation_path: Path
    results_path: Path
    summary_path: Path
    unit_results: tuple[Path, ...]
    status: str


@dataclass(frozen=True)
class _Unit:
    profile: str
    fixture_root: Path
    candidate_id: str
    case: Any
    suite_repetition: int

    @property
    def key(self) -> tuple[str, str, str, int]:
        return (self.profile, self.candidate_id, self.case.case_id, self.suite_repetition)


class _StreamDigest:
    def __init__(self) -> None:
        self.byte_count = 0
        self._digest = hashlib.sha256()

    def consume(self, source: BinaryIO) -> None:
        while chunk := source.read(64 * 1024):
            self.byte_count += len(chunk)
            self._digest.update(chunk)

    def payload(self) -> dict[str, object]:
        return {"byte_count": self.byte_count, "sha256": self._digest.hexdigest()}


def parse_watchdog_overrides(values: Sequence[str]) -> dict[str, float]:
    overrides: dict[str, float] = {}
    valid_groups = {group.value for group in shared.WorkloadGroup}
    for raw in values:
        key, separator, seconds_text = raw.partition("=")
        scope, colon, name = key.partition(":")
        if separator != "=" or colon != ":" or scope not in {"group", "profile"}:
            raise SuiteContractError(
                "watchdog overrides must use group:<name>=SECONDS or profile:<name>=SECONDS"
            )
        if (scope == "group" and name not in valid_groups) or (
            scope == "profile" and name not in _PROFILES
        ):
            raise SuiteContractError(f"unknown watchdog override {key!r}")
        if key in overrides:
            raise SuiteContractError(f"duplicate watchdog override {key!r}")
        try:
            seconds = float(seconds_text)
        except ValueError as error:
            raise SuiteContractError(f"watchdog override {key!r} is not numeric") from error
        overrides[key] = _bounded_seconds(seconds, label=f"watchdog {key}", allow_zero=False)
    return overrides


def resolve_watchdog(
    case: Any,
    *,
    profile: str,
    startup_grace_seconds: float,
    overrides: Mapping[str, float],
) -> Watchdog:
    for limit in case.early_stop_limits:
        if limit.metric is shared.StopMetric.ELAPSED_MS:
            return Watchdog(
                seconds=limit.maximum / 1000 + startup_grace_seconds,
                basis="hard_limit:elapsed_ms",
            )
    group_key = f"group:{case.group.value}"
    profile_key = f"profile:{profile}"
    if group_key in overrides:
        return Watchdog(seconds=overrides[group_key], basis=group_key)
    if profile_key in overrides:
        return Watchdog(seconds=overrides[profile_key], basis=profile_key)
    if case.group is shared.WorkloadGroup.BUILD:
        return Watchdog(seconds=_DEFAULT_PROFILE_SECONDS[profile], basis=profile_key)
    return Watchdog(
        seconds=_DEFAULT_GROUP_SECONDS[case.group],
        basis=group_key,
    )


def run_suite(config: SuiteConfig) -> SuiteArtifact:
    output_root = config.output_root.resolve()
    try:
        output_root.mkdir(parents=True)
    except FileExistsError as error:
        raise SuiteContractError(f"suite output root already exists: {output_root.name}") from error

    invocation_path = output_root / INVOCATION_FILE
    results_path = output_root / RESULT_STREAM_FILE
    summary_path = output_root / SUMMARY_FILE
    unit_result_paths: list[Path] = []
    attempted_units = 0
    passed_units = 0
    resumed_units = 0
    planned_units = 0
    failure: str | None = None
    _create_empty(results_path)

    try:
        fixtures = _materialize_fixtures(config, output_root)
        matrix = _workload_matrix()
        cases = _select_suite_cases(config, matrix)
        units = tuple(
            _Unit(profile, fixture_root, candidate_id, case, repetition)
            for profile, fixture_root in fixtures.items()
            for candidate_id in qualification.CANDIDATE_IDS
            if candidate_id in config.candidates
            for case in cases
            if qualification._case_matches_fixture(case, profile)
            for repetition in range(config.suite_repetitions)
        )
        if not units:
            raise SuiteContractError("suite selection has no fixture-compatible units")
        planned_units = len(units)
        overrides = parse_watchdog_overrides(config.watchdog_overrides)
        invocation = _suite_invocation(config, fixtures, matrix, units, overrides)
        _write_canonical_new(invocation_path, invocation)
        resume_map = _load_resume_results(config, units, matrix.digest)

        for index, unit in enumerate(units):
            unit_root = output_root / "units" / f"{index:06d}"
            unit_root.mkdir(parents=True)
            attempted_units += 1
            if unit.key in resume_map:
                result_path = _copy_resumed_unit(
                    resume_map[unit.key],
                    unit_root=unit_root,
                    unit=unit,
                    code_commit=config.code_commit,
                    workload_digest=matrix.digest,
                )
                resumed_units += 1
            else:
                watchdog = resolve_watchdog(
                    unit.case,
                    profile=unit.profile,
                    startup_grace_seconds=config.startup_grace_seconds,
                    overrides=overrides,
                )
                result_path = _execute_unit(
                    config,
                    unit=unit,
                    unit_root=unit_root,
                    watchdog=watchdog,
                    workload_digest=matrix.digest,
                )
            unit_result_paths.append(result_path)
            _append_record(results_path, result_path.read_bytes())
            result = _load_canonical_object(result_path, label="suite result")
            if result.get("status") != "passed":
                failure = str(result.get("failure") or "qualification unit failed")
                break
            passed_units += 1
    except (
        SuiteContractError,
        qualification.QualificationContractError,
        OSError,
        subprocess.SubprocessError,
    ) as error:
        failure = f"suite setup failed: {type(error).__name__}"

    status = "passed" if failure is None else "failed"
    summary = _summary_payload(
        status=status,
        planned_units=planned_units,
        attempted_units=attempted_units,
        passed_units=passed_units,
        resumed_units=resumed_units,
        result_paths=unit_result_paths,
        results_path=results_path,
        failure=failure,
    )
    _write_canonical_new(summary_path, summary)
    artifact = SuiteArtifact(
        output_root=output_root,
        invocation_path=invocation_path,
        results_path=results_path,
        summary_path=summary_path,
        unit_results=tuple(unit_result_paths),
        status=status,
    )
    if failure is not None:
        raise SuiteRunFailed(artifact, failure)
    return artifact


def _materialize_fixtures(
    config: SuiteConfig,
    output_root: Path,
) -> dict[str, Path]:
    fixtures: dict[str, Path] = {}
    for spec in config.fixture_specs:
        if spec.path is not None:
            fixture_root = spec.path.resolve()
            fixture = shared.load_fixture_bundle(fixture_root)
            if fixture.profile != spec.profile:
                raise SuiteContractError(
                    f"fixture profile {fixture.profile!r} differs from {spec.profile!r}"
                )
        else:
            fixture_root = output_root / "fixtures" / f"{spec.profile}-v1"
            command = (
                sys.executable,
                "-m",
                "tests.agent_kernel.fixtures.generator.cli",
                "--profile",
                spec.profile,
                "--output",
                str(fixture_root),
            )
            completed = subprocess.run(
                command,
                cwd=_REPOSITORY_ROOT,
                check=False,
                capture_output=True,
            )
            if completed.returncode != 0:
                raise SuiteContractError(
                    f"fixture generator failed for {spec.profile} "
                    f"(stdout_bytes={len(completed.stdout)}, stderr_bytes={len(completed.stderr)})"
                )
            fixture = shared.load_fixture_bundle(fixture_root)
            if fixture.profile != spec.profile:
                raise SuiteContractError("generated fixture profile differs from request")
        fixtures[spec.profile] = fixture_root
    return fixtures


def _workload_matrix() -> Any:
    logical_cores = os.cpu_count() or 1
    physical_cores = min(
        logical_cores,
        qualification._physical_core_count(logical_cores),
    )
    return shared.build_workload_matrix(physical_cores=physical_cores)


def _select_suite_cases(config: SuiteConfig, matrix: Any) -> tuple[Any, ...]:
    if config.case_ids:
        requested = set(config.case_ids)
        unknown = requested - {case.case_id for case in matrix.cases}
        if unknown:
            raise SuiteContractError(f"unknown workload cases: {sorted(unknown)!r}")
        cases = tuple(case for case in matrix.cases if case.case_id in requested)
    else:
        selected_groups = frozenset(config.group_ids)
        cases = tuple(case for case in matrix.cases if case.group in selected_groups)
    for case in cases:
        if case.group in qualification._RESEARCH_GROUPS and not config.include_research:
            raise SuiteContractError(f"research case {case.case_id} requires include-research")
    return cases


def _suite_invocation(
    config: SuiteConfig,
    fixtures: Mapping[str, Path],
    matrix: Any,
    units: Sequence[_Unit],
    overrides: Mapping[str, float],
) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": SUITE_INVOCATION_SCHEMA,
        "code_commit": config.code_commit,
        "fixture_profiles": tuple(fixtures),
        "fixture_sources": {
            spec.profile: "provided" if spec.path is not None else "generated"
            for spec in config.fixture_specs
        },
        "candidate_ids": tuple(
            candidate for candidate in qualification.CANDIDATE_IDS if candidate in config.candidates
        ),
        "case_ids": tuple(dict.fromkeys(unit.case.case_id for unit in units)),
        "group_ids": tuple(group.value for group in config.group_ids),
        "suite_repetitions": config.suite_repetitions,
        "workload_matrix_digest": matrix.digest,
        "watchdog_overrides": dict(sorted(overrides.items())),
        "startup_grace_seconds": config.startup_grace_seconds,
        "termination_grace_seconds": config.termination_grace_seconds,
        "planned_units": len(units),
        "resume_result_count": len(config.resume_results),
        "completion_marker": SUMMARY_FILE,
    }
    return {**base, "invocation_digest": shared.canonical_sha256(base)}


def _execute_unit(
    config: SuiteConfig,
    *,
    unit: _Unit,
    unit_root: Path,
    watchdog: Watchdog,
    workload_digest: str,
) -> Path:
    child_output = unit_root / "child-output"
    child_run_id = "qualification"
    command = [
        sys.executable,
        str(config.runner_path),
        "--fixture",
        str(unit.fixture_root),
        "--output",
        str(child_output),
        "--run-id",
        child_run_id,
        "--candidate",
        unit.candidate_id,
        "--case",
        unit.case.case_id,
        "--repetitions",
        "1",
    ]
    if unit.profile != "tiny":
        command.append("--allow-large-fixture")
    if unit.case.group in qualification._RESEARCH_GROUPS:
        command.append("--include-research")

    started = time.monotonic()
    process = subprocess.Popen(
        command,
        cwd=_REPOSITORY_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None and process.stderr is not None
    stdout = _StreamDigest()
    stderr = _StreamDigest()
    readers = (
        threading.Thread(target=stdout.consume, args=(process.stdout,), daemon=True),
        threading.Thread(target=stderr.consume, args=(process.stderr,), daemon=True),
    )
    for reader in readers:
        reader.start()

    timed_out = False
    termination_requested = False
    kill_requested = False
    try:
        return_code = process.wait(timeout=watchdog.seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        termination_requested = True
        _signal_process_group(process.pid, signal.SIGTERM)
        try:
            return_code = process.wait(timeout=config.termination_grace_seconds)
        except subprocess.TimeoutExpired:
            kill_requested = True
            _signal_process_group(process.pid, signal.SIGKILL)
            return_code = process.wait()
        if _process_group_exists(process.pid):
            kill_requested = True
            _signal_process_group(process.pid, signal.SIGKILL)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    for reader in readers:
        reader.join(timeout=config.termination_grace_seconds)
    streams = {"stdout": stdout.payload(), "stderr": stderr.payload()}

    if timed_out:
        timeout = {
            "schema": TIMEOUT_SCHEMA,
            "profile": unit.profile,
            "candidate_id": unit.candidate_id,
            "case_id": unit.case.case_id,
            "suite_repetition": unit.suite_repetition,
            "elapsed_ms": elapsed_ms,
            "watchdog_seconds": watchdog.seconds,
            "policy_basis": watchdog.basis,
            "termination_requested": termination_requested,
            "kill_requested": kill_requested,
            "reaped": process.poll() is not None,
            "return_code": return_code,
            "censored": True,
            "eligibility_pass": False,
            **streams,
        }
        timeout_path = unit_root / TIMEOUT_FILE
        _write_canonical_new(timeout_path, timeout)
        result = _unit_result(
            unit,
            status="failed",
            workload_digest=workload_digest,
            code_commit=config.code_commit,
            child_artifacts={},
            streams=streams,
            elapsed_ms=elapsed_ms,
            failure="watchdog timeout",
            censored=True,
            resumed=False,
            watchdog=watchdog,
        )
        result_path = unit_root / RESULT_FILE
        _write_canonical_new(result_path, result)
        return result_path

    child_root = child_output / child_run_id
    try:
        child_artifacts = _verify_and_copy_child(
            child_root,
            destination=unit_root / "child",
            unit=unit,
            code_commit=config.code_commit,
            workload_digest=workload_digest,
            require_pass=return_code == 0,
        )
        child_summary = _load_canonical_object(
            child_root / qualification.SUMMARY_FILE,
            label="child summary",
        )
        passed = return_code == 0 and child_summary["status"] == "passed"
        failure = None if passed else f"child exited {return_code}"
    except SuiteContractError as error:
        child_artifacts = {}
        passed = False
        failure = f"child summary/artifacts invalid: {error}"

    result = _unit_result(
        unit,
        status="passed" if passed else "failed",
        workload_digest=workload_digest,
        code_commit=config.code_commit,
        child_artifacts=child_artifacts,
        streams=streams,
        elapsed_ms=elapsed_ms,
        failure=failure,
        censored=False,
        resumed=False,
        watchdog=watchdog,
    )
    result_path = unit_root / RESULT_FILE
    _write_canonical_new(result_path, result)
    return result_path


def _verify_and_copy_child(
    source: Path,
    *,
    destination: Path,
    unit: _Unit,
    code_commit: str,
    workload_digest: str,
    require_pass: bool,
) -> dict[str, str]:
    invocation = _load_canonical_object(
        source / qualification.INVOCATION_FILE,
        label="child invocation",
    )
    summary = _load_canonical_object(
        source / qualification.SUMMARY_FILE,
        label="child summary",
    )
    _verify_digest_field(invocation, "invocation_digest", label="child invocation")
    _verify_digest_field(summary, "summary_digest", label="child summary")
    expected_invocation = {
        "code_commit": code_commit,
        "candidate_ids": [unit.candidate_id],
        "case_ids": [unit.case.case_id],
        "repetitions": 1,
        "workload_matrix_digest": workload_digest,
    }
    for key, expected in expected_invocation.items():
        if invocation.get(key) != expected:
            raise SuiteContractError(f"child invocation {key} differs from unit")
    fixture = invocation.get("fixture")
    if not isinstance(fixture, dict) or fixture.get("profile") != unit.profile:
        raise SuiteContractError("child invocation fixture differs from unit")
    if (
        summary.get("code_commit") != code_commit
        or summary.get("workload_matrix_digest") != workload_digest
    ):
        raise SuiteContractError("child summary identity differs from unit")
    if summary.get("records") != 1 or summary.get("planned_executions") != 1:
        raise SuiteContractError("child summary is not a one-unit artifact")
    if require_pass and summary.get("status") != "passed":
        raise SuiteContractError("child summary did not pass")
    measurements = source / qualification.MEASUREMENT_FILE
    details = source / qualification.DETAIL_FILE
    if _sha256(measurements) != summary.get("measurement_sha256"):
        raise SuiteContractError("child measurement digest differs from summary")
    if _sha256(details) != summary.get("details_sha256"):
        raise SuiteContractError("child details digest differs from summary")
    lines = measurements.read_bytes().splitlines()
    if len(lines) != 1:
        raise SuiteContractError("child measurement stream is not one record")
    try:
        measurement = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise SuiteContractError("child measurement is not JSON") from error
    identity = measurement.get("identity")
    if not isinstance(identity, dict) or (
        identity.get("candidate_id"),
        identity.get("case_id"),
        identity.get("repetition"),
        identity.get("code_commit"),
        identity.get("workload_matrix_digest"),
    ) != (unit.candidate_id, unit.case.case_id, 0, code_commit, workload_digest):
        raise SuiteContractError("child measurement identity differs from unit")
    try:
        qualification.load_execution_details(
            details,
            measurements_path=measurements,
            expected_sha256=str(summary["details_sha256"]),
            expected_records=1,
        )
    except qualification.QualificationContractError as error:
        raise SuiteContractError(f"child details are invalid: {error}") from error
    destination.mkdir()
    hashes: dict[str, str] = {}
    for name in _CHILD_FILES:
        source_path = source / name
        destination_path = destination / name
        shutil.copyfile(source_path, destination_path)
        hashes[name] = _sha256(destination_path)
    return dict(sorted(hashes.items()))


def _load_resume_results(
    config: SuiteConfig,
    units: Sequence[_Unit],
    workload_digest: str,
) -> dict[tuple[str, str, str, int], Path]:
    planned = {unit.key for unit in units}
    resumes: dict[tuple[str, str, str, int], Path] = {}
    for path in config.resume_results:
        result = _load_canonical_object(path.resolve(), label="resume suite result")
        if result.get("schema") != SUITE_RESULT_SCHEMA or result.get("status") != "passed":
            raise SuiteContractError("resume result must be one canonical passed suite result")
        _verify_digest_field(result, "result_digest", label="resume suite result")
        if result.get("eligibility_pass") is not True or result.get("censored") is not False:
            raise SuiteContractError("resume result is not an eligibility pass")
        raw_key = (
            result.get("profile"),
            result.get("candidate_id"),
            result.get("case_id"),
            result.get("suite_repetition"),
        )
        if not (
            isinstance(raw_key[0], str)
            and isinstance(raw_key[1], str)
            and isinstance(raw_key[2], str)
            and isinstance(raw_key[3], int)
            and not isinstance(raw_key[3], bool)
        ):
            raise SuiteContractError("resume result has an invalid unit identity")
        key = (raw_key[0], raw_key[1], raw_key[2], raw_key[3])
        if key not in planned:
            raise SuiteContractError("resume result does not match a planned unit")
        if key in resumes:
            raise SuiteContractError("duplicate resume result for one planned unit")
        if (
            result.get("code_commit") != config.code_commit
            or result.get("workload_matrix_digest") != workload_digest
        ):
            raise SuiteContractError("resume result code or workload digest differs")
        child = path.parent / "child"
        hashes = result.get("child_artifacts")
        if not isinstance(hashes, dict) or set(hashes) != set(_CHILD_FILES):
            raise SuiteContractError("resume result omits its bounded child artifacts")
        for name, expected in hashes.items():
            if _sha256(child / name) != expected:
                raise SuiteContractError(f"resume child artifact {name} digest differs")
        resumes[key] = path.resolve()
    return resumes


def _copy_resumed_unit(
    source_result: Path,
    *,
    unit_root: Path,
    unit: _Unit,
    code_commit: str,
    workload_digest: str,
) -> Path:
    source_child = source_result.parent / "child"
    child_hashes = _verify_and_copy_child(
        source_child,
        destination=unit_root / "child",
        unit=unit,
        code_commit=code_commit,
        workload_digest=workload_digest,
        require_pass=True,
    )
    source = _load_canonical_object(source_result, label="resume suite result")
    source["child_artifacts"] = child_hashes
    source["resumed"] = True
    source.pop("result_digest", None)
    result = {**source, "result_digest": shared.canonical_sha256(source)}
    destination = unit_root / RESULT_FILE
    _write_canonical_new(destination, result)
    return destination


def _unit_result(
    unit: _Unit,
    *,
    status: str,
    workload_digest: str,
    code_commit: str,
    child_artifacts: Mapping[str, str],
    streams: Mapping[str, Mapping[str, object]],
    elapsed_ms: int,
    failure: str | None,
    censored: bool,
    resumed: bool,
    watchdog: Watchdog,
) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": SUITE_RESULT_SCHEMA,
        "status": status,
        "profile": unit.profile,
        "candidate_id": unit.candidate_id,
        "case_id": unit.case.case_id,
        "suite_repetition": unit.suite_repetition,
        "code_commit": code_commit,
        "workload_matrix_digest": workload_digest,
        "elapsed_ms": elapsed_ms,
        "watchdog_seconds": watchdog.seconds,
        "watchdog_basis": watchdog.basis,
        "censored": censored,
        "eligibility_pass": status == "passed" and not censored,
        "resumed": resumed,
        "failure": failure,
        "stdout": streams["stdout"],
        "stderr": streams["stderr"],
        "child_artifacts": dict(sorted(child_artifacts.items())),
    }
    return {**base, "result_digest": shared.canonical_sha256(base)}


def _summary_payload(
    *,
    status: str,
    planned_units: int,
    attempted_units: int,
    passed_units: int,
    resumed_units: int,
    result_paths: Sequence[Path],
    results_path: Path,
    failure: str | None,
) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": SUITE_SUMMARY_SCHEMA,
        "status": status,
        "planned_units": planned_units,
        "attempted_units": attempted_units,
        "completed_units": passed_units,
        "resumed_units": resumed_units,
        "result_records": len(result_paths),
        "result_stream_sha256": _sha256(results_path),
        "failure": failure,
    }
    return {**base, "summary_digest": shared.canonical_sha256(base)}


def _load_canonical_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError) as error:
        raise SuiteContractError(f"{label} cannot be read as JSON") from error
    if not isinstance(value, dict) or shared.canonical_json_bytes(value) != payload:
        raise SuiteContractError(f"{label} is not one canonical object")
    return value


def _verify_digest_field(payload: Mapping[str, Any], field: str, *, label: str) -> None:
    expected = payload.get(field)
    base = {key: value for key, value in payload.items() if key != field}
    if expected != shared.canonical_sha256(base):
        raise SuiteContractError(f"{label} has an invalid {field}")


def _write_canonical_new(path: Path, payload: Mapping[str, object]) -> None:
    try:
        with path.open("xb") as output:
            output.write(shared.canonical_json_bytes(payload))
    except FileExistsError as error:
        raise SuiteContractError(f"refusing to overwrite {path.name}") from error


def _create_empty(path: Path) -> None:
    try:
        path.open("xb").close()
    except FileExistsError as error:
        raise SuiteContractError(f"refusing to overwrite {path.name}") from error


def _append_record(path: Path, payload: bytes) -> None:
    if not payload.endswith(b"\n"):
        raise SuiteContractError("suite result is missing its final LF")
    with path.open("ab") as output:
        output.write(payload)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise SuiteContractError(f"artifact {path.name} cannot be read") from error


def _bounded_seconds(value: float, *, label: str, allow_zero: bool) -> float:
    minimum = 0.0 if allow_zero else 0.001
    if not minimum <= value <= _MAX_WATCHDOG_SECONDS:
        raise SuiteContractError(f"{label} must be between {minimum} and 3600 seconds")
    return value


def _signal_process_group(process_group: int, signal_number: signal.Signals) -> None:
    try:
        os.killpg(process_group, signal_number)
    except ProcessLookupError:
        return


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    return True


def _parse_fixture(value: str) -> FixtureSpec:
    profile, separator, path_text = value.partition("=")
    return FixtureSpec(profile, Path(path_text) if separator else None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the bounded CK-04 qualification suite.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--profile",
        action="append",
        required=True,
        dest="fixture_specs",
        metavar="PROFILE[=PATH]",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        choices=qualification.CANDIDATE_IDS,
        dest="candidates",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--case", action="append", dest="case_ids")
    selection.add_argument(
        "--group",
        action="append",
        choices=tuple(group.value for group in shared.WorkloadGroup),
        dest="group_ids",
    )
    parser.add_argument("--suite-repetitions", type=int, default=1)
    parser.add_argument("--resume-result", action="append", type=Path, default=[])
    parser.add_argument("--watchdog", action="append", default=[])
    parser.add_argument("--startup-grace-seconds", type=float, default=10.0)
    parser.add_argument("--termination-grace-seconds", type=float, default=2.0)
    parser.add_argument("--include-research", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        config = SuiteConfig(
            output_root=arguments.output,
            code_commit=qualification.discover_code_commit(_REPOSITORY_ROOT),
            fixture_specs=tuple(_parse_fixture(value) for value in arguments.fixture_specs),
            candidates=tuple(arguments.candidates or qualification.CANDIDATE_IDS),
            case_ids=tuple(arguments.case_ids or ()),
            group_ids=tuple(shared.WorkloadGroup(value) for value in (arguments.group_ids or ())),
            suite_repetitions=arguments.suite_repetitions,
            watchdog_overrides=tuple(arguments.watchdog),
            startup_grace_seconds=arguments.startup_grace_seconds,
            termination_grace_seconds=arguments.termination_grace_seconds,
            resume_results=tuple(arguments.resume_result),
            include_research=arguments.include_research,
        )
        artifact = run_suite(config)
    except SuiteRunFailed as error:
        print(error.artifact.summary_path)
        return 1
    except (SuiteContractError, qualification.QualificationContractError) as error:
        parser.error(str(error))
    print(artifact.summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
