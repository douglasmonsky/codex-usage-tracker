from __future__ import annotations

import importlib
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")
candidate_c = importlib.import_module("candidate_c")
candidate_adapter = importlib.import_module("candidate_c.adapter")
candidate_schema = importlib.import_module("candidate_c.schema")
candidate_workload = importlib.import_module("candidate_c.workload")

_TINY = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"


def _fixture() -> shared.FixtureBundle:
    return shared.load_fixture_bundle(_TINY)


def _database(tmp_path: Path) -> tuple[shared.FixtureBundle, candidate_c.CandidateCDatabase]:
    fixture = _fixture()
    database = candidate_c.CandidateCDatabase(tmp_path)
    database.build(
        fixture,
        label="test-base",
        history_selection="all_time",
        parser_workers=1,
        index_mode="present",
    )
    return fixture, database


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _request(
    *,
    fixture: shared.FixtureBundle,
    case: shared.WorkloadCase,
    run_root: Path,
) -> shared.CandidateRequest:
    run_root.mkdir(parents=True, exist_ok=True)
    return shared.CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=run_root,
        repetition=0,
        stop=shared.EarlyStopController(case.case_id, case.early_stop_limits),
    )


def test_schema_has_one_backbone_and_no_shadow_sequence(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)
    artifact = database.current_artifact()
    connection = _readonly(artifact)

    tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    }
    indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'index'"
        )
    }
    model_occurrences, canonical_owners = connection.execute(
        """
        SELECT COUNT(*), SUM(canonical_owner)
        FROM event_backbone
        WHERE event_type = 'model_call'
        """
    ).fetchone()
    canonical_calls = connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
    foreign_key_failures = connection.execute("PRAGMA foreign_key_check").fetchall()
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    connection.close()

    assert set(candidate_schema.table_names()) <= tables
    assert set(candidate_schema.index_names()) <= indexes
    assert "sequence_index" not in tables
    assert metadata["sequence_authority"] == "event_backbone"
    assert model_occurrences == fixture.manifest["stream_aggregates"]["model_call_occurrences"]
    assert canonical_owners == fixture.manifest["stream_aggregates"]["canonical_model_calls"]
    assert canonical_calls == fixture.oracle["accounting"]["canonical_counts"]["model_calls"]
    assert foreign_key_failures == []


def test_backbone_is_occurrence_and_total_order_authority(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path / "first")
    second = candidate_c.CandidateCDatabase(tmp_path / "second")
    second.build(
        fixture,
        label="test-base",
        history_selection="all_time",
        parser_workers=4,
        index_mode="deferred",
    )

    first_rows = _all_evidence(database, limit=17)
    second_rows = _all_evidence(second, limit=19)
    first_keys = [_evidence_key(row) for row in first_rows]
    second_keys = [_evidence_key(row) for row in second_rows]

    assert first_keys == sorted(first_keys)
    assert first_keys == second_keys
    assert len(first_keys) == len(set(first_keys))
    assert len(first_keys) == database.row_counts().occurrence_rows
    assert any(not row["canonical_owner"] for row in first_rows)


def test_deep_pages_are_reached_by_gap_free_keyset_traversal(tmp_path: Path) -> None:
    _fixture_value, database = _database(tmp_path)
    first = database.evidence_page(limit=17)
    assert first.next_cursor is not None
    expected_second = database.evidence_page(after=first.next_cursor, limit=17)

    second, pages_traversed = database.evidence_page_at_position(
        page_position=2,
        limit=17,
    )
    beyond_end, terminal_traversal = database.evidence_page_at_position(
        page_position=10_000,
        limit=17,
    )

    assert second == expected_second
    assert pages_traversed == 2
    assert set(_evidence_key(row) for row in first.rows).isdisjoint(
        _evidence_key(row) for row in second.rows
    )
    assert _evidence_key(first.rows[-1]) < _evidence_key(second.rows[0])
    assert beyond_end.rows == ()
    assert beyond_end.next_cursor is None
    assert terminal_traversal < 10_000


def test_every_required_vertical_slice_question_matches_oracle(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)

    for question_id in shared.REQUIRED_SLICE_QUESTION_IDS:
        payload, equivalent, plans = database.query_question(
            fixture,
            question_id,
            exact_count=True,
        )
        expected = {
            oracle_id
            for oracle_id, question in fixture.oracle["questions"].items()
            if question["question_id"] == question_id
        }
        actual = {row["oracle_id"] for row in payload["rows"]}
        assert equivalent is True
        assert actual == expected
        assert payload["exact_count"] == len(expected)
        assert plans
        assert any("oracle_cases_question" in plan for plan in plans)


def test_typed_lifecycle_and_state_change_semantics(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)
    connection = _readonly(database.current_artifact())
    counts = {
        table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        for table in (
            "sessions",
            "turns",
            "model_calls",
            "tool_invocations",
            "tool_transitions",
            "state_changes",
        )
    }
    open_tools = connection.execute(
        "SELECT COUNT(*) FROM tool_invocations WHERE terminal_at_us IS NULL"
    ).fetchone()[0]
    causal, minimum_preceding, maximum_preceding = connection.execute(
        """
        SELECT
            SUM(causal_attribution),
            MIN(preceding_activity_count),
            MAX(preceding_activity_count)
        FROM state_changes
        """
    ).fetchone()
    late_parent_rows = connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE parent_session_id IS NOT NULL"
    ).fetchone()[0]
    connection.close()

    canonical = fixture.oracle["accounting"]["canonical_counts"]
    assert counts["sessions"] == canonical["sessions"]
    assert counts["turns"] == canonical["turns"]
    assert counts["model_calls"] == canonical["model_calls"]
    assert counts["tool_invocations"] == canonical["tool_invocations"]
    assert counts["state_changes"] == canonical["state_changes"]
    assert counts["tool_transitions"] == 49
    assert open_tools == 1
    assert causal == 0
    assert minimum_preceding >= 1
    assert maximum_preceding >= 2
    assert late_parent_rows >= 1


def test_allowance_observations_preserve_every_exact_observation(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)
    connection = _readonly(database.current_artifact())
    rows = connection.execute(
        """
        SELECT
            provider,
            limit_id,
            cycle_id,
            reset_identity,
            observation_ordinal,
            used_percent,
            remaining_percent,
            event_at_us
        FROM allowance_observations
        ORDER BY event_at_us, observation_ordinal, observation_id
        """
    ).fetchall()
    compatibility = connection.execute(
        "SELECT COUNT(*) FROM allowance_compatibility"
    ).fetchone()[0]
    connection.close()

    assert len(rows) == fixture.oracle["accounting"]["canonical_counts"]["allowance_observations"]
    assert rows == sorted(rows, key=lambda row: (row[7], row[4]))
    assert compatibility == 1
    assert all(row[5] is not None and row[6] is not None for row in rows)


def test_ordinary_tail_updates_only_dirty_keys_and_preserves_prior(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)
    prior = database.current_artifact()
    before = database.row_counts(prior)
    artifact = database.apply_ordinary(
        fixture,
        change="one_model_call",
        label="one-model-call",
    )
    after = database.row_counts(artifact.path)

    assert artifact.prior_path == prior
    assert artifact.path != prior
    assert artifact.stats.source_files_parsed == 0
    assert artifact.stats.source_bytes_parsed == 0
    assert artifact.stats.facts_inserted == 1
    assert artifact.stats.dirty_keys == 2
    assert artifact.stats.projection_rows_written == 2
    assert after.fact_rows == before.fact_rows + 1
    assert database.row_counts(prior) == before
    assert _readonly(prior).execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_large_tail_has_constant_projection_fanout(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)
    before = database.row_counts()
    artifact = database.apply_ordinary(
        fixture,
        change="2000_call_tail",
        label="two-thousand-call-tail",
    )
    after = database.row_counts()

    assert artifact.stats.facts_inserted == 2_000
    assert artifact.stats.dirty_keys == 2
    assert artifact.stats.projection_rows_written == 2
    assert artifact.stats.source_files_parsed == 0
    assert after.fact_rows == before.fact_rows + 2_000


@pytest.mark.parametrize(
    ("history", "expected"),
    (
        ("24_hours", 2),
        ("7_days", 2),
        ("30_days", 4),
        ("90_days", 10),
        ("one_year", 34),
        ("current_session", 10),
        ("all_time", 100),
    ),
)
def test_history_builds_select_exact_canonical_calls(
    tmp_path: Path,
    history: str,
    expected: int,
) -> None:
    fixture = _fixture()
    database = candidate_c.CandidateCDatabase(tmp_path)
    artifact = database.build(
        fixture,
        label=f"history:{history}",
        history_selection=history,
        parser_workers=2,
        index_mode="rebuilt",
    )
    connection = _readonly(artifact.path)
    count = connection.execute("SELECT COUNT(*) FROM model_calls").fetchone()[0]
    connection.close()

    assert count == expected
    assert artifact.stats.source_files_parsed == len(fixture.sources)


@pytest.mark.parametrize("group", ("archive", "moving_tail", "replacement", "truncation"))
def test_source_lifecycle_phase_matches_oracle_mapping(
    tmp_path: Path,
    group: str,
) -> None:
    fixture, database = _database(tmp_path)
    artifact = database.apply_source_phase(
        fixture,
        group=group,
        label=f"phase:{group}",
    )
    connection = _readonly(artifact.path)
    rows = {
        str(call_id): str(disposition)
        for call_id, disposition in connection.execute(
            """
            SELECT call_id, disposition
            FROM source_phase_occurrences
            WHERE group_name = ?
            """,
            (group,),
        )
    }
    connection.close()
    mapping = fixture.manifest["phase_occurrence_mappings"][group]
    expected = {
        call_id: disposition
        for disposition in ("inserted", "preserved", "removed")
        for call_id in mapping[disposition]
    }

    assert rows == expected
    assert artifact.prior_path is not None
    assert _readonly(artifact.prior_path).execute("PRAGMA quick_check").fetchone()[0] == "ok"


@pytest.mark.parametrize(
    "change",
    (
        "source_truncation",
        "source_replacement",
        "canonical_owner_change",
        "identity_normalization_change",
        "projection_schema_change",
        "recanonicalization",
        "database_schema_upgrade",
    ),
)
def test_unsafe_changes_use_isolated_publication(
    tmp_path: Path,
    change: str,
) -> None:
    fixture, database = _database(tmp_path)
    prior = database.current_artifact()
    artifact = database.apply_unsafe(
        fixture,
        change=change,
        label=f"unsafe:{change}",
    )

    assert artifact.path != prior
    assert artifact.prior_path == prior
    assert _readonly(prior).execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert _readonly(artifact.path).execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_schema_upgrade_stays_unpublished_until_explicit_promotion(tmp_path: Path) -> None:
    fixture, database = _database(tmp_path)
    prior = database.current_artifact()
    artifact = database.build_unpublished_upgrade(
        fixture,
        label="unpublished-upgrade",
    )
    connection = _readonly(artifact.path)
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    upgraded_version = connection.execute("PRAGMA user_version").fetchone()[0]
    connection.close()

    assert artifact.path != prior
    assert artifact.prior_path == prior
    assert database.current_artifact() == prior
    assert upgraded_version == candidate_schema.SCHEMA_VERSION + 1
    assert metadata["publication_state"] == "unpublished"
    assert _readonly(prior).execute("PRAGMA user_version").fetchone()[0] == (
        candidate_schema.SCHEMA_VERSION
    )


def test_crash_driver_matches_all_boundaries_and_faults(tmp_path: Path) -> None:
    fixture = _fixture()
    driver = candidate_c.CandidateCCrashDriver(fixture, tmp_path)

    for boundary in shared.CRASH_BOUNDARIES:
        crash_case = shared.CrashCase.termination(boundary)
        expected = fixture.crash_expectation(boundary)
        observed = shared.run_publication_crash_case(driver, crash_case, expected)
        assert observed.prior_publication_queryable is True
        assert observed.subsequent_operation_succeeds is True
    for fault in shared.CRASH_FAULTS:
        crash_case = shared.CrashCase.injected_fault(fault)
        observed = shared.run_publication_crash_case(driver, crash_case, {})
        assert observed.prior_publication_queryable is True
        assert observed.subsequent_operation_succeeds is True


def test_adapter_supports_each_mandatory_group_and_optional_staging(
    tmp_path: Path,
) -> None:
    fixture = _fixture()
    matrix = shared.build_workload_matrix(physical_cores=4)
    selected = (
        "build.scale.tiny",
        "build.schema_upgrade.unpublished",
        "ordinary.one_model_call",
        "unsafe.source_replacement",
        "query.q-ctx-01.warm_first_page",
        "crash.terminate.before_staging",
        "dbhub.named_preset.default",
        "agent_perf.standard_cpu_attribution",
    )
    for case_id in selected:
        case = matrix.by_id(case_id)
        request = _request(fixture=fixture, case=case, run_root=tmp_path / case_id)
        result = shared.execute_candidate(candidate_c.Adapter(), request)
        assert result.outcome in {shared.RunOutcome.PASSED, shared.RunOutcome.STOPPED}
        assert result.outcome is not shared.RunOutcome.UNSUPPORTED
        assert result.measurements.tracker_calls == 1
        assert result.measurements.oracle_equivalent is True
        assert result.publication is not None

    optional = matrix.by_id("build.writer.partitioned_staging")
    request = _request(fixture=fixture, case=optional, run_root=tmp_path / "optional")
    result = shared.execute_candidate(candidate_c.Adapter(), request)
    assert result.outcome is shared.RunOutcome.UNSUPPORTED
    assert result.detail_code == "candidate_c.partitioned_staging_not_implemented"


def test_adapter_uses_shared_early_stop_controller(tmp_path: Path) -> None:
    fixture = _fixture()
    base = shared.build_workload_matrix(physical_cores=4).by_id(
        "query.q-ctx-01.warm_first_page"
    )
    case = replace(
        base,
        case_id="query.q-ctx-01.forced-stop",
        early_stop_limits=(shared.MetricLimit(shared.StopMetric.RESPONSE_BYTES, 1),),
    )
    request = _request(fixture=fixture, case=case, run_root=tmp_path)
    result = shared.execute_candidate(candidate_c.Adapter(), request)

    assert result.outcome is shared.RunOutcome.STOPPED
    assert request.stop.decision is not None
    assert request.stop.decision.metric is shared.StopMetric.RESPONSE_BYTES


def test_agent_perf_workload_is_exact_standard_file_contract(tmp_path: Path) -> None:
    fixture = replace(_fixture(), profile="standard")
    matrix = shared.build_workload_matrix(physical_cores=8)
    contract_path = candidate_workload.write_agent_perf_workload(
        fixture=fixture,
        workload_matrix_digest=matrix.digest,
        output_path=tmp_path / "candidate-c-agent-perf-workload.json",
    )
    contract = shared.load_agent_perf_workload(contract_path)

    assert contract.candidate_id == "C"
    assert contract.workload_id == "build.scale.standard"
    assert contract.minimum_unprofiled_runs == 5
    assert contract.command_argv[2] == "candidate_c.workload"
    assert contract.profile_is_attribution_only is True


def test_database_stores_no_structural_record_body_column(tmp_path: Path) -> None:
    _fixture_value, database = _database(tmp_path)
    connection = _readonly(database.current_artifact())
    columns = {
        f"{table}.{row[1]}"
        for (table,) in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type = 'table' ORDER BY name"
        )
        for row in connection.execute(f"PRAGMA table_info({table})")
    }
    connection.close()

    assert not any(
        forbidden in column
        for column in columns
        for forbidden in ("raw_", "content_body", "command_body", "tool_output")
    )


def _all_evidence(
    database: candidate_c.CandidateCDatabase,
    *,
    limit: int,
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    cursor = None
    while True:
        page = database.evidence_page(after=cursor, limit=limit)
        rows.extend(page.rows)
        if page.next_cursor is None:
            break
        cursor = page.next_cursor
    return tuple(rows)


def _evidence_key(row: dict[str, object]) -> tuple[int, int, int, str, str]:
    return (
        int(row["event_at_us"]),
        int(row["event_kind_order"]),
        int(row["source_order"]),
        str(row["logical_id"]),
        str(row["occurrence_id"]),
    )
