from __future__ import annotations

import io
import json
import tarfile
import zipfile
from argparse import Namespace
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.release.artifact_manifest import (
    ManifestError,
    canonical_json_bytes,
    create_manifest,
    load_manifest,
    main,
    verify_manifest,
)
from codex_usage_tracker.release.artifact_normalization import (
    ArtifactNormalizationError,
    normalize_sdist_directory,
)
from codex_usage_tracker.release.artifact_normalization import (
    main as normalization_main,
)
from scripts.smoke_installed_package import _resolve_install_target
from tests.release.conftest import ReleaseFixture

SOURCE_SHA = "a" * 40


def _write_sdist(path: Path, *, mtime: int) -> None:
    with tarfile.open(path, mode="w:gz") as archive:
        for name, payload in (
            ("package/", None),
            ("package/PKG-INFO", b"Version: 0.23.0\n"),
        ):
            member = tarfile.TarInfo(name)
            member.mtime = mtime
            member.uid = mtime
            member.gid = mtime
            if payload is None:
                member.type = tarfile.DIRTYPE
                archive.addfile(member)
            else:
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))


def test_sdist_normalization_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    first_sdist = first / "codex_usage_tracking-0.23.0.tar.gz"
    second_sdist = second / "codex_usage_tracking-0.23.0.tar.gz"
    _write_sdist(first_sdist, mtime=1)
    _write_sdist(second_sdist, mtime=2)

    normalize_sdist_directory(first, epoch=123456)
    normalize_sdist_directory(second, epoch=123456)

    assert first_sdist.read_bytes() == second_sdist.read_bytes()
    with tarfile.open(first_sdist, mode="r:gz") as archive:
        assert all(
            (member.mtime, member.uid, member.gid, member.uname, member.gname)
            == (123456, 0, 0, "", "")
            for member in archive.getmembers()
        )


def test_sdist_normalization_cli_fails_closed(tmp_path: Path) -> None:
    assert normalization_main(["--source", str(tmp_path), "--epoch", "1"]) == 1
    with pytest.raises(ArtifactNormalizationError, match="must not be negative"):
        normalize_sdist_directory(tmp_path, epoch=-1)


def _create(fixture: ReleaseFixture) -> dict[str, Any]:
    return create_manifest(
        fixture.dist_dir,
        fixture.manifest_path,
        expected_sha=SOURCE_SHA,
        expected_version=fixture.version,
        repository_root=fixture.repo_root,
    )


def _verify(fixture: ReleaseFixture, *, expected_sha: str = SOURCE_SHA) -> dict[str, Any]:
    return verify_manifest(
        fixture.dist_dir,
        fixture.manifest_path,
        expected_sha=expected_sha,
        expected_version=fixture.version,
        repository_root=fixture.repo_root,
    )


def test_manifest_is_canonical_and_deterministic(release_fixture: ReleaseFixture) -> None:
    first = _create(release_fixture)
    first_bytes = release_fixture.manifest_path.read_bytes()

    second = _create(release_fixture)

    assert first == second
    assert release_fixture.manifest_path.read_bytes() == first_bytes
    assert first["source"]["git_sha"] == SOURCE_SHA
    assert [item["path"] for item in first["artifacts"]] == sorted(
        item["path"] for item in first["artifacts"]
    )
    assert _verify(release_fixture) == first


def test_verify_rejects_noncanonical_manifest(release_fixture: ReleaseFixture) -> None:
    manifest = _create(release_fixture)
    release_fixture.manifest_path.write_text(
        json.dumps(manifest, indent=4) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="canonical"):
        _verify(release_fixture)


def test_verify_rejects_unsafe_artifact_path(release_fixture: ReleaseFixture) -> None:
    manifest = _create(release_fixture)
    manifest["artifacts"][0]["path"] = "../unexpected.whl"
    release_fixture.manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ManifestError, match="safe basenames"):
        _verify(release_fixture)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda payload: payload.update(schema="unknown"), "unsupported manifest schema"),
        (lambda payload: payload.update(distribution="other"), "distribution name"),
        (lambda payload: payload.update(version=""), "version must"),
        (lambda payload: payload.update(source={}), "must contain a Git SHA"),
        (lambda payload: payload.update(contract_inventory=[]), "inventory must be an object"),
        (
            lambda payload: payload["contract_inventory"].update(json_schemas={}),
            "invalid json_schemas",
        ),
        (lambda payload: payload.update(artifacts=[]), "exactly one wheel"),
        (
            lambda payload: payload["artifacts"][0].update(sha256="bad"),
            "invalid SHA-256",
        ),
        (
            lambda payload: payload["artifacts"][0].update(size=-1),
            "invalid size",
        ),
        (
            lambda payload: payload["artifacts"][1].update(path=payload["artifacts"][0]["path"]),
            "paths must be unique",
        ),
        (
            lambda payload: payload["artifacts"][0].update(path="unexpected.whl"),
            "names do not match",
        ),
    ],
    ids=[
        "schema",
        "distribution",
        "version",
        "source",
        "inventory-root",
        "inventory-field",
        "artifact-count",
        "artifact-hash",
        "artifact-size",
        "duplicate-name",
        "unexpected-name",
    ],
)
def test_load_rejects_invalid_manifest_shape(
    release_fixture: ReleaseFixture,
    mutation: Callable[[dict[str, Any]], None],
    expected: str,
) -> None:
    manifest = deepcopy(_create(release_fixture))
    mutation(manifest)
    release_fixture.manifest_path.write_bytes(canonical_json_bytes(manifest))

    with pytest.raises(ManifestError, match=expected):
        load_manifest(release_fixture.manifest_path)


@pytest.mark.parametrize(
    "payload",
    [b"not-json\n", canonical_json_bytes([])],
    ids=["invalid-json", "non-object"],
)
def test_load_rejects_invalid_json_root(
    release_fixture: ReleaseFixture,
    payload: bytes,
) -> None:
    release_fixture.manifest_path.write_bytes(payload)

    with pytest.raises(ManifestError):
        load_manifest(release_fixture.manifest_path)


def test_verify_rejects_missing_artifact(release_fixture: ReleaseFixture) -> None:
    _create(release_fixture)
    release_fixture.wheel_path.unlink()

    with pytest.raises(ManifestError, match="distribution"):
        _verify(release_fixture)


def test_verify_rejects_altered_artifact(release_fixture: ReleaseFixture) -> None:
    _create(release_fixture)
    with zipfile.ZipFile(release_fixture.wheel_path, "a") as wheel:
        wheel.writestr("unexpected.txt", b"altered after manifest creation\n")

    with pytest.raises(ManifestError, match="manifest does not match"):
        _verify(release_fixture)


def test_verify_rejects_wrong_source_sha(release_fixture: ReleaseFixture) -> None:
    _create(release_fixture)

    with pytest.raises(ManifestError, match="source SHA"):
        _verify(release_fixture, expected_sha="b" * 40)


def test_create_rejects_wrong_version(release_fixture: ReleaseFixture) -> None:
    with pytest.raises(ManifestError, match="expected version"):
        create_manifest(
            release_fixture.dist_dir,
            release_fixture.manifest_path,
            expected_sha=SOURCE_SHA,
            expected_version="0.24.0",
            repository_root=release_fixture.repo_root,
        )


def test_create_rejects_multiple_versions(release_fixture: ReleaseFixture) -> None:
    release_fixture.write_distributions(version="0.24.0")

    with pytest.raises(ManifestError, match="one distribution version"):
        _create(release_fixture)


def test_create_rejects_stale_frontend_asset(release_fixture: ReleaseFixture) -> None:
    release_fixture.write_distributions(wheel_asset=b"console.log('stale');\n")

    with pytest.raises(ManifestError, match="stale Evidence Console asset"):
        _create(release_fixture)


@pytest.mark.parametrize("archive", ["wheel", "sdist"])
def test_create_rejects_unreadable_distribution(
    release_fixture: ReleaseFixture,
    archive: str,
) -> None:
    path = release_fixture.wheel_path if archive == "wheel" else release_fixture.sdist_path
    path.write_bytes(b"not an archive")

    with pytest.raises(ManifestError, match="could not read"):
        _create(release_fixture)


def test_create_rejects_missing_console_source(release_fixture: ReleaseFixture) -> None:
    empty_repo = release_fixture.root / "empty-repo"
    (empty_repo / "src" / "codex_usage_tracker").mkdir(parents=True)

    with pytest.raises(ManifestError, match="asset directory"):
        create_manifest(
            release_fixture.dist_dir,
            release_fixture.manifest_path,
            expected_sha=SOURCE_SHA,
            expected_version=release_fixture.version,
            repository_root=empty_repo,
        )


def test_create_rejects_duplicate_wheel(release_fixture: ReleaseFixture) -> None:
    duplicate = release_fixture.dist_dir / (
        f"codex_usage_tracking-{release_fixture.version}-py2-none-any.whl"
    )
    duplicate.write_bytes(release_fixture.wheel_path.read_bytes())

    with pytest.raises(ManifestError, match="exactly one wheel"):
        _create(release_fixture)


def test_verify_rejects_missing_manifest_file(release_fixture: ReleaseFixture) -> None:
    missing = Path(release_fixture.root / "missing.json")

    with pytest.raises(ManifestError, match="manifest file"):
        verify_manifest(
            release_fixture.dist_dir,
            missing,
            expected_sha=SOURCE_SHA,
            expected_version=release_fixture.version,
            repository_root=release_fixture.repo_root,
        )


def test_installed_smoke_selects_exact_existing_wheel(
    release_fixture: ReleaseFixture,
) -> None:
    args = Namespace(
        artifact_dir=release_fixture.dist_dir,
        from_pypi=False,
        version=release_fixture.version,
    )

    assert _resolve_install_target(args, release_fixture.root) == str(
        release_fixture.wheel_path.resolve()
    )


def test_installed_smoke_rejects_ambiguous_artifact_directory(
    release_fixture: ReleaseFixture,
) -> None:
    release_fixture.write_distributions(version="0.24.0")
    args = Namespace(
        artifact_dir=release_fixture.dist_dir,
        from_pypi=False,
        version=None,
    )

    with pytest.raises(FileNotFoundError, match="exactly one matching wheel"):
        _resolve_install_target(args, release_fixture.root)


def test_manifest_cli_create_verify_and_digest(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (release_fixture.repo_root / "pyproject.toml").write_text(
        f'[project]\nname = "codex-usage-tracking"\nversion = "{release_fixture.version}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(release_fixture.repo_root)

    assert (
        main(
            [
                "create",
                "--source",
                str(release_fixture.dist_dir),
                "--output",
                str(release_fixture.manifest_path),
                "--expected-sha",
                SOURCE_SHA,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify",
                "--source",
                str(release_fixture.dist_dir),
                "--manifest",
                str(release_fixture.manifest_path),
                "--expected-sha",
                SOURCE_SHA,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "digest",
                "--manifest",
                str(release_fixture.manifest_path),
            ]
        )
        == 0
    )
    assert "created" in capsys.readouterr().out


def test_manifest_cli_reports_contract_error(release_fixture: ReleaseFixture) -> None:
    assert (
        main(
            [
                "verify",
                "--source",
                str(release_fixture.dist_dir),
                "--manifest",
                str(release_fixture.root / "missing.json"),
                "--expected-sha",
                SOURCE_SHA,
                "--expected-version",
                release_fixture.version,
            ]
        )
        == 1
    )
