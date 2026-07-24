# Release checklist

Use this checklist for release preparation and for every GitHub Actions
dependency update.

## Review workflow dependencies

1. Read the release notes in the action's official GitHub repository.
2. Resolve the release tag to its full 40-character commit SHA from the
   official commit or tag record.
3. Update the workflow reference and trailing reviewed tag together:

   ```yaml
   uses: owner/action@0123456789abcdef0123456789abcdef01234567 # v1.2.3
   ```

4. Update the same `(action, tag) -> SHA` tuple in
   `REVIEWED_ACTION_PINS` in `scripts/release_quality.py`.
5. Review major-version changes for runtime, input, permission, and
   Node-version changes. Do not merge a Dependabot SHA-only update.

Local actions under `./` remain relative. Docker actions must use a
`sha256` digest rather than a mutable image tag.

## Promote one verified build

1. Use the manual `Publish Python package` workflow only for a TestPyPI dry run
   with a distinct prerelease version such as `0.24.0rc1`. Manual dispatch
   cannot publish to production PyPI, and a manually uploaded final version
   must not be reused by a later production run.
2. For a production release, publish the exact annotated `v<package-version>`
   tag as a GitHub Release without first manually uploading that final version.
   The release-event workflow checks out that tag, derives `SOURCE_DATE_EPOCH`
   from its commit, builds the wheel and sdist once, and performs TestPyPI
   qualification and production promotion in that same run.
3. Confirm the `python-dist` workflow artifact contains `dist/` and the
   canonical `release-manifest.json`, and record the manifest SHA-256 from the
   build job.
4. Confirm TestPyPI qualification downloaded both files, matched the manifest,
   and passed `smoke_installed_package.py --artifact-dir`.
5. Approve the protected `pypi` environment only after the
   `promotion-evidence.json` records the exact source SHA, Actions run, artifact
   hashes, contract inventories, console bundle hashes, and passed smoke.
6. Confirm the PyPI job publishes `promoted-dist/` downloaded from TestPyPI,
   never a rebuild or an unqualified local directory.
7. Confirm the GitHub Release receives bytes downloaded from PyPI plus the same
   manifest and promotion evidence.
8. Require the final public-location verification job to pass for TestPyPI,
   PyPI, and GitHub Release before declaring the release complete.

After TestPyPI accepts a final-version artifact, rerun failed jobs rather than
rerunning every job. A full rerun still uses the commit-derived build epoch and
must reproduce the manifest hashes or fail closed; never replace or work around
an uploaded version.

Local manifest verification:

```bash
export SOURCE_DATE_EPOCH="$(git show -s --format=%ct HEAD)"
python -m build
python -m codex_usage_tracker.release.artifact_normalization \
  --source dist \
  --epoch "$SOURCE_DATE_EPOCH"
python -m codex_usage_tracker.release.artifact_manifest create \
  --source dist \
  --output /tmp/codex-usage-release-manifest.json \
  --expected-sha "$(git rev-parse HEAD)"
python -m codex_usage_tracker.release.artifact_manifest verify \
  --source dist \
  --manifest /tmp/codex-usage-release-manifest.json \
  --expected-sha "$(git rev-parse HEAD)"
python scripts/smoke_installed_package.py --artifact-dir dist
```

## Verify

```bash
python -m pytest tests/ci/test_immutable_action_pins.py tests/release tests/quality -q
actionlint .github/workflows/*.yml
zizmor --offline --no-progress .github/workflows
python scripts/check_release.py
git diff --check
```

Before publishing, also complete the build, distribution, installed-package,
TestPyPI, PyPI, and GitHub Release checks documented in
[Development](development.md#publishing).
