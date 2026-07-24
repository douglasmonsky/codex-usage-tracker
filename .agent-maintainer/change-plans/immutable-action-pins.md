+++
id = "immutable-action-pins"
kind = "cohesive-release-hardening"
status = "complete"
base_ref = "origin/main"
expires = 2026-08-08
allowed_paths = [
  ".agent-maintainer/change-plans/immutable-action-pins.md",
  ".github/dependabot.yml",
  ".github/workflows/allowance-statistical-calibration.yml",
  ".github/workflows/ci.yml",
  ".github/workflows/pricing-compat.yml",
  ".github/workflows/publish.yml",
  "docs/development.md",
  "docs/install.md",
  "docs/one-dot-oh-readiness.md",
  "docs/release-checklist.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "scripts/check_release.py",
  "scripts/release_quality.py",
  "scripts/smoke_installed_package.py",
  "tests/ci/test_immutable_action_pins.py",
  "tests/cli/test_cli_release.py",
  "tests/quality/test_release_quality_gates.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 20
max_changed_lines = 1000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Cohesive Change Plan: immutable-action-pins

## Why this change intentionally large

Task 35 makes workflow supply-chain integrity one release-wide contract.
Four workflows, Dependabot policy, the installed-package Docker smoke, the
offline release checker, tests, and operator documentation must agree on the
same reviewed immutable revisions. Splitting those surfaces would leave a
window where mutable references or mismatched release comments can pass.

## Why this should not be split smaller

The workflow edits and offline validator are one fail-closed migration. Landing
either side alone would make release readiness disagree with the executable
workflows. The documentation, Dependabot policy, and tests describe and prove
that same tuple contract rather than adding independent product behavior.

## What allowed to change

- Third-party action references and reviewed release comments.
- The installed-package Docker smoke default digest.
- Offline release validation, focused tests, and release operator guidance.

## What must not change

- Runtime package, dashboard, MCP, CLI, privacy, schema, or data behavior.
- Trusted Publishing environments, permissions, package identity, or secrets.
- Release artifact construction or promotion topology owned by Task 36.

## Verification plan

- Focused immutable-pin, release-quality, and release CLI tests.
- `actionlint` and offline `zizmor` for every workflow.
- Source release readiness and installed-package smoke checks.
- One CI-equivalent Agent Maintainer profile after the diff is stable.

## Rollback plan

Revert the Task 35 commit. No runtime data or public JSON/MCP contract changes
are involved; rollback restores the prior mutable workflow and Docker tags.

## Follow-up ratchet work

Task 36 will promote one verified artifact bundle through TestPyPI, PyPI, and
the GitHub Release without rebuilding it.
