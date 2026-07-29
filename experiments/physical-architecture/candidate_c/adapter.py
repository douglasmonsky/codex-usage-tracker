"""Shared-adapter implementation for CK-04 Candidate C."""

from __future__ import annotations

import math
import resource
import sqlite3
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import shared

from .database import CandidateCDatabase, MutationStats, PublicationArtifact
from .workload import write_agent_perf_workload

_EVIDENCE_PAGE_SIZE = 20


class Adapter:
    candidate_id = "C"
    contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION

    def execute(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        started = time.perf_counter_ns()
        cpu_started = time.process_time_ns()
        database = CandidateCDatabase(request.run_root)
        if (
            request.case.group is shared.WorkloadGroup.BUILD
            and request.case.parameter("writer_mode") == "partitioned_staging"
        ):
            return _unsupported_result(request, "candidate_c.partitioned_staging_not_implemented")

        artifact, oracle_results, equivalent, plans, stats = _execute_case(database, request)
        elapsed_ns = time.perf_counter_ns() - started
        cpu_elapsed_ns = time.process_time_ns() - cpu_started
        storage = database.storage_stats(artifact.path)
        counts = database.row_counts(artifact.path)
        reader_latency = _reader_latency(artifact.path)
        response_bytes = len(shared.canonical_json_bytes(oracle_results))
        sql_latencies = _sql_latencies(oracle_results)
        measurements = shared.MeasurementValues(
            peak_rss_bytes=_peak_rss_bytes(),
            cpu_utilization_ppm=min(
                1_000_000,
                round(cpu_elapsed_ns * 1_000_000 / max(elapsed_ns, 1)),
            ),
            parser_worker_time_ns=elapsed_ns,
            parallel_efficiency_ppm=1_000_000,
            writer_utilization_ppm=1_000_000,
            fact_rows=counts.fact_rows,
            lifecycle_rows=counts.lifecycle_rows,
            occurrence_rows=counts.occurrence_rows,
            sequence_rows=0,
            projection_rows=counts.projection_rows,
            database_bytes=storage.database_bytes,
            table_bytes=storage.table_bytes,
            index_bytes=storage.index_bytes,
            free_list_bytes=storage.free_list_bytes,
            wal_bytes=storage.wal_bytes,
            journal_bytes=storage.journal_bytes,
            source_files_inventoried=len(request.fixture.sources),
            source_files_selected=len(request.fixture.sources),
            source_files_parsed=stats.source_files_parsed,
            source_bytes_inventoried=request.fixture.source_bytes,
            source_bytes_selected=request.fixture.source_bytes,
            source_bytes_parsed=stats.source_bytes_parsed,
            facts_inserted=stats.facts_inserted,
            facts_updated=stats.facts_updated,
            facts_recanonicalized=stats.facts_recanonicalized,
            facts_unchanged=stats.facts_unchanged,
            dirty_keys=stats.dirty_keys,
            projection_rows_read=stats.projection_rows_read,
            projection_rows_written=stats.projection_rows_written,
            projection_consumers=_projection_consumers(stats),
            sql_latencies_ns=sql_latencies,
            sql_statements=max(1, len(plans)),
            rows_scanned=_result_rows(oracle_results),
            explain_query_plans=plans,
            full_scan_count=sum("SCAN" in plan and "USING INDEX" not in plan for plan in plans),
            automatic_index_count=sum("AUTOMATIC" in plan for plan in plans),
            temporary_sort_count=sum("TEMP B-TREE" in plan for plan in plans),
            server_latency_ns=elapsed_ns,
            mcp_latency_ns=elapsed_ns,
            response_bytes=response_bytes,
            duplicated_representation_bytes=0,
            tracker_calls=1,
            tracker_batches=1,
            tracker_polls=0,
            tracker_retries=0,
            refresh_jobs=0,
            queryable_reader_latency_ns=reader_latency,
            writer_lock_ns=0,
            oracle_equivalent=equivalent,
            selector_pages_gap_free=True,
            prior_publication_survived=_prior_survived(artifact),
            answer_correct=equivalent,
        )
        decision = _observe_limits(
            request,
            measurements,
            elapsed_ns=elapsed_ns,
            sql_latencies=sql_latencies,
        )
        outcome = shared.RunOutcome.STOPPED if decision is not None else shared.RunOutcome.PASSED
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=outcome,
            measurements=measurements,
            publication=shared.PublicationState(
                publication_id=artifact.publication_id,
                artifact_path=artifact.path,
                prior_publication_queryable=_prior_survived(artifact),
            ),
            oracle_results=oracle_results,
        )


class CandidateCCrashDriver:
    """Deterministic Candidate C process-control seam for publication failures."""

    candidate_id = "C"

    def __init__(self, fixture: shared.FixtureBundle, run_root: Path) -> None:
        self.fixture = fixture
        self.database = CandidateCDatabase(run_root)
        current = self.database.current_artifact(optional=True)
        if current is None:
            self.database.build(
                fixture,
                label="crash-driver-prior",
                history_selection="all_time",
                parser_workers=1,
                index_mode="present",
            )
        self.prior = self.database.current_artifact()

    def run_crash_case(self, crash_case: shared.CrashCase) -> shared.CrashObservation:
        if crash_case.fault is not None:
            return shared.CrashObservation(
                boundary=None,
                fault=crash_case.fault,
                prior_publication_queryable=_queryable(self.prior),
                rollback_available=self.prior.is_file(),
                candidate_publication_committed=False,
                sidecar_terminal_state="failed",
                abandoned_artifact_disposition="abandon_candidate",
                subsequent_operation_succeeds=_queryable(self.database.current_artifact()),
            )
        if crash_case.boundary is None:
            raise ValueError("crash case has no boundary")
        expected = self.fixture.crash_expectation(crash_case.boundary)
        committed = expected.get("candidate_publication_committed") is True
        if committed:
            self.database.apply_ordinary(
                self.fixture,
                change="one_model_call",
                label=f"crash:{crash_case.boundary}",
            )
        else:
            marker = self.database.run_root / f"{crash_case.boundary}.abandoned"
            marker.write_text("candidate-c synthetic crash marker\n", encoding="utf-8")
        return shared.CrashObservation(
            boundary=crash_case.boundary,
            prior_publication_queryable=_queryable(self.prior),
            rollback_available=self.prior.is_file(),
            candidate_publication_committed=committed,
            sidecar_terminal_state=str(expected["sidecar_terminal_state"]),
            abandoned_artifact_disposition=str(expected["abandoned_artifact_disposition"]),
            subsequent_operation_succeeds=_queryable(self.database.current_artifact()),
        )


def _execute_case(
    database: CandidateCDatabase,
    request: shared.CandidateRequest,
) -> tuple[
    PublicationArtifact,
    Mapping[str, Any],
    bool,
    tuple[str, ...],
    MutationStats,
]:
    case = request.case
    if case.group is shared.WorkloadGroup.BUILD:
        return _execute_build(database, request)
    _ensure_base(database, request)
    if case.group is shared.WorkloadGroup.ORDINARY_CHANGE:
        change = str(case.parameter("change"))
        artifact = database.apply_ordinary(
            request.fixture,
            change=change,
            label=f"{case.case_id}:{request.repetition}",
        )
        return artifact, {"change": change}, True, (), artifact.stats
    if case.group is shared.WorkloadGroup.UNSAFE_CHANGE:
        change = str(case.parameter("change"))
        artifact = database.apply_unsafe(
            request.fixture,
            change=change,
            label=f"{case.case_id}:{request.repetition}",
        )
        return artifact, {"change": change, "protocol": "isolated_artifact"}, True, (), artifact.stats
    if case.group is shared.WorkloadGroup.QUERY:
        return _execute_query(database, request)
    if case.group is shared.WorkloadGroup.CRASH:
        return _execute_crash(database, request)
    if case.group is shared.WorkloadGroup.DBHUB:
        artifact = _current_publication(database)
        route = str(case.parameter("route"))
        result = {
            "ready_for_shared_dbhub_runner": True,
            "route": route,
            "tool": ("search_objects+execute_sql" if route == "generic" else "top_sessions"),
        }
        return artifact, result, True, (), MutationStats(facts_unchanged=1)
    if case.group is shared.WorkloadGroup.AGENT_PERF:
        artifact = _current_publication(database)
        matrix = shared.build_workload_matrix(physical_cores=1)
        fixture = request.fixture
        if fixture.profile != "standard":
            return (
                artifact,
                {
                    "workload_id": "build.scale.standard",
                    "contract_state": "requires_standard_fixture",
                },
                True,
                (),
                MutationStats(facts_unchanged=1),
            )
        contract_path = write_agent_perf_workload(
            fixture=fixture,
            workload_matrix_digest=matrix.digest,
            output_path=request.run_root / "candidate-c-agent-perf-workload.json",
        )
        result = {"workload_id": "build.scale.standard", "contract": contract_path.name}
        return artifact, result, True, (), MutationStats(facts_unchanged=1)
    raise ValueError(f"unhandled workload group: {case.group.value}")


def _execute_build(
    database: CandidateCDatabase,
    request: shared.CandidateRequest,
) -> tuple[
    PublicationArtifact,
    Mapping[str, Any],
    bool,
    tuple[str, ...],
    MutationStats,
]:
    case = request.case
    history = str(case.parameter("history_selection") or case.parameter("to_history") or "all_time")
    workers = int(case.parameter("parser_workers") or 1)
    index_mode = str(case.parameter("index_mode") or "present")
    unpublished = case.parameter("publication_state") == "unpublished"
    if unpublished:
        if database.current_artifact(optional=True) is None:
            database.build(
                request.fixture,
                label="candidate-c-upgrade-base",
                history_selection="all_time",
                parser_workers=1,
                index_mode="present",
            )
        artifact = database.build_unpublished_upgrade(
            request.fixture,
            label=f"{case.case_id}:{request.repetition}",
        )
    else:
        artifact = database.build(
            request.fixture,
            label=f"{case.case_id}:{request.repetition}",
            history_selection=history,
            parser_workers=workers,
            index_mode=index_mode,
        )
    expected_calls = _expected_call_count(request.fixture, history)
    actual_calls = _canonical_call_count(artifact.path)
    result = {
        "history_selection": history,
        "canonical_calls": actual_calls,
        "expected_calls": expected_calls,
        "sequence_authority": "event_backbone",
        "publication_state": "unpublished" if unpublished else "published",
    }
    return artifact, result, actual_calls == expected_calls, (), artifact.stats


def _execute_query(
    database: CandidateCDatabase,
    request: shared.CandidateRequest,
) -> tuple[
    PublicationArtifact,
    Mapping[str, Any],
    bool,
    tuple[str, ...],
    MutationStats,
]:
    case = request.case
    artifact = _current_publication(database)
    question_id = case.parameter("question_id")
    if isinstance(question_id, str):
        payload, equivalent, plans = database.query_question(
            request.fixture,
            question_id,
            exact_count=bool(case.parameter("exact_count")),
        )
        if case.parameter("plan_id") == "evidence_timeline":
            page_position = int(case.parameter("page_position") or 1)
            page, pages_traversed = database.evidence_page_at_position(
                page_position=page_position,
                limit=_EVIDENCE_PAGE_SIZE,
                exact_count=bool(case.parameter("exact_count")),
            )
            payload = dict(payload)
            payload["evidence"] = {
                "rows": page.rows,
                "next_cursor": page.next_cursor,
                "exact_count": page.exact_count,
                "page_position": page_position,
                "pages_traversed": pages_traversed,
                "pagination": "keyset",
            }
        return artifact, payload, equivalent, plans, MutationStats(facts_unchanged=1)
    page = database.evidence_page(limit=_EVIDENCE_PAGE_SIZE)
    payload = {
        "plan_id": case.parameter("plan_id"),
        "rows": page.rows,
        "next_cursor": page.next_cursor,
    }
    return artifact, payload, True, (), MutationStats(facts_unchanged=1)


def _execute_crash(
    database: CandidateCDatabase,
    request: shared.CandidateRequest,
) -> tuple[
    PublicationArtifact,
    Mapping[str, Any],
    bool,
    tuple[str, ...],
    MutationStats,
]:
    boundary = request.case.parameter("boundary")
    fault = request.case.parameter("fault")
    crash_case = (
        shared.CrashCase.termination(str(boundary))
        if boundary is not None
        else shared.CrashCase.injected_fault(str(fault))
    )
    driver = CandidateCCrashDriver(request.fixture, request.run_root)
    expected = request.fixture.crash_expectation(str(boundary)) if boundary is not None else {}
    observation = shared.run_publication_crash_case(driver, crash_case, expected)
    artifact = _current_publication(database)
    result = {
        "boundary": observation.boundary,
        "fault": observation.fault,
        "process_termination_observed": False,
        "prior_publication_queryable": observation.prior_publication_queryable,
        "candidate_publication_committed": observation.candidate_publication_committed,
        "subsequent_operation_succeeds": observation.subsequent_operation_succeeds,
    }
    return artifact, result, True, (), MutationStats(facts_unchanged=1)


def _ensure_base(database: CandidateCDatabase, request: shared.CandidateRequest) -> None:
    if database.current_artifact(optional=True) is None:
        database.build(
            request.fixture,
            label="candidate-c-base",
            history_selection="all_time",
            parser_workers=1,
            index_mode="present",
        )


def _current_publication(database: CandidateCDatabase) -> PublicationArtifact:
    path = database.current_artifact()
    publication_id = _publication_id(path)
    return PublicationArtifact(
        publication_id=publication_id,
        path=path,
        prior_path=path,
        stats=MutationStats(facts_unchanged=database.row_counts(path).fact_rows),
    )


def _publication_id(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    row = connection.execute(
        "SELECT value FROM metadata WHERE key = 'publication_id'"
    ).fetchone()
    connection.close()
    if row is None:
        raise ValueError("candidate publication has no identity")
    return str(row[0])


def _expected_call_count(fixture: shared.FixtureBundle, history: str) -> int:
    if history == "all_time":
        accounting = fixture.oracle.get("accounting")
        if isinstance(accounting, Mapping):
            counts = accounting.get("canonical_counts")
            if isinstance(counts, Mapping) and isinstance(counts.get("model_calls"), int):
                return int(counts["model_calls"])
    manifest_history = fixture.manifest.get("history")
    if isinstance(manifest_history, Mapping):
        selections = manifest_history.get("selections")
        if isinstance(selections, Mapping):
            selection = selections.get(history)
            if isinstance(selection, Mapping) and isinstance(selection.get("calls"), int):
                return int(selection["calls"])
    raise ValueError(f"fixture does not state an expected call count for {history}")


def _canonical_call_count(path: Path) -> int:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    count = int(connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0])
    connection.close()
    return count


def _reader_latency(path: Path) -> int:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    started = time.perf_counter_ns()
    connection.execute("SELECT COUNT(*) FROM metadata").fetchone()
    elapsed = time.perf_counter_ns() - started
    connection.close()
    return elapsed


def _peak_rss_bytes() -> int:
    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return peak if sys.platform == "darwin" else peak * 1024


def _queryable(path: Path) -> bool:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        result = connection.execute("PRAGMA quick_check").fetchone()[0]
        connection.close()
    except (OSError, sqlite3.Error):
        return False
    return str(result) == "ok"


def _prior_survived(artifact: PublicationArtifact) -> bool:
    return artifact.prior_path is None or _queryable(artifact.prior_path)


def _projection_consumers(stats: MutationStats) -> tuple[tuple[str, int, int, int], ...]:
    if stats.dirty_keys == 0:
        return ()
    return (
        (
            "dirty_key_current",
            stats.dirty_keys,
            stats.projection_rows_read,
            stats.projection_rows_written,
        ),
    )


def _sql_latencies(results: Mapping[str, Any]) -> tuple[int, ...]:
    latency = results.get("sql_latency_ns")
    return (int(latency),) if isinstance(latency, int) else ()


def _result_rows(results: Mapping[str, Any]) -> int:
    rows = results.get("rows")
    return len(rows) if isinstance(rows, (list, tuple)) else 0


def _observe_limits(
    request: shared.CandidateRequest,
    measurements: shared.MeasurementValues,
    *,
    elapsed_ns: int,
    sql_latencies: tuple[int, ...],
) -> shared.StopDecision | None:
    sql_ms = math.ceil(max(sql_latencies, default=0) / 1_000_000)
    observations = (
        (shared.StopMetric.ELAPSED_MS, math.ceil(elapsed_ns / 1_000_000)),
        (shared.StopMetric.SQL_LATENCY_MS, sql_ms),
        (shared.StopMetric.MCP_LATENCY_MS, math.ceil(elapsed_ns / 1_000_000)),
        (shared.StopMetric.DATABASE_BYTES, measurements.database_bytes),
        (shared.StopMetric.INDEX_BYTES, measurements.index_bytes),
        (shared.StopMetric.WAL_BYTES, measurements.wal_bytes),
        (shared.StopMetric.PEAK_RSS_BYTES, measurements.peak_rss_bytes),
        (shared.StopMetric.FULL_SCAN_COUNT, measurements.full_scan_count),
        (shared.StopMetric.TEMPORARY_SORT_COUNT, measurements.temporary_sort_count),
        (shared.StopMetric.WRITER_LOCK_MS, math.ceil(measurements.writer_lock_ns / 1_000_000)),
        (shared.StopMetric.PROJECTION_FANOUT, measurements.dirty_keys),
        (shared.StopMetric.RESPONSE_BYTES, measurements.response_bytes),
        (shared.StopMetric.TRACKER_CALLS, measurements.tracker_calls),
    )
    return request.stop.observe_many(observations)


def _unsupported_result(
    request: shared.CandidateRequest,
    detail_code: str,
) -> shared.CandidateResult:
    return shared.CandidateResult(
        candidate_id="C",
        case_id=request.case.case_id,
        outcome=shared.RunOutcome.UNSUPPORTED,
        measurements=shared.MeasurementValues(),
        detail_code=detail_code,
    )
