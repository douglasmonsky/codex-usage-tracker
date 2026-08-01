# CK-12 — Qualify and harden the MVP

**Status:** Blocked on CK-11-04; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Qualify one immutable candidate across correctness, performance,
recovery, packaging, and fresh-agent gates.

**Dependencies:** CK-11-04. Child sequence: CK-12-01; parallel
CK-12-02/03/04/05; CK-12-06.

**Non-goals:** This umbrella is never delegated directly; lanes do not modify
their candidate or weaken gates.

**Invariants:** Identical bytes/fixtures, first failures preserved, only
demonstrated defects fixed, affected lanes rerun, one final reviewer.

**Required tests/checks:** Complete L0-L5, recovery, artifact, installed-agent,
`just v/vc`, hosted CI, exact-main.

**Acceptance:** CK-12-06 records every hard gate passing.

**Failure/rollback:** Candidate stays disabled; create a narrow corrective task.

**Cleanup/docs:** Reconcile qualification, roadmap, ledger, index.

**Suggested commit:** `test: qualify agent kernel mvp`
