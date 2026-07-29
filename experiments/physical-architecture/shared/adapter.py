from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .fixture import FixtureBundle
from .measurement import MeasurementCollector, MeasurementIdentity, MeasurementValues
from .outcomes import RunOutcome
from .stop import EarlyStopController
from .workload import WorkloadCase

CANDIDATE_ADAPTER_CONTRACT_VERSION = "ck04-candidate-adapter-v1"
_CANDIDATE_IDS = frozenset({"A", "C", "D"})


class CandidateContractError(ValueError):
    pass


@dataclass(frozen=True)
class PublicationState:
    publication_id: str
    artifact_path: Path
    prior_publication_queryable: bool


@dataclass(frozen=True)
class CandidateRequest:
    case: WorkloadCase
    fixture: FixtureBundle
    run_root: Path
    repetition: int
    stop: EarlyStopController

    def __post_init__(self) -> None:
        if self.repetition < 0:
            raise CandidateContractError("candidate repetition must be nonnegative")
        if not self.run_root.is_dir():
            raise CandidateContractError("candidate run root must already exist")
        if self.stop.case_id != self.case.case_id:
            raise CandidateContractError("stop controller case differs from candidate request")
        actual_limits = {limit.metric: limit.maximum for limit in self.stop.limits}
        for required in self.case.early_stop_limits:
            actual = actual_limits.get(required.metric)
            if actual is None or actual > required.maximum:
                raise CandidateContractError(
                    f"candidate stop controller weakens {required.metric.value}"
                )


@dataclass(frozen=True)
class CandidateResult:
    candidate_id: str
    case_id: str
    outcome: RunOutcome
    measurements: MeasurementValues
    publication: PublicationState | None = None
    oracle_results: Mapping[str, Any] | None = None
    detail_code: str | None = None


@runtime_checkable
class CandidateAdapter(Protocol):
    """The only shared callable seam implemented by Candidates A, C, and D."""

    candidate_id: str
    contract_version: str

    def execute(self, request: CandidateRequest) -> CandidateResult: ...


def execute_candidate(
    adapter: CandidateAdapter,
    request: CandidateRequest,
) -> CandidateResult:
    if not isinstance(adapter, CandidateAdapter):
        raise CandidateContractError("candidate does not implement the adapter protocol")
    if adapter.candidate_id not in _CANDIDATE_IDS:
        raise CandidateContractError("candidate ID must be A, C, or D")
    if adapter.contract_version != CANDIDATE_ADAPTER_CONTRACT_VERSION:
        raise CandidateContractError("candidate adapter contract version mismatch")
    result = adapter.execute(request)
    if result.candidate_id != adapter.candidate_id:
        raise CandidateContractError("candidate result ID differs from adapter ID")
    if result.case_id != request.case.case_id:
        raise CandidateContractError("candidate result case differs from request")
    if result.outcome is RunOutcome.UNSUPPORTED and request.case.candidate_capability is None:
        raise CandidateContractError("mandatory workload case cannot be unsupported")
    if result.outcome in {RunOutcome.FAILED, RunOutcome.UNSUPPORTED} and not result.detail_code:
        raise CandidateContractError("failed/unsupported result must include a detail code")
    if result.outcome is RunOutcome.STOPPED and request.stop.decision is None:
        raise CandidateContractError("stopped result must include an early-stop decision")
    if result.publication is not None:
        artifact = result.publication.artifact_path.resolve()
        run_root = request.run_root.resolve()
        if not artifact.is_relative_to(run_root):
            raise CandidateContractError("candidate artifact must stay inside its run root")
    return result


def execute_measured_candidate(
    adapter: CandidateAdapter,
    request: CandidateRequest,
    collector: MeasurementCollector,
    identity: MeasurementIdentity,
) -> CandidateResult:
    if not isinstance(adapter, CandidateAdapter):
        raise CandidateContractError("candidate does not implement the adapter protocol")
    expected_identity = (
        adapter.candidate_id,
        request.case.case_id,
        request.fixture.profile,
        request.fixture.manifest_digest,
        request.fixture.oracle_digest,
        request.repetition,
    )
    actual_identity = (
        identity.candidate_id,
        identity.case_id,
        identity.fixture_profile,
        identity.fixture_manifest_digest,
        identity.fixture_oracle_digest,
        identity.repetition,
    )
    if actual_identity != expected_identity:
        raise CandidateContractError("measurement identity differs from candidate request")
    with collector.measure(identity) as draft:
        result = execute_candidate(adapter, request)
        draft.set_values(result.measurements)
        if result.outcome is RunOutcome.STOPPED:
            decision = request.stop.decision
            if decision is None:
                raise CandidateContractError("stopped result has no early-stop decision")
            draft.mark_stopped(decision)
        elif result.outcome is RunOutcome.FAILED:
            draft.mark_failed(result.detail_code or "candidate_failed")
        elif result.outcome is RunOutcome.UNSUPPORTED:
            draft.mark_unsupported(result.detail_code or "candidate_unsupported")
    return result
