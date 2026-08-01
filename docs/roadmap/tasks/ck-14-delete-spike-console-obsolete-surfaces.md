# CK-14 — Delete spike, Console, and obsolete surfaces

**Status:** Blocked on CK-13-03; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Retire obsolete runtime/UI/toolchain paths while preserving owned
oracles and release primitives.

**Dependencies:** CK-13-03. Child sequence: CK-14-01; parallel CK-14-02/03;
CK-14-04.

**Non-goals:** This umbrella is never delegated directly; no partial shims,
replacement UI, or deletion before inventory/approval.

**Invariants:** Sole replacement package, no old imports/paths/database
handling, retained oracles assigned, exact public surface preserved.
Deletion qualification uses the exact locally built candidate selected by
CK-13; external installation verification remains CK-16-owned.

**Required tests/checks:** Child absence/package/full qualification,
CI/review/exact-main.

**Acceptance:** CK-14-04 accepts a clean replacement-only package.

**Failure/rollback:** Restore deletion lanes together; never ship partial
cleanup.

**Cleanup/docs:** Reconcile disposition, package/CI, roadmap, ledger, index.

**Suggested commit:** `refactor: retire obsolete product surfaces`
