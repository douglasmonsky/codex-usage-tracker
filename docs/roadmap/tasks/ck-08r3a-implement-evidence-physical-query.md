# CK-08R3A — Implement bounded EvidenceService physical queries
**Status:** Conditional Ready after this authority merge exact-main
**Recommended owner:** `worker evidence-physical-query`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Independently reinspect/reapply bounded EvidenceService SQL.
**Blocker:** R3 commit `a28e9cdbff8e48d334712a449fdcee111c725673`/artifact `ae9107eda155a21b9bd9ef5a77971007d00864b772c3a23bc521652b5b17d471` exposed unbounded plans. The authority was reproduced at original base `f3f376fc644a2e3d23c313dd6b7ca4b707c2998b` and is now integrated with disjoint accepted CK-08R1C PR #411 at current exact base `fb0c57886097a6b985d2f321b2de858cbdfc0a97`; it revokes successor `718ff7032d050b13cb7fac1f857d0c99879d0ef3b13c57c39b55514fc610a88b` for inner temp sorts, scale growth, and rate-card page-scope regression, and permits only the new exact source plus required evidence-order DDL/schema identities; no implementation is accepted yet.
**Dependencies:** Accepted R0 plus this merge/exact-main. [Supersession authority](../../decisions/evidence/ck08r3a/evidence-service-supersession-authority.json) keeps predecessor exact and successor permitted_not_accepted until evidence.
**Owned files/interfaces:** EvidenceService and focused tests. The authority permits only the exact `analytical.sql` evidence-order indexes and matching `storage/schema.py` contract digest named in the supersession JSON; all other query/contracts/cursor/selectors/publication/projection/public/package/schema changes remain forbidden.
**Produces:** Bounded SQL/tests and bound digest evidence; no R3 scale.
**Independent truth source:** Test evaluator imports no production query/helper; applies selector/view/cursor, seven-part order, `limit + 1`.
**Consumer seam:** `EvidenceService.read()` stays one query-only snapshot; keyset/order/limit precede decode.
**Parallelism:** Disjoint from R1A,07R1A,QG1A; fresh task; blocked run is reproduction.
**Non-goals:** unbound DDL/schema/projection/API/budget/timing/R1/QG1/07R1/R3/R4/RG/09.
**Invariants:** Preserve selector/version/view/direction/cursor/publication, ties/missing/late/base/tail, gap-free/query-only/one-snapshot, <=100 rows/16384 bytes; synthetic; wheel <=1,000,000, sdist <=2,000,000.
**Required tests/checks:** First/deep forward/backward EXPLAIN rejects `SCAN stream`, `MATERIALIZE model_calls_visible`, `AUTOMATIC COVERING INDEX`, and every `USE TEMP B-TREE FOR ORDER BY`; independent rows/order/decode bound; valid active `rate_card` summary plus empty timeline/calls pages; regressions/authority/GitNexus; `just v/vc`; reviewer/PR/CI/merge/exact-main.
**Acceptance:** The exact source, evidence-order DDL, and schema-contract identities in the authority match byte-for-byte; all bounds and selector compatibility pass; generic drift forbidden.
**Failure/rollback:** Divergence/gate/broader-authority need stops; no retry-only/blind copy.
**Handoff:** SHA/PR/digests/plans/measurements/review/CI/exact-main/risks; then instruct coordinator to resume implementation worker `019fbe2b-20e8-78b2-a687-0231b159d0c7` in a fresh exact-main worktree before any fresh `test_engineer evidence-scale` R3 task.
**Cleanup/docs:** Retain blocker; preserve R3A→R3 and R4 join.
**Suggested commit:** `fix: bound evidence physical queries`
