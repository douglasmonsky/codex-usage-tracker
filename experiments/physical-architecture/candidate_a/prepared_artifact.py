from __future__ import annotations

import stat
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .ingest import BuildArtifact, IngestStats


class PreparedArtifactError(ValueError):
    """A retained scale artifact is unsafe to use as an ordinary-change source."""


@dataclass(frozen=True)
class PreparationEvidence:
    clone_method: str
    source_bytes: int
    preparation_wall_time_ns: int
    source_unchanged: bool
    source_publication_id: str
    destination_publication_id: str

    def as_oracle_result(self, *, source_case_id: str) -> dict[str, object]:
        return {
            "clone_method": self.clone_method,
            "mode": "prepared_scale_clone",
            "preparation_wall_time_ns": self.preparation_wall_time_ns,
            "copy_sidecars": False,
            "destination_distinct_inode": True,
            "source_unchanged": self.source_unchanged,
            "source_case_id": source_case_id,
            "source_bytes": self.source_bytes,
            "source_publication_id": self.source_publication_id,
            "destination_publication_id": self.destination_publication_id,
        }


def clone_prepared_artifact(
    artifact: BuildArtifact,
    *,
    retained_root: Path,
    destination: Path,
) -> tuple[BuildArtifact, PreparationEvidence]:
    """Create an isolated ordinary-change snapshot before measured execution."""
    source = artifact.path.resolve(strict=True)
    retained = retained_root.resolve(strict=True)
    if not source.is_relative_to(retained):
        raise PreparedArtifactError("prepared source escapes its retained scale root")
    source_stat = source.stat()
    source_identity = (source_stat.st_ino, source_stat.st_size, source_stat.st_mtime_ns)
    if not stat.S_ISREG(source_stat.st_mode):
        raise PreparedArtifactError("prepared source must be a regular file")
    _validate_source_sidecars(source, retained)
    if destination.exists() or destination.is_symlink():
        raise PreparedArtifactError("prepared destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.resolve(strict=False) == source:
        raise PreparedArtifactError("prepared destination must differ from source")

    try:
        started = time.perf_counter_ns()
        method = _clone_file(source, destination)
        preparation_wall_time_ns = time.perf_counter_ns() - started
        destination_stat = destination.stat()
        if not stat.S_ISREG(destination_stat.st_mode):
            raise PreparedArtifactError("prepared destination is not a regular file")
        if destination_stat.st_ino == source_stat.st_ino:
            raise PreparedArtifactError("prepared destination must have a distinct inode")
        if destination_stat.st_size != source_stat.st_size:
            raise PreparedArtifactError("prepared destination size differs from source")
        after = source.stat()
        source_unchanged = (after.st_ino, after.st_size, after.st_mtime_ns) == source_identity
        if not source_unchanged:
            raise PreparedArtifactError("prepared source changed while cloning")
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return (
        BuildArtifact(
            path=destination,
            publication_id=artifact.publication_id,
            observed_through_us=artifact.observed_through_us,
            stats=IngestStats(occurrence_rows=artifact.stats.occurrence_rows),
        ),
        PreparationEvidence(
            clone_method=method,
            source_bytes=source_stat.st_size,
            preparation_wall_time_ns=preparation_wall_time_ns,
            source_unchanged=source_unchanged,
            source_publication_id=artifact.publication_id,
            destination_publication_id=artifact.publication_id,
        ),
    )


def _validate_source_sidecars(source: Path, retained_root: Path) -> None:
    journal = source.with_name(f"{source.name}-journal")
    if journal.exists():
        raise PreparedArtifactError("prepared source has a rollback journal")
    wal = source.with_name(f"{source.name}-wal")
    if wal.exists() and wal.stat().st_size != 0:
        raise PreparedArtifactError("prepared source has a nonempty WAL")
    if (retained_root / "publication-lease.json").exists():
        raise PreparedArtifactError("prepared source has an active publication lease")


def _clone_file(source: Path, destination: Path) -> str:
    try:
        subprocess.run(("/bin/cp", "-c", "--", str(source), str(destination)), check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise PreparedArtifactError("prepared scale clone is unavailable") from error
    return "cp_clone"
