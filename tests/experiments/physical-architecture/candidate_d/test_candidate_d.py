from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_d = importlib.import_module("candidate_d")
candidate_schema = importlib.import_module("candidate_d.schema")

_TINY = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
_AGENT_PERF_WORKLOAD = _EXPERIMENT_ROOT / "candidate_d" / "agent-perf-workload.json"
_REQUIRED_QUESTION_IDS = set(shared.P1_QUESTION_IDS) | set(shared.REQUIRED_SLICE_QUESTION_IDS)


@pytest.fixture(scope="module")
def fixture() -> shared.FixtureBundle:
    return shared.load_fixture_bundle(_TINY)


@pytest.fixture
def store(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
) -> Iterator[candidate_d.CandidateDStore]:
    result, _, _ = candidate_d.publish_new_store(
        fixture=fixture,
        run_root=tmp_path,
    )
    yield result


def _connection(store: candidate_d.CandidateDStore) -> sqlite3.Connection:
    connection = sqlite3.connect(store.path)
    connection.row_factory = sqlite3.Row
    return connection


def _case(case_id: str) -> shared.WorkloadCase:
    return shared.build_workload_matrix(physical_cores=12).by_id(case_id)


def _request(
    *,
    case_id: str,
    fixture: shared.FixtureBundle,
    run_root: Path,
) -> shared.CandidateRequest:
    case = _case(case_id)
    run_root.mkdir(parents=True, exist_ok=True)
    return shared.CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=run_root,
        repetition=0,
        stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
    )


def _oracle_rows(
    fixture: shared.FixtureBundle,
    question_id: str,
) -> dict[str, object]:
    return {
        oracle_id: question["expected"]["row"]
        for oracle_id, question in fixture.oracle["questions"].items()
        if question["question_id"] == question_id
    }


def test_schema_is_typed_and_compact_sequence_is_synchronized(
    store: candidate_d.CandidateDStore,
) -> None:
    connection = _connection(store)
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
        }
        assert {
            "sessions",
            "session_parent_observations",
            "turns",
            "model_calls",
            "tool_invocations",
            "tool_transitions",
            "state_changes",
            "allowance_observations",
            "occurrences",
            "sequence_index",
        } <= tables
        sequence_columns = [
            str(row["name"]) for row in connection.execute("PRAGMA table_info(sequence_index)")
        ]
        assert sequence_columns == [
            "missing_time",
            "event_at_us",
            "source_order",
            "event_kind_order",
            "logical_id",
            "entity_kind",
            "occurrence_pk",
        ]
        sequence_sql = str(
            connection.execute(
                "SELECT sql FROM sqlite_schema WHERE name = 'sequence_index'"
            ).fetchone()[0]
        )
        assert "WITHOUT ROWID" in sequence_sql
        assert int(connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]) == 100
        assert int(connection.execute("SELECT COUNT(*) FROM tool_invocations").fetchone()[0]) == 25
        assert int(connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]) == 10
        assert int(connection.execute("SELECT COUNT(*) FROM turns").fetchone()[0]) == 50
        assert int(connection.execute("SELECT COUNT(*) FROM occurrences").fetchone()[0]) == 338
        assert int(connection.execute("SELECT COUNT(*) FROM sequence_index").fetchone()[0]) == 242
        assert (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM occurrences WHERE canonical = 0"
                ).fetchone()[0]
            )
            == 2
        )
        schema_text = "\n".join(
            str(row[0])
            for row in connection.execute("SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL")
        ).lower()
        assert "command_body" not in schema_text
        assert "tool_output_body" not in schema_text
    finally:
        connection.close()
    store.validate_integrity()


def test_sequence_integrity_check_detects_a_missing_mapping(
    store: candidate_d.CandidateDStore,
) -> None:
    connection = _connection(store)
    try:
        occurrence = int(
            connection.execute(
                "SELECT occurrence_pk FROM sequence_index ORDER BY logical_id LIMIT 1"
            ).fetchone()[0]
        )
        connection.execute(
            "DELETE FROM sequence_index WHERE occurrence_pk = ?",
            (occurrence,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(
        candidate_d.CandidateDIntegrityError,
        match="not synchronized",
    ):
        store.validate_integrity()


@pytest.mark.parametrize("question_id", sorted(_REQUIRED_QUESTION_IDS))
def test_every_required_question_returns_exact_fixture_rows_and_selectors(
    store: candidate_d.CandidateDStore,
    fixture: shared.FixtureBundle,
    question_id: str,
) -> None:
    result = store.query_question(question_id)
    actual = {row["oracle_id"]: row["row"] for row in result.payload["rows"]}

    assert actual == _oracle_rows(fixture, question_id)
    assert result.payload["row_count"] == 2
    assert all(row["selectors"] for row in result.payload["rows"])
    assert result.sql_latencies_ns
    assert result.plans
    assert all("question_id_idx" in plan for plan in result.plans if "SEARCH" in plan)


def test_equal_time_evidence_uses_compact_sequence_and_gap_free_keysets(
    store: candidate_d.CandidateDStore,
    fixture: shared.FixtureBundle,
) -> None:
    expected = fixture.oracle["evidence"]["equal_time_rows"]
    cursor: str | None = None
    rows: list[Mapping[str, object]] = []
    while True:
        result = store.evidence_page(
            cursor=cursor,
            limit=3,
            entity_kind=9,
        )
        rows.extend(result.payload["rows"])
        cursor = result.payload["next_cursor"]
        if cursor is None:
            break

    assert [row["logical_id"] for row in rows] == [row["logical_id"] for row in expected]
    assert [row["order_key"] for row in rows] == [row["order_key"] for row in expected]
    assert [row["selector"] for row in rows] == [row["selector"] for row in expected]
    assert [row["occurrence_coordinate"] for row in rows] == [
        row["occurrence_coordinate"] for row in expected
    ]
    assert len(rows) == len({tuple(row["order_key"]) for row in rows})
    assert any("sequence_index" in plan for plan in result.plans)


def test_late_event_enters_its_total_order_position_without_rebuild(
    store: candidate_d.CandidateDStore,
) -> None:
    connection = _connection(store)
    try:
        latest_before = int(
            connection.execute("SELECT MAX(event_at_us) FROM sequence_index").fetchone()[0]
        )
        calls_before = int(connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0])
    finally:
        connection.close()

    stats = store.apply_ordinary_change("late_event")

    connection = _connection(store)
    try:
        late_row = connection.execute(
            """
            SELECT event_at_us, logical_id
            FROM sequence_index
            WHERE logical_id LIKE 'call:candidate-d:%'
            ORDER BY event_at_us
            LIMIT 1
            """
        ).fetchone()
        calls_after = int(connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0])
    finally:
        connection.close()
    assert int(late_row["event_at_us"]) < latest_before
    assert calls_after == calls_before + 1
    assert stats.source_files_parsed == 0
    assert len(stats.dirty_keys) == 1


def test_lifecycle_parent_allowance_and_state_change_facts_are_exact(
    store: candidate_d.CandidateDStore,
) -> None:
    connection = _connection(store)
    try:
        assert int(connection.execute("SELECT COUNT(*) FROM tool_transitions").fetchone()[0]) == 49
        assert (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM tool_invocations WHERE terminal_occurrence_pk IS NULL"
                ).fetchone()[0]
            )
            == 1
        )
        assert (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM state_changes WHERE causal_attribution IS NULL"
                ).fetchone()[0]
            )
            == 5
        )
        assert {
            int(row[0])
            for row in connection.execute(
                "SELECT DISTINCT preceding_activity_count FROM state_changes"
            )
        } == {2}
        assert (
            int(connection.execute("SELECT COUNT(*) FROM allowance_observations").fetchone()[0])
            == 4
        )
        assert (
            int(connection.execute("SELECT COUNT(*) FROM allowance_compatibility").fetchone()[0])
            == 1
        )
        late_parent = connection.execute(
            """
            SELECT child_session_id, parent_session_id, transition
            FROM session_parent_observations
            """
        ).fetchone()
        assert late_parent is not None
        assert late_parent["child_session_id"] != late_parent["parent_session_id"]
        assert late_parent["transition"] == "parent_observed_late"
        assert (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM sessions WHERE direct_parent_session_id IS NOT NULL"
                ).fetchone()[0]
            )
            >= 1
        )
        depths = [
            int(row[0])
            for row in connection.execute(
                "SELECT delegation_depth FROM sessions ORDER BY delegation_depth"
            )
        ]
        assert depths[-1] >= 1
    finally:
        connection.close()


def test_tool_terminal_transition_adds_a_distinct_transition_occurrence(
    store: candidate_d.CandidateDStore,
) -> None:
    connection = _connection(store)
    try:
        transitions_before = int(
            connection.execute("SELECT COUNT(*) FROM tool_transitions").fetchone()[0]
        )
        sequence_before = int(
            connection.execute("SELECT COUNT(*) FROM sequence_index").fetchone()[0]
        )
    finally:
        connection.close()

    stats = store.apply_ordinary_change("tool_terminal_transition")

    connection = _connection(store)
    try:
        assert (
            int(connection.execute("SELECT COUNT(*) FROM tool_transitions").fetchone()[0])
            == transitions_before + 1
        )
        assert (
            int(connection.execute("SELECT COUNT(*) FROM sequence_index").fetchone()[0])
            == sequence_before + 1
        )
        assert (
            int(
                connection.execute(
                    "SELECT COUNT(*) FROM tool_invocations WHERE terminal_occurrence_pk IS NULL"
                ).fetchone()[0]
            )
            == 0
        )
    finally:
        connection.close()
    assert stats.source_files_parsed == 0


@pytest.mark.parametrize(
    "change",
    [
        "no_source_change",
        "one_model_call",
        "one_tool_start",
        "tool_terminal_transition",
        "tool_plus_state_change",
        "32_call_tail",
        "2000_call_tail",
        "late_event",
        "rate_card_change",
    ],
)
def test_every_ordinary_change_is_a_bounded_in_place_transaction(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
    change: str,
) -> None:
    store, _, _ = candidate_d.publish_new_store(
        fixture=fixture,
        run_root=tmp_path,
    )
    inode_before = store.path.stat().st_ino
    stats = store.apply_ordinary_change(change)

    assert store.path.stat().st_ino == inode_before
    assert stats.writer_transactions == 1
    assert stats.source_files_parsed == 0
    assert stats.source_bytes_parsed == 0
    assert stats.projection_rows_written <= max(1, len(stats.dirty_keys))
    store.validate_integrity()


@pytest.mark.parametrize(
    "change",
    [
        "source_truncation",
        "source_replacement",
        "canonical_owner_change",
        "identity_normalization_change",
        "projection_schema_change",
        "recanonicalization",
        "database_schema_upgrade",
    ],
)
def test_every_unsafe_change_uses_an_isolated_artifact_and_preserves_prior(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
    change: str,
) -> None:
    prior, _, _ = candidate_d.publish_new_store(
        fixture=fixture,
        run_root=tmp_path,
        artifact_label="prior",
    )
    prior_calls = prior.top_sessions(limit=10).payload
    destination = tmp_path / f"unsafe-{change}.sqlite"

    candidate, stats = prior.apply_unsafe_change(destination, change=change)

    assert candidate.path != prior.path
    assert prior.top_sessions(limit=10).payload == prior_calls
    assert stats.writer_transactions == 1
    assert stats.source_files_rescanned == 1
    candidate.validate_integrity()


@pytest.mark.parametrize("boundary", shared.CRASH_BOUNDARIES)
def test_process_termination_preserves_the_prior_publication(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
    boundary: str,
) -> None:
    driver = candidate_d.CandidateDCrashDriver(
        fixture=fixture,
        run_root=tmp_path,
    )
    crash_case = shared.CrashCase.termination(boundary)
    observation = driver.run_crash_case(crash_case)

    shared.validate_crash_observation(
        crash_case,
        fixture.crash_expectation(boundary),
        observation,
    )


@pytest.mark.parametrize("fault", ("disk_full", "busy_reader", "invalid_rate_card"))
def test_fault_hook_preserves_queryability_and_recovery(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
    fault: str,
) -> None:
    driver = candidate_d.CandidateDCrashDriver(
        fixture=fixture,
        run_root=tmp_path,
    )
    crash_case = shared.CrashCase.injected_fault(fault)
    observation = driver.run_crash_case(crash_case)

    shared.validate_crash_observation(crash_case, {}, observation)


def test_adapter_returns_a_measured_result_for_every_mandatory_case(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
) -> None:
    matrix = shared.build_workload_matrix(physical_cores=12)
    mandatory = [case for case in matrix.cases if case.candidate_capability is None]

    for index, case in enumerate(mandatory):
        request = _request(
            case_id=case.case_id,
            fixture=fixture,
            run_root=tmp_path / f"{index:03d}",
        )
        result = shared.execute_candidate(candidate_d.Adapter(), request)

        assert result.outcome in {
            shared.RunOutcome.PASSED,
            shared.RunOutcome.STOPPED,
        }, case.case_id
        assert result.publication is not None, case.case_id
        assert result.publication.artifact_path.is_file(), case.case_id
        assert result.measurements.oracle_equivalent is True, case.case_id
        assert result.measurements.answer_correct is True, case.case_id
        assert result.measurements.response_bytes > 0, case.case_id
        assert result.measurements.duplicated_representation_bytes == 0, case.case_id
        assert result.measurements.tracker_polls == 0, case.case_id
        assert result.measurements.refresh_jobs == 0, case.case_id


def test_only_declared_optional_case_is_unsupported(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
) -> None:
    matrix = shared.build_workload_matrix(physical_cores=12)
    optional = [case for case in matrix.cases if case.candidate_capability is not None]
    assert [case.case_id for case in optional] == ["build.writer.partitioned_staging"]
    request = _request(
        case_id=optional[0].case_id,
        fixture=fixture,
        run_root=tmp_path,
    )
    result = shared.execute_candidate(candidate_d.Adapter(), request)
    assert result.outcome is shared.RunOutcome.UNSUPPORTED


def test_measured_adapter_writes_a_valid_shared_result_envelope(
    tmp_path: Path,
    fixture: shared.FixtureBundle,
) -> None:
    matrix = shared.build_workload_matrix(physical_cores=12)
    request = _request(
        case_id="query.q-ops-04.warm_first_page",
        fixture=fixture,
        run_root=tmp_path / "run",
    )
    identity = shared.MeasurementIdentity(
        run_id="candidate-d-envelope",
        candidate_id="D",
        case_id=request.case.case_id,
        fixture_profile=fixture.profile,
        fixture_manifest_digest=fixture.manifest_digest,
        fixture_oracle_digest=fixture.oracle_digest,
        repetition=0,
        profiled=False,
        code_commit="d" * 40,
        workload_matrix_digest=matrix.digest,
        environment=shared.EnvironmentFingerprint(
            python_version="3.14.6",
            sqlite_version=sqlite3.sqlite_version,
            operating_system="synthetic-test-os",
            filesystem="synthetic-test-fs",
            cpu_model="synthetic-test-cpu",
            physical_cores=12,
            logical_cores=12,
            memory_bytes=16 * 1024**3,
            storage_model="synthetic-test-storage",
            compiler_flags=(),
            sqlite_settings=(
                ("cache_size", "-20000"),
                ("journal_mode", "wal"),
                ("mmap_size", "0"),
                ("page_size", "4096"),
                ("synchronous", "normal"),
                ("temp_store", "memory"),
                ("wal_autocheckpoint", "1000"),
            ),
            analyze_state="complete",
            filesystem_cache_state="warm",
        ),
    )
    collector = shared.MeasurementCollector(tmp_path / "measurements.jsonl")

    result = shared.execute_measured_candidate(
        candidate_d.Adapter(),
        request,
        collector,
        identity,
    )
    record = shared.load_measurements(collector.output_path)[0]

    assert result.outcome is shared.RunOutcome.PASSED
    assert record.values.oracle_equivalent is True
    assert record.values.selector_pages_gap_free is True
    assert record.values.tracker_calls == 1
    assert record.values.response_bytes <= 16_384
    assert record.values.fact_rows > 0
    assert record.values.sequence_rows > 0
    assert json.loads(collector.output_path.read_text(encoding="utf-8"))["schema"] == (
        shared.MEASUREMENT_SCHEMA
    )


def test_agent_perf_workload_is_the_frozen_standard_fixture_command() -> None:
    workload = shared.load_agent_perf_workload(_AGENT_PERF_WORKLOAD)

    assert workload.candidate_id == "D"
    assert workload.fixture_profile == "standard"
    assert workload.fixture_revision == "agent-kernel-structural-v1"
    assert workload.workload_id == "build.scale.standard"
    assert workload.minimum_unprofiled_runs == 5
    assert workload.profile_is_attribution_only is True
    assert workload.environment == {"PYTHONPATH": "experiments/physical-architecture"}
