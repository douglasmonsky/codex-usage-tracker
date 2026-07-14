# Dashboard Diagnostic Refresh Jobs

## Purpose

Move explicit dashboard diagnostic refreshes off synchronous request threads and
onto the shared dashboard analysis-job lifecycle described by PR 4 of the
dashboard query-pipeline roadmap.

## Why this change is intentionally large

The start/status HTTP contract, process-owned worker registry, persisted
snapshot refresh callbacks, frontend polling, visible module progress,
generated dashboard assets, route inventory, integration tests, and public API
documentation must agree on one lifecycle. Splitting those layers would either
ship a blocking route, a client that cannot consume the job handle, or an
undocumented contract.

## What is allowed to change

- Shared process-local lifecycle and HTTP adapters for diagnostic jobs.
- Explicit full and section diagnostic refresh route behavior.
- Diagnostic snapshot progress callbacks and persisted-result reloads.
- Diagnostics and Investigator refresh polling and progress presentation.
- Synthetic tests, generated React assets, route inventory, and dashboard/API
  documentation required by that behavior.

## What must not change

- Stored diagnostic snapshot payload schemas or aggregate-only privacy rules.
- Ordinary usage refresh, parser, pricing, allowance, CLI, or MCP behavior.
- Existing persisted diagnostic facts or source-log retention policy.
- Production credentials, release metadata, or unrelated dashboard design.

## Verification plan

- Test worker deduplication, monotonic progress, observer independence,
  structured failures, token protection, and missing jobs.
- Exercise a real localhost POST/start, GET/status, and persisted-snapshot reload
  cycle.
- Test Diagnostics and Investigator granular progress while stored evidence
  remains visible.
- Run Ruff, Mypy, dashboard lint/typecheck/tests/governance/build, the focused
  Python server/diagnostic suite, release checks, and the full Agent Maintainer
  verifier.

## Rollback plan

Revert this PR. Persisted snapshots remain compatible because the change only
replaces explicit refresh transport and orchestration; stored read endpoints
and snapshot schemas are unchanged.

## Follow-up boundary

PR 4B may expose the existing persistent Compression Lab lifecycle and compact
profile through the dashboard. PR 5 owns cache retention, invalidation, query
plans, and warm/cold budgets. Those changes are intentionally excluded here.
