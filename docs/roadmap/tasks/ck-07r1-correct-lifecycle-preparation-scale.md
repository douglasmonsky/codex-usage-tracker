# CK-07R1 — Correct lifecycle preparation scale

**Status:** `blocked_hold`; CK-07R1 remains unlaunched until a later exact-main reapplication produces a new CK-07 preparation digest

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `feature_worker lifecycle-scale`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Run authority:** The linked run-invocation authority remains blocked/no-run
and preserves the one-shot launch contract.

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Replace repeated per-entity transition scans with equivalent
one-pass grouping and requalify publication-valid scale.

**Why:** The current lifecycle fold is quadratic and an existing
production-shaped preparation attempt exceeded 15 minutes.

**Controls:** Publication/recovery, lifecycle, canonical fact, and benchmark
contracts.

**Dependencies:** CK-07R1A accepted, merged, and exact-main verified at
`4d8074952f679877f2b4fbb3e89c51015e96a197`; CK-07R1A0 path authority remains
historical; and the linked finite source/runtime authorities remain
`blocked_hold` with the one-run token unspent/unavailable. Exact-main
preparation `408d18e4…` is the only live source before R3A. Preparation
`e204e0da…` is permitted only inside the complete CK-08R3A cohort and is not a
direct CK-07 candidate. Historical `d192c858…` is retained read-only, revoked
for the new base, and forbidden for direct use. After accepted R3A exact-main,
the existing worker must start in a fresh worktree, deliberately reapply its
retained lifecycle diff onto the new preparation base, derive a new exact
preparation digest, and update CK-07 source authority before any end-to-end
run. PR #394 head `98a9b5b82951d136644a5fe5f8a70d320131ba08` is a stale failed
read-only witness and is not refreshed, rerun, or merged.

**Owned files/interfaces:** Lifecycle preparation implementation, focused
publication tests, profile/benchmark, and linked CK-07 evidence amendment;
the current authority binds the live preparation `408d18e4…`, the shared R3A
preparation `e204e0da…` only as a conditional two-state source, retained
benchmark `f173837d…`, lifecycle test `b6468b60…`, linked evidence `36eb76ca…`,
and the 720-second wrapper timeout without executing the worker. No CK-07
successor is currently selected for runtime use.

**Produces:** Publication-scale requalification with equivalent fold identity.

**Independent truth source:** Existing lifecycle-fold oracle and committed
database postconditions.

**Consumer seam:** Preparation to `PublicationWriter` to read-only publication.

**Parallelism:** Resume only the existing stopped CK-07R1 worker after the
R3A cohort is accepted and exact-main verifies, using an exact-main START, a
fresh worktree, and deliberate reapplication of only the retained lifecycle
diff onto the new R3A preparation base. Historical `d192c858…` cannot be
reapplied directly.
Never rebase, stash,
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
`just v/vc`; authority/schema/DAG/scope exact-record negative checks covering
the finite state transitions and real non-launching subprocess argv guard; no
E2E or benchmark run in the authority reconciliation.

**Acceptance:** Work is linear in observations plus prior transitions and all
publication-valid scale gates pass through the CK-07R1A0 reachable path and
the frozen CK-07R1A0 run-invocation contract. The existing worker must
revalidate the exact predecessor-to-successor digest
transition, bind every frozen path and prior identity, produce the
planner-valid receipt, and consume at most one new end-to-end run. The still-
unspent `maximum_new_end_to_end_runs=1` token can fund exactly one first
successful child launch only after the authority merge/exact-main gate and all
worker gates pass; this is not a retry, restart, or replacement of a launched
process. Receipt
absence before dispatch is not a blocker; receipt absence or invalidity at
successor acceptance remains fail-closed.

**Failure/rollback:** Retain the profile and create one narrow follow-up for a
new dominant blocker; never weaken the gate.

**Handoff:** Evidence digest, profiles, retained first hosted failure, PR #394
CI, exact-main result, and CK-08R4 input.

**Cleanup/docs:** Supersede only affected CK-07/08 scale claims.

**Suggested commit:** `perf: linearize lifecycle preparation`
