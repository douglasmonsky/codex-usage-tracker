from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes
from .outcomes import RunOutcome
from .stop import StopDecision, StopMetric

MEASUREMENT_SCHEMA = "codex-usage-tracker.physical-bakeoff-measurement.v2"
_ORDINARY_TAIL_LATENCY_BASIS = "ordinary_operation_after_preparation.v1"
_PAGES_WRITTEN_BASIS = "sqlite_wal_frames_clean_epoch.v1"
_WRITER_TRANSACTIONS_BASIS = "explicit_committed_analytical_transactions.v1"
_REQUIRED_SQLITE_SETTINGS = frozenset(
    {
        "cache_size",
        "journal_mode",
        "mmap_size",
        "page_size",
        "synchronous",
        "temp_store",
        "wal_autocheckpoint",
    }
)


class MeasurementContractError(ValueError):
    pass


@dataclass(frozen=True)
class EnvironmentFingerprint:
    python_version: str
    sqlite_version: str
    operating_system: str
    filesystem: str
    cpu_model: str
    physical_cores: int
    logical_cores: int
    memory_bytes: int
    storage_model: str
    compiler_flags: tuple[str, ...]
    sqlite_settings: tuple[tuple[str, str], ...]
    analyze_state: str
    filesystem_cache_state: str

    def __post_init__(self) -> None:
        text_fields = (
            self.python_version,
            self.sqlite_version,
            self.operating_system,
            self.filesystem,
            self.cpu_model,
            self.storage_model,
            self.analyze_state,
            self.filesystem_cache_state,
        )
        if any(not value.strip() for value in text_fields):
            raise MeasurementContractError("environment fingerprint fields cannot be blank")
        if self.physical_cores < 1 or self.logical_cores < self.physical_cores:
            raise MeasurementContractError("environment CPU counts are inconsistent")
        if self.memory_bytes < 1:
            raise MeasurementContractError("environment memory must be positive")
        if self.sqlite_settings != tuple(sorted(self.sqlite_settings)):
            raise MeasurementContractError("SQLite settings must be sorted")
        if len({name for name, _ in self.sqlite_settings}) != len(self.sqlite_settings):
            raise MeasurementContractError("SQLite settings must be unique")
        if not _REQUIRED_SQLITE_SETTINGS <= {name for name, _ in self.sqlite_settings}:
            raise MeasurementContractError("environment omits required SQLite settings")


@dataclass(frozen=True)
class MeasurementIdentity:
    run_id: str
    candidate_id: str
    case_id: str
    fixture_profile: str
    fixture_manifest_digest: str
    fixture_oracle_digest: str
    repetition: int
    profiled: bool
    code_commit: str
    workload_matrix_digest: str
    environment: EnvironmentFingerprint
    qualification_model: str | None = None

    def __post_init__(self) -> None:
        if self.candidate_id not in {"A", "C", "D"}:
            raise MeasurementContractError("measurement candidate ID must be A, C, or D")
        if self.repetition < 0:
            raise MeasurementContractError("measurement repetition must be nonnegative")
        for digest in (self.fixture_manifest_digest, self.fixture_oracle_digest):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise MeasurementContractError("measurement fixture digest must be SHA-256")
        for digest in (self.workload_matrix_digest,):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise MeasurementContractError("workload matrix digest must be SHA-256")
        if len(self.code_commit) != 40 or any(
            character not in "0123456789abcdef" for character in self.code_commit
        ):
            raise MeasurementContractError("measurement code commit must be a full SHA-1")
        if self.qualification_model is not None and not self.qualification_model.strip():
            raise MeasurementContractError("qualification model cannot be blank")


@dataclass(frozen=True)
class MeasurementValues:
    ordinary_tail_latency_ns: int | None = None
    ordinary_tail_latency_basis: str | None = None
    peak_rss_bytes: int = 0
    cpu_utilization_ppm: int = 0
    parser_worker_time_ns: int = 0
    parallel_efficiency_ppm: int = 0
    queue_wait_ns: int = 0
    merge_time_ns: int = 0
    writer_utilization_ppm: int = 0
    fact_rows: int = 0
    lifecycle_rows: int = 0
    occurrence_rows: int = 0
    sequence_rows: int = 0
    projection_rows: int = 0
    database_bytes: int = 0
    table_bytes: int = 0
    index_bytes: int = 0
    free_list_bytes: int = 0
    wal_bytes: int = 0
    journal_bytes: int = 0
    temporary_bytes: int = 0
    pages_read: int = 0
    pages_written: int | None = None
    pages_written_basis: str | None = None
    writer_transactions: int | None = None
    writer_transactions_basis: str | None = None
    source_files_inventoried: int = 0
    source_files_selected: int = 0
    source_files_parsed: int = 0
    source_files_deferred: int = 0
    source_files_rescanned: int = 0
    source_bytes_inventoried: int = 0
    source_bytes_selected: int = 0
    source_bytes_parsed: int = 0
    source_bytes_deferred: int = 0
    source_bytes_rescanned: int = 0
    facts_inserted: int = 0
    facts_updated: int = 0
    facts_recanonicalized: int = 0
    facts_unchanged: int = 0
    dirty_keys: int = 0
    projection_rows_read: int = 0
    projection_rows_written: int = 0
    projection_consumers: tuple[tuple[str, int, int, int], ...] = ()
    sql_latencies_ns: tuple[int, ...] = ()
    sql_statements: int = 0
    rows_scanned: int = 0
    explain_query_plans: tuple[str, ...] = ()
    full_scan_count: int = 0
    automatic_index_count: int = 0
    temporary_sort_count: int = 0
    server_latency_ns: int = 0
    mcp_latency_ns: int = 0
    response_bytes: int = 0
    duplicated_representation_bytes: int = 0
    tracker_calls: int = 0
    tracker_batches: int = 0
    tracker_polls: int = 0
    tracker_retries: int = 0
    refresh_jobs: int = 0
    model_input_tokens: int = 0
    model_output_tokens: int = 0
    model_cached_input_tokens: int = 0
    model_reasoning_tokens: int = 0
    queryable_reader_latency_ns: int = 0
    writer_lock_ns: int = 0
    oracle_equivalent: bool = False
    selector_pages_gap_free: bool = False
    prior_publication_survived: bool = False
    answer_correct: bool = False

    def __post_init__(self) -> None:
        for value_name, basis_name, expected in (
            ("ordinary_tail_latency_ns", "ordinary_tail_latency_basis", _ORDINARY_TAIL_LATENCY_BASIS),
            ("pages_written", "pages_written_basis", _PAGES_WRITTEN_BASIS),
            ("writer_transactions", "writer_transactions_basis", _WRITER_TRANSACTIONS_BASIS),
        ):
            value = getattr(self, value_name)
            basis = getattr(self, basis_name)
            # Candidate C/D elimination runs remain projectable.  Their legacy
            # measurements leave these Candidate-A-only write metrics unavailable.
            if value is None and basis is not None:
                raise MeasurementContractError(f"measurement {value_name} and {basis_name} must be paired")
            if basis is not None and basis != expected:
                raise MeasurementContractError(f"measurement {basis_name} is unsupported")
        for field in fields(self):
            value = getattr(self, field.name)
            if value is None:
                continue
            if isinstance(value, (bool, str)):
                continue
            if isinstance(value, int):
                if value < 0:
                    raise MeasurementContractError(f"measurement {field.name} must be nonnegative")
                continue
            if isinstance(value, tuple):
                if field.name == "sql_latencies_ns" and any(
                    not isinstance(item, int) or item < 0 for item in value
                ):
                    raise MeasurementContractError("SQL latency values must be nonnegative")
                if field.name == "explain_query_plans" and any(
                    not isinstance(item, str) for item in value
                ):
                    raise MeasurementContractError("query plans must be strings")
                if field.name == "projection_consumers":
                    if value != tuple(sorted(value)):
                        raise MeasurementContractError(
                            "projection consumer measurements must be sorted"
                        )
                    for item in value:
                        if (
                            len(item) != 4
                            or not isinstance(item[0], str)
                            or not item[0]
                            or any(not isinstance(metric, int) or metric < 0 for metric in item[1:])
                        ):
                            raise MeasurementContractError(
                                "projection consumer measurement is invalid"
                            )
                    if len({item[0] for item in value}) != len(value):
                        raise MeasurementContractError(
                            "projection consumer measurements must be unique"
                        )
                continue
            raise MeasurementContractError(f"unsupported measurement value: {field.name}")
        for field_name in (
            "cpu_utilization_ppm",
            "parallel_efficiency_ppm",
            "writer_utilization_ppm",
        ):
            if getattr(self, field_name) > 1_000_000:
                raise MeasurementContractError(f"{field_name} cannot exceed 1,000,000")


@dataclass(frozen=True)
class MeasurementRecord:
    identity: MeasurementIdentity
    wall_time_ns: int
    process_cpu_ns: int
    values: MeasurementValues
    outcome: RunOutcome
    stop_decision: StopDecision | None = None
    detail_code: str | None = None

    def __post_init__(self) -> None:
        if self.wall_time_ns < 0 or self.process_cpu_ns < 0:
            raise MeasurementContractError("measurement clocks moved backwards")
        latency = self.values.ordinary_tail_latency_ns
        if latency is not None and self.wall_time_ns < latency:
            raise MeasurementContractError("measurement wall time cannot be shorter than ordinary latency")
        if (self.outcome is RunOutcome.STOPPED) != (self.stop_decision is not None):
            raise MeasurementContractError("stopped measurement requires one stop decision")
        if self.outcome in {RunOutcome.FAILED, RunOutcome.UNSUPPORTED} and not self.detail_code:
            raise MeasurementContractError("failed/unsupported measurement requires detail code")

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": MEASUREMENT_SCHEMA,
            "identity": asdict(self.identity),
            "wall_time_ns": self.wall_time_ns,
            "process_cpu_ns": self.process_cpu_ns,
            "outcome": self.outcome.value,
            "partial": self.stop_decision is not None,
            "stop_decision": (
                {
                    "case_id": self.stop_decision.case_id,
                    "metric": self.stop_decision.metric.value,
                    "observed": self.stop_decision.observed,
                    "maximum": self.stop_decision.maximum,
                }
                if self.stop_decision is not None
                else None
            ),
            "detail_code": self.detail_code,
            "values": asdict(self.values),
        }


class MeasurementDraft:
    def __init__(self) -> None:
        self.values: MeasurementValues | None = None
        self.outcome = RunOutcome.PASSED
        self.stop_decision: StopDecision | None = None
        self.detail_code: str | None = None

    def set_values(self, values: MeasurementValues) -> None:
        if self.values is not None:
            raise MeasurementContractError("measurement values may only be set once")
        self.values = values

    def mark_stopped(self, decision: StopDecision) -> None:
        if decision.outcome is not RunOutcome.STOPPED or not decision.partial:
            raise MeasurementContractError("measurement stop decision is not a partial stop")
        self._set_outcome(RunOutcome.STOPPED, stop_decision=decision)

    def mark_failed(self, detail_code: str) -> None:
        self._set_outcome(RunOutcome.FAILED, detail_code=detail_code)

    def mark_unsupported(self, detail_code: str) -> None:
        self._set_outcome(RunOutcome.UNSUPPORTED, detail_code=detail_code)

    def _set_outcome(
        self,
        outcome: RunOutcome,
        *,
        stop_decision: StopDecision | None = None,
        detail_code: str | None = None,
    ) -> None:
        if self.outcome is not RunOutcome.PASSED:
            raise MeasurementContractError("measurement outcome may only be set once")
        if detail_code is not None and not detail_code.strip():
            raise MeasurementContractError("measurement detail code cannot be blank")
        self.outcome = outcome
        self.stop_decision = stop_decision
        self.detail_code = detail_code


class MeasurementCollector:
    """Collect host clocks while candidates provide explicit remaining measurements."""

    def __init__(
        self,
        output_path: Path,
        *,
        wall_clock_ns: Callable[[], int] = time.perf_counter_ns,
        process_clock_ns: Callable[[], int] = time.process_time_ns,
    ) -> None:
        self.output_path = output_path
        self._wall_clock_ns = wall_clock_ns
        self._process_clock_ns = process_clock_ns

    @contextmanager
    def measure(self, identity: MeasurementIdentity) -> Iterator[MeasurementDraft]:
        wall_start = self._wall_clock_ns()
        process_start = self._process_clock_ns()
        draft = MeasurementDraft()
        yield draft
        process_end = self._process_clock_ns()
        wall_end = self._wall_clock_ns()
        if draft.values is None:
            raise MeasurementContractError("candidate did not submit measurement values")
        record = MeasurementRecord(
            identity=identity,
            wall_time_ns=wall_end - wall_start,
            process_cpu_ns=process_end - process_start,
            values=draft.values,
            outcome=draft.outcome,
            stop_decision=draft.stop_decision,
            detail_code=draft.detail_code,
        )
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("ab") as output:
            output.write(canonical_json_bytes(record.as_dict()))


def _measurement_values(payload: dict[str, Any]) -> MeasurementValues:
    values = dict(payload)
    for name in ("sql_latencies_ns", "explain_query_plans", "projection_consumers"):
        item = values.get(name, [])
        if not isinstance(item, list):
            raise MeasurementContractError(f"measurement {name} must be a list")
        values[name] = tuple(tuple(value) if isinstance(value, list) else value for value in item)
    try:
        return MeasurementValues(**values)
    except TypeError as error:
        raise MeasurementContractError("measurement values use unknown fields") from error


def _measurement_identity(payload: dict[str, Any]) -> MeasurementIdentity:
    values = dict(payload)
    environment_payload = values.get("environment")
    if not isinstance(environment_payload, dict):
        raise MeasurementContractError("measurement environment must be an object")
    environment_values = dict(environment_payload)
    for field_name in ("compiler_flags", "sqlite_settings"):
        item = environment_values.get(field_name)
        if not isinstance(item, list):
            raise MeasurementContractError(f"environment {field_name} must be a list")
        environment_values[field_name] = tuple(
            tuple(value) if isinstance(value, list) else value for value in item
        )
    try:
        values["environment"] = EnvironmentFingerprint(**environment_values)
        return MeasurementIdentity(**values)
    except TypeError as error:
        raise MeasurementContractError("measurement identity uses unknown fields") from error


def load_measurements(path: Path) -> tuple[MeasurementRecord, ...]:
    records: list[MeasurementRecord] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise MeasurementContractError("measurement file cannot be read") from error
    for line_number, line in enumerate(lines, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise MeasurementContractError(f"measurement line {line_number} is not JSON") from error
        if not isinstance(payload, dict) or payload.get("schema") != MEASUREMENT_SCHEMA:
            raise MeasurementContractError(f"measurement line {line_number} has wrong schema")
        identity_payload = payload.get("identity")
        values_payload = payload.get("values")
        if not isinstance(identity_payload, dict) or not isinstance(values_payload, dict):
            raise MeasurementContractError(f"measurement line {line_number} is incomplete")
        try:
            identity = _measurement_identity(identity_payload)
            stop_payload = payload.get("stop_decision")
            stop_decision = None
            if stop_payload is not None:
                if not isinstance(stop_payload, dict):
                    raise MeasurementContractError("measurement stop decision must be an object")
                stop_decision = StopDecision(
                    case_id=str(stop_payload["case_id"]),
                    metric=StopMetric(str(stop_payload["metric"])),
                    observed=int(stop_payload["observed"]),
                    maximum=int(stop_payload["maximum"]),
                )
            if payload.get("partial") is not (stop_decision is not None):
                raise MeasurementContractError("measurement partial flag is inconsistent")
            record = MeasurementRecord(
                identity=identity,
                wall_time_ns=int(payload["wall_time_ns"]),
                process_cpu_ns=int(payload["process_cpu_ns"]),
                values=_measurement_values(values_payload),
                outcome=RunOutcome(str(payload["outcome"])),
                stop_decision=stop_decision,
                detail_code=(
                    str(payload["detail_code"]) if payload.get("detail_code") is not None else None
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise MeasurementContractError(f"measurement line {line_number} is invalid") from error
        records.append(record)
    return tuple(records)
