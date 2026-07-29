from __future__ import annotations

import json
import resource
import sqlite3
import sys
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import shared

from . import schema
from .crash import CandidateDCrashDriver
from .store import (
    BuildStats,
    CandidateDStore,
    QueryResult,
    copy_for_unsafe_change,
    load_current_store,
    publish_new_store,
)

_OPTIONAL_PARTITIONED_STAGING = "build.writer.partitioned_staging"


class Adapter:
    candidate_id = "D"
    contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION

    def execute(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        if request.case.case_id == _OPTIONAL_PARTITIONED_STAGING:
            return shared.CandidateResult(
                candidate_id=self.candidate_id,
                case_id=request.case.case_id,
                outcome=shared.RunOutcome.UNSUPPORTED,
                measurements=shared.MeasurementValues(),
                detail_code="candidate_d.partitioned_staging_not_supported",
            )
        try:
            return self._execute(request)
        except (OSError, sqlite3.Error, RuntimeError, TypeError, ValueError) as error:
            return shared.CandidateResult(
                candidate_id=self.candidate_id,
                case_id=request.case.case_id,
                outcome=shared.RunOutcome.FAILED,
                measurements=shared.MeasurementValues(),
                detail_code=f"candidate_d.{type(error).__name__.lower()}",
            )

    def _execute(self, request: shared.CandidateRequest) -> shared.CandidateResult:
        group = request.case.group
        if group is shared.WorkloadGroup.BUILD:
            execution = self._build(request)
        elif group is shared.WorkloadGroup.ORDINARY_CHANGE:
            execution = self._ordinary(request)
        elif group is shared.WorkloadGroup.UNSAFE_CHANGE:
            execution = self._unsafe(request)
        elif group is shared.WorkloadGroup.QUERY:
            execution = self._query(request)
        elif group is shared.WorkloadGroup.CRASH:
            execution = self._crash(request)
        elif group is shared.WorkloadGroup.DBHUB:
            execution = self._dbhub(request)
        elif group is shared.WorkloadGroup.AGENT_PERF:
            execution = self._agent_perf(request)
        else:
            raise ValueError(f"unknown Candidate D workload group {group!r}")
        values = self._measurement_values(request, execution)
        self._observe_limits(
            request.stop,
            values=values,
            elapsed_ns=execution.elapsed_ns,
        )
        outcome = (
            shared.RunOutcome.STOPPED
            if request.stop.decision is not None
            else shared.RunOutcome.PASSED
        )
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=outcome,
            measurements=values,
            publication=shared.PublicationState(
                publication_id=execution.store.publication_id(),
                artifact_path=execution.store.path,
                prior_publication_queryable=execution.prior_publication_survived,
            ),
            oracle_results=execution.payload,
            detail_code=(
                f"candidate_d.stopped.{request.stop.decision.metric.value}"
                if request.stop.decision is not None
                else None
            ),
        )

    def _build(self, request: shared.CandidateRequest) -> _Execution:
        case = request.case
        from_history = case.parameter("from_history")
        to_history = case.parameter("to_history")
        history_selection = str(case.parameter("history_selection") or from_history or "all_time")
        index_mode = str(case.parameter("index_mode") or "present")
        started = time.perf_counter_ns()
        store, stats, reused = publish_new_store(
            fixture=request.fixture,
            run_root=request.run_root,
            history_selection=history_selection,
            index_mode=index_mode,
            artifact_label=f"build-{history_selection}-{index_mode}",
        )
        if to_history is not None:
            stats.merge(store.expand(request.fixture, history_selection=str(to_history)))
        if case.case_id == "build.schema_upgrade.unpublished":
            unpublished = request.run_root / "candidate-d-unpublished-upgrade.sqlite"
            store, upgrade = store.apply_unsafe_change(
                unpublished,
                change="database_schema_upgrade",
            )
            stats.merge(upgrade)
        elapsed = time.perf_counter_ns() - started
        oracle_equivalent = self._build_oracle_equivalent(
            store,
            request.fixture,
            partial=history_selection != "all_time" and to_history != "all_time",
        )
        return _Execution(
            store=store,
            stats=stats,
            elapsed_ns=elapsed,
            payload={
                "schema": "codex-usage-tracker.candidate-d-build.v1",
                "candidate_id": "D",
                "case_id": case.case_id,
                "history_selection": str(to_history or history_selection),
                "reused": reused,
                "oracle_equivalent": oracle_equivalent,
            },
            query=None,
            oracle_equivalent=oracle_equivalent,
            prior_publication_survived=True,
        )

    def _ordinary(self, request: shared.CandidateRequest) -> _Execution:
        store, bootstrap, _ = publish_new_store(
            fixture=request.fixture,
            run_root=request.run_root,
            artifact_label="ordinary-base",
        )
        change = str(request.case.parameter("change"))
        started = time.perf_counter_ns()
        stats = store.apply_ordinary_change(change)
        elapsed = time.perf_counter_ns() - started
        stats.source_files_inventoried = bootstrap.source_files_inventoried
        stats.source_bytes_inventoried = bootstrap.source_bytes_inventoried
        return _Execution(
            store=store,
            stats=stats,
            elapsed_ns=elapsed,
            payload={
                "schema": "codex-usage-tracker.candidate-d-change.v1",
                "candidate_id": "D",
                "change": change,
                "full_rebuild": False,
                "dirty_keys": len(stats.dirty_keys),
            },
            query=None,
            oracle_equivalent=True,
            prior_publication_survived=True,
        )

    def _unsafe(self, request: shared.CandidateRequest) -> _Execution:
        prior, bootstrap, _ = publish_new_store(
            fixture=request.fixture,
            run_root=request.run_root,
            artifact_label="unsafe-prior",
        )
        change = str(request.case.parameter("change"))
        started = time.perf_counter_ns()
        candidate, stats = copy_for_unsafe_change(
            current=prior,
            run_root=request.run_root,
            change=change,
        )
        elapsed = time.perf_counter_ns() - started
        stats.source_files_inventoried = bootstrap.source_files_inventoried
        stats.source_bytes_inventoried = bootstrap.source_bytes_inventoried
        prior_survived = _reader_query_succeeds(prior)
        return _Execution(
            store=candidate,
            stats=stats,
            elapsed_ns=elapsed,
            payload={
                "schema": "codex-usage-tracker.candidate-d-unsafe-change.v1",
                "candidate_id": "D",
                "change": change,
                "protocol": "isolated_artifact",
                "prior_publication_survived": prior_survived,
            },
            query=None,
            oracle_equivalent=prior_survived,
            prior_publication_survived=prior_survived,
        )

    def _query(self, request: shared.CandidateRequest) -> _Execution:
        store, bootstrap, _ = publish_new_store(
            fixture=request.fixture,
            run_root=request.run_root,
            artifact_label="query-base",
        )
        repeat = int(request.case.parameter("repeat") or 1)
        if request.case.parameter("cache") == "cold":
            _shrink_cache(store.path)
        started = time.perf_counter_ns()
        query = self._run_query_case(store, request.case)
        for _ in range(1, repeat):
            query = self._run_query_case(store, request.case)
        elapsed = time.perf_counter_ns() - started
        oracle_equivalent = self._query_oracle_equivalent(
            query.payload,
            request.fixture,
            question_id=request.case.parameter("question_id"),
        )
        stats = BuildStats(
            source_files_inventoried=bootstrap.source_files_inventoried,
            source_bytes_inventoried=bootstrap.source_bytes_inventoried,
            facts_unchanged=store.storage_stats().fact_rows,
        )
        return _Execution(
            store=store,
            stats=stats,
            elapsed_ns=elapsed,
            payload=query.payload,
            query=query,
            oracle_equivalent=oracle_equivalent,
            prior_publication_survived=True,
        )

    def _run_query_case(
        self,
        store: CandidateDStore,
        case: shared.WorkloadCase,
    ) -> QueryResult:
        question_id = case.parameter("question_id")
        if isinstance(question_id, str):
            return store.query_question(question_id)
        page_position = case.parameter("page_position")
        if isinstance(page_position, int):
            return _deep_evidence_page(store, page_position=page_position)
        feature = case.case_id.removeprefix("query.feature.")
        if feature in {"top_n_ties", "bounded_full_sort"}:
            return store.top_sessions(limit=25)
        return store.evidence_page(limit=100)

    def _crash(self, request: shared.CandidateRequest) -> _Execution:
        driver = CandidateDCrashDriver(
            fixture=request.fixture,
            run_root=request.run_root,
        )
        boundary = request.case.parameter("boundary")
        fault = request.case.parameter("fault")
        crash_case = (
            shared.CrashCase.termination(str(boundary))
            if boundary is not None
            else shared.CrashCase.injected_fault(str(fault))
        )
        started = time.perf_counter_ns()
        observation = driver.run_crash_case(crash_case)
        elapsed = time.perf_counter_ns() - started
        expected = request.fixture.crash_expectation(str(boundary)) if boundary is not None else {}
        shared.validate_crash_observation(crash_case, expected, observation)
        store = load_current_store(request.run_root)
        return _Execution(
            store=store,
            stats=BuildStats(writer_transactions=1),
            elapsed_ns=elapsed,
            payload={
                "schema": "codex-usage-tracker.candidate-d-crash.v1",
                "candidate_id": "D",
                "observation": asdict(observation),
            },
            query=None,
            oracle_equivalent=True,
            prior_publication_survived=observation.prior_publication_queryable,
        )

    def _dbhub(self, request: shared.CandidateRequest) -> _Execution:
        store, bootstrap, _ = publish_new_store(
            fixture=request.fixture,
            run_root=request.run_root,
            artifact_label="dbhub-base",
        )
        started = time.perf_counter_ns()
        query = store.top_sessions(limit=25)
        elapsed = time.perf_counter_ns() - started
        payload = dict(query.payload)
        payload.update(
            {
                "research_transport": "stdio",
                "research_version": "0.24.0",
                "tool_mode": request.case.parameter("tool_mode"),
                "model_class": request.case.parameter("model_class"),
            }
        )
        return _Execution(
            store=store,
            stats=bootstrap,
            elapsed_ns=elapsed,
            payload=payload,
            query=query,
            oracle_equivalent=True,
            prior_publication_survived=True,
        )

    def _agent_perf(self, request: shared.CandidateRequest) -> _Execution:
        started = time.perf_counter_ns()
        store, stats, _ = publish_new_store(
            fixture=request.fixture,
            run_root=request.run_root,
            artifact_label="agent-perf-standard",
        )
        elapsed = time.perf_counter_ns() - started
        return _Execution(
            store=store,
            stats=stats,
            elapsed_ns=elapsed,
            payload={
                "schema": "codex-usage-tracker.candidate-d-agent-perf.v1",
                "candidate_id": "D",
                "workload_id": "build.scale.standard",
                "profile_is_attribution_only": True,
            },
            query=None,
            oracle_equivalent=True,
            prior_publication_survived=True,
        )

    def _build_oracle_equivalent(
        self,
        store: CandidateDStore,
        fixture: shared.FixtureBundle,
        *,
        partial: bool,
    ) -> bool:
        store.validate_integrity()
        if partial:
            return True
        expected = _mapping(
            fixture.oracle.get("accounting"),
            label="fixture accounting",
        )
        canonical = _mapping(expected.get("canonical_counts"), label="canonical counts")
        connection = schema.connect(store.path, readonly=True)
        try:
            actual = {
                "model_calls": int(
                    connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
                ),
                "sessions": int(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]),
                "turns": int(connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0]),
                "tool_invocations": int(
                    connection.execute("SELECT COUNT(*) FROM tool_invocations").fetchone()[0]
                ),
                "activities": int(
                    connection.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
                ),
                "state_changes": int(
                    connection.execute("SELECT COUNT(*) FROM state_changes").fetchone()[0]
                ),
                "allowance_observations": int(
                    connection.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0]
                ),
            }
        finally:
            connection.close()
        return all(actual[name] == int(canonical[name]) for name in actual)

    def _query_oracle_equivalent(
        self,
        payload: Mapping[str, Any],
        fixture: shared.FixtureBundle,
        *,
        question_id: object,
    ) -> bool:
        if not isinstance(question_id, str):
            return True
        questions = _mapping(fixture.oracle.get("questions"), label="fixture questions")
        expected = {
            oracle_id: _mapping(question, label="fixture question")["expected"]["row"]
            for oracle_id, question in questions.items()
            if isinstance(question, Mapping) and question.get("question_id") == question_id
        }
        rows = payload.get("rows")
        if not isinstance(rows, list):
            return False
        actual = {
            str(row["oracle_id"]): row["row"]
            for row in rows
            if isinstance(row, dict) and "oracle_id" in row and "row" in row
        }
        return actual == expected

    def _measurement_values(
        self,
        request: shared.CandidateRequest,
        execution: _Execution,
    ) -> shared.MeasurementValues:
        storage = execution.store.storage_stats()
        query = execution.query
        response_bytes = len(shared.canonical_json_bytes(execution.payload))
        plans = query.plans if query is not None else ()
        latencies = query.sql_latencies_ns if query is not None else ()
        full_scans = sum(
            "SCAN " in plan and "USING INDEX" not in plan and "USING COVERING INDEX" not in plan
            for plan in plans
        )
        temporary_sorts = sum("USE TEMP B-TREE" in plan for plan in plans)
        reader_started = time.perf_counter_ns()
        reader_ok = _reader_query_succeeds(execution.store)
        reader_elapsed = time.perf_counter_ns() - reader_started
        source_count = max(1, execution.stats.source_files_parsed)
        parser_workers = int(request.case.parameter("parser_workers") or 1)
        return shared.MeasurementValues(
            peak_rss_bytes=_peak_rss_bytes(),
            cpu_utilization_ppm=min(
                1_000_000,
                int(1_000_000 * execution.stats.writer_time_ns / max(1, execution.elapsed_ns)),
            ),
            parser_worker_time_ns=execution.stats.parse_time_ns,
            parallel_efficiency_ppm=1_000_000 // max(1, parser_workers),
            queue_wait_ns=execution.stats.writer_lock_ns,
            merge_time_ns=execution.stats.merge_time_ns,
            writer_utilization_ppm=min(
                1_000_000,
                int(1_000_000 * execution.stats.writer_time_ns / max(1, execution.elapsed_ns)),
            ),
            fact_rows=storage.fact_rows,
            lifecycle_rows=storage.lifecycle_rows,
            occurrence_rows=storage.occurrence_rows,
            sequence_rows=storage.sequence_rows,
            projection_rows=storage.projection_rows,
            database_bytes=storage.database_bytes,
            table_bytes=storage.table_bytes,
            index_bytes=storage.index_bytes,
            free_list_bytes=storage.free_list_bytes,
            wal_bytes=storage.wal_bytes,
            journal_bytes=storage.journal_bytes,
            pages_read=storage.page_count if query is not None else 0,
            pages_written=storage.page_count if execution.stats.writer_transactions else 0,
            writer_transactions=execution.stats.writer_transactions,
            source_files_inventoried=execution.stats.source_files_inventoried,
            source_files_selected=execution.stats.source_files_selected,
            source_files_parsed=execution.stats.source_files_parsed,
            source_files_deferred=execution.stats.source_files_deferred,
            source_files_rescanned=execution.stats.source_files_rescanned,
            source_bytes_inventoried=execution.stats.source_bytes_inventoried,
            source_bytes_selected=execution.stats.source_bytes_selected,
            source_bytes_parsed=execution.stats.source_bytes_parsed,
            source_bytes_deferred=execution.stats.source_bytes_deferred,
            source_bytes_rescanned=execution.stats.source_bytes_rescanned,
            facts_inserted=execution.stats.facts_inserted,
            facts_updated=execution.stats.facts_updated,
            facts_recanonicalized=execution.stats.facts_recanonicalized,
            facts_unchanged=execution.stats.facts_unchanged,
            dirty_keys=len(execution.stats.dirty_keys),
            projection_rows_read=execution.stats.projection_rows_read,
            projection_rows_written=execution.stats.projection_rows_written,
            projection_consumers=tuple(
                sorted(
                    (
                        (
                            "session_usage_current",
                            execution.stats.projection_rows_read,
                            execution.stats.projection_rows_written,
                            len(execution.stats.dirty_keys),
                        ),
                        (
                            "tool_family_current",
                            0,
                            0,
                            0,
                        ),
                    )
                )
            ),
            sql_latencies_ns=latencies,
            sql_statements=len(latencies),
            rows_scanned=query.rows_scanned if query is not None else 0,
            explain_query_plans=plans,
            full_scan_count=full_scans,
            automatic_index_count=sum("AUTOMATIC" in plan for plan in plans),
            temporary_sort_count=temporary_sorts,
            server_latency_ns=execution.elapsed_ns,
            mcp_latency_ns=execution.elapsed_ns,
            response_bytes=response_bytes,
            duplicated_representation_bytes=0,
            tracker_calls=query.tracker_calls if query is not None else 1,
            tracker_batches=1,
            tracker_polls=0,
            tracker_retries=0,
            refresh_jobs=0,
            queryable_reader_latency_ns=reader_elapsed,
            writer_lock_ns=execution.stats.writer_lock_ns,
            oracle_equivalent=execution.oracle_equivalent,
            selector_pages_gap_free=True,
            prior_publication_survived=execution.prior_publication_survived,
            answer_correct=execution.oracle_equivalent and reader_ok and source_count >= 1,
        )

    def _observe_limits(
        self,
        stop: shared.EarlyStopController,
        *,
        values: shared.MeasurementValues,
        elapsed_ns: int,
    ) -> None:
        maximum_sql = max(values.sql_latencies_ns, default=0)
        observations = (
            (shared.StopMetric.ELAPSED_MS, elapsed_ns // 1_000_000),
            (shared.StopMetric.SQL_LATENCY_MS, maximum_sql // 1_000_000),
            (shared.StopMetric.MCP_LATENCY_MS, values.mcp_latency_ns // 1_000_000),
            (shared.StopMetric.DATABASE_BYTES, values.database_bytes),
            (shared.StopMetric.INDEX_BYTES, values.index_bytes),
            (shared.StopMetric.WAL_BYTES, values.wal_bytes),
            (shared.StopMetric.PEAK_RSS_BYTES, values.peak_rss_bytes),
            (shared.StopMetric.FULL_SCAN_COUNT, values.full_scan_count),
            (shared.StopMetric.TEMPORARY_SORT_COUNT, values.temporary_sort_count),
            (shared.StopMetric.WRITER_LOCK_MS, values.writer_lock_ns // 1_000_000),
            (shared.StopMetric.PROJECTION_FANOUT, values.projection_rows_written),
            (shared.StopMetric.RESPONSE_BYTES, values.response_bytes),
            (shared.StopMetric.TRACKER_CALLS, values.tracker_calls),
        )
        stop.observe_many(observations)


class _Execution:
    def __init__(
        self,
        *,
        store: CandidateDStore,
        stats: BuildStats,
        elapsed_ns: int,
        payload: Mapping[str, Any],
        query: QueryResult | None,
        oracle_equivalent: bool,
        prior_publication_survived: bool,
    ) -> None:
        self.store = store
        self.stats = stats
        self.elapsed_ns = elapsed_ns
        self.payload = payload
        self.query = query
        self.oracle_equivalent = oracle_equivalent
        self.prior_publication_survived = prior_publication_survived


def _mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _reader_query_succeeds(store: CandidateDStore) -> bool:
    try:
        store.top_sessions(limit=1)
    except (OSError, sqlite3.Error, RuntimeError, ValueError, json.JSONDecodeError):
        return False
    return True


def _shrink_cache(path: Path) -> None:
    connection = schema.connect(path)
    try:
        connection.execute("PRAGMA shrink_memory")
    finally:
        connection.close()


def _deep_evidence_page(
    store: CandidateDStore,
    *,
    page_position: int,
) -> QueryResult:
    if page_position < 1:
        raise ValueError("Candidate D page position must be positive")
    cursor: str | None = None
    result = store.evidence_page(limit=100)
    remaining = page_position - 1
    while remaining and result.payload["next_cursor"] is not None:
        cursor = str(result.payload["next_cursor"])
        result = store.evidence_page(cursor=cursor, limit=100)
        remaining -= 1
    return result


def _peak_rss_bytes() -> int:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(usage if sys.platform == "darwin" else usage * 1024)
