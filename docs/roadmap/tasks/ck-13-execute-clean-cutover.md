# CK-13 — Execute clean cutover

**Status:** Blocked on CK-12-06; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Select the qualified replacement, prove rollback, and authorize
runtime retirement.

**Dependencies:** CK-12-06. Child sequence: CK-13-01, CK-13-02, CK-13-03.

**Non-goals:** This umbrella is never delegated directly; no deletion,
migration, dual-write, or release.

**Invariants:** Separate databases, no spike fallback/import, untouched
reinstallable 0.28 rollback, explicit maintainer deletion approval.

**Required tests/checks:** Child cutover/rollback matrix, CI/review/exact-main.

**Acceptance:** CK-13-03 passes and records explicit retirement approval.

**Failure/rollback:** Restore/select 0.28 and keep CK-14 blocked.

**Cleanup/docs:** Reconcile cutover messages, roadmap, ledger, index.

**Suggested commit:** `feat: complete clean cutover`
