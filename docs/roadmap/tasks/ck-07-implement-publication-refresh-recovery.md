# CK-07 — Implement publication, refresh, and recovery

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Publish small tails and large artifacts atomically while keeping
readers available and operations recoverable.

**Why:** This removes long analytical locks, full-tail rebuilds, duplicate jobs,
and inconsistent progress.

**Controls:** `PUBLICATION_REFRESH_RECOVERY.md`, CK-05/CK-06.
**Dependencies:** CK-06.

**Scope and expected files:**

- `publication/planner.py`, `writer.py`, `validation.py`, `recovery.py`;
- dirty-key registry and projection port;
- operational sidecar, lease/job/progress models;
- watcher dirty-hint seam plus bounded reconciliation;
- publication/source-lifecycle/crash/performance tests.

**Schema changes:** Publication, coverage, delta, source cursor, operational
lease/job/pointer tables selected by decision.
**API changes:** Internal setup/refresh operation contract and read-only status
snapshot.

**Non-goals:** Named queries, public MCP tools, model job polling, full
projection set.

**Invariants:** Short analytical transaction; no parse/scan/full derived work
inside `BEGIN IMMEDIATE`; same-snapshot authority; no-change zero analytical
writes; compatible work reused; state/progress coherent; prior publication
readable through every failure.

**Tests/benchmarks:** One-call/tool/32/2,000 tails, complete-history tail,
no-change, moving tail, lifecycle terminalization, rate-only, replacement,
recanonicalization, schema/projection upgrade, full crash matrix, concurrent
read/service start.

**Acceptance:** All publication hard gates pass; one-call/tool complete-history
tails update bounded keys; concurrent reads never fail with database locked;
startup recovery opens reads before sidecar repair writes.

**Failure/rollback:** SQLite rollback for small transaction; select prior valid
artifact/pointer for promotion ambiguity; never repair spike DB.

**Cleanup/docs:** Record actual small-tail limits and recovery error codes.

**Suggested commits:**

1. `feat: add atomic agent-kernel publication`
2. `feat: add durable refresh recovery`
3. `perf: bound ordinary tail publication`
