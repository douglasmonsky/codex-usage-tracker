# CK-09 — Admit projections and complete named plans

**Status:** Blocked on CK-08R0 through CK-08RG; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Admit only measured residual projections and qualify every named plan.

**Dependencies:** CK-08RG. Child sequence: CK-09-01; eligible CK-09-02/03/04;
CK-09-05; CK-09-06.

**Non-goals:** This umbrella is never delegated or implemented directly.
Provisional 18-plan classification is not admission.

**Invariants:** Exact fact-backed equivalence, bounded dirty maintenance,
current-only projections, attributed storage/WAL/fanout/tail, no generic SQL.

**Required tests/checks:** Child packet gates plus final all-plan, publication,
recovery, performance, payload, CI, review, and exact-main qualification.

**Acceptance:** CK-09-06 accepts every admitted projection and all named plans;
otherwise this parent remains blocked.

**Failure/rollback:** Remove failed admissions/bindings, preserve evidence, and
do not start CK-10.

**Cleanup/docs:** Reconcile query/physical contracts, roadmap, ledger, index.

**Suggested commit:** `feat: complete qualified projection plans`
