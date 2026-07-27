# Change Plan: K4 Bounded Query Engine

## Goal

Build one typed, generation-consistent, read-only query service for the seven
kernel datasets and a pure phase segmenter. The consuming model owns inference.

## Contract

- Every single or batched request binds once to the operational active path and
  generation, then executes inside one analytical read transaction.
- Requests use allowlisted datasets, operations, dimensions, measures, filters,
  ordering, limits, and opaque generation-bound cursors.
- Responses report stable plan identity/version, normalized scope, matched and
  returned counts, truncation/cursor, elapsed time, grade/coverage, and evidence
  selectors.
- Unknown or unbounded requests and unsupported cross-products fail before SQL.
- Queries never refresh, write, inspect raw content, or author narrative.
- Phase segmentation is pure, versioned, deterministic, and includes basis,
  confidence, unknown fallback, and token attribution.

## Owned Paths

- `src/codex_usage_tracker/kernel/query/`
- `tests/kernel/query/`
- K4 phase-gate, package, scope, performance, churn, and execution-ledger
  records.

## Validation

- contract-red typed-contract, generation, read-only, cursor, plan, and phase
  tests;
- accounting-oracle equivalence and named plan explain assertions;
- 100,000-call status/common/comparison/concentration budgets;
- package isolation, CI-equivalent gate, and one final read-only review.

## Budget

- Maximum changed files: 24
- Maximum changed lines: 4,500

The file allowance was raised from 22 to 24 after final review required the
machine-readable churn-policy test and release-checker coverage to change with
their owning records. The implementation remains below this amended ceiling.
