# CK-07 — Implement publication, refresh, and recovery

**Status:** Completed
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

## Execution record

CK-07 is implemented against database-v1 and the CK-06 change-set boundary.
The durable evidence is
[`publication-refresh-recovery-evidence.json`](../../decisions/evidence/ck07/publication-refresh-recovery-evidence.json).

The measured small path admits at most 32 complete records and uses one
`BEGIN IMMEDIATE` transaction. A 2,000-record tail is therefore
`append_safe_large`: it builds and validates an isolated artifact while the
prior publication remains readable, then performs a short fenced activation.
Five unprofiled local repetitions measured 2,000-record activation p95 at
24.052 ms after full candidate validation and candidate digest/fsync
preflight. The deliberately forced
short-writer diagnostic remains recorded as rejected evidence; it is not the
selected route.

Implemented recovery includes initial generation-one publication, active and
rollback validation, parent/source/generation fencing, PID plus process-start
lease ownership, compatible-operation joining, bounded host waits, canonical
pointer replacement with file and directory fsync, read-first startup repair,
dead-job and paginated-intent reconciliation, and ownership/age-gated cleanup.
The final read-only review produced five findings; all five were accepted and
corrected, including complete incremental coverage/accounting, fenced
small-publication pointer advancement, full isolated-artifact reconciliation,
and abrupt-process recovery gaps. Query does not import or invoke refresh,
and no model polling surface was added.

The CK-04 growth repetitions 3 and 4 remain explicitly waived. CK-07 makes no
strict-v2 aggregate claim. CK-08 query/evidence, projections and named plans,
public MCP/setup/CLI/skill surfaces, release, deployment, and optional CK-15
remain outside this packet.
