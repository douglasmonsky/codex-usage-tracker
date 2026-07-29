from __future__ import annotations

import ast
import importlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

qualification = importlib.import_module("qualification")
shared = importlib.import_module("shared")

_TINY = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"


def _environment(*, physical_cores: int = 8) -> Any:
    return shared.EnvironmentFingerprint(
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
        filesystem_cache_state="uncontrolled",
    )


class _FakeAdapter:
    contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION

    def __init__(
        self,
        candidate_id: str,
        *,
        outcome: Any = shared.RunOutcome.PASSED,
    ) -> None:
        self.candidate_id = candidate_id
        self.outcome = outcome
        self.calls: list[tuple[str, int]] = []

    def execute(self, request: Any) -> Any:
        self.calls.append((request.case.case_id, request.repetition))
        if self.outcome is shared.RunOutcome.STOPPED:
            limit = request.case.early_stop_limits[0]
            request.stop.observe(limit.metric, limit.maximum + 1)
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=self.outcome,
            measurements=shared.MeasurementValues(
                oracle_equivalent=self.outcome is shared.RunOutcome.PASSED,
            ),
            detail_code=(
                None if self.outcome is shared.RunOutcome.PASSED else f"fake.{self.outcome.value}"
            ),
        )


def _config(
    tmp_path: Path,
    *,
    run_id: str,
    candidates: tuple[str, ...] = ("A",),
    case_ids: tuple[str, ...] = ("build.scale.tiny",),
    repetitions: int = 1,
    speed_claim: bool = False,
    profiled: bool = False,
    retain_run_artifacts: bool = False,
) -> Any:
    return qualification.QualificationConfig(
        fixture_root=_TINY,
        output_root=tmp_path,
        run_id=run_id,
        code_commit="c" * 40,
        candidates=candidates,
        case_ids=case_ids,
        repetitions=repetitions,
        speed_claim=speed_claim,
        profiled=profiled,
        retain_run_artifacts=retain_run_artifacts,
    )


def test_routine_plan_is_tiny_bounded_and_excludes_research(
    tmp_path: Path,
) -> None:
    adapters = {candidate: _FakeAdapter(candidate) for candidate in ("A", "C", "D")}
    config = qualification.QualificationConfig(
        fixture_root=_TINY,
        output_root=tmp_path,
        run_id="routine",
        code_commit="c" * 40,
    )

    artifact = qualification.run_qualification(
        config,
        environment=_environment(),
        adapter_loader=adapters.__getitem__,
    )

    assert artifact.successful
    assert len(artifact.records) == 3 * len(qualification.ROUTINE_CASE_IDS)
    assert (
        tuple(row["case_id"] for row in artifact.summary["cases"] if row["candidate_id"] == "A")
        == qualification.ROUTINE_CASE_IDS
    )
    assert not any(
        record.identity.case_id.startswith(("dbhub.", "agent_perf.")) for record in artifact.records
    )


def test_speed_claim_requires_five_unprofiled_repetitions(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        qualification.QualificationContractError,
        match="at least five",
    ):
        _config(
            tmp_path,
            run_id="too-few",
            repetitions=4,
            speed_claim=True,
        )
    with pytest.raises(
        qualification.QualificationContractError,
        match="unprofiled",
    ):
        _config(
            tmp_path,
            run_id="profiled",
            repetitions=5,
            speed_claim=True,
            profiled=True,
        )

    adapter = _FakeAdapter("A")
    artifact = qualification.run_qualification(
        _config(
            tmp_path,
            run_id="five",
            repetitions=5,
            speed_claim=True,
        ),
        environment=_environment(),
        adapter_loader=lambda _: adapter,
    )

    assert [record.identity.repetition for record in artifact.records] == list(range(5))
    assert all(record.identity.profiled is False for record in artifact.records)
    assert artifact.summary["cases"][0]["wall_time_distribution"]["sample_count"] == 5


@pytest.mark.parametrize("outcome", [shared.RunOutcome.FAILED, shared.RunOutcome.STOPPED])
def test_mandatory_failed_or_stopped_case_fails_closed(
    tmp_path: Path,
    outcome: Any,
) -> None:
    case_id = (
        "query.q-acc-01.warm_first_page"
        if outcome is shared.RunOutcome.STOPPED
        else "build.scale.tiny"
    )
    adapter = _FakeAdapter("A", outcome=outcome)
    with pytest.raises(qualification.QualificationRunFailed) as raised:
        qualification.run_qualification(
            _config(tmp_path, run_id=f"mandatory-{outcome.value}", case_ids=(case_id,)),
            environment=_environment(),
            adapter_loader=lambda _: adapter,
        )

    artifact = raised.value.artifact
    assert artifact.status == "failed"
    assert artifact.summary["failure"]["case_id"] == case_id
    assert artifact.records[0].outcome is outcome
    detail = qualification.load_execution_details(
        artifact.details_path,
        measurements_path=artifact.measurements_path,
        expected_records=1,
    )[0]
    assert detail["outcome"] == outcome.value
    assert detail["detail_code"] == f"fake.{outcome.value}"
    assert detail["partial"] is (outcome is shared.RunOutcome.STOPPED)
    assert (detail["stop_decision"] is not None) is (outcome is shared.RunOutcome.STOPPED)


def test_unsupported_is_retained_only_for_optional_capability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = shared.load_fixture_bundle(_TINY)
    monkeypatch.setattr(
        shared,
        "load_fixture_bundle",
        lambda _: replace(fixture, profile="standard"),
    )
    optional = _FakeAdapter("A", outcome=shared.RunOutcome.UNSUPPORTED)
    config = qualification.QualificationConfig(
        fixture_root=_TINY,
        output_root=tmp_path,
        run_id="optional",
        code_commit="c" * 40,
        candidates=("A",),
        case_ids=("build.writer.partitioned_staging",),
        allow_large_fixture=True,
    )
    artifact = qualification.run_qualification(
        config,
        environment=_environment(),
        adapter_loader=lambda _: optional,
    )

    assert artifact.successful
    assert artifact.records[0].outcome is shared.RunOutcome.UNSUPPORTED
    assert artifact.summary["cases"][0]["mandatory"] is False
    unsupported_detail = qualification.load_execution_details(
        artifact.details_path,
        measurements_path=artifact.measurements_path,
        expected_records=1,
    )[0]
    assert unsupported_detail["outcome"] == "unsupported"
    assert unsupported_detail["detail_code"] == "fake.unsupported"

    mandatory = _FakeAdapter("A", outcome=shared.RunOutcome.UNSUPPORTED)
    with pytest.raises(
        qualification.QualificationContractError,
        match="mandatory",
    ):
        qualification.run_qualification(
            replace(
                config,
                run_id="mandatory-unsupported",
                case_ids=("query.q-acc-01.warm_first_page",),
            ),
            environment=_environment(),
            adapter_loader=lambda _: mandatory,
        )


def test_input_order_cannot_change_execution_or_summary_order(
    tmp_path: Path,
) -> None:
    cases = (
        "query.q-acc-01.warm_first_page",
        "build.scale.tiny",
    )
    adapters = {candidate: _FakeAdapter(candidate) for candidate in ("A", "D")}
    artifact = qualification.run_qualification(
        _config(
            tmp_path,
            run_id="ordering",
            candidates=("D", "A"),
            case_ids=cases,
        ),
        environment=_environment(),
        adapter_loader=adapters.__getitem__,
    )

    identities = [
        (record.identity.candidate_id, record.identity.case_id) for record in artifact.records
    ]
    assert identities == [
        ("A", "build.scale.tiny"),
        ("A", "query.q-acc-01.warm_first_page"),
        ("D", "build.scale.tiny"),
        ("D", "query.q-acc-01.warm_first_page"),
    ]
    assert [
        (row["candidate_id"], row["case_id"]) for row in artifact.summary["cases"]
    ] == identities


def test_measurement_identity_validation_rejects_commit_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = shared.execute_measured_candidate

    def drift(
        adapter: Any,
        request: Any,
        collector: Any,
        identity: Any,
    ) -> Any:
        wrong = replace(identity, code_commit="d" * 40)
        with collector.measure(wrong) as draft:
            result = adapter.execute(request)
            draft.set_values(result.measurements)
        return result

    monkeypatch.setattr(shared, "execute_measured_candidate", drift)
    with pytest.raises(
        qualification.QualificationContractError,
        match="identities differ",
    ):
        qualification.run_qualification(
            _config(tmp_path, run_id="identity-drift"),
            environment=_environment(),
            adapter_loader=lambda _: _FakeAdapter("A"),
        )
    monkeypatch.setattr(shared, "execute_measured_candidate", original)


def test_existing_run_root_is_never_reused_as_current_output(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, run_id="stale")
    qualification.run_qualification(
        config,
        environment=_environment(),
        adapter_loader=lambda _: _FakeAdapter("A"),
    )

    with pytest.raises(
        qualification.QualificationContractError,
        match="stale output",
    ):
        qualification.run_qualification(
            config,
            environment=_environment(),
            adapter_loader=lambda _: _FakeAdapter("A"),
        )


def test_completed_run_artifacts_are_discarded_unless_explicitly_retained(
    tmp_path: Path,
) -> None:
    class ArtifactAdapter(_FakeAdapter):
        def execute(self, request: Any) -> Any:
            (request.run_root / "candidate.sqlite").write_bytes(b"synthetic")
            return super().execute(request)

    discarded = qualification.run_qualification(
        _config(tmp_path, run_id="discarded"),
        environment=_environment(),
        adapter_loader=lambda _: ArtifactAdapter("A"),
    )

    discarded_runs = discarded.invocation_root / "runs"
    assert discarded.summary["retain_run_artifacts"] is False
    assert not discarded_runs.exists() or not any(
        path.is_file() for path in discarded_runs.rglob("*")
    )

    retained = qualification.run_qualification(
        _config(tmp_path, run_id="retained", retain_run_artifacts=True),
        environment=_environment(),
        adapter_loader=lambda _: ArtifactAdapter("A"),
    )

    assert retained.summary["retain_run_artifacts"] is True
    assert any((retained.invocation_root / "runs").rglob("candidate.sqlite"))


def test_fixture_profile_and_research_execution_are_explicit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = shared.load_fixture_bundle(_TINY)
    standard = replace(fixture, profile="standard")
    monkeypatch.setattr(shared, "load_fixture_bundle", lambda _: standard)
    config = qualification.QualificationConfig(
        fixture_root=_TINY,
        output_root=tmp_path,
        run_id="standard",
        code_commit="c" * 40,
        candidates=("A",),
        case_ids=("build.scale.standard",),
    )
    with pytest.raises(
        qualification.QualificationContractError,
        match="allow-large-fixture",
    ):
        qualification.run_qualification(
            config,
            environment=_environment(),
            adapter_loader=lambda _: _FakeAdapter("A"),
        )

    research = qualification.QualificationConfig(
        fixture_root=_TINY,
        output_root=tmp_path,
        run_id="research",
        code_commit="c" * 40,
        candidates=("A",),
        case_ids=("agent_perf.standard_cpu_attribution",),
        allow_large_fixture=True,
    )
    with pytest.raises(
        qualification.QualificationContractError,
        match="requires include-research",
    ):
        qualification.run_qualification(
            research,
            environment=_environment(),
            adapter_loader=lambda _: _FakeAdapter("A"),
        )


def test_artifacts_are_canonical_bounded_and_have_current_digests(
    tmp_path: Path,
) -> None:
    artifact = qualification.run_qualification(
        _config(tmp_path, run_id="canonical"),
        environment=_environment(),
        adapter_loader=lambda _: _FakeAdapter("A"),
    )

    invocation = json.loads(artifact.invocation_path.read_text(encoding="utf-8"))
    summary = json.loads(artifact.summary_path.read_text(encoding="utf-8"))
    assert artifact.invocation_path.read_bytes() == shared.canonical_json_bytes(invocation)
    assert artifact.summary_path.read_bytes() == shared.canonical_json_bytes(summary)
    unsigned_invocation = dict(invocation)
    invocation_digest = unsigned_invocation.pop("invocation_digest")
    assert shared.canonical_sha256(unsigned_invocation) == invocation_digest
    unsigned_summary = dict(summary)
    summary_digest = unsigned_summary.pop("summary_digest")
    assert shared.canonical_sha256(unsigned_summary) == summary_digest
    assert len(summary["cases"]) <= qualification.MAX_SUMMARY_CASES
    assert (
        summary["measurement_sha256"]
        == __import__("hashlib").sha256(artifact.measurements_path.read_bytes()).hexdigest()
    )
    assert (
        summary["details_sha256"]
        == __import__("hashlib").sha256(artifact.details_path.read_bytes()).hexdigest()
    )
    assert summary["detail_records"] == summary["records"] == 1


def test_detail_stream_preserves_bounded_oracle_and_process_evidence_before_cleanup(
    tmp_path: Path,
) -> None:
    class DetailedAdapter(_FakeAdapter):
        def execute(self, request: Any) -> Any:
            (request.run_root / "ephemeral.sqlite").write_bytes(b"synthetic")
            result = super().execute(request)
            return replace(
                result,
                oracle_results={
                    "query_rows": [
                        {
                            "session_id": "session:v1:synthetic",
                            "total_tokens": 12_345,
                        }
                    ],
                    "recovery": {
                        "worker_pid": 42_424,
                        "worker_exit_code": 86,
                        "subsequent_publication_succeeds": True,
                    },
                },
            )

    artifact = qualification.run_qualification(
        _config(tmp_path, run_id="detail-evidence"),
        environment=_environment(),
        adapter_loader=lambda _: DetailedAdapter("A"),
    )

    details = qualification.load_execution_details(
        artifact.details_path,
        measurements_path=artifact.measurements_path,
        expected_sha256=artifact.summary["details_sha256"],
        expected_records=artifact.summary["detail_records"],
    )
    assert len(details) == 1
    detail = details[0]
    assert detail["execution_index"] == 0
    assert detail["measurement_identity"] == {
        "candidate_id": "A",
        "case_id": "build.scale.tiny",
        "code_commit": "c" * 40,
        "environment_digest": artifact.summary["environment_digest"],
        "fixture_manifest_digest": artifact.summary["fixture_manifest_digest"],
        "fixture_oracle_digest": artifact.summary["fixture_oracle_digest"],
        "fixture_profile": "tiny",
        "profiled": False,
        "qualification_model": None,
        "repetition": 0,
        "run_id": "detail-evidence",
        "workload_matrix_digest": artifact.summary["workload_matrix_digest"],
    }
    assert detail["oracle_results"]["query_rows"][0]["total_tokens"] == 12_345
    assert detail["oracle_results"]["recovery"] == {
        "subsequent_publication_succeeds": True,
        "worker_exit_code": 86,
        "worker_pid": 42_424,
    }
    assert (
        detail["measurement_record_digest"]
        == __import__("hashlib").sha256(artifact.measurements_path.read_bytes()).hexdigest()
    )
    runs = artifact.invocation_root / "runs"
    assert not runs.exists() or not any(path.is_file() for path in runs.rglob("*"))


def test_detail_stream_rejects_canonical_tampering(
    tmp_path: Path,
) -> None:
    artifact = qualification.run_qualification(
        _config(tmp_path, run_id="detail-tamper"),
        environment=_environment(),
        adapter_loader=lambda _: _FakeAdapter("A"),
    )
    detail = json.loads(artifact.details_path.read_text(encoding="utf-8"))
    detail["outcome"] = "failed"
    artifact.details_path.write_bytes(shared.canonical_json_bytes(detail))

    with pytest.raises(
        qualification.QualificationContractError,
        match="wrong detail digest",
    ):
        qualification.load_execution_details(artifact.details_path)


def test_detail_stream_rejects_oversize_oracle_and_cleans_run_root(
    tmp_path: Path,
) -> None:
    class OversizeAdapter(_FakeAdapter):
        def execute(self, request: Any) -> Any:
            (request.run_root / "ephemeral.sqlite").write_bytes(b"synthetic")
            result = super().execute(request)
            return replace(
                result,
                oracle_results={"value": "x" * (qualification.MAX_DETAIL_STRING_BYTES + 1)},
            )

    config = _config(tmp_path, run_id="detail-oversize")
    with pytest.raises(
        qualification.QualificationContractError,
        match="string exceeds bounded capacity",
    ):
        qualification.run_qualification(
            config,
            environment=_environment(),
            adapter_loader=lambda _: OversizeAdapter("A"),
        )

    runs = tmp_path / config.run_id / "runs"
    assert not runs.exists() or not any(path.is_file() for path in runs.rglob("*"))


@pytest.mark.parametrize(
    ("oracle_results", "message"),
    [
        ({"api_key": "sk-synthetic-placeholder"}, "safe structural evidence"),
        ({"artifact": "/private/tmp/candidate.sqlite"}, "machine-specific path"),
    ],
)
def test_detail_stream_rejects_secret_like_or_machine_specific_values(
    tmp_path: Path,
    oracle_results: dict[str, str],
    message: str,
) -> None:
    class UnsafeAdapter(_FakeAdapter):
        def execute(self, request: Any) -> Any:
            return replace(super().execute(request), oracle_results=oracle_results)

    run_id = f"unsafe-{len(list(tmp_path.iterdir()))}"
    with pytest.raises(qualification.QualificationContractError, match=message):
        qualification.run_qualification(
            _config(tmp_path, run_id=run_id),
            environment=_environment(),
            adapter_loader=lambda _: UnsafeAdapter("A"),
        )


def test_detail_execution_count_is_bounded_before_output_is_created(
    tmp_path: Path,
) -> None:
    config = _config(
        tmp_path,
        run_id="too-many-details",
        repetitions=qualification.MAX_DETAIL_RECORDS + 1,
    )

    with pytest.raises(
        qualification.QualificationContractError,
        match="bounded detail capacity",
    ):
        qualification.run_qualification(
            config,
            environment=_environment(),
            adapter_loader=lambda _: _FakeAdapter("A"),
        )

    assert not (tmp_path / config.run_id).exists()


def test_runner_has_no_production_imports() -> None:
    for path in (
        _EXPERIMENT_ROOT / "qualification.py",
        _EXPERIMENT_ROOT / "run_bakeoff.py",
    ):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert not any(name.startswith("codex_usage_tracker") for name in imports)
        assert "src" not in imports
