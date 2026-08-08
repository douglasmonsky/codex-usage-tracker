# CK-08RG — Authorize CK-09 resumption

**Status:** Blocked on CK-08R4; CK-QG1 is complete

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `default ck09-resume`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Integrate corrective evidence on exact main and issue the only
authorized CK-09 handoff.

**Why:** Readiness must follow executable seams and measured admission, not a
packet status assertion.

**Controls:** All corrective packets, CI, review, and exact-main policy.

**Dependencies:** CK-08R4 and CK-QG1 merged and exact-main verified. CK-QG1
completed at exact main `68050b93`; CK-08R4 remains blocked.

**Owned files/interfaces:** Authority lock, supersession links, final resume
evidence, and task handoff; no feature implementation.

**Produces:** `ck09-resume-gate-v1` and exact CK-09-01 input.

**Independent truth source:** Executable corrective evidence and artifact
digests.

**Consumer seam:** Central plan readiness plus CK-09-01 clean task.

**Parallelism:** Serialized final gate; no other shared authority writer.

**Non-goals:** Projections, public surfaces, CK-10, or historical evidence
rewrites.

**Invariants:** No stale digest, residual full-materialization route,
unmeasured plan, or maintainability bypass.

**Required tests/checks:** Complete affected requalification, `just v`,
`just vc`, hosted CI, one final read-only reviewer, merge and exact-main checks.

**Acceptance:** Every gate passes and CK-09-01 receives the exact measured
candidate list; otherwise CK-09 remains blocked.

**Failure/rollback:** Preserve all evidence and status as blocked.

**Handoff:** PR, merged SHA, CI, exact-main checks, classifications, residuals,
and newly Ready CK-09-01.

**Cleanup/docs:** Reconcile all current-boundary authorities.

**Suggested commit:** `docs: authorize measured ck09 resumption`
