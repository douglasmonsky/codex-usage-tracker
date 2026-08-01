# CK-08R0 — Freeze corrective query and scale contracts

**Status:** Ready; not started

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `default corrective-contracts`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze independent truth, runtime paging, benchmark-v2,
supersession, requalification, and shared ownership contracts before code work.

**Why:** CK-08's mechanism proof cannot authorize projections or physical
paging while its semantic and measurement seams share production logic.

**Controls:** Query/evidence, publication, physical decision, and qualification
contracts; exact CK-08 source and evidence.

**Dependencies:** Exact current `origin/main` and retained CK-09 blocker
reproduction.

**Owned files/interfaces:** Architecture and qualification documents,
corrective task status, benchmark-v2 and internal page-executor schemas; no
production code.

**Produces:** `corrective-gates-v1` authority record with explicit version and
requalification sets.

**Independent truth source:** Locked scenario declarations, formula contracts,
and direct code-path reproductions.

**Consumer seam:** CK-08R1/R2/R3, CK-07R1, CK-QG1, and CK-08R4.

**Parallelism:** Serialized first task. No corrective implementation starts
before merge and exact-main verification.

**Non-goals:** Product redesign, schema rewrite, projections, generic SQL,
public surfaces, CK-10 or later work.

**Invariants:** Preserve canonical facts, publication identity, accepted result
envelopes, selectors, cursor identity, and historical evidence.

**Required tests/checks:** Documentation authority, scope/release checks,
`git diff --check`, `just v`, `just vc`, and one final read-only reviewer.

**Acceptance:** Every corrective lane has a closed interface, truth source,
consumer seam, ownership lock, budget, supersession rule, and fail-closed stop.

**Failure/rollback:** Leave CK-09 blocked and revert only this authority change
if it would alter product scope or accepted logical semantics.

**Handoff:** Exact merged SHA and the five Wave-2 tasks made Ready.

**Cleanup/docs:** Reconcile roadmap, ledger, index, qualification, and affected
architecture claims.

**Suggested commit:** `docs: freeze corrective query and scale contracts`
