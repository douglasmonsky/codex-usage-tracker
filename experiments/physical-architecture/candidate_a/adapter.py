from __future__ import annotations

import os
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import shared

from .ingest import BuildArtifact, IngestStats, build_artifact
from .maintenance import (
    MaintenanceStats,
    TailFoldRequired,
    apply_ordinary_change,
    apply_source_phase,
)
from .metrics import ArtifactMetrics, artifact_metrics
from .publication import CandidateACrashDriver, publish_artifact
from .queries import (
    QueryResult,
    run_bounded_sort,
    run_evidence_feature,
    run_question,
)
from .schema import database, validate_database

_UNSAFE_PHASES = {
    "source_truncation": ("truncation", "after"),
    "source_replacement": ("replacement", "after"),
    "canonical_owner_change": ("archive", "after"),
    "recanonicalization": ("moving_tail", "after"),
}


class Adapter:
    candidate_id = "A"
    contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION

    def __init__(self) -> None:
        self._prepared_query_artifacts: dict[int, BuildArtifact] = {}

    def execute(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        group = request.case.group
        if group is shared.WorkloadGroup.BUILD:
            return self._build(request)
        if group is shared.WorkloadGroup.ORDINARY_CHANGE:
            return self._ordinary(request)
        if group is shared.WorkloadGroup.UNSAFE_CHANGE:
            return self._unsafe(request)
        if group is shared.WorkloadGroup.QUERY:
            return self._query(request)
        if group is shared.WorkloadGroup.CRASH:
            return self._crash(request)
        if group is shared.WorkloadGroup.DBHUB:
            return self._dbhub(request)
        if group is shared.WorkloadGroup.AGENT_PERF:
            return self._agent_perf(request)
        raise ValueError(f"unknown candidate A workload group: {group}")

    def _build(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        if request.case.parameter("writer_mode") == "partitioned_staging":
            return shared.CandidateResult(
                candidate_id=self.candidate_id,
                case_id=request.case.case_id,
                outcome=shared.RunOutcome.UNSUPPORTED,
                measurements=shared.MeasurementValues(),
                detail_code="candidate_a.single_writer_only",
            )
        history = str(
            request.case.parameter("to_history")
            or request.case.parameter("history_selection")
            or "all_time"
        )
        index_mode = str(request.case.parameter("index_mode") or "deferred")
        defer_secondary_indexes = index_mode == "deferred"
        parser_workers = self._parser_worker_count(request)
        started = time.perf_counter_ns()
        if request.case.case_id.startswith("build.expand."):
            prior_history = str(request.case.parameter("from_history"))
            prior = build_artifact(
                request.fixture,
                request.run_root / "prior.sqlite",
                history_selection=prior_history,
                parser_workers=parser_workers,
            )
            artifact = publish_artifact(
                request.fixture,
                request.run_root,
                history_selection=history,
                parent_publication_id=prior.publication_id,
                defer_secondary_indexes=defer_secondary_indexes,
                parser_workers=parser_workers,
            )
        elif request.case.case_id == "build.schema_upgrade.unpublished":
            artifact = build_artifact(
                request.fixture,
                request.run_root / "unpublished.sqlite",
                history_selection=history,
                defer_secondary_indexes=defer_secondary_indexes,
                parser_workers=parser_workers,
            )
        else:
            artifact = publish_artifact(
                request.fixture,
                request.run_root,
                history_selection=history,
                defer_secondary_indexes=defer_secondary_indexes,
                parser_workers=parser_workers,
            )
        if request.case.case_id == f"build.scale.{request.fixture.profile}":
            self._prepared_query_artifacts[request.repetition] = artifact
        index_maintenance_ns = artifact.stats.index_maintenance_ns
        if index_mode == "rebuilt":
            rebuild_started = time.perf_counter_ns()
            with database(artifact.path) as connection:
                connection.execute("REINDEX")
                connection.execute("PRAGMA optimize")
            index_maintenance_ns += time.perf_counter_ns() - rebuild_started
        elapsed = time.perf_counter_ns() - started
        storage = artifact_metrics(
            artifact.path,
            occurrence_rows=artifact.stats.occurrence_rows,
        )
        if self._observe_stop(
            request,
            (
                (shared.StopMetric.ELAPSED_MS, _milliseconds(elapsed)),
                (shared.StopMetric.DATABASE_BYTES, storage.database_bytes),
                (shared.StopMetric.INDEX_BYTES, storage.index_bytes),
                (shared.StopMetric.WAL_BYTES, storage.wal_bytes),
            ),
        ):
            return self._stopped(request, self._values(artifact, storage))
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=self._values(
                artifact,
                storage,
                parser_worker_time_ns=artifact.stats.parser_worker_time_ns,
                parallel_efficiency_ppm=(artifact.stats.parser_parallel_efficiency_ppm),
                queue_wait_ns=artifact.stats.parser_queue_wait_ns,
                merge_time_ns=(artifact.stats.parser_merge_time_ns + index_maintenance_ns),
                writer_utilization_ppm=1_000_000,
            ),
            publication=self._publication(artifact, prior_queryable=True),
            oracle_results={
                "schema_id": "codex-usage-tracker.physical-bakeoff.candidate-a.v1",
                "history_selection": history,
                "index_mode": index_mode,
                "secondary_indexes_deferred": (artifact.stats.secondary_indexes_deferred),
                "secondary_indexes_restored": (artifact.stats.secondary_indexes_restored),
                "staging_journal_mode": artifact.stats.staging_journal_mode,
                "staging_synchronous": artifact.stats.staging_synchronous,
                "final_journal_mode": artifact.stats.final_journal_mode,
                "final_synchronous": artifact.stats.final_synchronous,
                "durability_transition_ns": (artifact.stats.durability_transition_ns),
                "validation_mode": artifact.stats.validation_mode,
                "validation_ns": artifact.stats.validation_ns,
                "parser_workers": artifact.stats.parser_workers,
                "parser_tasks_submitted": artifact.stats.parser_tasks_submitted,
                "parser_queue_capacity": artifact.stats.parser_queue_capacity,
                "parser_peak_pending": artifact.stats.parser_peak_pending,
                "writer_mode": request.case.parameter("writer_mode") or "single",
            },
        )

    @staticmethod
    def _parser_worker_count(request: shared.CandidateRequest) -> int:
        configured = request.case.parameter("parser_workers")
        if configured is not None:
            return int(configured)
        if (
            request.case.case_id == f"build.scale.{request.fixture.profile}"
            and request.fixture.profile in {"production", "growth"}
        ):
            return min(4, os.cpu_count() or 1)
        return 1

    def _ordinary(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        artifact = publish_artifact(request.fixture, request.run_root)
        change = str(request.case.parameter("change"))
        started = time.perf_counter_ns()
        try:
            maintenance = apply_ordinary_change(artifact.path, change)
        except TailFoldRequired as fold:
            elapsed = time.perf_counter_ns() - started
            storage = artifact_metrics(
                artifact.path,
                occurrence_rows=artifact.stats.occurrence_rows,
            )
            return shared.CandidateResult(
                candidate_id=self.candidate_id,
                case_id=request.case.case_id,
                outcome=shared.RunOutcome.FAILED,
                measurements=self._values(
                    artifact,
                    storage,
                    sql_latencies_ns=(elapsed,),
                ),
                publication=self._publication(artifact, prior_queryable=True),
                oracle_results={
                    "change": change,
                    "tail_fold_required": True,
                    "tail_rows": fold.current_rows,
                    "requested_rows": fold.requested_rows,
                    "maximum_rows": fold.maximum_rows,
                    "fold_mode": "isolated_artifact",
                },
                detail_code="candidate_a.tail_fold_required",
            )
        elapsed = time.perf_counter_ns() - started
        storage = artifact_metrics(
            artifact.path,
            occurrence_rows=artifact.stats.occurrence_rows + maintenance.facts_inserted,
        )
        values = self._values(
            artifact,
            storage,
            maintenance=maintenance,
            sql_latencies_ns=(elapsed,),
        )
        if self._observe_stop(
            request,
            (
                (shared.StopMetric.ELAPSED_MS, _milliseconds(elapsed)),
                (shared.StopMetric.DATABASE_BYTES, storage.database_bytes),
                (shared.StopMetric.INDEX_BYTES, storage.index_bytes),
                (shared.StopMetric.WAL_BYTES, storage.wal_bytes),
                (shared.StopMetric.PROJECTION_FANOUT, maintenance.projection_rows_written),
            ),
        ):
            return self._stopped(request, values)
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=values,
            publication=self._publication(artifact, prior_queryable=True),
            oracle_results={
                "change": change,
                "incremental": True,
                "source_files_rescanned": 0,
                "dirty_keys": maintenance.dirty_keys,
            },
        )

    def _unsafe(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        change = str(request.case.parameter("change"))
        prior = build_artifact(request.fixture, request.run_root / "prior.sqlite")
        staging = build_artifact(
            request.fixture,
            request.run_root / "isolated-candidate.sqlite",
            parent_publication_id=prior.publication_id,
        )
        recanonicalized = 0
        phase = _UNSAFE_PHASES.get(change)
        if phase is not None:
            with database(staging.path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                recanonicalized = len(
                    apply_source_phase(
                        connection,
                        request.fixture,
                        group=phase[0],
                        phase=phase[1],
                    )
                )
                connection.commit()
                validate_database(connection)
        publication_path = request.run_root / "publication.sqlite"
        os.replace(staging.path, publication_path)
        artifact = BuildArtifact(
            path=publication_path,
            publication_id=staging.publication_id,
            observed_through_us=staging.observed_through_us,
            stats=staging.stats,
        )
        storage = artifact_metrics(
            artifact.path,
            occurrence_rows=artifact.stats.occurrence_rows + recanonicalized,
        )
        maintenance = MaintenanceStats(
            facts_recanonicalized=recanonicalized,
            writer_transactions=1,
            source_files_rescanned=artifact.stats.source_files_parsed,
            source_bytes_rescanned=artifact.stats.source_bytes_parsed,
        )
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=self._values(
                artifact,
                storage,
                maintenance=maintenance,
                prior_publication_survived=True,
            ),
            publication=self._publication(artifact, prior_queryable=True),
            oracle_results={
                "change": change,
                "protocol": "isolated_artifact",
                "prior_publication_id": prior.publication_id,
                "phase_occurrences": recanonicalized,
            },
        )

    def _query(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        artifact = self._query_artifact(request)
        started = time.perf_counter_ns()
        plan_stopped = False
        with database(artifact.path, read_only=True) as connection:
            result = self._execute_query_case(connection, request, artifact)
            plan_stopped = self._observe_stop(
                request,
                self._query_plan_observations(result),
            )
            if not plan_stopped and request.case.parameter("repeat") == 2:
                repeated = self._execute_query_case(connection, request, artifact)
                if repeated.encoded != result.encoded:
                    raise ValueError("candidate A repeated query is not deterministic")
                result = QueryResult(
                    payload=result.payload,
                    encoded=result.encoded,
                    sql_latencies_ns=result.sql_latencies_ns + repeated.sql_latencies_ns,
                    query_plans=result.query_plans + repeated.query_plans,
                    rows_scanned=result.rows_scanned + repeated.rows_scanned,
                    full_scan_count=result.full_scan_count + repeated.full_scan_count,
                    automatic_index_count=(
                        result.automatic_index_count + repeated.automatic_index_count
                    ),
                    temporary_sort_count=(
                        result.temporary_sort_count + repeated.temporary_sort_count
                    ),
                    oracle_equivalent=(result.oracle_equivalent and repeated.oracle_equivalent),
                    selector_pages_gap_free=(
                        result.selector_pages_gap_free and repeated.selector_pages_gap_free
                    ),
                )
                plan_stopped = self._observe_stop(
                    request,
                    self._query_plan_observations(result),
                )
        elapsed = time.perf_counter_ns() - started
        storage = artifact_metrics(
            artifact.path,
            occurrence_rows=artifact.stats.occurrence_rows,
        )
        values = self._values(
            artifact,
            storage,
            query=result,
            server_latency_ns=elapsed,
            mcp_latency_ns=elapsed,
        )
        if plan_stopped:
            return self._stopped(request, values)
        maximum_sql_ns = max(result.sql_latencies_ns, default=0)
        if self._observe_stop(
            request,
            (
                (shared.StopMetric.SQL_LATENCY_MS, _milliseconds(maximum_sql_ns)),
                (shared.StopMetric.MCP_LATENCY_MS, _milliseconds(elapsed)),
                (shared.StopMetric.RESPONSE_BYTES, len(result.encoded)),
                (shared.StopMetric.TRACKER_CALLS, 1),
            ),
        ):
            return self._stopped(request, values)
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=values,
            publication=self._publication(artifact, prior_queryable=True),
            oracle_results=result.payload,
        )

    def _query_artifact(self, request: shared.CandidateRequest) -> BuildArtifact:
        artifact = self._prepared_query_artifacts.get(request.repetition)
        if artifact is not None and artifact.path.resolve().is_relative_to(
            request.run_root.resolve()
        ):
            return artifact
        return publish_artifact(request.fixture, request.run_root)

    @staticmethod
    def _query_plan_observations(
        result: QueryResult,
    ) -> tuple[tuple[shared.StopMetric, int], ...]:
        return (
            (shared.StopMetric.FULL_SCAN_COUNT, result.full_scan_count),
            (
                shared.StopMetric.AUTOMATIC_INDEX_COUNT,
                result.automatic_index_count,
            ),
            (shared.StopMetric.TEMPORARY_SORT_COUNT, result.temporary_sort_count),
        )

    def _execute_query_case(
        self,
        connection: Any,
        request: shared.CandidateRequest,
        artifact: BuildArtifact,
    ) -> QueryResult:
        case_id = request.case.case_id
        if case_id == "query.feature.exact_count":
            return run_evidence_feature(
                connection,
                publication_id=artifact.publication_id,
                exact_count=True,
            )
        if case_id == "query.feature.selected_session_timeline":
            history = request.fixture.manifest["history"]["windows"]["current_session"]
            return run_evidence_feature(
                connection,
                publication_id=artifact.publication_id,
                selected_session_id=str(history["session_id"]),
            )
        if case_id.startswith("query.deep_keyset."):
            return run_evidence_feature(
                connection,
                publication_id=artifact.publication_id,
                page_position=int(request.case.parameter("page_position") or 0),
            )
        if case_id == "query.feature.bounded_full_sort":
            return run_bounded_sort(connection)
        question_id = str(request.case.parameter("question_id"))
        plan_id = str(request.case.parameter("plan_id"))
        return run_question(
            connection,
            request.fixture,
            question_id=question_id,
            plan_id=plan_id,
        )

    def _crash(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        boundary = request.case.parameter("boundary")
        fault = request.case.parameter("fault")
        crash_case = (
            shared.CrashCase.termination(str(boundary))
            if boundary is not None
            else shared.CrashCase.injected_fault(str(fault))
        )
        driver = CandidateACrashDriver(request.fixture, request.run_root / "crashes")
        if boundary is not None:
            observation = shared.run_publication_crash_case(
                driver,
                crash_case,
                request.fixture.crash_expectation(str(boundary)),
            )
        else:
            observation = driver.run_crash_case(crash_case)
            shared.validate_crash_observation(crash_case, {}, observation)
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=shared.MeasurementValues(
                oracle_equivalent=True,
                selector_pages_gap_free=True,
                prior_publication_survived=observation.prior_publication_queryable,
                answer_correct=True,
                writer_transactions=1,
            ),
            oracle_results={
                **asdict(observation),
                **driver.execution_evidence,
            },
        )

    def _dbhub(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        route = request.case.parameter("route")
        if route not in {"generic", "named_preset"}:
            raise ValueError("candidate A DBHub readiness route is invalid")
        artifact = publish_artifact(request.fixture, request.run_root)
        storage = artifact_metrics(
            artifact.path,
            occurrence_rows=artifact.stats.occurrence_rows,
        )
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=self._values(
                artifact,
                storage,
                response_bytes=256,
                tracker_calls=1,
            ),
            publication=self._publication(artifact, prior_queryable=True),
            oracle_results={
                "route": route,
                "tool": ("search_objects+execute_sql" if route == "generic" else "top_sessions"),
                "ready_for_shared_dbhub_runner": True,
            },
        )

    def _agent_perf(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        contract_path = Path(__file__).with_name("agent-perf-workload.json")
        contract = shared.load_agent_perf_workload(contract_path)
        if contract.candidate_id != self.candidate_id:
            raise ValueError("candidate A agent-perf contract has wrong candidate")
        artifact = publish_artifact(request.fixture, request.run_root)
        storage = artifact_metrics(
            artifact.path,
            occurrence_rows=artifact.stats.occurrence_rows,
        )
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.PASSED,
            measurements=self._values(artifact, storage),
            publication=self._publication(artifact, prior_queryable=True),
            oracle_results={
                "workload_file": contract_path.name,
                "workload_digest": contract.digest,
                "workload_id": contract.workload_id,
                "minimum_unprofiled_runs": contract.minimum_unprofiled_runs,
            },
        )

    @staticmethod
    def _observe_stop(
        request: shared.CandidateRequest,
        observations: tuple[tuple[shared.StopMetric, int], ...],
    ) -> bool:
        for metric, value in observations:
            if request.stop.observe(metric, value) is not None:
                return True
        return False

    def _stopped(
        self,
        request: shared.CandidateRequest,
        values: shared.MeasurementValues,
    ) -> shared.CandidateResult:
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=shared.RunOutcome.STOPPED,
            measurements=values,
            oracle_results={"partial": True},
        )

    @staticmethod
    def _publication(
        artifact: BuildArtifact,
        *,
        prior_queryable: bool,
    ) -> shared.PublicationState:
        return shared.PublicationState(
            publication_id=artifact.publication_id,
            artifact_path=artifact.path,
            prior_publication_queryable=prior_queryable,
        )

    @staticmethod
    def _values(
        artifact: BuildArtifact,
        storage: ArtifactMetrics,
        *,
        maintenance: MaintenanceStats | None = None,
        query: QueryResult | None = None,
        parser_worker_time_ns: int = 0,
        parallel_efficiency_ppm: int = 0,
        queue_wait_ns: int = 0,
        merge_time_ns: int = 0,
        writer_utilization_ppm: int = 0,
        server_latency_ns: int = 0,
        mcp_latency_ns: int = 0,
        response_bytes: int | None = None,
        tracker_calls: int | None = None,
        prior_publication_survived: bool = True,
        sql_latencies_ns: tuple[int, ...] = (),
    ) -> shared.MeasurementValues:
        ingest: IngestStats = artifact.stats
        update = maintenance or MaintenanceStats()
        query_result = query
        projection_consumers = (
            (
                "session_usage_current",
                update.dirty_keys,
                update.projection_rows_read,
                update.projection_rows_written,
            ),
            (
                "tool_family_current",
                update.dirty_keys,
                update.projection_rows_read,
                update.projection_rows_written,
            ),
        )
        return shared.MeasurementValues(
            peak_rss_bytes=storage.peak_rss_bytes,
            parser_worker_time_ns=parser_worker_time_ns,
            parallel_efficiency_ppm=parallel_efficiency_ppm,
            queue_wait_ns=queue_wait_ns,
            merge_time_ns=merge_time_ns,
            writer_utilization_ppm=writer_utilization_ppm,
            fact_rows=storage.fact_rows,
            lifecycle_rows=storage.lifecycle_rows,
            occurrence_rows=storage.occurrence_rows,
            sequence_rows=0,
            projection_rows=storage.projection_rows,
            database_bytes=storage.database_bytes,
            table_bytes=storage.table_bytes,
            index_bytes=storage.index_bytes,
            free_list_bytes=storage.free_list_bytes,
            wal_bytes=storage.wal_bytes,
            journal_bytes=storage.journal_bytes,
            pages_written=storage.pages_written,
            writer_transactions=ingest.writer_transactions + update.writer_transactions,
            source_files_inventoried=ingest.source_files_inventoried,
            source_files_selected=ingest.source_files_selected,
            source_files_parsed=ingest.source_files_parsed,
            source_files_deferred=ingest.source_files_deferred,
            source_files_rescanned=update.source_files_rescanned,
            source_bytes_inventoried=ingest.source_bytes_inventoried,
            source_bytes_selected=ingest.source_bytes_selected,
            source_bytes_parsed=ingest.source_bytes_parsed,
            source_bytes_deferred=ingest.source_bytes_deferred,
            source_bytes_rescanned=update.source_bytes_rescanned,
            facts_inserted=ingest.facts_inserted + update.facts_inserted,
            facts_updated=ingest.facts_updated + update.facts_updated,
            facts_recanonicalized=update.facts_recanonicalized,
            facts_unchanged=update.facts_unchanged,
            dirty_keys=update.dirty_keys,
            projection_rows_read=update.projection_rows_read,
            projection_rows_written=update.projection_rows_written,
            projection_consumers=projection_consumers,
            sql_latencies_ns=(
                query_result.sql_latencies_ns if query_result is not None else sql_latencies_ns
            ),
            sql_statements=(
                len(query_result.sql_latencies_ns)
                if query_result is not None
                else len(sql_latencies_ns)
            ),
            rows_scanned=query_result.rows_scanned if query_result is not None else 0,
            explain_query_plans=(query_result.query_plans if query_result is not None else ()),
            full_scan_count=(query_result.full_scan_count if query_result is not None else 0),
            automatic_index_count=(
                query_result.automatic_index_count if query_result is not None else 0
            ),
            temporary_sort_count=(
                query_result.temporary_sort_count if query_result is not None else 0
            ),
            server_latency_ns=server_latency_ns,
            mcp_latency_ns=mcp_latency_ns,
            response_bytes=(
                len(query_result.encoded) if query_result is not None else response_bytes or 0
            ),
            duplicated_representation_bytes=0,
            tracker_calls=(1 if query_result is not None else tracker_calls or 0),
            tracker_batches=1 if query_result is not None else 0,
            tracker_polls=0,
            tracker_retries=0,
            refresh_jobs=0,
            oracle_equivalent=(
                query_result.oracle_equivalent if query_result is not None else True
            ),
            selector_pages_gap_free=(
                query_result.selector_pages_gap_free if query_result is not None else True
            ),
            prior_publication_survived=prior_publication_survived,
            answer_correct=(query_result.oracle_equivalent if query_result is not None else True),
        )


def _milliseconds(nanoseconds: int) -> int:
    return (nanoseconds + 999_999) // 1_000_000
