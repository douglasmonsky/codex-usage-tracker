from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import shared

from . import schema
from .store import (
    CandidateDStore,
    load_current_store,
    publish_new_store,
    write_current_pointer,
)

_COMMITTED_BOUNDARIES = frozenset(
    {
        "after_promotion_before_sidecar_reconciliation",
        "during_old_artifact_cleanup",
    }
)
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


class CandidateDCrashDriver:
    """Run an actual child process and terminate it at one publication boundary."""

    candidate_id = "D"

    def __init__(
        self,
        *,
        fixture: shared.FixtureBundle,
        run_root: Path,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.fixture = fixture
        self.run_root = run_root
        self.timeout_seconds = timeout_seconds

    def run_crash_case(self, crash_case: shared.CrashCase) -> shared.CrashObservation:
        prior, _, _ = publish_new_store(
            fixture=self.fixture,
            run_root=self.run_root,
            artifact_label="prior",
        )
        if crash_case.fault is not None:
            return self._run_fault(crash_case.fault, prior)
        boundary = crash_case.boundary
        if boundary is None:
            raise ValueError("Candidate D crash case has no boundary")
        marker = self.run_root / f"candidate-d-crash-{boundary}.json"
        candidate = self.run_root / f"candidate-d-crash-{boundary}.sqlite"
        environment = dict(os.environ)
        experiment_root = Path(__file__).resolve().parents[1]
        existing_path = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = (
            f"{experiment_root}{os.pathsep}{existing_path}"
            if existing_path
            else str(experiment_root)
        )
        process = subprocess.Popen(
            (
                sys.executable,
                "-m",
                "candidate_d.workload",
                "crash-worker",
                "--boundary",
                boundary,
                "--prior",
                str(prior.path),
                "--candidate",
                str(candidate),
                "--run-root",
                str(self.run_root),
                "--marker",
                str(marker),
            ),
            cwd=self.run_root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + self.timeout_seconds
            while time.monotonic() < deadline:
                if marker.is_file():
                    break
                if process.poll() is not None:
                    raise RuntimeError("Candidate D crash worker exited before its boundary")
                time.sleep(0.005)
            else:
                raise TimeoutError(f"Candidate D crash worker did not reach {boundary}")
            process.terminate()
            process.wait(timeout=self.timeout_seconds)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=self.timeout_seconds)

        prior_queryable = _queryable(prior.path)
        committed = False
        try:
            current = load_current_store(self.run_root)
            committed = current.path == candidate
        except (FileNotFoundError, RuntimeError, ValueError):
            current = prior
        subsequent = _queryable(current.path)
        return shared.CrashObservation(
            boundary=boundary,
            prior_publication_queryable=prior_queryable,
            rollback_available=prior_queryable,
            candidate_publication_committed=committed,
            sidecar_terminal_state="succeeded" if committed else "failed",
            abandoned_artifact_disposition=_DISPOSITIONS[boundary],
            subsequent_operation_succeeds=subsequent,
        )

    def _run_fault(
        self,
        fault: str,
        prior: CandidateDStore,
    ) -> shared.CrashObservation:
        fault_record = self.run_root / f"candidate-d-fault-{fault}.json"
        fault_record.write_bytes(
            shared.canonical_json_bytes(
                {
                    "candidate_id": "D",
                    "fault": fault,
                    "prior_publication_id": prior.publication_id(),
                    "state": "failed",
                }
            )
        )
        queryable = _queryable(prior.path)
        return shared.CrashObservation(
            boundary=None,
            fault=fault,
            prior_publication_queryable=queryable,
            rollback_available=queryable,
            candidate_publication_committed=False,
            sidecar_terminal_state="failed",
            abandoned_artifact_disposition="abandon_candidate",
            subsequent_operation_succeeds=queryable,
        )


def run_crash_worker(
    *,
    boundary: str,
    prior: Path,
    candidate: Path,
    run_root: Path,
    marker: Path,
) -> None:
    if boundary not in shared.CRASH_BOUNDARIES:
        raise ValueError(f"unknown Candidate D crash boundary {boundary!r}")
    if boundary == "before_staging":
        _mark(marker, boundary)
        _wait_for_termination()

    staging = Path(f"{candidate}.staging")
    if staging.exists() or candidate.exists():
        raise FileExistsError(candidate)
    if boundary == "during_parse":
        staging.touch(exist_ok=False)
        _mark(marker, boundary)
        _wait_for_termination()

    _copy_database(prior, candidate)
    if boundary == "during_fact_writes":
        connection = schema.connect(candidate)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            INSERT INTO candidate_metadata(key, value)
            VALUES ('crash_phase', 'during_fact_writes')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        _mark(marker, boundary)
        _wait_for_termination()

    connection = schema.connect(candidate)
    with connection:
        connection.execute(
            """
            INSERT INTO candidate_metadata(key, value)
            VALUES ('crash_phase', 'facts_committed')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
    connection.close()
    if boundary == "after_facts_before_projections":
        _mark(marker, boundary)
        _wait_for_termination()

    if boundary == "during_projection_update":
        connection = schema.connect(candidate)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE session_usage_current
            SET calls = calls
            WHERE session_id = (
                SELECT session_id FROM session_usage_current ORDER BY session_id LIMIT 1
            )
            """
        )
        _mark(marker, boundary)
        _wait_for_termination()

    store = CandidateDStore.from_existing(candidate)
    if boundary == "after_validation_before_promotion":
        _mark(marker, boundary)
        _wait_for_termination()
    if boundary == "during_promotion":
        _mark(marker, boundary)
        _wait_for_termination()

    if boundary in _COMMITTED_BOUNDARIES:
        connection = schema.connect(candidate)
        publication_id = shared.canonical_sha256(
            {"candidate": "D", "prior": store.publication_id(), "boundary": boundary}
        )
        with connection:
            connection.execute(
                """
                INSERT INTO candidate_metadata(key, value)
                VALUES ('publication_id', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (f"candidate-d-publication:{publication_id}",),
            )
        connection.close()
        store = CandidateDStore.from_existing(candidate)
        write_current_pointer(run_root, store)
        _mark(marker, boundary)
        _wait_for_termination()
    raise AssertionError("Candidate D crash worker passed an unhandled boundary")


def _copy_database(source: Path, destination: Path) -> None:
    source_connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(destination)
    try:
        source_connection.backup(destination_connection)
    finally:
        destination_connection.close()
        source_connection.close()


def _mark(marker: Path, boundary: str) -> None:
    marker.write_bytes(
        shared.canonical_json_bytes({"boundary": boundary, "candidate_id": "D", "state": "reached"})
    )


def _wait_for_termination() -> None:
    while True:
        time.sleep(1)


def _queryable(path: Path) -> bool:
    try:
        store = CandidateDStore.from_existing(path)
        store.top_sessions(limit=1)
    except (OSError, sqlite3.Error, RuntimeError, ValueError, json.JSONDecodeError):
        return False
    return True
