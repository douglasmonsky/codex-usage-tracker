# CK-07R1A0 — Freeze lifecycle planner/recovery path authority

**Status:** Completed on merge; path authority exact-main verified at `519b503aa3b23019033b6481687c08b23fc6c31e`;
the exact CK-07 successor
source/runtime transition is pending merge and exact-main verification, so the
existing worker remains held

**Release-candidate package ceilings:** sdist remains at most 2,000,000
bytes and wheel remains at most 1,000,000 bytes. The historical 828000/383000
values remain historical facts in the package-budget supersession evidence.

**Parent:** Corrective prerequisite for CK-07R1

**Recommended owner:** `default lifecycle-path-authority`; Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze the reachable planner/recovery qualification path exposed by
the CK-07R1 lifecycle-scale blocker.

**Why:** The retained all-profile receipt manually constructed
`APPEND_SAFE_SMALL` plans and called `PublicationWriter` directly. It proves
writer behavior only; it does not prove reachable planner selection or
read-first recovery semantics.

**Dependencies:** CK-QG1A0 accepted, merged, and exact-main verified at
`eb3ded92408d9549d4a4c15c69c045cc3845689c`; CK-07R1A accepted, merged, and
exact-main verified at `4d8074952f679877f2b4fbb3e89c51015e96a197`; CK-08R0
remains accepted.

**Owned files/interfaces:** Authority/docs/tests only. The strict Authority v2
contract is
[lifecycle-path-authority.json](../../decisions/evidence/ck07r1a0/lifecycle-path-authority.json)
with its schema. The linked [source-digest authority](../../decisions/evidence/ck07r1a0/lifecycle-source-digest-authority.json)
and its schema freeze the exact predecessor/successor transition. The
[versioned shared successor overlay](../../decisions/evidence/ck07r1a0/shared-successor-overlay-authority-v1.json)
preserves accepted CK-08R1B v1, CK-08R1 evidence, and CK-QG1 authority bytes
while reconciling their consumers with only the complete exact successor. The retained
CK-07R1 implementation/profile/evidence diff is read-only evidence;
accepted R3A preparation `6689d61f…` remains historical, current R1B
preparation `7d1831ff…` is the live predecessor, and only the exact
`66c015de…` preparation plus `1c7e1ea7…` benchmark and `a8de9667…` lifecycle
test may enter worker prequalification. Historical `d192c858…`, mixed cohorts,
and every other digest fail closed; prior R3A candidate `e204e0da…` remains
superseded and forbidden. The selected cohort does not claim runtime acceptance.
Linked evidence `36eb76ca…` and canonical fixture identities remain unchanged.
The linked run-invocation authority is
`docs/decisions/evidence/ck07r1a0/lifecycle-run-invocation-authority.json`;
it adds no runtime implementation, freezes the corrected argv guard,
720-second wrapper timeout, four-path non-overwriting preflight, pre-release
child `os._exit(71)` isolation with ignored wait signals, positive-PID cleanup,
and unique same-directory temporary-ledger cleanup with durable consumed/no-retry
terminal evidence. Temporary parent signal handlers remain installed through
bounded reap, evidence, receipt, and terminal persistence and restore only
after the terminal-state attempt. The authority keeps the
retained candidate runtime-unqualified.

**Produces:** A frozen entry-path contract, finite source/runtime state machine,
APPEND_SAFE_SMALL selection rule,
independent lifecycle oracle/postconditions, exact source/diff identity,
allowed lifecycle symbol/file scope, one-run authorization condition,
preserved attempt ledger, and exact worker revalidation requirements.

**Independent truth source:**
`tests/agent_kernel/contracts/reference/lifecycle.py::fold_lifecycle`,
independent synthetic transition vectors, and committed publication/recovery
postconditions; no SQLite-derived expected answers.

**Consumer seam:** The future CK-07R1 requalification harness must enter
read-first recovery, obtain its plan from `plan_refresh` before the writer lock,
and pass that selected plan through `PublicationWriter.publish_with_pointer`
and `publish_small_with_pointer` for small publications. The same run must bind
`ReadSelection.head.publication_id` to `RefreshIntent.parent_publication_id`,
`PublicationPlan.parent_publication_id`,
`SmallPublicationRequest.expected_active_publication_id`, and the committed
publication chain; any mismatch fails closed rather than allowing stitched
artifacts.

**Parallelism:** Sole authority owner. Do not create or dispatch CK-07R1,
CK-08R4, CK-08RG, CK-09, or any other dependent task from this packet.

**Non-goals:** Lifecycle implementation, benchmark execution, production
qualification, PR #394 changes, writer/planner/recovery code, budgets,
schemas/DDL/query/evidence services, projections, releases, or real/private
Codex data.

**Invariants:** CK-07R1A remains accepted at `4d807495…`; CK-07R1 remains
`blocked_hold` with no launch/output/token consumption. The exact
predecessor digest is
`7d1831ff5229e8e2a9819f0bd155d116ad97c3c3579bfa0444f791fe81e81feb` and the
permitted-not-accepted retained successor digest is
`66c015de949a6c380bd49964cb6c48c30dee64ecb14074b480837c44024328ea`
only with benchmark `1c7e1ea7…` and lifecycle test `a8de9667…`; historical
`d192c858b48e44b5aa7a7e39ef524e5ec2f08085655fe485639f5e875a727aa1` is
revoked and direct use fails closed; generic or different digest drift fails
closed; linked evidence is
`36eb76ca286b3448037857b701caab9371afc704a22bc479523149e70aca41eb`; the
wrapper timeout is exactly 720 seconds while the five budgets remain
`5000/120000/100/500/500` ms; the malformed 62-character dispatch value is
revoked, never authoritative, and never used; the source-digest and
run-invocation authorities must be accepted, merged, and exact-main verified
before a future CK-07R1 requalification may proceed; every prior attempt and its
identity/timestamp/failure remains visible; receipt
`935e4427b93e67c5ca649b773b0b3895dafac87f49bc76d7ed8917dff2f0250d` remains
writer-only evidence and is never reused or upgraded. The old argv-guard
attempt is preserved as `pre_child_argv_guard_failure`, not a launch; no old
candidate invocation may recur.
The current finite state is `authority_main`; no worker resumes from this
packet, no receipt can claim qualification, and final acceptance additionally
requires worker PR merge and exact-main verification.

**Required tests/checks:** Real non-launching subprocess argv integration test;
strict authority-schema and exact-record negative-mutation tests; DAG/ledger/
status tests; exact scope-manifest tests; evidence identity and `git diff
--check`; `just v` and `just vc` as required by repository packet rules; one
independent read-only review maximum; exactly one PR; hosted CI; squash merge
only when every required job passes; attached exact-main verification. No E2E,
benchmark, worker resume, token consumption, or downstream dispatch occurs in
this authority.

**Acceptance:** The authority artifact validates, exact identities and run
accounting are preserved, only the retained CK-07R1 authority additions are
bound, the stale failed PR #394 is explicitly superseded read-only, and CK-07R1
is Conditional Ready only after the linked authorities merge and exact-main
verification. The planner-valid receipt is a future successor acceptance
output, not a pre-dispatch dependency. This packet does not run or authorize a
production qualification run by itself.

Earlier CK-07R1 wording that says to resume, refresh, or rerun PR #394 is
historical provenance and is superseded by this read-only policy.

**Failure/rollback:** Preserve the exact candidate, evidence, and failed
attempts; stop closed on any identity, scope, DAG, schema, review, CI, merge,
or exact-main mismatch. Do not weaken a budget or infer publication-validity
from a manually forced plan.

**Handoff:** Coordinator `019fbeb3-00d5-7f80-a8c2-c8f469385312` and parent
`019fbea6-66b5-71e0-b85a-b6654fd414c5` receive the merged SHA, source-digest
and run-invocation authority paths, exact candidate source/diff identity, preserved
attempts/digests, validation/reviewer/CI/exact-main results, and unchanged
downstream gates.

**Cleanup/docs:** CK-07R1 owns the implementation/requalification successor;
the retained CK-07R1 worktree, PR #394, and historical worktrees remain
read-only evidence.

**Suggested commit:** `docs: freeze lifecycle source digest authority`
