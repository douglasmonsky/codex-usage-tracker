"""Create and verify canonical manifests for one wheel/sdist release build."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import zipfile
from email.parser import Parser
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA = "codex-usage-tracker.release-artifact-manifest.v1"
DISTRIBUTION_NAME = "codex-usage-tracking"
DIST_FILE_STEM = "codex_usage_tracking"
IMPORT_PACKAGE = "codex_usage_tracker"
_SOURCE_SHA = re.compile(r"[0-9a-f]{40}\Z")
_WHEEL_NAME = re.compile(
    rf"{DIST_FILE_STEM}-(?P<version>[^-]+)-[^/]+\.whl\Z",
)
_SDIST_NAME = re.compile(rf"{DIST_FILE_STEM}-(?P<version>.+)\.tar\.gz\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ManifestError(ValueError):
    """Raised when release files cannot prove one unchanged build."""


def canonical_json_bytes(payload: object) -> bytes:
    """Serialize a release record in its only accepted byte representation."""
    return (
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_sha256(path: Path) -> str:
    """Return the digest of a canonical manifest file."""
    return sha256_file(path)


def create_manifest(
    source: Path,
    output: Path,
    *,
    expected_sha: str,
    expected_version: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Inspect one dist directory and write its canonical release manifest."""
    repo_root = repository_root or _default_repository_root()
    version = expected_version or _project_version(repo_root)
    manifest = inspect_artifacts(
        source,
        expected_sha=expected_sha,
        expected_version=version,
        repository_root=repo_root,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(manifest))
    return manifest


def inspect_artifacts(
    source: Path,
    *,
    expected_sha: str,
    expected_version: str,
    repository_root: Path,
) -> dict[str, Any]:
    """Return the deterministic manifest payload without writing a file."""
    return _build_manifest(
        source,
        expected_sha=expected_sha,
        expected_version=expected_version,
        repository_root=repository_root,
    )


def verify_manifest(
    source: Path,
    manifest_path: Path,
    *,
    expected_sha: str,
    expected_version: str | None = None,
    repository_root: Path | None = None,
) -> dict[str, Any]:
    """Verify manifest canonicalization, identity, contents, and source assets."""
    if not manifest_path.is_file():
        raise ManifestError(f"manifest file does not exist: {manifest_path}")
    raw = manifest_path.read_bytes()
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest file is not valid UTF-8 JSON: {manifest_path}") from exc
    if not isinstance(manifest, dict):
        raise ManifestError("manifest root must be an object")
    if raw != canonical_json_bytes(manifest):
        raise ManifestError("manifest is not in canonical JSON form")
    _validate_manifest_payload(manifest)
    _validate_source_sha(expected_sha)
    source_record = manifest.get("source")
    if not isinstance(source_record, dict) or source_record.get("git_sha") != expected_sha:
        raise ManifestError("manifest source SHA does not match the expected Git commit")

    repo_root = repository_root or _default_repository_root()
    version = expected_version or _project_version(repo_root)
    current = inspect_artifacts(
        source,
        expected_sha=expected_sha,
        expected_version=version,
        repository_root=repo_root,
    )
    if manifest != current:
        raise ManifestError(
            "release artifact manifest does not match the current distribution files"
        )
    return manifest


def load_manifest(path: Path) -> dict[str, Any]:
    """Load a canonical manifest without re-reading its distribution directory."""
    if not path.is_file():
        raise ManifestError(f"manifest file does not exist: {path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest file is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ManifestError("manifest root must be an object")
    if raw != canonical_json_bytes(payload):
        raise ManifestError("manifest is not in canonical JSON form")
    _validate_manifest_payload(payload)
    return payload


def _build_manifest(
    source: Path,
    *,
    expected_sha: str,
    expected_version: str,
    repository_root: Path,
) -> dict[str, Any]:
    _validate_source_sha(expected_sha)
    wheel, sdist, version = _distribution_pair(source, expected_version)
    wheel_members = _wheel_members(wheel)
    sdist_members = _sdist_members(sdist)
    _verify_metadata_version(wheel_members, ".dist-info/METADATA", version, wheel.name)
    _verify_metadata_version(sdist_members, "/PKG-INFO", version, sdist.name)
    bundles = _evidence_console_bundles(repository_root, wheel_members, sdist_members)
    artifacts = [
        {"path": path.name, "sha256": sha256_file(path), "size": path.stat().st_size}
        for path in sorted((wheel, sdist), key=lambda item: item.name)
    ]
    return {
        "artifacts": artifacts,
        "contract_inventory": _contract_inventory(bundles),
        "distribution": DISTRIBUTION_NAME,
        "schema": MANIFEST_SCHEMA,
        "source": {"git_sha": expected_sha},
        "version": version,
    }


def _distribution_pair(source: Path, expected_version: str) -> tuple[Path, Path, str]:
    if not source.is_dir():
        raise ManifestError(f"distribution source directory does not exist: {source}")
    wheels: list[tuple[Path, str]] = []
    sdists: list[tuple[Path, str]] = []
    for path in sorted(source.iterdir()):
        wheel_match = _WHEEL_NAME.fullmatch(path.name)
        sdist_match = _SDIST_NAME.fullmatch(path.name)
        if wheel_match:
            wheels.append((path, wheel_match.group("version")))
        elif sdist_match:
            sdists.append((path, sdist_match.group("version")))
    versions = {version for _, version in (*wheels, *sdists)}
    if len(versions) != 1:
        raise ManifestError(
            "expected exactly one distribution version across one wheel and one sdist; "
            f"found {sorted(versions)}"
        )
    version = versions.pop()
    if len(wheels) != 1 or len(sdists) != 1:
        raise ManifestError(
            "expected exactly one wheel and one source distribution; "
            f"found wheels={len(wheels)}, sdists={len(sdists)}"
        )
    if version != expected_version:
        raise ManifestError(
            f"distribution expected version {expected_version!r}, found {version!r}"
        )
    return wheels[0][0], sdists[0][0], version


def _wheel_members(path: Path) -> dict[str, bytes]:
    try:
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ManifestError(f"could not read wheel distribution: {path.name}") from exc


def _sdist_members(path: Path) -> dict[str, bytes]:
    try:
        with tarfile.open(path) as archive:
            members: dict[str, bytes] = {}
            for member in archive.getmembers():
                if not member.isfile():
                    continue
                extracted = archive.extractfile(member)
                if extracted is not None:
                    members[member.name] = extracted.read()
            return members
    except (OSError, tarfile.TarError) as exc:
        raise ManifestError(f"could not read source distribution: {path.name}") from exc


def _verify_metadata_version(
    members: dict[str, bytes],
    suffix: str,
    expected_version: str,
    archive_name: str,
) -> None:
    matches = [
        payload
        for name, payload in members.items()
        if name.endswith(suffix) and (suffix != "/PKG-INFO" or name.count("/") == 1)
    ]
    if len(matches) != 1:
        raise ManifestError(f"{archive_name} must contain exactly one {suffix}")
    metadata = Parser().parsestr(matches[0].decode("utf-8"))
    if metadata.get("Version") != expected_version:
        raise ManifestError(
            f"{archive_name} metadata version {metadata.get('Version')!r} "
            f"does not match expected version {expected_version!r}"
        )


def _evidence_console_bundles(
    repository_root: Path,
    wheel_members: dict[str, bytes],
    sdist_members: dict[str, bytes],
) -> list[dict[str, object]]:
    package_root = _package_root(repository_root)
    console_root = package_root / "plugin_data" / "dashboard" / "react"
    if not console_root.is_dir():
        raise ManifestError(f"Evidence Console asset directory does not exist: {console_root}")
    bundles: list[dict[str, object]] = []
    for source_path in sorted(path for path in console_root.rglob("*") if path.is_file()):
        relative = source_path.relative_to(package_root).as_posix()
        expected = source_path.read_bytes()
        wheel_name = f"{IMPORT_PACKAGE}/{relative}"
        sdist_suffix = f"/src/{IMPORT_PACKAGE}/{relative}"
        wheel_payload = wheel_members.get(wheel_name)
        sdist_matches = [
            payload for name, payload in sdist_members.items() if name.endswith(sdist_suffix)
        ]
        if wheel_payload != expected or sdist_matches != [expected]:
            raise ManifestError(f"stale Evidence Console asset in distributions: {relative}")
        bundles.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(expected).hexdigest(),
                "size": len(expected),
            }
        )
    return bundles


def _contract_inventory(bundles: list[dict[str, object]]) -> dict[str, object]:
    from codex_usage_tracker.core.json_contracts import known_json_schemas
    from codex_usage_tracker.interfaces.mcp.profiles import tools_for_profile
    from codex_usage_tracker.store.schema import SCHEMA_VERSION

    profiles = {
        profile: [spec.name for spec in tools_for_profile(profile)]
        for profile in ("core", "full", "developer")
    }
    return {
        "database_schema_version": SCHEMA_VERSION,
        "evidence_console_bundles": bundles,
        "json_schemas": list(known_json_schemas()),
        "mcp_tools": profiles,
    }


def _package_root(repository_root: Path) -> Path:
    source_root = repository_root / "src" / IMPORT_PACKAGE
    if source_root.is_dir():
        return source_root
    return Path(__file__).resolve().parents[1]


def _project_version(repository_root: Path) -> str:
    pyproject = repository_root / "pyproject.toml"
    if pyproject.is_file():
        project_section = re.search(
            r"(?ms)^\[project\]\s*$.*?^version\s*=\s*[\"'](?P<version>[^\"']+)[\"']",
            pyproject.read_text(encoding="utf-8"),
        )
        if project_section is None:
            raise ManifestError("pyproject.toml [project] is missing a string version")
        return project_section.group("version")
    try:
        return installed_version(DISTRIBUTION_NAME)
    except PackageNotFoundError as exc:
        raise ManifestError("could not determine the expected distribution version") from exc


def _default_repository_root() -> Path:
    current = Path.cwd()
    if (current / "pyproject.toml").is_file() and (current / "src" / IMPORT_PACKAGE).is_dir():
        return current
    return Path(__file__).resolve().parents[3]


def _validate_source_sha(value: str) -> None:
    if not _SOURCE_SHA.fullmatch(value):
        raise ManifestError("expected source SHA must be a lowercase 40-character Git commit")


def _validate_manifest_payload(payload: dict[str, Any]) -> None:
    if payload.get("schema") != MANIFEST_SCHEMA:
        raise ManifestError(f"unsupported manifest schema: {payload.get('schema')!r}")
    if payload.get("distribution") != DISTRIBUTION_NAME:
        raise ManifestError("manifest distribution name does not match")
    version = _manifest_version(payload.get("version"))
    _validate_manifest_source(payload.get("source"))
    _validate_contract_inventory(payload.get("contract_inventory"))
    names = _validate_artifact_entries(payload.get("artifacts"))
    _validate_artifact_names(names, version)


def _manifest_version(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ManifestError("manifest version must be a non-empty string")
    return value


def _validate_manifest_source(value: object) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("git_sha"), str):
        raise ManifestError("manifest source must contain a Git SHA")
    _validate_source_sha(value["git_sha"])


def _validate_contract_inventory(value: object) -> None:
    if not isinstance(value, dict):
        raise ManifestError("manifest contract inventory must be an object")
    required_types = (
        ("database_schema_version", int),
        ("evidence_console_bundles", list),
        ("json_schemas", list),
        ("mcp_tools", dict),
    )
    invalid = [key for key, expected in required_types if not isinstance(value.get(key), expected)]
    if invalid:
        raise ManifestError(f"manifest contract inventory has invalid {invalid[0]}")


def _validate_artifact_entries(value: object) -> list[str]:
    if not isinstance(value, list) or len(value) != 2:
        raise ManifestError("manifest must contain exactly one wheel and one sdist")
    names = [_validate_artifact_entry(artifact) for artifact in value]
    if len(set(names)) != len(names):
        raise ManifestError("manifest artifact paths must be unique")
    return names


def _validate_artifact_entry(value: object) -> str:
    if not isinstance(value, dict):
        raise ManifestError("manifest artifact entry must be an object")
    name = value.get("path")
    digest = value.get("sha256")
    size = value.get("size")
    if not isinstance(name, str) or Path(name).name != name:
        raise ManifestError("manifest artifact paths must be safe basenames")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise ManifestError(f"manifest artifact has invalid SHA-256: {name}")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ManifestError(f"manifest artifact has invalid size: {name}")
    return name


def _validate_artifact_names(names: list[str], version: str) -> None:
    if not _has_expected_wheel(names, version) or not _has_expected_sdist(names, version):
        raise ManifestError("manifest artifact names do not match the manifest version")


def _has_expected_wheel(names: list[str], version: str) -> bool:
    matches = [match for name in names if (match := _WHEEL_NAME.fullmatch(name)) is not None]
    return len(matches) == 1 and matches[0].group("version") == version


def _has_expected_sdist(names: list[str], version: str) -> bool:
    matches = [match for name in names if (match := _SDIST_NAME.fullmatch(name)) is not None]
    return len(matches) == 1 and matches[0].group("version") == version


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("create", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--source", type=Path, required=True)
        subparser.add_argument("--expected-sha", required=True)
        subparser.add_argument("--expected-version")
        if command == "create":
            subparser.add_argument("--output", type=Path, required=True)
        else:
            subparser.add_argument("--manifest", type=Path, required=True)
    digest = subparsers.add_parser("digest")
    digest.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run shell-friendly manifest creation, verification, or digest output."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            manifest = create_manifest(
                args.source,
                args.output,
                expected_sha=args.expected_sha,
                expected_version=args.expected_version,
            )
            print(f"created {args.output} for {manifest['version']}")
        elif args.command == "verify":
            manifest = verify_manifest(
                args.source,
                args.manifest,
                expected_sha=args.expected_sha,
                expected_version=args.expected_version,
            )
            print(f"verified {len(manifest['artifacts'])} release artifacts")
        else:
            load_manifest(args.manifest)
            print(manifest_sha256(args.manifest))
    except ManifestError as exc:
        print(f"release manifest error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
