+++
id = "clone-copy-deduping"
kind = "mechanical-migration"
status = "complete"
base_ref = "c755e8ecc20d9f3b62b9813aba4721898be01bb5"
expires = 2026-07-28
allowed_paths = [".github/workflows/ci.yml", "README.md", "config/vulture-whitelist.py", "docs/**", "frontend/**", "skills/**", "src/**", "tests/**"]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 120
max_changed_lines = 12000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: clone-copy-deduping

## Why this change intentionally large
Clone/copy deduplication crosses the parser identity contract, SQLite schema and migration, every billable aggregate consumer, HTTP/CLI/MCP contracts, dashboard disclosure, packaged skills, and synthetic integration tests. The CI workflow is also intentionally split into parallel hardening jobs while preserving its required umbrella check.

## Why this should not be split smaller
Splitting only the identity or storage layer from its default consumers would temporarily ship inconsistent totals. The schema migration, canonical query defaults, derived-table reconciliation, provenance diagnostics, and public contracts must land as one compatibility unit.

## What allowed to change
Only the usage identity/deduplication implementation, canonical aggregate consumers, derived-data maintenance, public diagnostic contracts, relevant dashboard and packaged-skill surfaces, tests/docs, and the CI hardening workflow may change.

## What must not change
Raw transcript/content indexing, unrelated product behavior, production configuration, credentials, deployment state, Git history, and physical provenance retention must not change.

## Verification plan
Run focused identity/parser/store/API/MCP/dashboard tests, Ruff, Pyright, Tach, workflow schema/security linters, frontend lint/typecheck/test/build, release readiness, and the repository full verifier. Validate the live v25 database and dedupe endpoint with a bounded 5,000-row dashboard server.

## Rollback plan
Revert the feature and CI commits together. Schema v25 is additive and preserves every physical usage row, so rollback can ignore the canonical columns/view while retaining source provenance; no destructive data rollback is required.

## Follow-up ratchet work
After adoption, measure v25 migration duration on large histories and consider batching the fingerprint backfill without changing identity semantics. Keep existing file-length and quality ratchets unchanged.
