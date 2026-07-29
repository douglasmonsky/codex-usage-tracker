from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import shared

from .ingest import BuildArtifact, build_artifact, file_sha256
from .schema import database, validate_database

_DISPOSITIONS = {
    "before_staging": "none",
    "during_parse": "abandon_staging",
    "during_fact_writes": "abandon_candidate",
    "after_facts_before_projections": "abandon_candidate",
    "during_projection_update": "abandon_candidate",
    "after_validation_before_promotion": "retain_valid_candidate",
    "during_promotion": "reconcile_pointer_or_rollback",
    "after_promotion_before_sidecar_reconciliation": "reconcile_sidecar",
    "during_old_artifact_cleanup": "defer_cleanup",
}


def publish_artifact(
    fixture: shared.FixtureBundle,
    run_root: Path,
    *,
    history_selection: str = "all_time",
    parent_publication_id: str | None = None,
    hook: Callable[[str], None] | None = None,
    defer_secondary_indexes: bool = True,
) -> BuildArtifact:
    run_root.mkdir(parents=True, exist_ok=True)
    staging = run_root / "candidate.sqlite"
    publication = run_root / "publication.sqlite"
    if staging.exists():
        raise FileExistsError(staging)
    if hook is not None:
        hook("before_staging")
    artifact = build_artifact(
        fixture,
        staging,
        history_selection=history_selection,
        parent_publication_id=parent_publication_id,
        hook=hook,
        defer_secondary_indexes=defer_secondary_indexes,
    )
    if hook is not None:
        hook("after_validation_before_promotion")
        hook("during_promotion")
    os.replace(staging, publication)
    if hook is not None:
        hook("after_promotion_before_sidecar_reconciliation")
    sidecar = run_root / "publication-state.json"
    sidecar.write_bytes(
        shared.canonical_json_bytes(
            {
                "artifact_sha256": file_sha256(publication),
                "publication_id": artifact.publication_id,
                "state": "succeeded",
            }
        )
    )
    if hook is not None:
        hook("during_old_artifact_cleanup")
    return BuildArtifact(
        path=publication,
        publication_id=artifact.publication_id,
        observed_through_us=artifact.observed_through_us,
        stats=artifact.stats,
    )


def _publication_id(path: Path) -> str:
    with database(path, read_only=True) as connection:
        validate_database(connection)
        row = connection.execute(
            """
            SELECT publication_id FROM publications
            WHERE status='committed'
            ORDER BY committed_at_us DESC, publication_id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise ValueError("candidate A publication has no committed identity")
        return str(row["publication_id"])


class CandidateACrashDriver:
    candidate_id = "A"

    def __init__(
        self,
        fixture: shared.FixtureBundle,
        run_root: Path,
    ) -> None:
        self.fixture = fixture
        self.run_root = run_root

    def run_crash_case(self, crash_case: shared.CrashCase) -> shared.CrashObservation:
        case_root = self.run_root / crash_case.case_id.replace(".", "-")
        case_root.mkdir(parents=True, exist_ok=False)
        prior = build_artifact(self.fixture, case_root / "prior.sqlite")
        shutil.copyfile(prior.path, case_root / "publication.sqlite")
        boundary = crash_case.boundary or _fault_boundary(crash_case.fault)
        command = (
            sys.executable,
            "-m",
            "candidate_a.crash_worker",
            "--fixture",
            str(self.fixture.root),
            "--run-root",
            str(case_root),
            "--parent-publication-id",
            prior.publication_id,
            "--stop-at",
            boundary,
        )
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONHASHSEED": "0",
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        }
        completed = subprocess.run(
            command,
            check=False,
            env=environment,
            capture_output=True,
            text=False,
            timeout=30,
        )
        if completed.returncode != 86:
            raise RuntimeError(
                f"candidate A crash worker exited {completed.returncode}, expected 86"
            )
        with database(case_root / "prior.sqlite", read_only=True) as connection:
            validate_database(connection)
            prior_queryable = connection.execute(
                "SELECT count(*) FROM model_calls"
            ).fetchone()[0] > 0
        current_id = _publication_id(case_root / "publication.sqlite")
        committed = current_id != prior.publication_id
        subsequent_succeeds = _publication_id(case_root / "publication.sqlite") == current_id
        if crash_case.fault is not None:
            return shared.CrashObservation(
                boundary=None,
                fault=crash_case.fault,
                prior_publication_queryable=prior_queryable,
                rollback_available=True,
                candidate_publication_committed=committed,
                sidecar_terminal_state="failed",
                abandoned_artifact_disposition="abandon_candidate",
                subsequent_operation_succeeds=subsequent_succeeds,
            )
        return shared.CrashObservation(
            boundary=crash_case.boundary,
            prior_publication_queryable=prior_queryable,
            rollback_available=True,
            candidate_publication_committed=committed,
            sidecar_terminal_state="succeeded" if committed else "failed",
            abandoned_artifact_disposition=_DISPOSITIONS[boundary],
            subsequent_operation_succeeds=subsequent_succeeds,
        )


def _fault_boundary(fault: str | None) -> str:
    if fault in {"disk_full_before_transaction", "invalid_rate_card"}:
        return "before_staging"
    if fault in {"malformed_source", "disappearing_source"}:
        return "during_parse"
    if fault in {"disk_full", "disk_full_during_transaction", "stale_writer_lease"}:
        return "during_fact_writes"
    if fault in {
        "corrupt_staging_artifact",
        "analytical_candidate_corruption",
        "schema_projection_incompatibility",
    }:
        return "after_validation_before_promotion"
    if fault in {
        "sidecar_corruption",
        "pointer_mismatch",
        "read_process_open_during_promotion",
        "simultaneous_startup_recovery",
        "stale_lease_pid_reuse",
        "busy_reader",
    }:
        return "during_promotion"
    raise ValueError(f"unknown candidate A crash fault: {fault}")
