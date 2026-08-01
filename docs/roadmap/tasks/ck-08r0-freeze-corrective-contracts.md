# CK-08R0 — Freeze corrective query and scale contracts

**Status:** Completed on merge — exact-main verification required in handoff

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

**Dependencies:** Exact `origin/main`
`7fa6e57f1148ac205b530e1e53b0a88aca1bf379`, authority PR #389, and retained
CK-09 blocker reproductions.

**Owned files/interfaces:** Architecture and qualification documents,
corrective task status, benchmark-v2 and internal page-executor schemas; no
production code.

**Produces:** Source-bound, schema-validated
[`corrective-gates-v1`](../../decisions/evidence/ck08r0/corrective-gates-v1.json)
with exact lane seams, locks, evidence schemas, scales, budgets, stops,
requalification sets, and four bounded supersessions.

**Independent truth source:** Locked scenario declarations, formula contracts,
and direct code-path reproductions.

**Consumer seam:** CK-08R1/R2/R3, CK-07R1, CK-QG1, CK-08R4, and CK-08RG.

**Parallelism:** Serialized first task. No corrective implementation starts
before merge and exact-main verification.

**Non-goals:** Product redesign, schema rewrite, projections, generic SQL,
public surfaces, CK-08R1/R2/R3 or CK-07R1/CK-QG1 implementation, CK-09,
CK-10, or later work.

**Invariants:** Preserve canonical facts, publication identity, accepted result
envelopes, selectors, cursor identity, historical evidence, release-size
ratchets, privacy, exact-main, one-reviewer, hosted-CI, and fail-closed rules.

**Required tests/checks:** Schema and semantic contract tests, documentation
authority, scope/release checks, `git diff --check`, `just v`, `just vc`, and
one final comprehensive read-only reviewer.

**Acceptance:** Every corrective lane has a closed interface, truth source,
consumer seam, ownership lock, budget, evidence schema, supersession rule,
precise requalification set, and fail-closed stop.

**Failure/rollback:** Leave CK-09 blocked and revert only this authority change
if it would alter product scope or accepted logical semantics.

**Handoff:** Exact merged SHA and authority digest activate five Conditional
Ready Wave-2 tasks only after exact-main verification; CK-08R4 and CK-08RG
remain uncreated until their joins close.

**Cleanup/docs:** Reconcile roadmap, ledger, index, qualification, and affected
architecture claims.

**Suggested commit:** `docs: freeze corrective query and scale contracts`
