# CK-07R1 — Correct lifecycle preparation scale

**Status:** Blocked on CK-07R1A

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `feature_worker lifecycle-scale`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Replace repeated per-entity transition scans with equivalent
one-pass grouping and requalify publication-valid scale.

**Why:** The current lifecycle fold is quadratic and an existing
production-shaped preparation attempt exceeded 15 minutes.

**Controls:** Publication/recovery, lifecycle, canonical fact, and benchmark
contracts.

**Dependencies:** CK-07R1A accepted, merged, and exact-main verified; existing
PR #394 refreshed from corrected main and all required CI rerun.

**Owned files/interfaces:** Lifecycle preparation implementation, focused
publication tests, profile/benchmark, and linked CK-07 evidence amendment.

**Produces:** Publication-scale requalification with equivalent fold identity.

**Independent truth source:** Existing lifecycle-fold oracle and committed
database postconditions.

**Consumer seam:** Preparation to `PublicationWriter` to read-only publication.

**Parallelism:** Resume existing task
`019fbb41-804b-7fe2-8987-3d2b9e94a4d5` only after CK-07R1A handoff; other
corrective locks stay disjoint.

**Non-goals:** Writer/pointer/schema redesign, facts, projections, or budget
waivers.

**Invariants:** Same transition versions/folds; prior publication readable;
bounded RSS; synthetic data; no writer recovery regression.

**Required tests/checks:** Focused lifecycle/publication, equivalent results,
standard/production fixtures, five unprofiled samples, 30-day/all-time gates,
`just v/vc`.

**Acceptance:** Work is linear in observations plus prior transitions and all
publication-valid scale gates pass.

**Failure/rollback:** Retain the profile and create one narrow follow-up for a
new dominant blocker; never weaken the gate.

**Handoff:** Evidence digest, profiles, retained first hosted failure, PR #394
CI, exact-main result, and CK-08R4 input.

**Cleanup/docs:** Supersede only affected CK-07/08 scale claims.

**Suggested commit:** `perf: linearize lifecycle preparation`
