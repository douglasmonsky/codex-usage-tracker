+++
id = "dashboard-query-pipeline-enforcement"
kind = "cohesive-migration"
status = "active"
base_ref = "origin/main"
expires = 2026-07-29
allowed_paths = [
  ".agent-maintainer/dashboard-source-baseline.json",
  ".agent-maintainer/change-plans/dashboard-query-pipeline-enforcement.md",
  ".markdownlint-cli2.yaml",
  ".agent-maintainer/change-plans/dashboard-query-cache-hardening.md",
  ".codex/tasks.toml",
  ".github/workflows/ci.yml",
  "config/dashboard-route-budgets.json",
  "docs/architecture.md",
  "docs/architecture/decisions/0005-dashboard-router-and-query-runtime.md",
  "docs/cli-json-schemas.md",
  "docs/dashboard-query-pipeline-refactor-roadmap.md",
  "docs/dashboard-route-inventory.md",
  "docs/development.md",
  "frontend/dashboard/src/data/**",
  "frontend/dashboard/src/App.live-refresh.test.tsx",
  "frontend/dashboard/src/App.tsx",
  "frontend/dashboard/src/api/compressionLab.test.ts",
  "frontend/dashboard/src/api/compressionLab.ts",
  "frontend/dashboard/src/features/compression-lab/CompressionLabPage.test.tsx",
  "frontend/dashboard/src/features/compression-lab/CompressionLabPage.tsx",
  "frontend/dashboard/src/features/overview/OverviewMetrics.tsx",
  "frontend/dashboard/src/features/overview/OverviewPage.test.tsx",
  "frontend/dashboard/src/features/overview/overviewModel.test.ts",
  "frontend/dashboard/src/features/overview/overviewModel.ts",
  "frontend/dashboard/src/features/diagnostics/DiagnosticsPage.tsx",
  "frontend/dashboard/src/features/diagnostics/DiagnosticsPage.query.test.tsx",
  "frontend/dashboard/src/features/diagnostics/useDiagnosticFactEvidence.ts",
  "frontend/dashboard/src/features/calls/CallInspector.tsx",
  "frontend/dashboard/src/App.diagnostics.test.tsx",
  "frontend/dashboard/src/api/allowance.ts",
  "frontend/dashboard/src/api/allowance.test.ts",
  "frontend/dashboard/src/features/threads/ThreadInspector.tsx",
  "frontend/dashboard/src/features/threads/ThreadsExplorerView.tsx",
  "frontend/dashboard/src/features/threads/ThreadsPage.tsx",
  "scripts/benchmark_dashboard_routes.py",
  "scripts/dashboard_route_benchmark_support.py",
  "src/codex_usage_tracker/cli/commands_lifecycle.py",
  "src/codex_usage_tracker/cli/dashboard.py",
  "src/codex_usage_tracker/cli/mcp_investigations.py",
  "src/codex_usage_tracker/cli/mcp_server.py",
  "src/codex_usage_tracker/recommendation_engine/api.py",
  "src/codex_usage_tracker/recommendation_engine/materialization.py",
  "src/codex_usage_tracker/recommendation_engine/query.py",
  "src/codex_usage_tracker/recommendation_engine/summary_materialization.py",
  "src/codex_usage_tracker/reports/agentic.py",
  "src/codex_usage_tracker/allowance_intelligence/model.py",
  "src/codex_usage_tracker/allowance_intelligence/statistics.py",
  "src/codex_usage_tracker/plugin_data/dashboard/react/assets/**",
  "src/codex_usage_tracker/server/recommendations.py",
  "src/codex_usage_tracker/server/compression_routes.py",
  "src/codex_usage_tracker/server/investigations.py",
  "src/codex_usage_tracker/server/route_inventory.py",
  "src/codex_usage_tracker/server/usage_refresh.py",
  "src/codex_usage_tracker/server/allowance.py",
  "src/codex_usage_tracker/server/api.py",
  "src/codex_usage_tracker/server/handler.py",
  "src/codex_usage_tracker/server/live_rows.py",
  "src/codex_usage_tracker/server/diagnostic_facts.py",
  "src/codex_usage_tracker/server/diagnostic_routes.py",
  "src/codex_usage_tracker/store/schema.py",
  "src/codex_usage_tracker/store/schema_query_indexes.py",
  "src/codex_usage_tracker/store/thread_summaries.py",
  "src/codex_usage_tracker/store/query_sql.py",
  "src/codex_usage_tracker/store/large_low_output.py",
  "src/codex_usage_tracker/store/repeated_files.py",
  "src/codex_usage_tracker/store/shell_churn.py",
  "src/codex_usage_tracker/store/usage_api_queries.py",
  "src/codex_usage_tracker/store/diagnostic_queries.py",
  "tests/cli/test_dashboard_route_benchmark.py",
  "tests/cli/test_cli_lifecycle.py",
  "tests/cli/test_mcp_integration.py",
  "tests/dashboard/test_dashboard_server_live_slices.py",
  "tests/reports/test_indexed_recommendations.py",
  "tests/allowance_intelligence/test_allowance_intelligence.py",
  "tests/server/test_route_inventory.py",
  "tests/server/test_compression_routes.py",
  "tests/server/test_server_investigations.py",
  "tests/server/test_server_recommendations.py",
  "tests/server/test_server_usage_refresh.py",
  "tests/server/test_server_allowance.py",
  "tests/server/test_server_live_rows.py",
  "tests/server/test_server_diagnostic_facts.py",
  "tests/store/test_store_dashboard_queries.py",
  "tests/store/test_store_dashboard_mcp.py",
  "tests/store/test_store_migrations.py",
  "tests/store/test_recommendation_queries.py",
  "tests/store/test_compression_runs.py",
  "tests/store/test_refresh_parallel.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 96
max_changed_lines = 2700
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: Dashboard Query Pipeline Enforcement

## Purpose

Complete PR 6 of the dashboard query-pipeline roadmap by removing the automatic
request-thread recommendation scan, enforcing deterministic query/schema/performance
contracts in CI, and documenting the extension rules for future dashboard work.

## Why this change intentionally large

The cleanup is safe only when the replacement behavior, frontend query identity,
route classification, benchmark budgets, CI wiring, and maintainer documentation
land together. Splitting enforcement from its contracts would leave a window where
the architecture could regress without a failing gate.

Live all-history verification also exposed adjacent request-path regressions that
would make the enforced architecture unreliable in practice: stale recommendation
facts, incomplete summary fallback, repeated full-summary refresh work, expensive
investigation joins, Compression Lab writer contention, and unclear cost-first
Overview reporting. Their bounded fixes and regression tests remain part of this
same final enforcement slice because each validates the indexed query pipeline
under the production-sized workload used for the acceptance audit.

## Why this should not be split smaller

PR 6 removes legacy fallback behavior only after its indexed replacement,
frontend contracts, cache identity, schema migration, and deterministic route
budgets are present together. Separating those changes would either remove a
fallback before parity is enforced or merge enforcement that the current routes
cannot yet satisfy. The line estimate includes explicit benchmark support and
allowlisted SQL-template helpers added to satisfy source-length and security
ratchets without suppressions.

## What allowed to change

- Require current materialized recommendation facts and return an explicit
  refresh-required error instead of rebuilding the legacy report on a request.
- Register dashboard query definitions with endpoint, data-class, and schema
  metadata and fail tests on duplicate query identities or contract drift.
- Add stable synthetic cold/warm route budgets for summary and recommendations.
- Remove the non-indexable per-thread latest-record lookup found during live
  route verification and include Threads in the performance budget.
- Bound selected-thread call hydration and page it on demand so large threads
  cannot return hundreds of megabytes to the browser.
- Cover diagnostic-fact aggregation, remove its correlated representative-call
  scan, cache generation-stable responses, and load only the selected notebook
  fact module so the two heaviest tabs do not contend on first render.
- Preserve selected-call thread context with bounded before/after hydration and
  keep selected-thread pages globally sorted by the requested server order.
- Reduce allowance change-point statistics to rank-relevant split points and
  cache the resulting generation-stable Limits payloads within a dedicated
  bounded cache.
- Keep the exact running-median split evaluator in the existing statistics
  module and isolate reusable synthetic route benchmark helpers so complexity,
  file-length, and suppression ratchets remain enforced.
- Propagate pricing, allowance, rate-card, and threshold identity through every
  refresh entry point so indexed recommendation facts remain current after the
  request-time fallback is removed.
- Add a named local task and CI step for the deterministic dashboard route gate.
- Finish the route inventory, architecture, API, roadmap, and maintainer guidance.

## What must not change

- No public response schema or endpoint rename.
- No benchmark gate for asynchronous Compression Lab completion time.
- No weakening of existing quality, privacy, architecture, or performance limits.
- No ingestion/content-index optimization; that cold-start path remains separate.

## Verification plan

- Focused recommendation availability/parity and server response tests.
- Frontend registry uniqueness and schema-manifest tests plus typecheck.
- Route inventory and dashboard contract tests.
- Deterministic route benchmark at the CI fixture size with enforced budgets.
- Agent Perf comparison for the touched route path.
- Agent Maintainer precommit and CI-equivalent verification.

## Follow-up ratchet work

Keep route thresholds fixed after this migration and treat regressions as query,
index, or cache defects. Future dashboard work should add one registered query
contract and one measured route budget at a time rather than reopening this
cohesive migration plan.

## Rollback plan

Revert this PR. The additive diagnostic covering index can remain safely on user
databases or be dropped independently; it stores no new user data. The prior
request-thread recommendation fallback and non-enforced benchmark behavior will
be restored by the revert.
