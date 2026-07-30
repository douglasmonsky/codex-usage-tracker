from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

CRASH_BOUNDARIES = (
    "before_staging",
    "during_parse",
    "during_fact_writes",
    "after_facts_before_projections",
    "during_projection_update",
    "after_validation_before_promotion",
    "during_promotion",
    "after_promotion_before_sidecar_reconciliation",
    "during_old_artifact_cleanup",
)
CRASH_FAULTS = (
    "disk_full",
    "disk_full_before_transaction",
    "disk_full_during_transaction",
    "malformed_source",
    "disappearing_source",
    "busy_reader",
    "stale_writer_lease",
    "stale_lease_pid_reuse",
    "corrupt_staging_artifact",
    "sidecar_corruption",
    "analytical_candidate_corruption",
    "pointer_mismatch",
    "schema_projection_incompatibility",
    "invalid_rate_card",
    "read_process_open_during_promotion",
    "simultaneous_startup_recovery",
)


class CrashContractError(AssertionError):
    pass


@dataclass(frozen=True)
class CrashCase:
    case_id: str
    boundary: str | None = None
    fault: str | None = None

    def __post_init__(self) -> None:
        if (self.boundary is None) == (self.fault is None):
            raise ValueError("crash case must select exactly one boundary or fault")
        if self.boundary is not None and self.boundary not in CRASH_BOUNDARIES:
            raise ValueError(f"unknown crash boundary: {self.boundary}")
        if self.fault is not None and self.fault not in CRASH_FAULTS:
            raise ValueError(f"unknown crash fault: {self.fault}")

    @classmethod
    def termination(cls, boundary: str) -> CrashCase:
        return cls(case_id=f"crash.terminate.{boundary}", boundary=boundary)

    @classmethod
    def injected_fault(cls, fault: str) -> CrashCase:
        return cls(case_id=f"crash.fault.{fault}", fault=fault)


@dataclass(frozen=True)
class CrashObservation:
    boundary: str | None
    prior_publication_queryable: bool
    rollback_available: bool
    candidate_publication_committed: bool
    sidecar_terminal_state: str
    abandoned_artifact_disposition: str
    subsequent_operation_succeeds: bool
    fault: str | None = None


@runtime_checkable
class PublicationCrashDriver(Protocol):
    """Candidate-owned process driver controlled by the shared crash harness."""

    candidate_id: str

    def run_crash_case(self, crash_case: CrashCase) -> CrashObservation: ...


def run_publication_crash_case(
    driver: PublicationCrashDriver,
    crash_case: CrashCase,
    expected: Mapping[str, Any],
) -> CrashObservation:
    if not isinstance(driver, PublicationCrashDriver):
        raise CrashContractError("candidate does not implement the publication crash driver")
    if driver.candidate_id not in {"A", "C", "D"}:
        raise CrashContractError("publication crash driver candidate must be A, C, or D")
    observed = driver.run_crash_case(crash_case)
    validate_crash_observation(crash_case, expected, observed)
    return observed


def validate_crash_observation(
    crash_case: CrashCase,
    expected: Mapping[str, Any],
    observed: CrashObservation,
) -> None:
    if crash_case.fault is not None:
        if observed.fault != crash_case.fault or observed.boundary is not None:
            raise CrashContractError("observed crash fault differs from requested fault")
        if not observed.prior_publication_queryable:
            raise CrashContractError("prior publication is not queryable after injected fault")
        if not observed.rollback_available:
            raise CrashContractError("rollback is not available after injected fault")
        if not observed.subsequent_operation_succeeds:
            raise CrashContractError("subsequent operation failed after injected fault")
        return
    if crash_case.boundary is None:
        raise CrashContractError("crash case has neither a boundary nor a fault")
    if observed.boundary != crash_case.boundary:
        raise CrashContractError("observed crash boundary differs from requested boundary")
    checks = (
        (
            "prior publication queryability",
            observed.prior_publication_queryable,
            expected.get("prior_publication_queryable"),
        ),
        ("rollback availability", observed.rollback_available, expected.get("rollback_available")),
        (
            "candidate publication state",
            observed.candidate_publication_committed,
            expected.get("candidate_publication_committed"),
        ),
        (
            "sidecar terminal state",
            observed.sidecar_terminal_state,
            expected.get("sidecar_terminal_state"),
        ),
        (
            "abandoned artifact disposition",
            observed.abandoned_artifact_disposition,
            expected.get("abandoned_artifact_disposition"),
        ),
        (
            "subsequent operation",
            observed.subsequent_operation_succeeds,
            expected.get("subsequent_operation_succeeds"),
        ),
    )
    for label, actual, wanted in checks:
        if actual != wanted:
            raise CrashContractError(f"{label} does not match the CK-03 crash oracle")
