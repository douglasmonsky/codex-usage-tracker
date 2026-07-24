"""Qualify release bytes from package indexes and record promotion evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from codex_usage_tracker.release.artifact_manifest import (
    ManifestError,
    canonical_json_bytes,
    load_manifest,
    manifest_sha256,
)

PROMOTION_SCHEMA = "codex-usage-tracker.release-promotion-evidence.v1"


class PromotionError(ValueError):
    """Raised when published artifacts are not safe to promote."""


def create_promotion_evidence(
    manifest_path: Path,
    output: Path,
    *,
    run_id: str,
    run_attempt: str,
    index_url: str,
    installed_smoke: str,
) -> dict[str, Any]:
    """Write canonical evidence for a successful TestPyPI qualification."""
    manifest = _load_release_manifest(manifest_path)
    if installed_smoke != "passed":
        raise PromotionError("installed smoke must be recorded as passed")
    if not run_id.isdigit() or not run_attempt.isdigit():
        raise PromotionError("GitHub Actions run id and attempt must be numeric")
    _validate_https_url(index_url, label="package index")
    evidence = {
        "artifacts": manifest["artifacts"],
        "contract_inventory": manifest["contract_inventory"],
        "github_actions": {"run_attempt": run_attempt, "run_id": run_id},
        "manifest_sha256": manifest_sha256(manifest_path),
        "qualification": {
            "index_url": index_url,
            "installed_smoke": installed_smoke,
        },
        "schema": PROMOTION_SCHEMA,
        "source_sha": manifest["source"]["git_sha"],
        "version": manifest["version"],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(evidence))
    return evidence


def verify_promotion_evidence(
    manifest_path: Path,
    evidence_path: Path,
    *,
    expected_sha: str,
    expected_run_id: str | None = None,
) -> dict[str, Any]:
    """Verify qualification evidence remains bound to one canonical manifest."""
    manifest = _load_release_manifest(manifest_path)
    evidence = _load_canonical_evidence(evidence_path)
    _verify_evidence_identity(evidence, manifest, manifest_path, expected_sha)
    _verify_run_identity(evidence, expected_run_id)
    _verify_qualification(evidence)
    _verify_manifest_fields(evidence, manifest)
    return evidence


def _verify_evidence_identity(
    evidence: dict[str, Any],
    manifest: dict[str, Any],
    manifest_path: Path,
    expected_sha: str,
) -> None:
    if evidence.get("manifest_sha256") != manifest_sha256(manifest_path):
        raise PromotionError("promotion evidence manifest SHA-256 does not match")
    if evidence.get("source_sha") != expected_sha:
        raise PromotionError("promotion evidence source SHA does not match")
    if manifest["source"]["git_sha"] != expected_sha:
        raise PromotionError("release manifest source SHA does not match")


def _verify_run_identity(evidence: dict[str, Any], expected_run_id: str | None) -> None:
    if expected_run_id is None:
        return
    actions = evidence.get("github_actions")
    if not isinstance(actions, dict) or actions.get("run_id") != expected_run_id:
        raise PromotionError("promotion evidence GitHub Actions run id does not match")


def _verify_qualification(evidence: dict[str, Any]) -> None:
    qualification = evidence.get("qualification")
    if not isinstance(qualification, dict) or qualification.get("installed_smoke") != "passed":
        raise PromotionError("promotion evidence does not record a passed installed smoke")


def _verify_manifest_fields(
    evidence: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    for key in ("version", "artifacts", "contract_inventory"):
        if evidence.get(key) != manifest.get(key):
            raise PromotionError(f"promotion evidence {key} does not match the manifest")


def validate_index_payload(
    manifest: dict[str, Any],
    payload: dict[str, Any],
) -> list[str]:
    """Return mismatches between an index version payload and the manifest."""
    failures = _index_version_failures(manifest, payload)
    urls = payload.get("urls")
    if not isinstance(urls, list):
        return [*failures, "index payload urls must be a list"]
    published, entry_failures = _published_artifacts(urls)
    failures.extend(entry_failures)
    expected_names = {artifact["path"] for artifact in manifest["artifacts"]}
    unexpected = sorted(set(published).difference(expected_names))
    if unexpected:
        failures.append(f"index has unexpected release artifacts: {unexpected}")
    for artifact in manifest["artifacts"]:
        failures.extend(_artifact_index_failures(artifact, published))
    return failures


def _index_version_failures(
    manifest: dict[str, Any],
    payload: dict[str, Any],
) -> list[str]:
    info = payload.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    if version != manifest.get("version"):
        return [
            f"index version {version!r} does not match manifest version {manifest.get('version')!r}"
        ]
    return []


def _published_artifacts(
    urls: list[object],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    published: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for item in urls:
        if not isinstance(item, dict):
            failures.append("index artifact entries must be objects with string filenames")
            continue
        filename = item.get("filename")
        if not isinstance(filename, str):
            failures.append("index artifact entries must be objects with string filenames")
        elif filename in published:
            failures.append(f"index has duplicate release artifact: {filename}")
        else:
            published[filename] = item
    return published, failures


def _artifact_index_failures(
    artifact: dict[str, Any],
    published: dict[str, dict[str, Any]],
) -> list[str]:
    filename = artifact["path"]
    item = published.get(filename)
    if item is None:
        return [f"index is missing release artifact: {filename}"]
    failures: list[str] = []
    digests = item.get("digests")
    sha256 = digests.get("sha256") if isinstance(digests, dict) else None
    if sha256 != artifact["sha256"]:
        failures.append(f"index SHA-256 does not match manifest for {filename}")
    if item.get("size") != artifact["size"]:
        failures.append(f"index size does not match manifest for {filename}")
    return failures


def download_index_artifacts(
    manifest_path: Path,
    index_json_url: str,
    destination: Path,
    *,
    attempts: int = 12,
    delay_seconds: float = 10.0,
) -> list[Path]:
    """Download and verify every manifest artifact from one package index."""
    if attempts < 1:
        raise PromotionError("download attempts must be at least one")
    if delay_seconds < 0:
        raise PromotionError("download delay must not be negative")
    _validate_https_url(index_json_url, label="package index")
    manifest = _load_release_manifest(manifest_path)
    last_error = "index did not return release metadata"
    for attempt in range(1, attempts + 1):
        try:
            payload = _read_json_url(index_json_url)
            failures = validate_index_payload(manifest, payload)
            if failures:
                raise PromotionError("; ".join(failures))
            return _download_payload_files(manifest, payload, destination)
        except (PromotionError, urllib.error.URLError) as exc:
            last_error = str(exc)
            if attempt < attempts:
                time.sleep(delay_seconds)
    raise PromotionError(
        f"package index artifacts were not ready after {attempts} attempts: {last_error}"
    )


def _download_payload_files(
    manifest: dict[str, Any],
    payload: dict[str, Any],
    destination: Path,
) -> list[Path]:
    urls = {
        item["filename"]: item
        for item in payload["urls"]
        if isinstance(item, dict) and isinstance(item.get("filename"), str)
    }
    destination.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    for artifact in manifest["artifacts"]:
        filename = artifact["path"]
        url = urls[filename].get("url")
        if not isinstance(url, str):
            raise PromotionError(f"index artifact has no download URL: {filename}")
        _validate_https_url(url, label=f"artifact {filename}")
        with _open_https_url(url, timeout=60) as response:
            payload_bytes = response.read()
        digest = hashlib.sha256(payload_bytes).hexdigest()
        if digest != artifact["sha256"] or len(payload_bytes) != artifact["size"]:
            raise PromotionError(f"downloaded artifact bytes do not match manifest: {filename}")
        output = destination / filename
        partial = destination / f".{filename}.part"
        partial.write_bytes(payload_bytes)
        partial.replace(output)
        downloaded.append(output)
    return downloaded


def _read_json_url(url: str) -> dict[str, Any]:
    with _open_https_url(url, timeout=30) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise PromotionError("package index response must be a JSON object")
    return payload


def _load_release_manifest(path: Path) -> dict[str, Any]:
    try:
        return load_manifest(path)
    except ManifestError as exc:
        raise PromotionError(str(exc)) from exc


def _load_canonical_evidence(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PromotionError(f"promotion evidence file does not exist: {path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromotionError("promotion evidence is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise PromotionError("promotion evidence root must be an object")
    if raw != canonical_json_bytes(payload):
        raise PromotionError("promotion evidence is not in canonical JSON form")
    if payload.get("schema") != PROMOTION_SCHEMA:
        raise PromotionError(f"unsupported promotion evidence schema: {payload.get('schema')!r}")
    return payload


def _validate_https_url(url: str, *, label: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise PromotionError(f"{label} URL must be credential-free HTTPS")


def _open_https_url(url: str, *, timeout: int) -> Any:
    _validate_https_url(url, label="network")
    # The immediately preceding validator permits only credential-free HTTPS.
    return urllib.request.urlopen(url, timeout=timeout)  # nosec B310


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--manifest", type=Path, required=True)
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--run-id", required=True)
    create.add_argument("--run-attempt", required=True)
    create.add_argument("--index-url", required=True)
    create.add_argument("--installed-smoke", choices=("passed", "failed"), required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--evidence", type=Path, required=True)
    verify.add_argument("--expected-sha", required=True)
    verify.add_argument("--run-id")
    download = subparsers.add_parser("download-index")
    download.add_argument("--manifest", type=Path, required=True)
    download.add_argument("--index-json-url", required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--attempts", type=int, default=12)
    download.add_argument("--delay-seconds", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run promotion evidence and index-download commands."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "create":
            evidence = create_promotion_evidence(
                args.manifest,
                args.output,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                index_url=args.index_url,
                installed_smoke=args.installed_smoke,
            )
            print(f"recorded promotion evidence for {evidence['version']}")
        elif args.command == "verify":
            evidence = verify_promotion_evidence(
                args.manifest,
                args.evidence,
                expected_sha=args.expected_sha,
                expected_run_id=args.run_id,
            )
            print(f"verified promotion evidence for {evidence['version']}")
        else:
            downloaded = download_index_artifacts(
                args.manifest,
                args.index_json_url,
                args.output,
                attempts=args.attempts,
                delay_seconds=args.delay_seconds,
            )
            print(f"downloaded and verified {len(downloaded)} release artifacts")
    except PromotionError as exc:
        print(f"promotion evidence error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
