# Change Plan: K3 Incremental And Live Ingestion

## Goal

Build one source planner, structural JSONL parser, normalizer, bounded writer,
recoverable refresh lease, and watcher path without restoring derived-state
work.

## Contract

- Explicit refresh is the only first-build trigger.
- No-change, append, moving-tail, replace, truncate, archive, and restore use
  one cursor contract.
- Raw prompts, arguments, output, reasoning, and full paths never enter the
  analytical database.
- Parsing completes outside SQLite write transactions.
- Generations publish atomically; readers retain the prior committed snapshot.
- Compatible work joins one durable lease and stale ownership recovers.
- Writer transactions meet the 50 ms p95 synthetic budget.
- No compression, FTS, analysis, recommendation, OTel, HTTP, MCP, CLI, or
  frontend module is restored.

## Owned Paths

- `src/codex_usage_tracker/kernel/{discovery,parser,normalize,ingest,lease,writer,watcher}.py`
- `tests/kernel/test_ingest_*.py`
- `tests/kernel/test_watcher.py`
- K3 phase gates, manifests, performance/churn records, execution ledger, and
  this change plan.

## Validation

- contract-red lifecycle, privacy, recovery, concurrency, and performance;
- identical unprofiled and agent-perf synthetic workloads;
- K1 accounting/source-lifecycle oracles;
- 100,000-call build, active append, two-owner lease, and writer-lock budgets;
- phase CI, package isolation, and one final read-only review.

## Budget

- Maximum changed files: 37
- Maximum changed lines: 6,000

## Qualified design

- No-change, append, and unique new-source work stay on the active artifact.
- Replacement, truncation, and proven active/archive canonical conflicts use a
  side artifact so failed promotion cannot damage the prior active view.
- Pending generations plus the operational active-generation pointer keep
  multi-transaction 350-row writes invisible to generation-bound readers.
- Initial hydration parses and normalizes at most 1,000 JSONL lines at a time,
  catches up a moving complete-line tail before promotion, and never retains
  the whole history in memory.
- Promotion validates one bounded generation digest exactly once. Every writer
  transaction and promotion is fenced by the durable refresh lease.
- Refresh ownership lives in `lease.py`; its host heartbeat protects long
  parse phases without holding the analytical writer lock.
- The final 100,000-call synthetic build measured 16.051 seconds end to end and
  35.510 ms writer-transaction p95 across 804 transactions.
- K3 changed exactly 37 files and 4,899 lines. The original 32-file
  estimate was amended for required ledger/gate records, `database.py`'s
  bounded generation digest, and repository guidance that retires arbitrary
  file-length churn while preserving Xenon complexity budgets.
