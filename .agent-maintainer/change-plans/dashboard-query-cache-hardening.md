+++
id = "dashboard-query-cache-hardening"
kind = "cohesive-migration"
status = "active"
base_ref = "origin/main"
expires = 2026-07-29
allowed_paths = [
  ".agent-maintainer/change-plans/dashboard-diagnostic-refresh-jobs.md",
  ".agent-maintainer/change-plans/dashboard-query-cache-hardening.md",
  "docs/dashboard-query-pipeline-refactor-roadmap.md",
  "docs/dashboard-route-inventory.md",
  "frontend/dashboard/src/data/**",
  "scripts/benchmark_dashboard_routes.py",
  "src/codex_usage_tracker/cli/commands_reports.py",
  "src/codex_usage_tracker/dashboard/api.py",
  "src/codex_usage_tracker/dashboard/cache_identity.py",
  "src/codex_usage_tracker/recommendation_engine/query.py",
  "src/codex_usage_tracker/reports/query.py",
  "src/codex_usage_tracker/server/**",
  "src/codex_usage_tracker/plugin_data/dashboard/react/assets/**",
  "src/codex_usage_tracker/store/schema.py",
  "src/codex_usage_tracker/store/schema_query_indexes.py",
  "src/codex_usage_tracker/store/schema_source_index.py",
  "tests/cli/test_dashboard_route_benchmark.py",
  "tests/cli/test_commands_reports.py",
  "tests/dashboard/test_dashboard_server_live_slices.py",
  "tests/dashboard/test_dashboard_server.py",
  "tests/reports/test_indexed_recommendations.py",
  "tests/server/**",
  "tests/store/test_store_dashboard_mcp.py",
  "tests/store/test_compression_runs.py",
  "tests/store/test_refresh_parallel.py",
  "tests/store/test_store_migrations.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 50
max_changed_lines = 3000
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: Dashboard Query Cache Hardening

## Purpose

Complete PR 5 of the dashboard query-pipeline roadmap by adding bounded,
generation-aware immutable response caching only where persisted facts still
miss the warm interactive budget.

## Why this change intentionally large

The server cache, source/config identity, API metadata, browser-persistence
guard, schema index, deterministic benchmark, migration coverage, generated
assets, and route documentation form one cache contract. Leaving any layer out
would either make cache provenance incorrect, retain private content, or ship
performance claims without reproducible evidence.

## Why this should not be split smaller

The implementation is already limited to two aggregate routes. Splitting the
cache core from invalidation, privacy, and benchmark evidence would merge an
unproven cache or temporarily expose incomplete semantics. PR 6 remains a
separate cleanup and CI-enforcement change.

## What allowed to change

- Share one bounded server-process cache across dashboard request handlers.
- Cache summary and recommendation aggregate responses by canonical query,
  source generation, privacy mode, and every local configuration dependency.
- Coalesce identical in-flight builders and return detached serialized copies.
- Bypass storage for oversized responses without changing explicit API limits.
- Reject raw or indexed content before writing aggregate browser caches.
- Add one diagnostic-fact covering index justified by query-plan evidence.
- Extend the deterministic route benchmark with cold, warm, payload, and cache
  provenance measurements.
- Update the route inventory and roadmap with measured evidence.

## What must not change

- No caching for context, raw-content, live mutation, or Compression Lab job
  routes.
- No public query/filter/schema removal or response-size cap on explicit API
  requests.
- No summary date-expression index; measured query plans showed it regressed
  the representative 400,000-row query.
- No legacy-path cleanup or CI performance ratchets; PR 6 owns those changes.

## Verification plan

- Cache immutability, semantic-key, generation invalidation, coalescing,
  oversized-bypass, and failure-recovery tests.
- Schema migration and `EXPLAIN QUERY PLAN` coverage for the diagnostic lookup.
- Browser-cache privacy tests plus React typecheck, lint, tests, and build.
- Clean 400,000-row cold/warm route benchmark and a representative Agent Perf
  profile with unprofiled timing reported separately.
- Agent Maintainer precommit and full verification profiles.

## Rollback plan

Revert this PR. The response cache is process-local and requires no persisted
data rollback; schema version 22's additive index is harmless if retained and
can be dropped independently if a later query plan no longer uses it.

## Follow-up ratchet work

PR 6 will remove parity-proven compatibility scans, add deterministic CI
performance/schema/query-key ratchets, and finish the route/documentation
audit. This PR does not weaken or preempt those enforcement changes.

Recorded evidence:

- Clean 400,000-call benchmark: summary 544 ms cold / 1.42 ms warm p95;
  recommendations 140 ms cold / 1.87 ms warm p95.
- Stored payloads measured 8.7 KiB and 155.1 KiB, below the 256 KiB bound.
- Agent Perf run `20260714T110929Z-1747f5c7` completed the same pipeline at
  100,000 calls. Ranked application CPU remained in ingestion and fact
  materialization; the response cache introduced no reported hotspot.
