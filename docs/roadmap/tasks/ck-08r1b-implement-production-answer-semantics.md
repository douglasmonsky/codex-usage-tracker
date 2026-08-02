# CK-08R1B — Implement production answer semantics
**Status:** Ready after CK-08R1A merge exact-main verification
**Recommended owner:** `worker production-semantics`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Implement R1A Q-REV-03/Q-WF-02 semantics.
**Dependencies:** R1A accepted/merged/exact-main.
**Owned files/interfaces:** Structural derivations/domain tests only; query/evidence/cursor/public/evaluator forbidden.
**Produces:** Exact comparison/boundaries/nulls and closure.
**Independent truth source:** R1A plus synthetic facts; no grading/SQLite/R1C.
**Consumer seam:** `compile_plan_operands` emits final-R1 materializations.
**Parallelism:** R1C after R1A; disjoint locks.
**Non-goals:** Query/public/projection/R3/R4/RG/09.
**Invariants:** No placeholders; unsupported fails closed; CK-08R2 and 19 fail-closed residual plans unchanged; synthetic; sdist <=2,000,000.
**Required tests/checks:** R1A vectors; formula/operand/query/closure; `just v/vc`; reviewer/CI/merge/exact-main.
**Acceptance:** Facts alone drive output; no grading source.
**Failure/rollback:** Revert lock; keep R1 blocked.
**Handoff:** SHA/R1A digest/closure/gates/risks.
**Cleanup/docs:** Final R1 accounting.
**Suggested commit:** `fix: derive supported answer semantics`
