# Change Plan: K2 Schema And Stable Identity

## Goal

Create the schema-v1 analytical cache and owner-only operational sidecar
without restoring the schema-39 runtime or any retired analysis surface.

## Contract

- The analytical database has exactly eight foundational fact tables.
- Refresh jobs, full source paths, and cutover state exist only in the
  owner-only operational sidecar.
- Stable public identities never depend on SQLite row IDs or input order.
- Every connection enables foreign keys and validates integrity.
- Cache creation is side-by-side, atomic, deterministic, and never opens the
  0.25 database.
- Synthetic sensitive paths never enter analytical bytes or exports.
- Generic K1 assignments that cover retired compression, analysis, dashboard,
  and migration behavior are corrected rather than transplanted.

## Owned Paths

- `src/codex_usage_tracker/kernel/{schema,identity,database,operational,models}.py`
- `tests/kernel/test_{schema,identity,database_lifecycle,cutover_control,source_registry_privacy}.py`
- K2 phase gates, package rules, disposition transitions, execution ledger,
  and this change plan.

## Validation

- contract-red K2 tests;
- schema dump, table/index budgets, foreign keys, and integrity;
- identity stability and privacy;
- interrupted creation, reopening, cutover, and rollback;
- exact package isolation and Python 3.10/3.14 phase CI;
- one final read-only review.

## Budget

- Maximum changed files: 30
- Maximum changed lines: 5,000
