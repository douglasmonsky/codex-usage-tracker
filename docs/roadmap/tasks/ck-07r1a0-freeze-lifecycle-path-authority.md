# CK-07R1A0 — Freeze lifecycle planner/recovery path authority

**Status:** Completed on merge; exact-main verified at `519b503aa3b23019033b6481687c08b23fc6c31e`; CK-07R1 is Conditional Ready after this transition authority exact-main

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
with its schema. The retained CK-07R1 implementation/profile/evidence diff is
read-only evidence.

**Produces:** A frozen entry-path contract, APPEND_SAFE_SMALL selection rule,
independent lifecycle oracle/postconditions, one-run authorization condition,
preserved attempt ledger, and exact scope bindings.

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

**Non-goals:** Lifecycle implementation, benchmark correction, production
qualification, PR #394 changes, writer/planner/recovery code, budgets,
schemas/DDL/query/evidence services, projections, releases, or real/private
Codex data.

**Invariants:** CK-07R1A remains accepted at `4d807495…`; CK-07R1 becomes
Conditional Ready only after this authority is accepted, merged, and exact-main
verified; the five budgets remain `5000/120000/100/500/500` ms; every prior
attempt and its identity/timestamp/failure remains visible; receipt
`935e4427b93e67c5ca649b773b0b3895dafac87f49bc76d7ed8917dff2f0250d` remains
writer-only evidence and is never reused or upgraded.

**Required tests/checks:** Strict authority-schema and negative-mutation tests;
DAG/ledger/status tests; exact scope-manifest tests; evidence identity and
`git diff --check`; `just v` and `just vc` as required by repository packet
rules; one final read-only review; hosted CI; squash merge; attached
exact-main verification.

**Acceptance:** The authority artifact validates, exact identities and run
accounting are preserved, only the two retained CK-07R1 scope additions are
bound, the stale failed PR #394 is explicitly superseded read-only, and CK-07R1
becomes Conditional Ready only after this authority's merge and exact-main
verification. The planner-valid receipt is a future successor acceptance
output, not a pre-dispatch dependency. This packet does not run or authorize a
production qualification run by itself.

Earlier CK-07R1 wording that says to resume, refresh, or rerun PR #394 is
historical provenance and is superseded by this read-only policy.

**Failure/rollback:** Preserve the exact candidate, evidence, and failed
attempts; stop closed on any identity, scope, DAG, schema, review, CI, merge,
or exact-main mismatch. Do not weaken a budget or infer publication-validity
from a manually forced plan.

**Handoff:** Coordinator `019fbeb3-00d5-7f22-ba65-ae4672838140` and parent
`019fbea6-66b5-71e0-b85a-b6654fd414c5` receive the merged SHA, Authority v2
path, exact scope additions, preserved attempts/digests, validation/reviewer/
CI/exact-main results, and unchanged downstream gates.

**Cleanup/docs:** CK-07R1 owns the implementation/requalification successor;
the retained CK-07R1 worktree, PR #394, and historical worktrees remain
read-only evidence.

**Suggested commit:** `docs: freeze lifecycle path authority`
