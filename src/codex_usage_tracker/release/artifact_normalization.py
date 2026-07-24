"""Normalize the source distribution created by one release build."""

from __future__ import annotations

import argparse
import copy
import gzip
import io
import tarfile
from pathlib import Path


class ArtifactNormalizationError(ValueError):
    """Raised when a built source distribution cannot be normalized safely."""


def normalize_sdist_directory(source: Path, *, epoch: int) -> Path:
    """Normalize the sole sdist in a directory to a reproducible byte stream."""
    if epoch < 0:
        raise ArtifactNormalizationError("normalization epoch must not be negative")
    if not source.is_dir():
        raise ArtifactNormalizationError(f"distribution directory does not exist: {source}")
    candidates = sorted(source.glob("codex_usage_tracking-*.tar.gz"))
    if len(candidates) != 1:
        raise ArtifactNormalizationError(
            "expected exactly one source distribution to normalize; "
            f"found {[path.name for path in candidates]}"
        )
    _normalize_sdist(candidates[0], epoch=epoch)
    return candidates[0]


def _normalize_sdist(path: Path, *, epoch: int) -> None:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            entries = [
                (_normalized_member(member, epoch=epoch), _member_payload(archive, member))
                for member in sorted(archive.getmembers(), key=lambda item: item.name)
            ]
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactNormalizationError(
            f"could not read source distribution: {path.name}"
        ) from exc

    temporary = path.with_name(f".{path.name}.normalized")
    try:
        with (
            temporary.open("wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed,
            tarfile.open(
                fileobj=compressed,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive,
        ):
            for member, payload in entries:
                archive.addfile(member, payload)
        temporary.replace(path)
    except OSError as exc:
        raise ArtifactNormalizationError(
            f"could not write normalized source distribution: {path.name}"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _normalized_member(member: tarfile.TarInfo, *, epoch: int) -> tarfile.TarInfo:
    normalized = copy.copy(member)
    normalized.mtime = epoch
    normalized.uid = 0
    normalized.gid = 0
    normalized.uname = ""
    normalized.gname = ""
    normalized.pax_headers = {}
    return normalized


def _member_payload(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
) -> io.BytesIO | None:
    if not member.isfile():
        return None
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ArtifactNormalizationError(
            f"source distribution member has no payload: {member.name}"
        )
    return io.BytesIO(extracted.read())


def main(argv: list[str] | None = None) -> int:
    """Run shell-friendly source-distribution normalization."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--epoch", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        path = normalize_sdist_directory(args.source, epoch=args.epoch)
    except ArtifactNormalizationError as exc:
        print(f"release artifact normalization error: {exc}")
        return 1
    print(f"normalized {path.name} at epoch {args.epoch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
