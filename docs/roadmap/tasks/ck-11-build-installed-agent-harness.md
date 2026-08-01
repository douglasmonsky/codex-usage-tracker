# CK-11 — Build exact installed-agent harness

**Status:** Blocked on CK-10-05; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Automate exact artifact install and fresh CLI/Desktop/default/lower
model trials into one closed scorecard.

**Dependencies:** CK-10-05. Child sequence: CK-11-01; parallel CK-11-02/03;
CK-11-04.

**Non-goals:** This umbrella is never delegated directly; fake-only or
source-checkout results never count as installed qualification.

**Invariants:** Exact hashes, isolated synthetic workspace, fresh tasks,
deadlines/cancellation/cleanup, bounded body-free records.

**Required tests/checks:** Child gates plus complete matrix, deterministic
scorecard, privacy checks, CI/review/exact-main.

**Acceptance:** CK-11-04 emits a valid scorecard from one exact bundle.

**Failure/rollback:** Bundle remains unqualified and CK-12 blocked.

**Cleanup/docs:** Reconcile qualification plan, roadmap, ledger, index.

**Suggested commit:** `test: complete installed agent harness`
