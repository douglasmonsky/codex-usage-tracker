+++
id = "k1-oracle-baseline"
kind = "kernel-reset-task"
status = "active"
base_ref = "62726189c05d423f08abdec6ad1454434188d734"
expires = 2026-10-31
allowed_paths = [
  ".agent-maintainer/change-plans/k1-oracle-baseline.md",
  ".agent-maintainer/git-agent-ratchet-duplicate-helpers.json",
  ".agent-maintainer/git-agent-ratchet-max-file-lines.json",
  ".agent-maintainer/git-agent-ratchet-private-imports.json",
  "AGENTS.md",
  "AGENTS.agent-maintainer.md",
  "config/kernel-code-disposition-v1.json",
  "config/kernel-development-efficiency-v1.json",
  "config/kernel-performance-budget.json",
  "config/kernel-retired-surfaces-v1.json",
  "docs/maintainability-scorecard.md",
  "docs/roadmap/product-kernel-reset-execution.md",
  "justfile",
  "scripts/benchmark_kernel.py",
  "scripts/check_kernel_maintainability.py",
  "scripts/check_wemake_baseline.py",
  "scripts/generate_kernel_manifests.py",
  "tests/kernel/**",
  "pyproject.toml",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 40
max_changed_lines = 6000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Change Plan: K1 Accounting Oracle Baseline

## Purpose

Freeze the smallest synthetic behavioral oracle and exact repository inventories
needed to build the lean kernel without importing the experimental 0.25
implementation by assumption.

## Allowed Behavior Change

None. K1 adds synthetic fixtures, contract tests, deterministic manifest
generation, benchmark evidence, and execution-ledger evidence. Runtime source,
package version, plugin assets, installed software, user databases, and public
contracts remain unchanged.

## Contracts

- The current runtime reproduces one versioned accounting oracle covering
  canonical counts, four token classes, grouping, identity, parentage,
  allowance selection, diagnostic activity, and privacy-safe normalized fields.
- The source-lifecycle oracle covers new, appended, partial, replaced,
  truncated, archived, and restored sources.
- The retired-surface manifest exactly freezes every removal across MCP, HTTP,
  CLI, schema, table, Console, package, and source boundaries.
- The code-disposition manifest resolves every K1 `git ls-files` path exactly
  once as `keep`, `transplant`, `retire`, or `historical`.
- Synthetic benchmark evidence records fixed-seed 10,000- and 100,000-call
  workloads as comparison evidence, not future acceptance thresholds.
- Replacement-kernel source has one repository-owned 600-line and Xenon-B
  maintainability gate with fail-closed tests.
- No fixture or output contains a real path, prompt, tool output, credential,
  local database row, or other private usage content.

## Verification

Run the focused K1 tests twice, then the repository full verifier because K1
touches release, privacy, schema, MCP, package, and architecture contracts.
Also run release readiness, formatting/static checks, deterministic manifest
regeneration, benchmark smoke, local-link checks, and disclosure scans.

## Rollback

Revert the K1 changeset. No runtime state, installation, tag, branch, release,
or user data is mutated by these artifacts.
