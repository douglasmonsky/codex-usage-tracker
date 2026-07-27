# Change Plan: K5 Exact Evidence And Live Timeline

## Goal

Resolve stable logical selectors to bounded evidence pages and expose one
persistent, reconnectable, privacy-safe post-commit generation stream.

## Contract

- Thread, turn, call, tool, and allowance selectors resolve through logical
  identity and survive a clean rebuild.
- Summary, timeline, calls, tools, activities, and allowance reads bind to one
  active generation, paginate with generation-bound cursors, and never write.
- Every valid selector has one deterministic relative destination; live mode
  changes only the live flag.
- Journal IDs are monotonic and persistent with bounded replay, heartbeat,
  restart, generation-gap, and snapshot-fallback semantics.
- Refresh publishes only after promotion. Journal failure cannot invalidate an
  analytical generation and is surfaced as snapshot-required.
- Evidence and stream payloads exclude prompt, reasoning, raw arguments,
  output, shell bodies, secrets, and full local paths.

## Owned Paths

- `src/codex_usage_tracker/kernel/evidence/`
- `src/codex_usage_tracker/kernel/live/`
- K5 integration seams in ingestion and the operational schema
- `tests/kernel/evidence/`
- `tests/kernel/live/`
- K5 scope, manifest, package, CI, churn, and execution-ledger records

## Validation

- selector, invalid-scope, rebuild, cursor, privacy, and read-only contracts;
- replay retention, burst, slow-client, disconnect, restart, rollover, and
  journal-failure contracts;
- 100,000-row timeline first-page p95 at or below 500 ms;
- package isolation, CI-equivalent gate, and one final read-only review.

## Budget

- Maximum changed files: 28 (the implementation inventory is 25; the
  mandatory development-efficiency ledger and its policy test add two, and
  the CI performance-step regression test adds one)
- Maximum changed lines: 4,500
