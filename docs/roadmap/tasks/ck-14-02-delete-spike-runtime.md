# CK-14-02 — Delete the spike runtime

**Status:** Blocked on CK-14-01

**Parent:** CK-14 umbrella

**Recommended owner:** `worker spike-deletion`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Remove only the manifest-approved frozen spike runtime, legacy data
paths, and owned obsolete tests.

**Why:** Dead runtime code recreates package and agent-maintenance collisions.

**Controls:** CK-14-01 deletion set and retained-oracle map.

**Dependencies:** CK-14-01 merged and exact-main verified.

**Owned files/interfaces:** Exact spike/runtime deletion paths; package/CI
manifests remain integrator-owned.

**Produces:** Spike absence/import-scan evidence.

**Independent truth source:** Retirement manifest and replacement tests.

**Consumer seam:** Installed replacement import/runtime path.

**Parallelism:** May run with CK-14-03 from the same base.

**Non-goals:** Console/frontend/Node deletion, package/CI integration,
compatibility shims.

**Invariants:** Retained oracles/release primitives preserved; no old database
handling or imports remain.

**Required tests/checks:** Focused replacement tests, static import/path scans,
retained-oracle checks, `just v/vc`.

**Acceptance:** All approved spike paths are absent and replacement behavior
remains green.

**Failure/rollback:** Revert the deletion lane; never add a shim.

**Handoff:** Deletion diff and absence evidence to CK-14-04.

**Cleanup/docs:** Integrator owns final disposition updates.

**Suggested commit:** `refactor: remove retired spike runtime`
