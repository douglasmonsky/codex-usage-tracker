+++
id = "compression-parallel-ingestion"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-07-27
allowed_paths = [
  ".agent-maintainer/change-plans/compression-*.md",
  "docs/compression-lab-roadmap.md",
  "docs/development.md",
  "scripts/benchmark_refresh_ingestion.py",
  "src/codex_usage_tracker/compression/evidence.py",
  "src/codex_usage_tracker/parser/api.py",
  "src/codex_usage_tracker/parser/jsonl_v1.py",
  "src/codex_usage_tracker/store/allowance_observations.py",
  "src/codex_usage_tracker/store/api.py",
  "src/codex_usage_tracker/store/compression_fact_*.py",
  "src/codex_usage_tracker/store/compression_revisions.py",
  "src/codex_usage_tracker/store/compression_schema.py",
  "src/codex_usage_tracker/store/content_*.py",
  "src/codex_usage_tracker/store/refresh.py",
  "src/codex_usage_tracker/store/refresh_*.py",
  "src/codex_usage_tracker/store/schema.py",
  "src/codex_usage_tracker/store/schema_source_index.py",
  "src/codex_usage_tracker/store/source_records.py",
  "src/codex_usage_tracker/store/source_replacement.py",
  "src/codex_usage_tracker/store/thread_summaries.py",
  "tests/cli/test_cli_benchmarks.py",
  "tests/parser/test_parser.py",
  "tests/parser/test_parser_observer.py",
  "tests/store/test_compression_facts.py",
  "tests/store/test_content_index.py",
  "tests/store/test_content_index_refresh.py",
  "tests/store/test_refresh_parallel.py",
  "tests/store/test_store_dashboard_mcp.py",
  "tests/store/test_store_large_batches.py",
  "tests/store/test_store_migrations.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 41
max_changed_lines = 4000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: compression-parallel-ingestion

## Why this change intentionally large

CP6 validates and hardens the complete first-refresh path across source parsing,
worker scheduling, deterministic merge order, the single SQLite writer, synthetic
benchmarking, and the final CP1-CP6 evidence ledger. Partial changes could make
the benchmark pass without preserving refresh determinism or bounded memory.

## Why this should not be split smaller

Queue bounds are meaningful only with a serial/parallel equivalence benchmark,
while the benchmark is not a completion artifact until the worker and writer
contracts are explicit and tested. These pieces form one reviewable performance
boundary and do not alter public payloads.

## What allowed to change

- Refresh parser scheduling and conservative worker selection.
- Content-index scheduling only if profiling identifies it as the remaining
  first-build bottleneck.
- Synthetic refresh benchmark, focused scheduling tests, development guidance,
  and compression roadmap evidence.

## What must not change

- Parser output, record IDs, source provenance, public refresh payloads, or
  content-index privacy semantics.
- MCP/CLI/dashboard contracts, pricing, release metadata, or raw user data
  handling. Schema changes are limited to the additive source-file lookup index
  required by the measured content-index hot path.
- Deterministic serial fallback and compatibility with custom parser facades.

## Verification plan

- Compare serial and automatic-worker refreshes from identical synthetic JSONL
  trees across repeated fresh databases.
- Require equal aggregate/content fingerprints, below-25-second P95, below-20-
  second current-scale runs, material speedup, and bounded peak RSS.
- Test one-file fallback, configured workers, skewed completion order, bounded
  submissions, process-pool failure fallback, and progress payloads.
- Run focused tests, Ruff, Mypy, Tach, the full suite, release checks, and both
  Agent Maintainer verifier profiles.

## Rollback plan

Revert the CP6 squash commit. Schema v18 is additive, the prior schema remains
readable after rollback, and no public payload or privacy contract changes.

## Follow-up ratchet work

Close the performance program only after the roadmap records authoritative
timings and fingerprints. Dashboard, MCP, detector, and release work remain
separate follow-up PRs.
