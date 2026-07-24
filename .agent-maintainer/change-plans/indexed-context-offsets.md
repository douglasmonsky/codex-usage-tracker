+++
id = "indexed-context-offsets"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-08-07
allowed_paths = [
  ".agent-maintainer/change-plans/indexed-context-offsets.md",
  "docs/architecture.md",
  "docs/roadmap/mcp-first-pivot-execution.md",
  "scripts/benchmark_context_offsets.py",
  "scripts/benchmark_synthetic_history.py",
  "src/codex_usage_tracker/context/**",
  "src/codex_usage_tracker/core/models.py",
  "src/codex_usage_tracker/core/schema.py",
  "src/codex_usage_tracker/parser/jsonl_v1.py",
  "src/codex_usage_tracker/parser/jsonl_values.py",
  "src/codex_usage_tracker/store/context_offsets.py",
  "src/codex_usage_tracker/store/schema.py",
  "src/codex_usage_tracker/store/schema_query_indexes.py",
  "src/codex_usage_tracker/store/sources.py",
  "tests/context/test_byte_offset_reads.py",
  "tests/context/test_byte_offset_safety.py",
  "tests/core/test_schema.py",
  "tests/store/test_context_offsets.py",
  "tests/store/test_otel_schema.py",
  "tests/store/test_store_dashboard_mcp.py",
  "tests/store/test_store_migrations.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 25
max_changed_lines = 1600
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Cohesive Change Plan: Indexed Context Offsets

## Purpose

Complete MCP-first pivot Task 32 by persisting exact JSONL byte offsets and
using them for bounded, provenance-validated selected-call context reads.

## Why this change intentionally large

The schema migration, parser cursor, source-provenance validation, bounded seek
reader, sequential fallback, diagnostics, migration fixtures, equivalence
tests, and 100,000-line synthetic ratchet form one safety contract. The added
lines are predominantly explicit cross-platform and fallback coverage plus the
reproducible performance harness.

## Why this should not be split smaller

Landing offsets without provenance checks could trust replaced files. Landing
the seek path without payload-equivalence and inspected-byte evidence could
silently change explicit context or make an unverified speed claim. The schema,
reader, tests, benchmark, and architecture note therefore ship together.

## What allowed to change

- One additive nullable usage-event byte-offset column and schema migration.
- Parser byte-position tracking, validated offset resolution, bounded context
  seeking, unchanged sequential fallback, and aggregate diagnostics.
- Synthetic tests, benchmark helpers, architecture notes, and execution-ledger
  evidence required by Task 32.

## What must not change

- No raw context is persisted in SQLite, dashboard payloads, support bundles, or
  default exports.
- No offset is trusted after source provenance becomes stale.
- No context payload, redaction, tool-output default, quick/full mode, or
  compatibility route is removed or weakened.
- No unrelated dashboard, API, analytics, or Task 33 work is included.

## Verification plan

- Exact ASCII and multibyte UTF-8 offsets with LF and CRLF input.
- Append, rewrite, clone, stale-provenance, malformed-line, and old-row
  fallback coverage.
- Quick/full, tool-output, compaction, boundary, and normalized payload
  equivalence.
- A synthetic 100,000-line final target with less than 5% of bytes inspected
  and at least 5x speedup over five-run sequential medians.
- Focused tests, full Python/coverage gates, static checks, release checks, and
  one final read-only review.

## Rollback plan

Revert the task commit. Schema v35 is additive and nullable, so retained
databases remain readable; without the seek path, null or ignored offsets use
the existing sequential reader.

## Follow-up ratchet work

Keep the 100,000-line inspected-byte and median-speed ratchet on future context
reader changes. Task 33 and later tasks must not reuse raw context offsets as a
generic job cursor or broaden stored raw-content scope.
