from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

qualification_suite = importlib.import_module("run_ck04_qualification")
shared = importlib.import_module("shared")

_TINY = _REPO_ROOT / "tests" / "agent_kernel" / "fixtures" / "tiny-v1"
_COMMIT = "c" * 40


def _helper(tmp_path: Path) -> Path:
    helper = tmp_path / "synthetic_bakeoff.py"
    helper.write_text(
        """
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ["CK04_REPO_ROOT"])
EXPERIMENT_ROOT = ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(EXPERIMENT_ROOT))
import qualification
import shared

parser = argparse.ArgumentParser()
parser.add_argument("--fixture", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--run-id", required=True)
parser.add_argument("--candidate", required=True)
parser.add_argument("--case", required=True)
parser.add_argument("--repetitions", type=int, required=True)
parser.add_argument("--allow-large-fixture", action="store_true")
parser.add_argument("--include-research", action="store_true")
args = parser.parse_args()
mode = os.environ.get("CK04_TEST_MODE", "pass")
launch_log = os.environ.get("CK04_LAUNCH_LOG")
if launch_log:
    with open(launch_log, "a", encoding="utf-8") as output:
        output.write(args.candidate + "\\n")
if mode == "hang":
    pid_path = os.environ["CK04_PID_PATH"]
    Path(pid_path).write_text(str(os.getpid()), encoding="utf-8")
    while True:
        time.sleep(1)

class Adapter:
    candidate_id = args.candidate
    contract_version = shared.CANDIDATE_ADAPTER_CONTRACT_VERSION
    def execute(self, request):
        outcome = shared.RunOutcome.FAILED if mode == "fail" else shared.RunOutcome.PASSED
        return shared.CandidateResult(
            candidate_id=self.candidate_id,
            case_id=request.case.case_id,
            outcome=outcome,
            measurements=shared.MeasurementValues(
                oracle_equivalent=outcome is shared.RunOutcome.PASSED,
            ),
            detail_code=None if outcome is shared.RunOutcome.PASSED else "synthetic.failure",
        )

config = qualification.QualificationConfig(
    fixture_root=args.fixture,
    output_root=args.output,
    run_id=args.run_id,
    code_commit=os.environ["CK04_CODE_COMMIT"],
    candidates=(args.candidate,),
    case_ids=(args.case,),
    repetitions=args.repetitions,
    allow_large_fixture=args.allow_large_fixture,
    include_research=args.include_research,
)
try:
    artifact = qualification.run_qualification(
        config,
        adapter_loader=lambda _: Adapter(),
    )
except qualification.QualificationRunFailed as error:
    artifact = error.artifact
    print(artifact.summary_path)
    raise SystemExit(1)
if mode == "invalid_summary":
    artifact.summary_path.write_text("{}\\n", encoding="utf-8")
print(artifact.summary_path)
""".lstrip(),
        encoding="utf-8",
    )
    return helper


def _config(
    tmp_path: Path,
    *,
    helper: Path,
    candidates: tuple[str, ...] = ("A",),
    case_ids: tuple[str, ...] = ("build.scale.tiny",),
    watchdog_overrides: tuple[str, ...] = (),
    resume_results: tuple[Path, ...] = (),
) -> Any:
    return qualification_suite.SuiteConfig(
        output_root=tmp_path / "suite",
        code_commit=_COMMIT,
        fixture_specs=(qualification_suite.FixtureSpec("tiny", _TINY),),
        candidates=candidates,
        case_ids=case_ids,
        suite_repetitions=1,
        runner_path=helper,
        watchdog_overrides=watchdog_overrides,
        startup_grace_seconds=0.05,
        termination_grace_seconds=0.2,
        resume_results=resume_results,
    )


@pytest.fixture(autouse=True)
def _helper_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CK04_REPO_ROOT", str(_REPO_ROOT))
    monkeypatch.setenv("CK04_CODE_COMMIT", _COMMIT)


def test_valid_one_unit_completion_is_canonical(tmp_path: Path) -> None:
    artifact = qualification_suite.run_suite(_config(tmp_path, helper=_helper(tmp_path)))

    assert artifact.status == "passed"
    result = json.loads(artifact.unit_results[0].read_text(encoding="utf-8"))
    assert result["status"] == "passed"
    assert result["eligibility_pass"] is True
    assert result["censored"] is False
    assert set(result["child_artifacts"]) == {
        "details.jsonl",
        "invocation.json",
        "measurements.jsonl",
        "summary.json",
    }
    assert artifact.summary_path.read_bytes().endswith(b"\n")


def test_timeout_terminates_reaps_and_records_partial_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = _helper(tmp_path)
    pid_path = tmp_path / "pid"
    monkeypatch.setenv("CK04_TEST_MODE", "hang")
    monkeypatch.setenv("CK04_PID_PATH", str(pid_path))
    launched_pids: list[int] = []
    real_popen = qualification_suite.subprocess.Popen

    def recording_popen(*args: Any, **kwargs: Any) -> Any:
        process = real_popen(*args, **kwargs)
        command = args[0] if args else kwargs["args"]
        if str(helper) in command:
            launched_pids.append(process.pid)
        return process

    monkeypatch.setattr(qualification_suite.subprocess, "Popen", recording_popen)
    config = _config(
        tmp_path,
        helper=helper,
        watchdog_overrides=("profile:tiny=0.1",),
    )

    with pytest.raises(qualification_suite.SuiteRunFailed) as raised:
        qualification_suite.run_suite(config)

    artifact = raised.value.artifact
    timeout = json.loads(
        (artifact.output_root / "units" / "000000" / "timeout.json").read_text(encoding="utf-8")
    )
    assert timeout["censored"] is True
    assert timeout["eligibility_pass"] is False
    assert timeout["termination_requested"] is True
    assert timeout["reaped"] is True
    assert timeout["stdout"]["byte_count"] >= 0
    assert len(timeout["stderr"]["sha256"]) == 64
    assert len(launched_pids) == 1
    pid = launched_pids[0]
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    summary = json.loads(artifact.summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == "failed"
    assert summary["completed_units"] == 0


def test_fail_fast_never_launches_second_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launch_log = tmp_path / "launches"
    monkeypatch.setenv("CK04_TEST_MODE", "fail")
    monkeypatch.setenv("CK04_LAUNCH_LOG", str(launch_log))

    with pytest.raises(qualification_suite.SuiteRunFailed):
        qualification_suite.run_suite(
            _config(tmp_path, helper=_helper(tmp_path), candidates=("A", "C"))
        )

    assert launch_log.read_text(encoding="utf-8").splitlines() == ["A"]


def test_invalid_child_summary_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CK04_TEST_MODE", "invalid_summary")

    with pytest.raises(qualification_suite.SuiteRunFailed, match="child summary"):
        qualification_suite.run_suite(_config(tmp_path, helper=_helper(tmp_path)))


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "suite"
    output.mkdir()
    marker = output / "keep"
    marker.write_text("untouched", encoding="utf-8")

    with pytest.raises(qualification_suite.SuiteContractError, match="already exists"):
        qualification_suite.run_suite(_config(tmp_path, helper=_helper(tmp_path)))

    assert marker.read_text(encoding="utf-8") == "untouched"


def test_explicit_complete_artifact_resume_is_self_contained(tmp_path: Path) -> None:
    first = qualification_suite.run_suite(_config(tmp_path, helper=_helper(tmp_path)))
    resume_result = first.unit_results[0]
    second_root = tmp_path / "second"
    second = qualification_suite.run_suite(
        qualification_suite.SuiteConfig(
            **{
                **_config(second_root, helper=_helper(tmp_path)).__dict__,
                "resume_results": (resume_result,),
            }
        )
    )

    result = json.loads(second.unit_results[0].read_text(encoding="utf-8"))
    assert result["resumed"] is True
    assert (second.output_root / "units" / "000000" / "child" / "summary.json").is_file()


def test_tiny_fixture_can_be_generated_or_accepted(tmp_path: Path) -> None:
    accepted = qualification_suite.run_suite(_config(tmp_path, helper=_helper(tmp_path)))
    assert accepted.status == "passed"

    generated_root = tmp_path / "generated"
    generated = qualification_suite.run_suite(
        qualification_suite.SuiteConfig(
            **{
                **_config(generated_root, helper=_helper(tmp_path)).__dict__,
                "fixture_specs": (qualification_suite.FixtureSpec("tiny", None),),
            }
        )
    )
    assert generated.status == "passed"
    assert (generated.output_root / "fixtures" / "tiny-v1" / "manifest.json").is_file()


def test_watchdog_basis_defaults_and_overrides_are_validated(tmp_path: Path) -> None:
    matrix = shared.build_workload_matrix(physical_cores=8)
    build = matrix.by_id("build.scale.tiny")
    query = matrix.by_id("query.q-ctx-01.warm_first_page")

    build_policy = qualification_suite.resolve_watchdog(
        build,
        profile="tiny",
        startup_grace_seconds=10,
        overrides={},
    )
    assert build_policy.seconds == 30
    assert build_policy.basis == "profile:tiny"

    query_policy = qualification_suite.resolve_watchdog(
        query,
        profile="tiny",
        startup_grace_seconds=10,
        overrides={"group:query": 17.0},
    )
    assert query_policy.seconds == 17.0
    assert query_policy.basis == "group:query"

    hard_limited = matrix.by_id("ordinary.no_source_change")
    hard_limit_policy = qualification_suite.resolve_watchdog(
        hard_limited,
        profile="production",
        startup_grace_seconds=10,
        overrides={"group:ordinary_change": 17.0, "profile:production": 240.0},
    )
    assert hard_limit_policy.seconds == 10.1
    assert hard_limit_policy.basis == "hard_limit:elapsed_ms"

    assert qualification_suite.parse_watchdog_overrides(
        ("group:query=12.5", "profile:growth=240")
    ) == {"group:query": 12.5, "profile:growth": 240.0}
    with pytest.raises(qualification_suite.SuiteContractError):
        qualification_suite.parse_watchdog_overrides(("query=12",))
    with pytest.raises(qualification_suite.SuiteContractError):
        qualification_suite.parse_watchdog_overrides(("group:query=-1",))
