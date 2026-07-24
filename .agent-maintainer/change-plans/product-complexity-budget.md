+++
id = "product-complexity-budget"
kind = "cohesive-quality-gate"
status = "complete"
base_ref = "origin/main"
expires = 2026-08-08
allowed_paths = [
  ".agent-maintainer/change-plans/artifact-promotion.md",
  ".agent-maintainer/change-plans/product-complexity-budget.md",
  ".github/workflows/ci.yml",
  "MANIFEST.in",
  "config/product-complexity-budget.json",
  "docs/architecture.md",
  "docs/development.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "pyproject.toml",
  "scripts/check-dashboard-bundles.mjs",
  "scripts/check_product_complexity.py",
  "scripts/check_release.py",
  "tests/cli/test_cli_release.py",
  "tests/quality/test_product_complexity_budget.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 14
max_changed_lines = 1800
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = ["scripts/check_product_complexity.py"]
+++

# Cohesive Change Plan: product-complexity-budget

## Why this change intentionally large

Task 37 adds one deterministic policy surface for product complexity. The
measurement script, committed ceilings, focused fail-closed tests, dashboard
bundle integration, release integration, CI steps, and operator documentation
must agree on the same metric names and authoritative registries.

## Why this should not be split smaller

Landing the checker without its measured ceilings would create an undefined
policy. Landing ceilings without CI, release, bundle, and test integration
would create a false-green policy. The source and built-artifact halves share
one schema so later releases can ratchet them together.

## What allowed to change

Only the Task 37 budget, checker, focused tests, CI and release wiring,
dashboard bundle gate, project configuration, architecture/development
documentation, execution ledger, and Task 36 plan closure listed in
`allowed_paths`.

## What must not change

This task does not alter runtime accounting, dashboard behavior, MCP/CLI
contracts, persistence schemas, package publication, production data, or
credentials. It must not raise a ceiling without an explicit architecture
decision recorded beside the changed fixture.

## Verification plan

- Focused tests that lower every ceiling and prove each metric blocks.
- Deterministic source-only measurement and JSON report comparison.
- Dashboard bundle report plus the dedicated product-complexity gate.
- Canonical wheel/sdist build followed by artifact-size checks.
- Existing release, lint, type, workflow, and repository quality gates.
- One read-only final reviewer after the diff is stable.

## Rollback plan

Revert the Task 37 commit. The new checker is additive and does not migrate
data or change public behavior, so rollback removes only the additional gate.

## Follow-up ratchet work

Task 38 removes legacy workbench route imports and should reduce the initial
React bundle. Tasks 40/41 in the next release ratchet removed compatibility
surfaces downward.
