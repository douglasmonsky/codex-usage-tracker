from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import shared

from .ingest import file_sha256
from .publication import (
    _ACTIVE_ARTIFACT,
    _ACTIVE_POINTER,
    _FAULT_OBSERVATION,
    _LEASE,
    _SIDECAR,
    _atomic_write_bytes,
    _atomic_write_json,
    _fault_boundary,
    _publication_id,
    publish_artifact,
    recover_publication_state,
)
from .schema import database

_FAULT_EXIT = 87


class _FaultController:
    def __init__(
        self,
        *,
        fault: str,
        run_root: Path,
        driver_pid: int,
        driver_start_token: str,
        timeout_seconds: float,
    ) -> None:
        if fault not in shared.CRASH_FAULTS:
            raise ValueError(f"unknown candidate A injected fault: {fault}")
        self.fault = fault
        self.run_root = run_root
        self.driver_pid = driver_pid
        self.driver_start_token = driver_start_token
        self.timeout_seconds = timeout_seconds
        self.expected_stage = _fault_boundary(fault)
        self.injected = False
        self.reader_process: subprocess.Popen[bytes] | None = None
        self.reader_ready = run_root / "fault-reader.ready"
        self.reader_release = run_root / "fault-reader.release"
        self.reader_result = run_root / "fault-reader-result.json"
        self.reader_lock = run_root / "fault-reader.lock"

    def prepare(self) -> None:
        if self.fault not in {"busy_reader", "read_process_open_during_promotion"}:
            return
        command = (
            sys.executable,
            "-m",
            "candidate_a.crash_worker",
            "--reader-path",
            str(self.run_root / _ACTIVE_ARTIFACT),
            "--reader-ready",
            str(self.reader_ready),
            "--reader-release",
            str(self.reader_release),
            "--reader-result",
            str(self.reader_result),
            "--reader-lock",
            str(self.reader_lock),
            "--reader-timeout",
            str(self.timeout_seconds),
        )
        self.reader_process = subprocess.Popen(
            command,
            cwd=self.run_root,
            env=dict(os.environ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + self.timeout_seconds
        while not self.reader_ready.is_file():
            if self.reader_process.poll() is not None:
                raise RuntimeError("candidate A injected reader exited before becoming ready")
            if time.monotonic() >= deadline:
                raise TimeoutError("candidate A injected reader did not become ready")
            time.sleep(0.005)

    def close(self) -> None:
        if self.reader_process is None:
            return
        if self.reader_process.poll() is None:
            _atomic_write_json(
                self.reader_release,
                {"schema": "candidate-a-reader-release.v1", "state": "released"},
            )
            try:
                self.reader_process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                self.reader_process.kill()
                self.reader_process.wait(timeout=self.timeout_seconds)
                raise
        if self.reader_process.returncode != 0:
            raise RuntimeError("candidate A injected reader failed")
        reader_result = _read_record(self.reader_result)
        fault_record = _read_record(self.run_root / _FAULT_OBSERVATION)
        if fault_record is not None:
            fault_record["reader_result"] = reader_result
            _atomic_write_json(self.run_root / _FAULT_OBSERVATION, fault_record)
        self.reader_process = None

    def __call__(self, boundary: str) -> None:
        if boundary != self.expected_stage:
            return
        handlers = {
            "disk_full": self._disk_full,
            "disk_full_before_transaction": self._disk_full_before_transaction,
            "disk_full_during_transaction": self._disk_full_during_transaction,
            "malformed_source": self._malformed_source,
            "disappearing_source": self._disappearing_source,
            "busy_reader": self._busy_reader,
            "stale_writer_lease": self._stale_writer_lease,
            "stale_lease_pid_reuse": self._stale_lease_pid_reuse,
            "corrupt_staging_artifact": self._corrupt_staging_artifact,
            "sidecar_corruption": self._sidecar_corruption,
            "analytical_candidate_corruption": self._analytical_candidate_corruption,
            "pointer_mismatch": self._pointer_mismatch,
            "schema_projection_incompatibility": self._schema_projection_incompatibility,
            "invalid_rate_card": self._invalid_rate_card,
            "read_process_open_during_promotion": self._read_process_open_during_promotion,
            "simultaneous_startup_recovery": self._simultaneous_startup_recovery,
        }
        handlers[self.fault](boundary)

    def _record(self, boundary: str, mechanism: str, **observed: object) -> None:
        self.injected = True
        _atomic_write_json(
            self.run_root / _FAULT_OBSERVATION,
            {
                "fault": self.fault,
                "mechanism": mechanism,
                "observed": observed,
                "schema": "candidate-a-fault-observation.v1",
                "stage": boundary,
                "state": "injected",
            },
        )

    def _raise_oserror(self, boundary: str, mechanism: str) -> None:
        self._record(
            boundary,
            mechanism,
            errno=errno.ENOSPC,
            exception_type="OSError",
        )
        raise OSError(errno.ENOSPC, "candidate A injected disk capacity exhaustion")

    def _disk_full(self, boundary: str) -> None:
        self._raise_oserror(boundary, "enospc_projection_write")

    def _disk_full_before_transaction(self, boundary: str) -> None:
        self._raise_oserror(boundary, "enospc_before_transaction")

    def _disk_full_during_transaction(self, boundary: str) -> None:
        self._raise_oserror(boundary, "enospc_fact_transaction")

    def _malformed_source(self, boundary: str) -> None:
        source = self.run_root / "injected-malformed-source.jsonl"
        source.write_bytes(b'{"type":"model_call","payload":\n')
        try:
            json.loads(source.read_bytes())
        except json.JSONDecodeError as error:
            self._record(
                boundary,
                "json_decode_failure",
                exception_type=type(error).__name__,
                source=source.name,
            )
            raise
        raise AssertionError("candidate A malformed source fault did not fail")

    def _disappearing_source(self, boundary: str) -> None:
        source = self.run_root / "injected-disappearing-source.jsonl"
        source.write_bytes(b'{"type":"synthetic"}\n')
        source.unlink()
        self._record(
            boundary,
            "source_unlinked_before_read",
            source=source.name,
        )
        source.read_bytes()

    def _busy_reader(self, boundary: str) -> None:
        with self.reader_lock.open("a+b") as reader_lock:
            try:
                fcntl.flock(
                    reader_lock.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                self._record(
                    boundary,
                    "reader_shared_lock_blocks_promotion_lease",
                    reader_process_alive=bool(
                        self.reader_process is not None and self.reader_process.poll() is None
                    ),
                )
                raise sqlite3.OperationalError(
                    "candidate A injected busy reader promotion conflict"
                ) from None
            finally:
                fcntl.flock(reader_lock.fileno(), fcntl.LOCK_UN)
        raise AssertionError("candidate A busy reader fault did not contend")

    def _stale_writer_lease(self, boundary: str) -> None:
        _atomic_write_json(
            self.run_root / _LEASE,
            {
                "operation_id": "injected-stale-writer",
                "pid": 2_147_483_647,
                "schema": "candidate-a-publication-lease.v1",
                "start_token": "dead-process",
            },
        )
        self._record(
            boundary,
            "dead_pid_writer_lease",
            pid=2_147_483_647,
        )
        raise RuntimeError("candidate A injected stale writer lease")

    def _stale_lease_pid_reuse(self, boundary: str) -> None:
        _atomic_write_json(
            self.run_root / _LEASE,
            {
                "operation_id": "injected-reused-pid",
                "pid": self.driver_pid,
                "schema": "candidate-a-publication-lease.v1",
                "start_token": f"reused:{self.driver_start_token}",
            },
        )
        self._record(
            boundary,
            "live_pid_start_token_mismatch",
            live_pid=self.driver_pid,
            token_matches=False,
        )
        raise RuntimeError("candidate A injected stale lease PID reuse")

    def _corrupt_staging_artifact(self, boundary: str) -> None:
        staging = self.run_root / "candidate.sqlite"
        before = file_sha256(staging)
        with staging.open("r+b") as artifact:
            artifact.seek(0)
            artifact.write(b"not-a-sqlite-db!")
            artifact.flush()
            os.fsync(artifact.fileno())
        self._record(
            boundary,
            "sqlite_header_corruption",
            digest_changed=file_sha256(staging) != before,
        )
        raise RuntimeError("candidate A injected corrupt staging artifact")

    def _sidecar_corruption(self, boundary: str) -> None:
        sidecar = self.run_root / _SIDECAR
        _atomic_write_bytes(sidecar, b"{corrupt-sidecar")
        self._record(
            boundary,
            "invalid_sidecar_json",
            sidecar=sidecar.name,
        )
        raise RuntimeError("candidate A injected sidecar corruption")

    def _analytical_candidate_corruption(self, boundary: str) -> None:
        staging = self.run_root / "candidate.sqlite"
        with sqlite3.connect(staging) as connection:
            connection.execute("UPDATE metadata SET value='corrupt' WHERE key='candidate_id'")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        self._record(
            boundary,
            "analytical_metadata_corruption",
            metadata_key="candidate_id",
        )
        raise RuntimeError("candidate A injected analytical candidate corruption")

    def _pointer_mismatch(self, boundary: str) -> None:
        _atomic_write_json(
            self.run_root / _ACTIVE_POINTER,
            {
                "artifact_path": _ACTIVE_ARTIFACT,
                "artifact_sha256": "0" * 64,
                "publication_id": "publication:candidate-a:injected-mismatch",
                "schema": "candidate-a-publication-pointer.v1",
            },
        )
        self._record(
            boundary,
            "active_pointer_identity_digest_mismatch",
            pointer=_ACTIVE_POINTER,
        )
        raise RuntimeError("candidate A injected active pointer mismatch")

    def _schema_projection_incompatibility(self, boundary: str) -> None:
        staging = self.run_root / "candidate.sqlite"
        with sqlite3.connect(staging) as connection:
            connection.execute("DROP TABLE tool_family_current")
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        self._record(
            boundary,
            "projection_table_removed",
            projection="tool_family_current",
        )
        raise RuntimeError("candidate A injected schema/projection incompatibility")

    def _invalid_rate_card(self, boundary: str) -> None:
        rate_card = self.run_root / "injected-invalid-rate-card.json"
        _atomic_write_json(
            rate_card,
            {
                "input_per_million": "-1.00",
                "model": "",
                "revision": "synthetic-invalid",
            },
        )
        value = json.loads(rate_card.read_bytes())
        self._record(
            boundary,
            "rate_card_validation_failure",
            rate_card=rate_card.name,
        )
        if (
            not isinstance(value, dict)
            or not value.get("model")
            or float(value["input_per_million"]) < 0
        ):
            raise ValueError("candidate A injected invalid rate card")
        raise AssertionError("candidate A invalid rate card fault did not fail")

    def _read_process_open_during_promotion(self, boundary: str) -> None:
        self.close()
        reader_result = _read_record(self.reader_result)
        active_publication_id = _publication_id(self.run_root / _ACTIVE_ARTIFACT)
        self._record(
            boundary,
            "separate_reader_snapshot_spans_atomic_promotion",
            active_publication_id=active_publication_id,
            reader_result=reader_result,
        )
        raise RuntimeError("candidate A injected interruption with reader open")

    def _simultaneous_startup_recovery(self, boundary: str) -> None:
        self._record(
            boundary,
            "two_process_startup_recovery_barrier",
            recovery_workers=2,
        )
        raise RuntimeError("candidate A injected simultaneous startup recovery")


def _read_record(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _run_reader(
    *,
    path: Path,
    ready: Path,
    release: Path,
    result: Path,
    lock_path: Path,
    timeout_seconds: float,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    with (
        database(path, read_only=True) as connection,
        lock_path.open("a+b") as reader_lock,
    ):
        connection.execute("BEGIN")
        before = str(
            connection.execute(
                "SELECT publication_id FROM publications WHERE status='committed'"
            ).fetchone()[0]
        )
        fcntl.flock(reader_lock.fileno(), fcntl.LOCK_SH)
        _atomic_write_json(
            ready,
            {
                "publication_id": before,
                "schema": "candidate-a-reader-ready.v1",
                "state": "reading",
            },
        )
        while not release.is_file():
            if time.monotonic() >= deadline:
                raise TimeoutError("candidate A reader release timed out")
            time.sleep(0.005)
        after = str(
            connection.execute(
                "SELECT publication_id FROM publications WHERE status='committed'"
            ).fetchone()[0]
        )
        _atomic_write_json(
            result,
            {
                "after_publication_id": after,
                "before_publication_id": before,
                "same_snapshot": before == after,
                "schema": "candidate-a-reader-result.v1",
            },
        )
        fcntl.flock(reader_lock.fileno(), fcntl.LOCK_UN)
    return 0


def _run_recovery(
    *,
    run_root: Path,
    prior_publication_id: str,
    recovery_id: str,
    ready: Path,
    start: Path,
    result: Path,
    timeout_seconds: float,
) -> int:
    _atomic_write_json(
        ready,
        {
            "recovery_id": recovery_id,
            "schema": "candidate-a-recovery-ready.v1",
            "state": "ready",
        },
    )
    deadline = time.monotonic() + timeout_seconds
    while not start.is_file():
        if time.monotonic() >= deadline:
            raise TimeoutError("candidate A recovery start barrier timed out")
        time.sleep(0.005)
    recovered = recover_publication_state(
        run_root,
        prior_publication_id=prior_publication_id,
        recovery_id=recovery_id,
        timeout_seconds=timeout_seconds,
    )
    _atomic_write_json(
        result,
        {
            "active_publication_id": recovered.active_publication_id,
            "candidate_publication_committed": recovered.candidate_publication_committed,
            "recovery_action": recovered.recovery_action,
            "recovery_id": recovery_id,
            "schema": "candidate-a-recovery-worker-result.v1",
            "sidecar_terminal_state": recovered.sidecar_terminal_state,
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--parent-publication-id")
    parser.add_argument("--stop-at", choices=shared.CRASH_BOUNDARIES)
    parser.add_argument("--fault", choices=shared.CRASH_FAULTS)
    parser.add_argument("--driver-pid", type=int, default=0)
    parser.add_argument("--driver-start-token", default="")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--reader-path", type=Path)
    parser.add_argument("--reader-ready", type=Path)
    parser.add_argument("--reader-release", type=Path)
    parser.add_argument("--reader-result", type=Path)
    parser.add_argument("--reader-lock", type=Path)
    parser.add_argument("--reader-timeout", type=float, default=10.0)
    parser.add_argument("--recover-run-root", type=Path)
    parser.add_argument("--recover-prior-publication-id")
    parser.add_argument("--recover-id")
    parser.add_argument("--recover-ready", type=Path)
    parser.add_argument("--recover-start", type=Path)
    parser.add_argument("--recover-result", type=Path)
    args = parser.parse_args()

    if args.reader_path is not None:
        reader_values = (
            args.reader_ready,
            args.reader_release,
            args.reader_result,
            args.reader_lock,
        )
        if any(value is None for value in reader_values):
            parser.error("candidate A reader mode requires all reader paths")
        return _run_reader(
            path=args.reader_path,
            ready=args.reader_ready,
            release=args.reader_release,
            result=args.reader_result,
            lock_path=args.reader_lock,
            timeout_seconds=args.reader_timeout,
        )
    if args.recover_run_root is not None:
        recovery_values = (
            args.recover_prior_publication_id,
            args.recover_id,
            args.recover_ready,
            args.recover_start,
            args.recover_result,
        )
        if any(value is None for value in recovery_values):
            parser.error("candidate A recovery mode requires all recovery arguments")
        return _run_recovery(
            run_root=args.recover_run_root,
            prior_publication_id=args.recover_prior_publication_id,
            recovery_id=args.recover_id,
            ready=args.recover_ready,
            start=args.recover_start,
            result=args.recover_result,
            timeout_seconds=args.timeout,
        )
    operation_values = (
        args.fixture,
        args.run_root,
        args.parent_publication_id,
    )
    if any(value is None for value in operation_values):
        parser.error("candidate A operation mode requires fixture, run root, and parent")
    if (args.stop_at is None) == (args.fault is None):
        parser.error("candidate A operation mode requires exactly one stop point or fault")
    fixture = shared.load_fixture_bundle(args.fixture)

    if args.stop_at is not None:

        def stop(boundary: str) -> None:
            if boundary == args.stop_at:
                os._exit(86)

        publish_artifact(
            fixture,
            args.run_root,
            parent_publication_id=args.parent_publication_id,
            hook=stop,
        )
        return 0

    controller = _FaultController(
        fault=args.fault,
        run_root=args.run_root,
        driver_pid=args.driver_pid,
        driver_start_token=args.driver_start_token,
        timeout_seconds=args.timeout,
    )
    controller.prepare()
    try:
        publish_artifact(
            fixture,
            args.run_root,
            parent_publication_id=args.parent_publication_id,
            hook=controller,
        )
    except Exception:
        if not controller.injected:
            raise
    else:
        raise AssertionError("candidate A injected fault did not interrupt publication")
    finally:
        controller.close()
    return _FAULT_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
