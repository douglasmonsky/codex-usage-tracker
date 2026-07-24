from __future__ import annotations

import io
import shutil
import urllib.error
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codex_usage_tracker.release import promotion_evidence as promotion_module
from codex_usage_tracker.release.artifact_manifest import create_manifest
from codex_usage_tracker.release.promotion_evidence import (
    PromotionError,
    create_promotion_evidence,
    download_index_artifacts,
    main,
    validate_index_payload,
    verify_promotion_evidence,
)
from scripts import release_promotion_quality
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


def test_evidence_records_exact_release_identity(release_fixture: ReleaseFixture) -> None:
    manifest = _manifest(release_fixture)
    evidence_path = release_fixture.root / "promotion-evidence.json"

    evidence = create_promotion_evidence(
        release_fixture.manifest_path,
        evidence_path,
        run_id="123456",
        run_attempt="2",
        index_url="https://test.pypi.org/pypi/codex-usage-tracking/0.23.0/json",
        installed_smoke="passed",
    )

    assert evidence["source_sha"] == SOURCE_SHA
    assert evidence["github_actions"] == {"run_attempt": "2", "run_id": "123456"}
    assert evidence["qualification"]["installed_smoke"] == "passed"
    assert evidence["artifacts"] == manifest["artifacts"]
    assert evidence["contract_inventory"] == manifest["contract_inventory"]
    assert (
        verify_promotion_evidence(
            release_fixture.manifest_path,
            evidence_path,
            expected_sha=SOURCE_SHA,
            expected_run_id="123456",
        )
        == evidence
    )


def test_evidence_rejects_failed_smoke(release_fixture: ReleaseFixture) -> None:
    _manifest(release_fixture)

    with pytest.raises(PromotionError, match="installed smoke"):
        create_promotion_evidence(
            release_fixture.manifest_path,
            release_fixture.root / "promotion-evidence.json",
            run_id="123456",
            run_attempt="1",
            index_url="https://test.pypi.org/pypi/codex-usage-tracking/0.23.0/json",
            installed_smoke="failed",
        )


def test_evidence_rejects_manifest_substitution(release_fixture: ReleaseFixture) -> None:
    _manifest(release_fixture)
    evidence_path = release_fixture.root / "promotion-evidence.json"
    create_promotion_evidence(
        release_fixture.manifest_path,
        evidence_path,
        run_id="123456",
        run_attempt="1",
        index_url="https://test.pypi.org/pypi/codex-usage-tracking/0.23.0/json",
        installed_smoke="passed",
    )
    release_fixture.manifest_path.write_bytes(
        release_fixture.manifest_path.read_bytes().replace(SOURCE_SHA.encode(), ("b" * 40).encode())
    )

    with pytest.raises(PromotionError, match="manifest SHA-256"):
        verify_promotion_evidence(
            release_fixture.manifest_path,
            evidence_path,
            expected_sha=SOURCE_SHA,
        )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda payload: payload["github_actions"].update(run_id="other"),
            "run id",
        ),
        (
            lambda payload: payload.update(source_sha="b" * 40),
            "source SHA",
        ),
        (
            lambda payload: payload["qualification"].update(installed_smoke="failed"),
            "passed installed smoke",
        ),
        (
            lambda payload: payload.update(version="0.24.0"),
            "version does not match",
        ),
    ],
    ids=["run-id", "source-sha", "smoke", "version"],
)
def test_evidence_verify_rejects_changed_qualification(
    release_fixture: ReleaseFixture,
    mutation: Callable[[dict[str, Any]], None],
    expected: str,
) -> None:
    _manifest(release_fixture)
    evidence_path = release_fixture.root / "promotion-evidence.json"
    evidence = create_promotion_evidence(
        release_fixture.manifest_path,
        evidence_path,
        run_id="123456",
        run_attempt="1",
        index_url="https://test.pypi.org/pypi/codex-usage-tracking/0.23.0/json",
        installed_smoke="passed",
    )
    mutation(evidence)
    evidence_path.write_bytes(promotion_module.canonical_json_bytes(evidence))

    with pytest.raises(PromotionError, match=expected):
        verify_promotion_evidence(
            release_fixture.manifest_path,
            evidence_path,
            expected_sha=SOURCE_SHA,
            expected_run_id="123456",
        )


@pytest.mark.parametrize(
    ("run_id", "run_attempt", "index_url", "expected"),
    [
        ("not-numeric", "1", "https://test.pypi.org/project", "numeric"),
        ("1", "nope", "https://test.pypi.org/project", "numeric"),
        ("1", "1", "http://test.pypi.org/project", "credential-free HTTPS"),
        ("1", "1", "https://user@example.com/project", "credential-free HTTPS"),
    ],
)
def test_evidence_create_rejects_invalid_identity(
    release_fixture: ReleaseFixture,
    run_id: str,
    run_attempt: str,
    index_url: str,
    expected: str,
) -> None:
    _manifest(release_fixture)

    with pytest.raises(PromotionError, match=expected):
        create_promotion_evidence(
            release_fixture.manifest_path,
            release_fixture.root / "promotion-evidence.json",
            run_id=run_id,
            run_attempt=run_attempt,
            index_url=index_url,
            installed_smoke="passed",
        )


def test_index_payload_must_match_every_artifact_hash(
    release_fixture: ReleaseFixture,
) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)

    assert validate_index_payload(manifest, payload) == []

    altered = deepcopy(payload)
    altered["urls"][0]["digests"]["sha256"] = "0" * 64
    failures = validate_index_payload(manifest, altered)

    assert any("SHA-256" in failure for failure in failures)


def test_index_payload_rejects_missing_file(release_fixture: ReleaseFixture) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)
    payload["urls"].pop()

    failures = validate_index_payload(manifest, payload)

    assert any("missing release artifact" in failure for failure in failures)


def test_index_payload_rejects_wrong_version_size_and_shape(
    release_fixture: ReleaseFixture,
) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)
    payload["info"] = {"version": "0.24.0"}
    payload["urls"][0]["size"] = -1

    failures = validate_index_payload(manifest, payload)

    assert any("index version" in failure for failure in failures)
    assert any("index size" in failure for failure in failures)
    assert validate_index_payload(manifest, {"info": payload["info"], "urls": None})[-1] == (
        "index payload urls must be a list"
    )


def test_download_index_artifacts_writes_exact_bytes(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)
    source_by_name = {
        path.name: path.read_bytes()
        for path in (release_fixture.wheel_path, release_fixture.sdist_path)
    }
    monkeypatch.setattr(promotion_module, "_read_json_url", lambda _url: payload)
    monkeypatch.setattr(
        promotion_module,
        "_open_https_url",
        lambda url, *, timeout: io.BytesIO(source_by_name[Path(url).name]),
    )
    output = release_fixture.root / "downloaded"

    downloaded = download_index_artifacts(
        release_fixture.manifest_path,
        "https://test.pypi.org/project/version/json",
        output,
        attempts=1,
    )

    assert [path.name for path in downloaded] == [item["path"] for item in manifest["artifacts"]]
    assert all(path.read_bytes() == source_by_name[path.name] for path in downloaded)


def test_download_index_retries_then_succeeds(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(release_fixture)
    valid = _index_payload(manifest)
    invalid = deepcopy(valid)
    invalid["info"] = {"version": "pending"}
    payloads = iter((invalid, valid))
    sleeps: list[float] = []
    source_by_name = {
        path.name: path.read_bytes()
        for path in (release_fixture.wheel_path, release_fixture.sdist_path)
    }
    monkeypatch.setattr(promotion_module, "_read_json_url", lambda _url: next(payloads))
    monkeypatch.setattr(promotion_module.time, "sleep", sleeps.append)
    monkeypatch.setattr(
        promotion_module,
        "_open_https_url",
        lambda url, *, timeout: io.BytesIO(source_by_name[Path(url).name]),
    )

    download_index_artifacts(
        release_fixture.manifest_path,
        "https://test.pypi.org/project/version/json",
        release_fixture.root / "retried",
        attempts=2,
        delay_seconds=0.25,
    )

    assert sleeps == [0.25]


@pytest.mark.parametrize(
    ("attempts", "delay", "url", "expected"),
    [
        (0, 0.0, "https://example.com", "at least one"),
        (1, -1.0, "https://example.com", "must not be negative"),
        (1, 0.0, "file:///tmp/index.json", "credential-free HTTPS"),
    ],
)
def test_download_index_rejects_invalid_options(
    release_fixture: ReleaseFixture,
    attempts: int,
    delay: float,
    url: str,
    expected: str,
) -> None:
    _manifest(release_fixture)

    with pytest.raises(PromotionError, match=expected):
        download_index_artifacts(
            release_fixture.manifest_path,
            url,
            release_fixture.root / "downloaded",
            attempts=attempts,
            delay_seconds=delay,
        )


def test_download_index_reports_unready_release(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest(release_fixture)
    payload = _index_payload(manifest)
    payload["urls"].pop()
    monkeypatch.setattr(promotion_module, "_read_json_url", lambda _url: payload)

    with pytest.raises(PromotionError, match="not ready"):
        download_index_artifacts(
            release_fixture.manifest_path,
            "https://test.pypi.org/project/version/json",
            release_fixture.root / "downloaded",
            attempts=1,
            delay_seconds=0,
        )


def test_read_json_url_rejects_non_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promotion_module,
        "_open_https_url",
        lambda _url, *, timeout: io.BytesIO(b"[]"),
    )

    with pytest.raises(PromotionError, match="JSON object"):
        promotion_module._read_json_url("https://example.com/project.json")


def test_open_https_url_rejects_url_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        promotion_module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )

    with pytest.raises(urllib.error.URLError):
        promotion_module._open_https_url("https://example.com", timeout=1)


def test_repository_publish_workflow_promotes_one_build() -> None:
    assert check_publish_workflow(ROOT) == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("\n      - run: python -m build\n", "exactly once"),
        ("\n# inputs.target\n", "manual PyPI target"),
    ],
    ids=["second-build", "manual-pypi-dispatch"],
)
def test_release_check_rejects_unsafe_promotion_workflow(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    (workflow_dir / "publish.yml").write_text(workflow + mutation, encoding="utf-8")

    failures = check_publish_workflow(tmp_path)

    assert any(expected in failure for failure in failures)


def test_release_check_rejects_forbidden_events_and_secrets(tmp_path: Path) -> None:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = (ROOT / ".github" / "workflows" / "publish.yml").read_text(encoding="utf-8")
    workflow += "\npush:\npull_request:\n# secrets.PYPI api-token password:\n"
    (workflow_dir / "publish.yml").write_text(workflow, encoding="utf-8")

    failures = check_publish_workflow(tmp_path)

    assert any("ordinary pushes" in failure for failure in failures)
    assert any("pull requests" in failure for failure in failures)
    assert any("token secrets" in failure for failure in failures)


def test_release_check_reports_missing_workflow(tmp_path: Path) -> None:
    assert check_publish_workflow(tmp_path) == [
        "missing publish workflow: .github/workflows/publish.yml"
    ]


def test_release_artifact_contract_handles_git_and_manifest_failures(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        release_promotion_quality.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stdout=""),
    )
    assert (
        "source Git SHA"
        in release_promotion_quality.check_release_artifact_contract(
            release_fixture.repo_root,
            release_fixture.version,
        )[0]
    )

    monkeypatch.setattr(
        release_promotion_quality.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=SOURCE_SHA),
    )
    repo_dist = release_fixture.repo_root / "dist"
    repo_dist.mkdir()
    shutil.copy2(release_fixture.wheel_path, repo_dist)
    shutil.copy2(release_fixture.sdist_path, repo_dist)
    assert (
        release_promotion_quality.check_release_artifact_contract(
            release_fixture.repo_root,
            release_fixture.version,
        )
        == []
    )


def test_promotion_cli_create_verify_and_download(
    release_fixture: ReleaseFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _manifest(release_fixture)
    evidence = release_fixture.root / "promotion-evidence.json"
    assert (
        main(
            [
                "create",
                "--manifest",
                str(release_fixture.manifest_path),
                "--output",
                str(evidence),
                "--run-id",
                "123",
                "--run-attempt",
                "1",
                "--index-url",
                "https://test.pypi.org/project/version/json",
                "--installed-smoke",
                "passed",
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "verify",
                "--manifest",
                str(release_fixture.manifest_path),
                "--evidence",
                str(evidence),
                "--expected-sha",
                SOURCE_SHA,
                "--run-id",
                "123",
            ]
        )
        == 0
    )
    monkeypatch.setattr(
        promotion_module,
        "download_index_artifacts",
        lambda *_args, **_kwargs: [release_fixture.wheel_path, release_fixture.sdist_path],
    )
    assert (
        main(
            [
                "download-index",
                "--manifest",
                str(release_fixture.manifest_path),
                "--index-json-url",
                "https://test.pypi.org/project/version/json",
                "--output",
                str(release_fixture.root / "downloaded"),
            ]
        )
        == 0
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
