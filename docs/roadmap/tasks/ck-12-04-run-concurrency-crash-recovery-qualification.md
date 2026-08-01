# CK-12-04 — Run concurrency, crash, and recovery qualification

**Status:** Blocked on CK-12-01

**Parent:** CK-12 umbrella

**Recommended owner:** `test_engineer recovery-lane`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Run publication lock, moving-tail, source lifecycle, rate-card,
artifact promotion, rollback, and crash matrices.

**Why:** Correct happy-path answers do not prove safe publication ownership or
recovery.

**Controls:** CK-12 candidate and publication/refresh/recovery contracts.

**Dependencies:** CK-12-01.

**Owned files/interfaces:** Read-only/fault-injection qualification and lane
evidence; no candidate edits.

**Produces:** Concurrency/recovery lane artifact.

**Independent truth source:** Frozen recovery matrix and database/file
postconditions.

**Consumer seam:** Sidecar, writer, active/rollback artifacts, concurrent
query-only readers.

**Parallelism:** May run with CK-12-02/03/05 on identical candidate.

**Non-goals:** Repairing runtime, compatibility migration, gate changes.

**Invariants:** Prior publication remains readable; no analytical lock from
sidecar recovery; subsequent operation succeeds.

**Required tests/checks:** Every failure cut point, cancellation, crash,
moving-tail, replacement, rate-only change, artifact promotion/rollback.

**Acceptance:** Every recovery postcondition and availability gate passes.

**Failure/rollback:** Retain reproduction and stop; candidate remains disabled.

**Handoff:** Lane digest and exact failed cut point/postcondition.

**Cleanup/docs:** Evidence only.

**Suggested commit:** `test: qualify candidate recovery`
