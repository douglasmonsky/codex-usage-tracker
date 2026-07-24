+++
id = "blocking-quality-gates"
kind = "cohesive-quality-gate"
status = "complete"
base_ref = "origin/main"
expires = 2026-08-07
allowed_paths = [
  ".agent-maintainer/change-plans/blocking-quality-gates.md",
  ".github/workflows/ci.yml",
  "AGENTS.agent-maintainer.md",
  "docs/cli-json-schemas.md",
  "docs/deprecations.md",
  "docs/development.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "pyproject.toml",
  "scripts/check_release.py",
  "scripts/release_quality.py",
  "src/codex_usage_tracker/core/json_contracts.py",
  "src/codex_usage_tracker/interfaces/mcp/models.py",
  "src/codex_usage_tracker/interfaces/mcp/registry.py",
  "src/codex_usage_tracker/interfaces/mcp/work_proof.py",
  "tests/cli/test_cli_release.py",
  "tests/mcp/test_tool_registry.py",
  "tests/quality/test_compatibility_inventory.py",
  "tests/quality/test_release_quality_gates.py",
  "tests/quality/test_schema_inventory.py",
  "tests/quality/test_tool_work_proof.py",
  "tests/release_catalog.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 25
max_changed_lines = 2000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: blocking-quality-gates

## Why this change intentionally large

Task 34 turns four previously indirect quality expectations into fail-closed
release contracts: total and changed-line coverage, per-tool work proof, schema
inventory, and compatibility inventory. Most of the size is explicit static
schema and alias catalogs plus their documentation and false-green tests.

## Why this should not be split smaller

Landing a registry without its static release catalog would allow drift.
Landing CI thresholds without the negative-path tests would block the branch
without proving the new work-proof behavior. The runtime metadata, static
inventories, release checker, CI wiring, docs, and tests must therefore become
blocking together.

## What allowed to change

- MCP catalog metadata and validation for constant, row, source, evidence, and
  job work proof.
- Runtime, documented, and static release schema inventories.
- The normative deprecated MCP alias inventory and migration metadata checks.
- Coverage dependencies, thresholds, CI commands, release checks, generated
  Agent Maintainer guidance, and Task 34 execution evidence.

## What must not change

- MCP tool names, profiles, handler call signatures, or compatibility removal
  dates.
- Canonical accounting, pricing, allowance, evidence, or database semantics.
- Dashboard routes or payload behavior beyond registering an already-emitted
  selected-report schema.
- Coverage exclusions, suppression budgets, or relaxed quality thresholds.

## Verification plan

- Focused work-proof, schema, compatibility, registry, JSON-contract, and
  release-checker tests.
- Full pytest with branch coverage at or above 85% and `diff-cover` at or above
  90%.
- Ruff on changed files, MyPy, Pyright, Tach, Deptry, Vulture, Bandit,
  compileall, release source/dist checks, build, Twine, and installed-package
  smoke.
- One Agent Maintainer `ci` profile and one final read-only reviewer after the
  diff is stable.

## Rollback plan

Revert the Task 34 commit. The work-proof fields and auxiliary schema registry
entries are additive metadata; reverting restores the prior 80% total threshold
and non-blocking inventory posture without a data migration.

## Follow-up ratchet work

Task 35 pins workflow dependencies immutably. Later release-hardening tasks
should reuse these catalogs and checks instead of introducing parallel
inventories or weaker aliases.
