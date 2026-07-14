+++
id = "dashboard-compression-lab-jobs"
kind = "cohesive-migration"
status = "complete"
base_ref = "origin/main"
expires = 2026-07-28
allowed_paths = [
  ".agent-maintainer/change-plans/dashboard-compression-lab-jobs.md",
  "config/vulture-whitelist.py",
  "docs/architecture/decisions/0011-compression-dashboard-adapter.md",
  "docs/cli-json-schemas.md",
  "docs/dashboard-guide.md",
  "docs/dashboard-query-pipeline-refactor-roadmap.md",
  "docs/dashboard-route-inventory.md",
  "docs/mcp.md",
  "docs/privacy.md",
  "frontend/dashboard/src/**",
  "scripts/benchmark_dashboard_routes.py",
  "src/codex_usage_tracker/compression/jobs.py",
  "src/codex_usage_tracker/plugin_data/dashboard/react/assets/**",
  "src/codex_usage_tracker/plugin_data/docs/dashboard-guide.html",
  "src/codex_usage_tracker/server/**",
  "src/codex_usage_tracker/store/compression_runs.py",
  "tests/cli/test_dashboard_route_benchmark.py",
  "tests/compression/test_jobs.py",
  "tests/dashboard/test_dashboard_compression_server.py",
  "tests/playwright/dashboard-react.spec.mjs",
  "tests/server/test_compression_routes.py",
  "tests/server/test_route_inventory.py",
  "tests/server/test_server_routes.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 50
max_changed_lines = 2800
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++
# Cohesive Change Plan: Dashboard Compression Lab Jobs

## Purpose

Complete PR 4 of the dashboard query-pipeline roadmap by exposing the existing
persistent Compression Lab lifecycle to the dashboard without duplicating its
detectors, estimators, cache, or public payload builders.

## Scope

- Add authenticated localhost HTTP adapters for Compression Lab start, status,
  and profile reads.
- Declare and document the one-way server-to-compression adapter dependency in
  Tach and ADR 0011; compression remains independent of HTTP types.
- Return the existing `codex-usage-tracker-compression-api-v1` payloads used by
  MCP. The dashboard server must not introduce a second profile schema.
- Add the routes to the maintained route inventory with async-start, read-only
  polling, persisted-profile, and result-bound metadata.
- Keep route-profile metadata types separate from the concrete inventory so
  adding endpoint classifications does not grow the inventory past its ratchet.
- Add source- and scope-aware TanStack Query options for completed profiles and
  an abortable user-action observer for transient status polling.
- Add a dedicated desktop Compression Lab workspace that:
  - reads an existing exact-scope profile without starting work implicitly;
  - starts or refreshes a persistent run only from an explicit user action;
  - polls monotonic detector progress without cancelling the shared worker when
    the browser observer disappears;
  - renders observed exposure, overlap-adjusted low/likely/high savings,
    detector-family summaries, coverage, cache state, warnings, and caveats
    directly from the shared compact profile;
  - presents structured missing, interrupted, failed, and partial-success
    states with exact next actions.
- Update generated packaged dashboard assets and public documentation.

## Explicit Non-Scope

- No new detector, estimator, attribution, simulation, or compression schema.
- No candidate-detail or excerpt UI in this PR.
- No raw or indexed content in browser caches or normal dashboard responses.
- No new server cache. PR 5 owns response caching and query-plan hardening.
- No replacement of the existing Python HTTP server.

## Architecture

The server adapter parses the dashboard scope and delegates to
`start_compression_analysis`, `compression_status`, or `compression_profile`.
Those application services remain the only lifecycle/profile implementation and
continue to serve MCP callers. The React transport validates the shared schema,
uses the server-provided poll delay, and reloads the completed profile by run ID.
Completed profiles use source- and scope-aware query keys. Transient status
remains in the explicit action observer rather than browser persistence, so
navigation can stop polling locally while the persistent process worker
continues.

## Test-First Sequence

1. Add failing server adapter and route-inventory tests proving token checks,
   exact shared payload parity, scope parsing, async start, and read-only status.
2. Implement the server routes and rerun focused Python tests.
3. Add failing React transport/query tests for profile lookup, start/status poll,
   source/scope identity, abort behavior, and structured errors.
4. Implement the transport and query layer.
5. Add failing page/navigation tests for cached, cold, running, completed,
   warning, and failure states.
6. Implement the workspace and visual treatment, rebuild packaged assets, and
   run desktop browser checks.

## Verification

- Focused Python server, compression, route inventory, and real HTTP tests.
- Focused React API, query, page, navigation, and shell tests.
- Dashboard verify, desktop Playwright, release readiness, and `git diff --check`.
- Agent Maintainer precommit and full profiles.
- Agent Perf evidence for a deterministic dashboard start/status/profile route
  workload, with unprofiled timings reported separately.

Recorded evidence:

- 400,000 synthetic calls: 2.9 ms cold start handle, 6.03 s completed
  detector run, 72 ms active-status p95, and 261 ms active-status maximum.
- Exact completed-profile reads: 4.0 ms warm-start p95, 1.3 ms status p95,
  and 1.3 ms profile p95, with compact payloads below 2.6 KB.
- Agent Perf run `20260714T094938Z-90e678ab` used the identical 100,000-row,
  10-iteration dashboard benchmark as the unprofiled validation run.
- Desktop Playwright covers explicit start, measurable progress, completed
  profile hydration, token authentication, no page errors, and no
  document-level overflow.

## Follow-Up Boundary

PR 5 owns immutable response caching, source-generation invalidation hardening,
query-plan evidence, payload budgets, and coalescing/performance ratchets. PR 6
owns legacy cleanup, CI enforcement, and the final requirement audit.
