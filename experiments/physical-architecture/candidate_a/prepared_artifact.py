from __future__ import annotations

import ctypes
import errno
import os
import platform
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from .ingest import BuildArtifact, IngestStats


class PreparedArtifactError(ValueError):
    """A retained scale artifact is unsafe to use as an ordinary-change source."""


@dataclass(frozen=True)
class PreparationEvidence:
    clone_method: str
    source_bytes: int

    def as_oracle_result(self, *, source_case_id: str) -> dict[str, object]:
        return {
            "clone_method": self.clone_method,
            "copy_sidecars": False,
            "destination_distinct_inode": True,
            "source_case_id": source_case_id,
            "source_bytes": self.source_bytes,
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
    if not stat.S_ISREG(source_stat.st_mode):
        raise PreparedArtifactError("prepared source must be a regular file")
    _validate_source_sidecars(source, retained)
    if destination.exists() or destination.is_symlink():
        raise PreparedArtifactError("prepared destination must not already exist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.resolve(strict=False) == source:
        raise PreparedArtifactError("prepared destination must differ from source")

    try:
        method = _clone_file(source, destination)
        destination_stat = destination.stat()
        if not stat.S_ISREG(destination_stat.st_mode):
            raise PreparedArtifactError("prepared destination is not a regular file")
        if destination_stat.st_ino == source_stat.st_ino:
            raise PreparedArtifactError("prepared destination must have a distinct inode")
        if destination_stat.st_size != source_stat.st_size:
            raise PreparedArtifactError("prepared destination size differs from source")
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
        PreparationEvidence(clone_method=method, source_bytes=source_stat.st_size),
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
    if platform.system() != "Darwin":
        shutil.copyfile(source, destination)
        return "copyfile"
    try:
        _darwin_clonefile(source, destination)
        return "clonefile"
    except OSError as error:
        if error.errno not in {errno.ENOTSUP, errno.EXDEV}:
            raise PreparedArtifactError("native clonefile failed") from error
    shutil.copyfile(source, destination)
    return "copyfile_fallback"


def _darwin_clonefile(source: Path, destination: Path) -> None:
    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    clonefile = library.clonefile
    clonefile.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int)
    clonefile.restype = ctypes.c_int
    if clonefile(os.fsencode(source), os.fsencode(destination), 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number), str(source), str(destination))
