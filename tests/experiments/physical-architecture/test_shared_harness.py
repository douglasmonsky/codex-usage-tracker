from __future__ import annotations

import importlib
import json
import os
import sqlite3
import sys
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import tomllib

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

shared = importlib.import_module("shared")

AgentPerfContractError = shared.AgentPerfContractError
CandidateRequest = shared.CandidateRequest
CandidateResult = shared.CandidateResult
CandidateScoreInput = shared.CandidateScoreInput
CrashCase = shared.CrashCase
CrashObservation = shared.CrashObservation
DbhubContractError = shared.DbhubContractError
DbhubCustomTool = shared.DbhubCustomTool
EarlyStopController = shared.EarlyStopController
EnvironmentFingerprint = shared.EnvironmentFingerprint
FixtureContractError = shared.FixtureContractError
MeasurementCollector = shared.MeasurementCollector
MeasurementIdentity = shared.MeasurementIdentity
MeasurementValues = shared.MeasurementValues
MetricLimit = shared.MetricLimit
PublicationState = shared.PublicationState
RunOutcome = shared.RunOutcome
ScoreDimension = shared.ScoreDimension
StopMetric = shared.StopMetric
WorkloadGroup = shared.WorkloadGroup
build_dbhub_run = shared.build_dbhub_run
build_workload_matrix = shared.build_workload_matrix
distribution_summary = shared.distribution_summary
load_agent_perf_workload = shared.load_agent_perf_workload
load_fixture_bundle = shared.load_fixture_bundle
rank_candidates = shared.rank_candidates
validate_crash_observation = shared.validate_crash_observation

_TINY = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"


def _environment(*, physical_cores: int = 8) -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        python_version="3.14.6",
        sqlite_version="3.50.4",
        operating_system="synthetic-test-os",
        filesystem="synthetic-test-fs",
        cpu_model="synthetic-test-cpu",
        physical_cores=physical_cores,
        logical_cores=max(physical_cores, 12),
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
    )


def test_fixture_ingestion_verifies_ck03_bytes_and_contract() -> None:
    fixture = load_fixture_bundle(_TINY)

    assert fixture.profile == "tiny"
    assert fixture.seed == 20260728
    assert fixture.fixture_revision == "agent-kernel-structural-v1"
    assert fixture.manifest_digest == (
        "a599cf149783af04d861699b0ff587a169f20dec4d372e4ffbe3f21c51995817"
    )
    assert fixture.oracle_digest == (
        "9f78b8f87c17ef5e98810be6a4a01f4a13bfc055ac8eb74c9f147a7087d8e41b"
    )
    assert len(fixture.sources) == 11
    assert len(fixture.phases) == 8
    assert {phase.group for phase in fixture.phases} == {
        "archive",
        "moving_tail",
        "replacement",
        "truncation",
    }
    assert fixture.source_bytes == 244_657
    assert set(fixture.vertical_slices) == {
        "context_deterioration",
        "workflow_sequence_first_mutation",
        "allowance_interval_accounting",
        "parent_subagent_aggregation",
        "evidence_source_lifecycle",
    }
    assert {
        "Q-CTX-01",
        "Q-WF-02",
        "Q-ALW-03",
        "Q-ACC-05",
        "Q-OPS-04",
    } <= fixture.question_ids
    with pytest.raises(TypeError):
        fixture.manifest["sources"][0]["path"] = "mutated.jsonl"


def test_fixture_ingestion_rejects_tampering_and_escaping_paths(
    tmp_path: Path,
) -> None:
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    manifest = json.loads((_TINY / "manifest.json").read_text(encoding="utf-8"))
    oracle = (_TINY / "oracle-bundle.json").read_bytes()
    (fixture_root / "oracle-bundle.json").write_bytes(oracle)

    manifest["sources"][0]["path"] = "../outside.jsonl"
    (fixture_root / "manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FixtureContractError, match="manifest digest"):
        load_fixture_bundle(fixture_root)

    manifest_without_digest = dict(manifest)
    manifest_without_digest.pop("manifest_digest")
    manifest["manifest_digest"] = shared.canonical_sha256(manifest_without_digest)
    (fixture_root / "manifest.json").write_text(
        json.dumps(manifest, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FixtureContractError, match="relative source path"):
        load_fixture_bundle(fixture_root)


def test_candidate_adapter_protocol_is_one_versioned_execution_seam(
    tmp_path: Path,
) -> None:
    fixture = load_fixture_bundle(_TINY)
    workload = build_workload_matrix(physical_cores=12)
    case = workload.by_id("ordinary.no_source_change")

    class FakeAdapter:
        candidate_id = "A"
        contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION

        def execute(self, request: CandidateRequest) -> CandidateResult:
            assert request.case == case
            return CandidateResult(
                candidate_id=self.candidate_id,
                case_id=request.case.case_id,
                outcome=RunOutcome.PASSED,
                measurements=MeasurementValues(oracle_equivalent=True),
                publication=PublicationState(
                    publication_id="publication:v1:synthetic",
                    artifact_path=request.run_root / "publication.sqlite",
                    prior_publication_queryable=True,
                ),
            )

    request = CandidateRequest(
        case=case,
        fixture=fixture,
        run_root=tmp_path,
        repetition=0,
        stop=EarlyStopController(case.case_id, case.early_stop_limits),
    )
    identity = MeasurementIdentity(
        run_id="adapter-run",
        candidate_id="A",
        case_id=case.case_id,
        fixture_profile=fixture.profile,
        fixture_manifest_digest=fixture.manifest_digest,
        fixture_oracle_digest=fixture.oracle_digest,
        repetition=0,
        profiled=False,
        code_commit="c" * 40,
        workload_matrix_digest=workload.digest,
        environment=_environment(physical_cores=12),
    )
    collector = MeasurementCollector(
        tmp_path / "adapter-measurement.jsonl",
        wall_clock_ns=iter((1, 2)).__next__,
        process_clock_ns=iter((1, 2)).__next__,
    )
    result = shared.execute_measured_candidate(
        FakeAdapter(),
        request,
        collector,
        identity,
    )

    assert isinstance(FakeAdapter(), shared.CandidateAdapter)
    assert result.outcome is RunOutcome.PASSED
    assert result.case_id == case.case_id
    assert shared.load_measurements(collector.output_path)[0].outcome is RunOutcome.PASSED


def test_workload_matrix_is_complete_unique_and_deterministic() -> None:
    first = build_workload_matrix(physical_cores=12)
    second = build_workload_matrix(physical_cores=12)

    assert first.digest == second.digest
    assert len(first.cases) == len({case.case_id for case in first.cases})
    assert {case.group for case in first.cases} == set(WorkloadGroup)
    assert first.worker_counts == (1, 2, 4, 8)
    assert build_workload_matrix(physical_cores=2).worker_counts == (1, 2, 4)

    assert set(first.ids(WorkloadGroup.BUILD)) >= {
        "build.empty.current_session",
        "build.empty.24_hours",
        "build.empty.7_days",
        "build.empty.30_days",
        "build.empty.90_days",
        "build.empty.one_year",
        "build.empty.all_time",
        "build.expand.30_days_to_90_days",
        "build.expand.90_days_to_one_year",
        "build.expand.one_year_to_all_time",
        "build.scale.tiny",
        "build.scale.small",
        "build.scale.standard",
        "build.scale.production",
        "build.scale.growth",
        "build.writer.single",
        "build.writer.partitioned_staging",
        "build.index.present",
        "build.index.deferred",
        "build.index.rebuilt",
        "build.schema_upgrade.unpublished",
    }
    assert set(first.ids(WorkloadGroup.ORDINARY_CHANGE)) == {
        "ordinary.no_source_change",
        "ordinary.one_model_call",
        "ordinary.one_tool_start",
        "ordinary.tool_terminal_transition",
        "ordinary.tool_plus_state_change",
        "ordinary.32_call_tail",
        "ordinary.2000_call_tail",
        "ordinary.late_event",
        "ordinary.rate_card_change",
    }
    assert set(first.ids(WorkloadGroup.UNSAFE_CHANGE)) == {
        "unsafe.source_truncation",
        "unsafe.source_replacement",
        "unsafe.canonical_owner_change",
        "unsafe.identity_normalization_change",
        "unsafe.projection_schema_change",
        "unsafe.recanonicalization",
        "unsafe.database_schema_upgrade",
    }
    assert set(first.ids(WorkloadGroup.CRASH)) == {
        *(f"crash.terminate.{boundary}" for boundary in shared.CRASH_BOUNDARIES),
        *(f"crash.fault.{fault}" for fault in shared.CRASH_FAULTS),
    }
    assert all(
        case.minimum_repetitions == 5
        for case in first.cases
        if case.group in {WorkloadGroup.BUILD, WorkloadGroup.ORDINARY_CHANGE, WorkloadGroup.QUERY}
    )
    assert all(
        case.minimum_repetitions == 1
        for case in first.cases
        if case.group in {WorkloadGroup.UNSAFE_CHANGE, WorkloadGroup.CRASH}
    )
    assert set(first.ids(WorkloadGroup.DBHUB)) == {
        "dbhub.generic.default",
        "dbhub.generic.less_capable",
        "dbhub.named_preset.default",
        "dbhub.named_preset.less_capable",
    }
    query_question_ids = {
        case.parameter("question_id")
        for case in first.cases
        if case.group is WorkloadGroup.QUERY and case.parameter("question_id")
    }
    assert set(shared.P1_QUESTION_IDS) | set(shared.REQUIRED_SLICE_QUESTION_IDS) <= (
        query_question_ids
    )


def test_query_workload_contract_matches_frozen_ck02_catalog() -> None:
    catalog = json.loads(
        (_REPO_ROOT / "config" / "agent-kernel" / "question-catalog-v1.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {question["question_id"]: question for question in catalog["questions"]}

    for question_id, (plan_id, performance_class) in shared.QUESTION_WORKLOAD_CONTRACTS.items():
        question = by_id[question_id]
        assert question["plan_id"] == plan_id
        assert performance_class in question["performance_classes"]


def test_early_stop_is_monotonic_and_records_partial_failure() -> None:
    controller = EarlyStopController(
        "build.scale.production",
        (
            MetricLimit(StopMetric.ELAPSED_MS, 120_000),
            MetricLimit(StopMetric.WAL_BYTES, 1_000),
        ),
    )

    assert controller.observe(StopMetric.ELAPSED_MS, 10_000) is None
    decision = controller.observe(StopMetric.WAL_BYTES, 1_001)

    assert decision is not None
    assert decision.outcome is RunOutcome.STOPPED
    assert decision.partial is True
    assert decision.metric is StopMetric.WAL_BYTES
    assert controller.observe(StopMetric.ELAPSED_MS, 20_000) == decision
    with pytest.raises(ValueError, match="monotonic"):
        EarlyStopController(
            "case",
            (MetricLimit(StopMetric.WAL_BYTES, 10),),
        ).observe_many(
            (
                (StopMetric.WAL_BYTES, 5),
                (StopMetric.WAL_BYTES, 4),
            )
        )


def test_measurement_collector_emits_canonical_schema_and_jsonl(
    tmp_path: Path,
) -> None:
    output = tmp_path / "measurements.jsonl"
    identity = MeasurementIdentity(
        run_id="run-001",
        candidate_id="C",
        case_id="query.q-acc-01",
        fixture_profile="tiny",
        fixture_manifest_digest="a" * 64,
        fixture_oracle_digest="b" * 64,
        repetition=0,
        profiled=False,
        code_commit="c" * 40,
        workload_matrix_digest="d" * 64,
        environment=_environment(),
    )
    collector = MeasurementCollector(
        output,
        wall_clock_ns=iter((100, 350)).__next__,
        process_clock_ns=iter((25, 125)).__next__,
    )

    with collector.measure(identity) as sample:
        sample.set_values(
            MeasurementValues(
                peak_rss_bytes=4096,
                database_bytes=2048,
                sql_latencies_ns=(11, 13, 17),
                facts_inserted=3,
                tracker_calls=1,
                response_bytes=512,
                oracle_equivalent=True,
            )
        )

    records = shared.load_measurements(output)
    assert len(records) == 1
    assert records[0].wall_time_ns == 250
    assert records[0].process_cpu_ns == 100
    assert records[0].values.sql_latencies_ns == (11, 13, 17)
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == (shared.MEASUREMENT_SCHEMA)


def test_measurement_collector_persists_early_stop_as_partial_failure(
    tmp_path: Path,
) -> None:
    output = tmp_path / "stopped.jsonl"
    identity = MeasurementIdentity(
        run_id="run-stop",
        candidate_id="D",
        case_id="build.scale.production",
        fixture_profile="production",
        fixture_manifest_digest="a" * 64,
        fixture_oracle_digest="b" * 64,
        repetition=0,
        profiled=False,
        code_commit="c" * 40,
        workload_matrix_digest="d" * 64,
        environment=_environment(),
    )
    controller = EarlyStopController(
        identity.case_id,
        (MetricLimit(StopMetric.ELAPSED_MS, 120_000),),
    )
    decision = controller.observe(StopMetric.ELAPSED_MS, 120_001)
    assert decision is not None
    collector = MeasurementCollector(
        output,
        wall_clock_ns=iter((1, 2)).__next__,
        process_clock_ns=iter((1, 2)).__next__,
    )

    with collector.measure(identity) as sample:
        sample.set_values(MeasurementValues(oracle_equivalent=False))
        sample.mark_stopped(decision)

    record = shared.load_measurements(output)[0]
    assert record.outcome is RunOutcome.STOPPED
    assert record.stop_decision == decision
    assert json.loads(output.read_text(encoding="utf-8"))["partial"] is True


def test_distribution_and_weighted_scoring_are_order_independent() -> None:
    summary = distribution_summary((5, 1, 4, 2, 3))
    assert summary.median == Decimal("3")
    assert summary.p95 == Decimal("5")
    assert summary.maximum == Decimal("5")
    assert summary.sample_count == 5

    def score_input(candidate: str, offset: int) -> CandidateScoreInput:
        return CandidateScoreInput(
            candidate_id=candidate,
            fixture_manifest_digest="a" * 64,
            fixture_oracle_digest="b" * 64,
            code_commit="c" * 40,
            scale="standard",
            costs=tuple(
                shared.DimensionCost(
                    dimension=dimension,
                    value=Decimal(index + offset),
                    source_case_ids=(f"case-{index}",),
                )
                for index, dimension in enumerate(ScoreDimension, start=1)
            ),
        )

    inputs = (score_input("A", 0), score_input("C", 1), score_input("D", 2))
    forward = rank_candidates(inputs)
    reverse = rank_candidates(tuple(reversed(inputs)))

    assert [item.candidate_id for item in forward] == ["A", "C", "D"]
    assert forward == reverse
    assert sum(shared.SCORE_WEIGHTS.values()) == 100
    assert all(item.input_digest for item in forward)


def test_crash_publication_observation_matches_ck03_oracle() -> None:
    fixture = load_fixture_bundle(_TINY)
    crash_case = CrashCase.termination("during_promotion")
    expected = fixture.crash_expectation("during_promotion")
    observation = CrashObservation(
        boundary="during_promotion",
        prior_publication_queryable=True,
        rollback_available=True,
        candidate_publication_committed=False,
        sidecar_terminal_state="failed",
        abandoned_artifact_disposition="reconcile_pointer_or_rollback",
        subsequent_operation_succeeds=True,
    )

    class FakeDriver:
        candidate_id = "C"

        def run_crash_case(self, requested: CrashCase) -> CrashObservation:
            assert requested == crash_case
            return observation

    assert shared.run_publication_crash_case(FakeDriver(), crash_case, expected) == observation
    with pytest.raises(shared.CrashContractError, match="prior publication"):
        validate_crash_observation(
            crash_case,
            expected,
            replace(observation, prior_publication_queryable=False),
        )


def test_injected_fault_requires_prior_publication_and_recovery() -> None:
    crash_case = CrashCase.injected_fault("disk_full")
    observation = CrashObservation(
        boundary=None,
        fault="disk_full",
        prior_publication_queryable=True,
        rollback_available=True,
        candidate_publication_committed=False,
        sidecar_terminal_state="failed",
        abandoned_artifact_disposition="abandon_candidate",
        subsequent_operation_succeeds=True,
    )

    validate_crash_observation(crash_case, {}, observation)
    with pytest.raises(shared.CrashContractError, match="subsequent operation"):
        validate_crash_observation(
            crash_case,
            {},
            replace(observation, subsequent_operation_succeeds=False),
        )


def test_dbhub_runner_is_pinned_disposable_and_read_only(
    tmp_path: Path,
) -> None:
    source = tmp_path / "candidate.sqlite"
    connection = sqlite3.connect(source)
    connection.execute("CREATE TABLE facts (logical_id TEXT PRIMARY KEY, value INTEGER)")
    connection.execute("INSERT INTO facts VALUES ('synthetic', 1)")
    connection.commit()
    connection.close()

    custom_tool = DbhubCustomTool(
        name="ck04_fact_by_id",
        description="Fetch one synthetic fact by logical ID.",
        statement="SELECT logical_id, value FROM facts WHERE logical_id = ?",
        parameters=(
            shared.DbhubParameter(
                name="logical_id",
                parameter_type="string",
                description="Synthetic logical ID.",
            ),
        ),
    )
    run = build_dbhub_run(
        source_snapshot=source,
        run_root=tmp_path / "dbhub-run",
        custom_tools=(custom_tool,),
        max_rows=50,
    )

    config = tomllib.loads(run.config_path.read_text(encoding="utf-8"))
    assert run.package == "@bytebase/dbhub"
    assert run.version == "0.24.0"
    assert run.argv[:4] == (
        "npx",
        "--yes",
        "@bytebase/dbhub@0.24.0",
        "--transport",
    )
    assert run.argv[4] == "stdio"
    assert config["sources"][0]["database"] == str(run.snapshot_path)
    assert {tool["name"] for tool in config["tools"]} == {
        "search_objects",
        "execute_sql",
        "ck04_fact_by_id",
    }
    assert all(tool.get("readonly", True) for tool in config["tools"])
    assert all(tool.get("max_rows", 50) <= 50 for tool in config["tools"])
    assert not os.stat(run.snapshot_path).st_mode & 0o222
    run.verify_unchanged()
    pinned = json.loads(
        (_EXPERIMENT_ROOT / "shared" / "dbhub-v0.24.0.contract.json").read_text(encoding="utf-8")
    )
    assert pinned["package"] == run.package
    assert pinned["version"] == run.version
    assert pinned["npm_integrity"] == run.package_integrity
    assert pinned["transport"] == "stdio"
    assert pinned["engine_read_only"] is True
    assert pinned["max_rows"] == shared.DBHUB_MAX_ROW_CAP

    with pytest.raises(DbhubContractError, match="read-only SELECT"):
        build_dbhub_run(
            source_snapshot=source,
            run_root=tmp_path / "rejected",
            custom_tools=(
                replace(custom_tool, statement="DELETE FROM facts WHERE logical_id = ?"),
            ),
        )


def test_agent_perf_workload_is_file_based_synthetic_and_same_workload(
    tmp_path: Path,
) -> None:
    contract_path = tmp_path / "agent-perf-workload.json"
    contract_path.write_text(
        json.dumps(
            {
                "schema": shared.AGENT_PERF_WORKLOAD_SCHEMA,
                "version": 1,
                "candidate_id": "D",
                "fixture_profile": "standard",
                "fixture_revision": "agent-kernel-structural-v1",
                "fixture_manifest_digest": "a" * 64,
                "fixture_oracle_digest": "b" * 64,
                "workload_matrix_digest": "d" * 64,
                "synthetic_only": True,
                "workload_id": "build.scale.standard",
                "command_argv": [
                    "{python}",
                    "-m",
                    "candidate_d.workload",
                    "--fixture",
                    "{fixture_root}",
                    "--output",
                    "{output_root}",
                ],
                "environment": {"PYTHONHASHSEED": "0"},
                "minimum_unprofiled_runs": 5,
                "profile_is_attribution_only": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    contract = load_agent_perf_workload(contract_path)
    command = contract.command(
        python=Path(sys.executable),
        fixture_root=tmp_path / "fixture",
        output_root=tmp_path / "output",
    )
    assert command[0] == sys.executable
    assert contract.fixture_profile == "standard"
    assert contract.minimum_unprofiled_runs == 5
    assert contract.profile_is_attribution_only is True

    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["command_argv"] = ["sh", "-c", "cat ~/.codex/private"]
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(AgentPerfContractError, match="shell"):
        load_agent_perf_workload(contract_path)


def test_all_shared_test_data_is_synthetic_and_paths_are_allowlisted() -> None:
    tracked = [
        path
        for path in _REPO_ROOT.rglob("*")
        if path.is_file()
        and (
            path.is_relative_to(_EXPERIMENT_ROOT / "shared")
            or path.is_relative_to(_REPO_ROOT / "tests" / "experiments" / "physical-architecture")
        )
    ]
    forbidden = (
        "pro" + "mpt",
        "response_" + "body",
        "reasoning_" + "content",
        "/" + "Users/",
    )
    for path in tracked:
        if path.suffix in {".py", ".md", ".json", ".toml"}:
            text = path.read_text(encoding="utf-8")
            assert not any(value in text for value in forbidden)
