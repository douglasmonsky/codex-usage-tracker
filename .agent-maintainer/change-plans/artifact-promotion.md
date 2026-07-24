+++
id = "artifact-promotion"
kind = "cohesive-release-hardening"
status = "active"
base_ref = "origin/main"
expires = 2026-08-08
allowed_paths = [
  ".agent-maintainer/change-plans/artifact-promotion.md",
  ".github/workflows/publish.yml",
  "docs/architecture.md",
  "docs/cli-json-schemas.md",
  "docs/contracts.md",
  "docs/development.md",
  "docs/release-checklist.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "scripts/check_release.py",
  "scripts/release_promotion_quality.py",
  "scripts/release_quality.py",
  "scripts/smoke_installed_package.py",
  "src/codex_usage_tracker/core/json_contracts.py",
  "src/codex_usage_tracker/release/**",
  "tests/release/**",
  "tests/release_catalog.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 23
max_changed_lines = 3200
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Cohesive Change Plan: artifact-promotion

## Why this change intentionally large

Task 36 replaces the release graph as one fail-closed contract. The canonical
manifest, TestPyPI qualification evidence, installed-wheel smoke, workflow job
dependencies, offline release checks, schema inventory, tests, and operator
documentation must agree on the same artifact identity. Splitting those pieces
would permit an intermediate workflow to publish bytes that the local checker
cannot reproduce or verify.

## Why this should not be split smaller

The production job is safe only when the build job emits the manifest, the
qualification job proves published TestPyPI bytes, and the PyPI and GitHub jobs
consume those exact qualified bytes. Landing any subset would either retain the
old rebuild/manual-production path or make the release gate disagree with the
executable workflow.

## What allowed to change

The release workflow, deterministic release modules, installed-artifact smoke,
offline release checks, schema catalogs, focused tests, and the release
architecture/operator documentation listed in `allowed_paths`.

## What must not change

This task does not change runtime usage accounting, user data, dashboard
behavior, public MCP/CLI behavior, pricing, persistence, production credentials,
or published package state. It must not relax Trusted Publishing, environment
approval, immutable action pins, or existing release gates.

## Verification plan

- Focused manifest, promotion-evidence, packaging, workflow-policy, and
  installed-artifact smoke tests.
- Canonical wheel/sdist build, manifest create/verify, and
  `scripts/check_release.py --dist`.
- Ruff, mypy, actionlint, offline Zizmor, schema inventory, and whitespace
  checks.
- One CI-equivalent Agent Maintainer run after the diff is stable.
- One read-only final reviewer after primary validation.

## Rollback plan

Before publication, revert the Task 36 commit and restore the previous workflow
as one commit. After any TestPyPI or PyPI upload, do not reuse or replace the
version; preserve the evidence, patch forward to the next version, and rerun the
full promotion graph.

## Follow-up ratchet work

Task 37 will add package-size and public-surface budgets against artifacts
produced by this manifest. Task 39 will consume the promotion evidence in the
final 0.24 release gate.
