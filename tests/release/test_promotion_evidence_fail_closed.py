from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from codex_usage_tracker.release import promotion_evidence as promotion_module
from codex_usage_tracker.release.artifact_manifest import create_manifest
from codex_usage_tracker.release.promotion_evidence import (
    PromotionError,
    create_promotion_evidence,
    download_index_artifacts,
    verify_promotion_evidence,
)
from scripts.release_quality import check_publish_workflow
from tests.release.conftest import ReleaseFixture

SOURCE_SHA = "a" * 40
ROOT = Path(__file__).resolve().parents[2]


def _manifest(fixture: ReleaseFixture) -> dict[str, Any]:
    return create_manifest(
        fixture.dist_dir,
        fixture.manifest_path,
        expected_sha=SOURCE_SHA,
        expected_version=fixture.version,
        repository_root=fixture.repo_root,
    )


def _index_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "info": {"version": manifest["version"]},
        "urls": [
            {
                "filename": item["path"],
                "digests": {"sha256": item["sha256"]},
                "size": item["size"],
                "url": f"https://files.pythonhosted.org/{item['path']}",
            }
            for item in manifest["artifacts"]
        ],
    }


def test_evidence_loader_rejects_noncanonical_or_malformed_files(
    release_fixture: ReleaseFixture,
) -> None:
    _manifest(release_fixture)
    evidence_path = release_fixture.root / "promotion-evidence.json"
    verification = {
        "manifest_path": release_fixture.manifest_path,
        "evidence_path": evidence_path,
        "expected_sha": SOURCE_SHA,
    }

    with pytest.raises(PromotionError, match="does not exist"):
        verify_promotion_evidence(**verification)

    evidence_path.write_bytes(b"{")
    with pytest.raises(PromotionError, match="valid UTF-8 JSON"):
        verify_promotion_evidence(**verification)

    evidence_path.write_bytes(b"[]\n")
    with pytest.raises(PromotionError, match="root must be an object"):
        verify_promotion_evidence(**verification)

    evidence = create_promotion_evidence(
        release_fixture.manifest_path,
        evidence_path,
        run_id="123",
        run_attempt="1",
        index_url="https://test.pypi.org/project/version/json",
        installed_smoke="passed",
    )
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    with pytest.raises(PromotionError, match="canonical JSON"):
        verify_promotion_evidence(**verification)

    evidence["schema"] = "unsupported"
    evidence_path.write_bytes(promotion_module.canonical_json_bytes(evidence))
    with pytest.raises(PromotionError, match="unsupported promotion evidence schema"):
        verify_promotion_evidence(**verification)


@pytest.mark.parametrize("failure", ("missing-url", "altered-bytes"))
def test_download_rejects_unusable_index_artifacts(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)
    source_by_name = {
        path.name: path.read_bytes()
        for path in (release_fixture.wheel_path, release_fixture.sdist_path)
    }
    expected = "download URL"
    if failure == "missing-url":
        payload["urls"][0].pop("url")
    else:
        first_name = manifest["artifacts"][0]["path"]
        source_by_name[first_name] += b"altered"
        expected = "bytes do not match"

    monkeypatch.setattr(promotion_module, "_read_json_url", lambda _url: payload)
    monkeypatch.setattr(
        promotion_module,
        "_open_https_url",
        lambda url, *, timeout: io.BytesIO(source_by_name[Path(url).name]),
    )

    with pytest.raises(PromotionError, match=expected):
        download_index_artifacts(
            release_fixture.manifest_path,
            "https://test.pypi.org/project/version/json",
            release_fixture.root / "downloaded",
            attempts=1,
        )


@pytest.mark.parametrize("failure", ("unexpected", "duplicate", "malformed"))
def test_index_payload_requires_exact_artifact_set(
    release_fixture: ReleaseFixture,
    failure: str,
) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)
    if failure == "unexpected":
        extra = dict(payload["urls"][0])
        extra["filename"] = "codex_usage_tracking-0.23.0-py3-none-macos.whl"
        payload["urls"].append(extra)
    elif failure == "duplicate":
        payload["urls"].append(dict(payload["urls"][0]))
    else:
        payload["urls"].append({"filename": 42})

    failures = promotion_module.validate_index_payload(manifest, payload)

    assert any(failure in message or "string filenames" in message for message in failures)


@pytest.mark.parametrize(
    "required",
    [
        'SOURCE_DATE_EPOCH=$(git show -s --format=%ct "$GITHUB_SHA")',
        'expected_tag="v$version"',
        'if [ "$GITHUB_REF_NAME" != "$expected_tag" ]; then',
    ],
    ids=["reproducible-epoch", "versioned-tag", "tag-comparison"],
)
def test_release_check_requires_reproducible_version_bound_release(
    tmp_path: Path,
    required: str,
) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    (workflow_dir / "publish.yml").write_text(
        workflow.replace(required, "removed-release-proof", 1),
        encoding="utf-8",
    )

    failures = check_publish_workflow(tmp_path)

    assert any(required in failure for failure in failures)
