# CK-08R3A — Implement bounded EvidenceService physical queries
**Status:** Conditional Ready after this authority merge exact-main
**Recommended owner:** `worker evidence-physical-query`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Independently reinspect/reapply bounded EvidenceService SQL.
**Blocker:** R3 commit `a28e9cdbff8e48d334712a449fdcee111c725673`/artifact `ae9107eda155a21b9bd9ef5a77971007d00864b772c3a23bc521652b5b17d471` exposed unbounded plans. R3A task `019fbbc0-cd25-7041-a847-b0098dfae29d` changed frozen `service.py` `ea32223d1afd997f310419bff0b6b260193e527c8333c9f561bcab280447dfa3` to selected `718ff7032d050b13cb7fac1f857d0c99879d0ef3b13c57c39b55514fc610a88b`; focused/release passed, `just v` stopped 1391/1 on authority, rollback followed; no review/PR/merge/exact-main/R3.
**Dependencies:** Accepted R0 plus this merge/exact-main. [Supersession authority](../../decisions/evidence/ck08r3a/evidence-service-supersession-authority.json) keeps predecessor exact and successor permitted_not_accepted until evidence.
**Owned files/interfaces:** EvidenceService, focused tests, R3A evidence only; query/contracts/cursor/selectors/DDL/index/publication/schema/projection/public/package/authority forbidden.
**Produces:** Bounded SQL/tests and bound digest evidence; no R3 scale.
**Independent truth source:** Test evaluator imports no production query/helper; applies selector/view/cursor, seven-part order, `limit + 1`.
**Consumer seam:** `EvidenceService.read()` stays one query-only snapshot; keyset/order/limit precede decode.
**Parallelism:** Disjoint from R1A,07R1A,QG1A; fresh task; blocked run is reproduction.
**Non-goals:** DDL/schema/projection/API/budget/timing/R1/QG1/07R1/R3/R4/RG/09.
**Invariants:** Preserve selector/version/view/direction/cursor/publication, ties/missing/late/base/tail, gap-free/query-only/one-snapshot, <=100 rows/16384 bytes; synthetic; wheel <=1,000,000, sdist <=2,000,000.
**Required tests/checks:** First/deep EXPLAIN rejects `SCAN stream`, `MATERIALIZE model_calls_visible`, `AUTOMATIC COVERING INDEX`, `USE TEMP B-TREE FOR ORDER BY`; independent rows/order/decode bound; regressions/authority/GitNexus; `just v/vc`; reviewer/PR/CI/merge/exact-main.
**Acceptance:** Selected source/evidence identity and all bounds pass; generic drift forbidden.
**Failure/rollback:** Divergence/gate/broader-authority need stops; no retry-only/blind copy.
**Handoff:** SHA/PR/digests/plans/measurements/review/CI/exact-main/risks; then fresh `test_engineer evidence-scale` R3.
**Cleanup/docs:** Retain blocker; preserve R3A→R3 and R4 join.
**Suggested commit:** `fix: bound evidence physical queries`
