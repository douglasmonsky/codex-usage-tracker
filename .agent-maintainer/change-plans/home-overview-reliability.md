+++
id = "home-overview-reliability"
kind = "cohesive-migration"
status = "active"
base_ref = "origin/main"
expires = 2026-08-01
allowed_paths = [
  ".agent-maintainer/change-plans/home-overview-reliability.md",
  "CHANGELOG.md",
  "config/dashboard-route-budgets.json",
  "docs/cli-json-schemas.md",
  "docs/releases/0.25.0.md",
  "frontend/dashboard/src/**",
  "scripts/benchmark_dashboard_routes.py",
  "src/codex_usage_tracker/plugin_data/dashboard/react/assets/**",
  "src/codex_usage_tracker/server/status.py",
  "src/codex_usage_tracker/store/home_observed_queries.py",
  "src/codex_usage_tracker/store/home_queries.py",
  "tests/cli/test_dashboard_route_benchmark.py",
  "tests/server/test_server_status.py",
  "tests/store/test_home_queries.py",
]
forbidden_paths = ["config/prod/**", ".env", ".env.*"]
max_changed_files = 30
max_changed_lines = 2300
allow_source_without_test_change = false
requires_tests = true
requires_full_verify = true
ratchet_targets = []
+++

# Cohesive Change Plan: Home Overview Reliability

## Purpose

Keep the Evidence Console Home overview accurate and responsive while optional
recommendation analysis catches up, and remove the persisted-evidence section
from the Home boot path.

## Why this change intentionally large

The fix crosses one compact SQLite query layer, the status payload, the React
contract and page, generated package assets, deterministic performance budgets,
tests, and release documentation. These files form one user-visible load
contract.

## Why this should not be split smaller

Splitting the database fallback from its payload and React changes would either
ship stale zero totals, retain the slow evidence queries, or leave generated
package assets out of sync. The benchmark and docs must land with the behavior
they constrain and describe.

## What allowed to change

- Read exact call and token totals from incrementally maintained thread
  summaries when recommendation materialization is behind.
- Replace the full deduplication diagnostic aggregation with compact exact
  status counts needed by Home and Settings.
- Remove persisted findings and recent-evidence hydration from Home.
- Add a stale-analysis `/api/status` case to the 100,000-row route benchmark
  and enforce its measured latency budget.
- Rebuild deterministic React package assets and update the 0.25.0 user-facing
  documentation.

## What must not change

- Do not trigger refresh, schema initialization, or derived-state rebuilds from
  a read-only Home request.
- Do not weaken canonical accounting, deduplication, privacy, freshness, or
  database integrity.
- Keep Evidence Console deep links and non-Home evidence workflows unchanged.
- Use synthetic fixtures for tests and profiling.

## Verification plan

- Focused Home query, status server, and route benchmark tests.
- Full React lint, typecheck, tests, governance, deterministic assets, and
  bundle budgets.
- Synthetic 100,000-row route benchmark with recommendation generation lag.
- Agent Maintainer full and release/security profiles, built distributions,
  and installed-package smoke.

## Rollback plan

Revert the focused fix commit to restore the prior Home response and generated
assets. No schema, migration, or persisted data changes require rollback.

## Follow-up ratchet work

Keep the new `/api/status` 100,000-row p95 ceiling at or below 0.400 seconds and
lower it only after repeatable synthetic measurements justify a tighter bound.
