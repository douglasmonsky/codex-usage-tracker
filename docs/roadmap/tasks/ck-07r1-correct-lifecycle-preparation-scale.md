# CK-07R1 — Correct lifecycle preparation scale

**Status:** Conditional Ready after the source-digest authority merges and exact-main verifies; worker pre-run gates remain required

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

**Dependencies:** CK-07R1A accepted, merged, and exact-main verified at
`4d8074952f679877f2b4fbb3e89c51015e96a197`; CK-07R1A0 path authority accepted
at exact main `519b503aa3b23019033b6481687c08b23fc6c31e`; and the linked
source-digest authority accepted, merged, and exact-main verified. The worker
must then start from that exact merged main and reapply the retained candidate,
revalidating predecessor and successor digests before any end-to-end run. PR #394 head
`98a9b5b82951d136644a5fe5f8a70d320131ba08` is a stale failed read-only
witness and is not refreshed, rerun, or merged.

**Owned files/interfaces:** Lifecycle preparation implementation, focused
publication tests, profile/benchmark, and linked CK-07 evidence amendment.

**Produces:** Publication-scale requalification with equivalent fold identity.

**Independent truth source:** Existing lifecycle-fold oracle and committed
database postconditions.

**Consumer seam:** Preparation to `PublicationWriter` to read-only publication.

**Parallelism:** Resume only the existing CK-07R1 worker after this authority
merges and exact-main verifies, using an exact-main START, a fresh worktree,
and deliberate reapplication of the retained candidate. Never rebase, stash,
reset, clean, delete, overwrite, or mutate the witness; do not create a
replacement worker task. The planner-valid receipt is produced by that worker
and is required for acceptance, not for authority completion; other corrective
locks stay disjoint and no downstream packet becomes Ready here.

**Non-goals:** Writer/pointer/schema redesign, facts, projections, or budget
waivers.

**Invariants:** Same transition versions/folds; prior publication readable;
bounded RSS; synthetic data; no writer recovery regression.

**Required tests/checks:** Focused lifecycle/publication, equivalent results,
standard/production fixtures, five unprofiled samples, 30-day/all-time gates,
`just v/vc`.

**Acceptance:** Work is linear in observations plus prior transitions and all
publication-valid scale gates pass through the CK-07R1A0 reachable path. The
existing worker must revalidate the exact predecessor-to-successor digest
transition, bind every frozen path and prior identity, produce the
planner-valid receipt, and consume at most one new end-to-end run. Receipt
absence before dispatch is not a blocker; receipt absence or invalidity at
successor acceptance remains fail-closed.

**Failure/rollback:** Retain the profile and create one narrow follow-up for a
new dominant blocker; never weaken the gate.

**Handoff:** Evidence digest, profiles, retained first hosted failure, PR #394
CI, exact-main result, and CK-08R4 input.

**Cleanup/docs:** Supersede only affected CK-07/08 scale claims.

**Suggested commit:** `perf: linearize lifecycle preparation`
