# OPS-REL-025 central-product reliability

## Goal

Make the installed Codex Usage Tracker plugin and core MCP surface coherent,
incremental, concurrency-safe, observable, and independently verifiable before
the static-product removal work begins.

## Allowed scope

- Plugin installation, cache identity, launchers, diagnostics, and installed smoke.
- Core MCP refresh and job-status application paths.
- Generic durable job persistence and its operational SQLite placement.
- Refresh parsing, fixed source boundaries, transaction duration, progress, and timing.
- Synthetic performance/E2E fixtures, release checks, docs, and product budgets.

Task 40 removal paths and Task 41 focused query-plan removal remain out of scope.

## Acceptance

- MCP startup performs no write transaction and succeeds while a synthetic refresh
  writer owns the usage-index write lock.
- Equivalent refresh requests from independent application containers join one
  durable job and can poll monotonic progress/results.
- Refresh work survives the initiating MCP request/process boundary.
- Active JSONL files are parsed only through a fixed complete-line byte boundary;
  concurrently appended rows remain for the next incremental refresh.
- No-change and append-only refreshes do not rebuild historical source rows.
- Long derived-state work reports truthful phase, elapsed time, counts, and heartbeat.
- Analysis calls can read the last committed snapshot while refresh is running and
  report that snapshot's freshness without attempting a competing write.
- Installed two-task core-MCP dogfood proves plugin identity, refresh join/polling,
  incremental hydration, evidence accuracy, and privacy-safe output.
- Synthetic large-index profiling identifies the measured hot phase and establishes
  a bounded lock-duration/performance regression gate.

## Verification

- Focused application/job/store/MCP concurrency and boundary tests.
- Deterministic synthetic no-change, append-during-refresh, interrupted-worker, and
  two-process job tests.
- Agent Perf baseline and post-change profiles on an identical synthetic fixture.
- Packaging, installed-package smoke, release checks, type/lint, complexity/package
  budgets, and the repository's broader qualification suite.
- One final read-only reviewer after the diff and primary validation are stable.
