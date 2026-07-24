+++
id = "tach-domain-boundaries"
kind = "cohesive-migration"
status = "complete"
base_ref = "0a21a71ebcb8334a43f2c15db02173290f339531"
expires = 2026-08-06
allowed_paths = [
  ".agent-maintainer/change-plans/tach-domain-boundaries.md",
  ".github/workflows/ci.yml",
  "docs/architecture.md",
  "docs/architecture/decisions/**",
  "docs/cli-json-schemas.md",
  "docs/releases/0.22.0.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "src/codex_usage_tracker/**",
  "tach.toml",
  "tests/analytics/**",
  "tests/application/**",
  "tests/architecture/**",
  "tests/core/**",
  "tests/diagnostics/**",
  "tests/store/**",
  "tests/**",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 110
max_changed_lines = 9000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: Tach Domain Boundaries

## Why this change intentionally large

Task 30 turns the documented package model into an enforced repository
contract. The current graph has four Python file cycles, eight already-blocked
domain imports, nine undeclared target domains, and several compatibility
packages that need explicit ownership. The domain declarations, focused
dependency inversions, secondary import regression tests, CI gate, ADR, and
execution ledger must describe one consistent graph.

## Why this should not be split smaller

Enabling forbidden root modules or circular dependencies before the involved
packages are declared and the cycles are removed makes every intermediate
commit unrunnable. Moving a shared model without its compatibility re-export
also breaks application, analytics, and interface imports. The work remains
reviewable through focused commits on one task branch, but the final policy and
the refactors it enforces must land together.

## What allowed to change

- Declare the roadmap-named core, ingest, store, analytics, evidence, jobs,
  application, interfaces, dashboard, plugin, and compatibility domains.
- Move or split internal symbols only where needed to remove a recorded cycle
  or forbidden dependency, retaining compatibility imports where the stable
  package contract requires them.
- Add deterministic import-direction tests and make Tach an explicit Python
  hardening step before dead-code checks.
- Record the boundary decision, verification evidence, and deviations.

## What must not change

- Do not change CLI, MCP, HTTP, JSON, SQLite, dashboard, pricing, allowance, or
  privacy behavior.
- Do not add dependencies, routes, tools, tables, schemas, suppressions, or a
  broad ignored-import baseline.
- Do not modify generated dashboard assets or unrelated roadmap tasks.

## Verification plan

- Capture the pre-change Tach and GitNexus cycle inventory by target domain.
- Run Tach until every Python module is owned, all declared directions pass,
  and circular dependencies are forbidden.
- Run the new architecture tests, the directly affected analytics,
  application, diagnostics, store, interface, and compatibility suites, then
  the complete Python suite.
- Run source Pyright, Ruff, mypy, compileall, Vulture, release readiness, CI
  workflow validation, and the repository CI-equivalent gate.
- Run GitNexus staged change impact and one final read-only reviewer.

## Rollback plan

Revert the Task 30 squash commit. No schema or data migration is involved; the
previous permissive Tach configuration and original internal module locations
return together.

## Follow-up ratchet work

Later roadmap tasks may migrate remaining legacy analytical packages into the
canonical package names. They must tighten the explicit domain graph rather
than add cross-layer allowances or compatibility imports into stable domains.
