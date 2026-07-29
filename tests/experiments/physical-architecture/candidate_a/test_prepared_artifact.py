from __future__ import annotations

import errno
import importlib
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXPERIMENT_ROOT = _REPO_ROOT / "experiments" / "physical-architecture"
sys.path.insert(0, str(_EXPERIMENT_ROOT))

ingest = importlib.import_module("candidate_a.ingest")
prepared_artifact = importlib.import_module("candidate_a.prepared_artifact")


def _artifact(path: Path) -> Any:
    path.write_bytes(b"prepared database")
    return ingest.BuildArtifact(
        path=path,
        publication_id="publication:candidate-a:prepared",
        observed_through_us=123,
        stats=ingest.IngestStats(
            occurrence_rows=7,
            facts_inserted=99,
            source_files_parsed=4,
            writer_transactions=5,
        ),
    )


def test_native_clone_is_isolated_and_has_fresh_ordinary_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "scale" / "publication.sqlite"
    source_path.parent.mkdir(parents=True)
    source = _artifact(source_path)
    monkeypatch.setattr(prepared_artifact.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(prepared_artifact, "_darwin_clonefile", shutil.copyfile)

    cloned, evidence = prepared_artifact.clone_prepared_artifact(
        source,
        retained_root=source.path.parent,
        destination=tmp_path / "ordinary" / "ordinary.sqlite",
    )

    assert evidence.clone_method == "clonefile"
    assert cloned.path.read_bytes() == source.path.read_bytes()
    assert cloned.path.stat().st_ino != source.path.stat().st_ino
    assert cloned.publication_id == source.publication_id
    assert cloned.observed_through_us == source.observed_through_us
    assert cloned.stats.occurrence_rows == 7
    assert cloned.stats.source_files_parsed == 0
    assert cloned.stats.facts_inserted == 0
    assert cloned.stats.writer_transactions == 0
    cloned.path.write_bytes(b"ordinary mutation")
    assert source.path.read_bytes() == b"prepared database"


@pytest.mark.parametrize("error_number", [errno.ENOTSUP, errno.EXDEV])
def test_native_clone_supported_fallbacks_copyfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_number: int,
) -> None:
    source_path = tmp_path / "scale" / "publication.sqlite"
    source_path.parent.mkdir(parents=True)
    source = _artifact(source_path)
    monkeypatch.setattr(prepared_artifact.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        prepared_artifact,
        "_darwin_clonefile",
        lambda *_: (_ for _ in ()).throw(OSError(error_number, "unsupported")),
    )

    cloned, evidence = prepared_artifact.clone_prepared_artifact(
        source,
        retained_root=source.path.parent,
        destination=tmp_path / "ordinary.sqlite",
    )

    assert evidence.clone_method == "copyfile_fallback"
    assert cloned.path.read_bytes() == source.path.read_bytes()


def test_native_clone_other_errors_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "scale" / "publication.sqlite"
    source_path.parent.mkdir(parents=True)
    source = _artifact(source_path)
    destination = tmp_path / "ordinary.sqlite"
    monkeypatch.setattr(prepared_artifact.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        prepared_artifact,
        "_darwin_clonefile",
        lambda *_: (_ for _ in ()).throw(OSError(errno.EIO, "io error")),
    )

    with pytest.raises(prepared_artifact.PreparedArtifactError, match="native clonefile failed"):
        prepared_artifact.clone_prepared_artifact(
            source,
            retained_root=source.path.parent,
            destination=destination,
        )
    assert not destination.exists()


def test_copy_error_removes_a_partial_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_path = tmp_path / "scale" / "publication.sqlite"
    source_path.parent.mkdir(parents=True)
    source = _artifact(source_path)
    destination = tmp_path / "ordinary.sqlite"

    def partial_copy(*_: object) -> None:
        destination.write_bytes(b"partial")
        raise OSError(errno.EIO, "io error")

    monkeypatch.setattr(prepared_artifact.platform, "system", lambda: "Linux")
    monkeypatch.setattr(prepared_artifact.shutil, "copyfile", partial_copy)

    with pytest.raises(OSError, match="io error"):
        prepared_artifact.clone_prepared_artifact(
            source,
            retained_root=source.path.parent,
            destination=destination,
        )
    assert not destination.exists()


@pytest.mark.parametrize("sidecar", ["publication.sqlite-journal", "publication.sqlite-wal"])
def test_journal_or_nonempty_wal_rejects_preparation(tmp_path: Path, sidecar: str) -> None:
    source_path = tmp_path / "scale" / "publication.sqlite"
    source_path.parent.mkdir(parents=True)
    source = _artifact(source_path)
    (source.path.parent / sidecar).write_bytes(b"unsafe")

    with pytest.raises(prepared_artifact.PreparedArtifactError):
        prepared_artifact.clone_prepared_artifact(
            source,
            retained_root=source.path.parent,
            destination=tmp_path / "ordinary.sqlite",
        )


def test_lease_rejects_preparation_without_copying_sidecars(tmp_path: Path) -> None:
    source_path = tmp_path / "scale" / "publication.sqlite"
    source_path.parent.mkdir(parents=True)
    source = _artifact(source_path)
    (source.path.parent / "publication-lease.json").write_text("{}", encoding="utf-8")

    with pytest.raises(prepared_artifact.PreparedArtifactError, match="active publication lease"):
        prepared_artifact.clone_prepared_artifact(
            source,
            retained_root=source.path.parent,
            destination=tmp_path / "ordinary.sqlite",
        )
