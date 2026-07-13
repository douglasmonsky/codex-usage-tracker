+++
id = "compression-detector-facts"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-07-27
allowed_paths = [".agent-maintainer/change-plans/compression-detector-facts.md", "src/**", "tests/**", "docs/**", "scripts/benchmark_compression_lab.py"]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 23
max_changed_lines = 2500
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: compression-detector-facts

## Why this change intentionally large
This pull request persists detector-ready compression facts as part of the
canonical SQLite refresh transaction. The change necessarily spans the schema,
migration, incremental refresh hooks, full backfill, read path, benchmark, and
contract tests. Shipping only part of that chain would either create stale fact
tables or make the detector path depend on data that existing databases cannot
produce.

## Why this should not be split smaller
The schema and writers are not useful without the guarded reader, while the
reader is unsafe without generation and manifest integrity checks. The reset,
source-replacement, content-index, and incremental-refresh hooks must land with
the initial schema so every supported mutation preserves the same invariant.
The new modules already separate contracts, queries, synchronization, and full
backfill into reviewable ownership boundaries; splitting those boundaries over
multiple deployable commits would increase migration and rollback risk.

## What allowed to change
- Compression fact schema and migration code.
- Full and targeted fact synchronization during existing store mutations.
- Compression evidence loading, run construction, and cache identity checks.
- The compression domain dependency declaration when imports are removed.
- The existing Tach boundary decision note for that dependency contraction.
- The synthetic benchmark and focused migration, store, CLI, and compression
  tests.
- The compression-lab roadmap evidence for this checkpoint.

## What must not change
- Existing MCP, CLI, dashboard, and persisted-record payload contracts.
- Detector ranking, candidate identity, profile identity, or thresholds.
- Pricing behavior, source parser behavior, privacy boundaries, or raw content
  retention.
- Production configuration, credentials, release metadata, or unrelated
  architecture.

## Verification plan
- Prove migration, incremental synchronization, replacement/reset cleanup,
  transaction rollback, stale-manifest fallback, and canonical detector output
  with focused tests and the full Python suite.
- Run Ruff, Mypy, Tach, Bandit, Xenon, dashboard typecheck, release checks, and
  the full Agent Maintainer verifier.
- Compare fact-backed and fallback detector candidate/profile fingerprints.
- Enforce the 100k-call benchmark threshold and record cold, warm, and real-data
  temporary-copy measurements without exposing private content.

## Rollback plan
Revert this squash commit before any dependent compression-lab checkpoint is
merged. Existing databases remain readable because the migration is additive;
the previous evidence loader does not consult the new tables. If a runtime
integrity check fails before rollback, the guarded reader falls back to the CP2
evidence query rather than returning partial facts.

## Follow-up ratchet work
Keep each fact module below the repository source-size limits and preserve the
static SQL target whitelist. Subsequent checkpoints must add their own focused
tests and may not expand this plan to cover revision-aware pricing, MCP/API
surfaces, simulator work, or dashboard changes.
