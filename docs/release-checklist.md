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

## Verify

```bash
python -m pytest tests/ci/test_immutable_action_pins.py tests/quality -q
actionlint .github/workflows/*.yml
zizmor --offline --no-progress .github/workflows
python scripts/check_release.py
git diff --check
```

Before publishing, also complete the build, distribution, installed-package,
TestPyPI, PyPI, and GitHub Release checks documented in
[Development](development.md#publishing).
