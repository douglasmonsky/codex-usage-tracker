+++
id = "kernel-code-quarantine-amendment"
kind = "documentation-amendment"
status = "active"
base_ref = "e6d6b76"
expires = 2026-09-30
allowed_paths = [
  "AGENTS.md",
  "CHANGELOG.md",
  "README.md",
  ".agent-maintainer/change-plans/kernel-code-quarantine-amendment.md",
  "docs/architecture.md",
  "docs/deprecations.md",
  "docs/release-checklist.md",
  "docs/roadmap/product-kernel-reset.md",
  "docs/roadmap/product-kernel-reset-execution.md",
  "docs/superpowers/plans/2026-07-26-product-kernel-reset.md",
  "docs/superpowers/specs/2026-07-26-kernel-code-quarantine-design.md",
  "docs/superpowers/specs/2026-07-26-product-kernel-reset-design.md",
  "tests/packaging/test_public_docs.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 14
max_changed_lines = 2500
allow_source_without_test_change = true
requires_tests = true
requires_full_verify = false
ratchet_targets = []
+++

# Change Plan: Early Kernel Code Quarantine

## Purpose

Amend the Product Kernel Reset before implementation so agents do not develop
the new kernel inside the full experimental 0.25 source tree. K1 freezes exact
public-surface and per-path disposition manifests. K1A then creates a lean
integration tree before K2 begins.

## Allowed Behavior Change

None. This change affects documentation, governance, task sequencing, and
public-document contract tests only. It must not alter runtime source, package
version, generated plugin assets, installed software, database state, or
release artifacts.

## Contracts

- Every path returned by `git ls-files` at K1 is classified exactly once as
  `keep`, `transplant`, `retire`, or `historical`.
- `verified` is the only terminal state, with a disposition-specific proof for
  all four classes.
- Current `main` remains the releasable 0.25.1 line through K9.
- K1A–K9 use short-lived branches based on and targeting the temporary,
  non-publishable `kernel/0.26-integration` branch.
- A branch/ref publication guard rejects integration through K9.
- K10 creates `release/0.26.0` from audited current `main`, incorporates the
  qualified integration head once, and opens the release-to-`main` cutover PR.
- Post-K1 main deltas fail closed until represented and, when needed, ported on
  a named integration-targeting branch with oracle and ledger updates.
- Normal Serena, GitNexus, and text-search scope excludes the v0.25.1
  reference worktree after K1A.
- Tagged source remains available as a bounded behavioral oracle; no worktree
  or branch is deleted without explicit maintainer permission.

## Verification

```bash
python -m pytest tests/packaging/test_public_docs.py \
  tests/cli/test_cli_release.py -q
python scripts/check_release.py
npx markdownlint-cli2 README.md "docs/**/*.md" \
  ".agent-maintainer/change-plans/*.md"
git diff --check
```

Also run the changed-document local-link check and inspect the final copy-aware
diff, explicit staged paths, and secret-pattern scan.

## Rollback

Revert this documentation changeset. The v0.25.1 runtime, source, worktrees,
branches, installed plugin, and user data remain untouched.
