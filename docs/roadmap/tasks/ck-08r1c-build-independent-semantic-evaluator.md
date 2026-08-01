# CK-08R1C — Build independent semantic evaluator
**Status:** Blocked on CK-08R1A
**Recommended owner:** `worker independent-evaluator`; Sol-class
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md); [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md); [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)
**Goal:** Independently evaluate all 80 variants.
**Dependencies:** R1A accepted/merged/exact-main.
**Owned files/interfaces:** Test evaluator/import guards only; production, SQLite/replay, R1B, grading, authority forbidden.
**Produces:** Rows/grades/order/evidence, Recursive closure, independence runs.
**Independent truth source:** R1A schemas plus synthetic facts; no production helpers.
**Consumer seam:** R1 compares identical database-v1 declarations.
**Parallelism:** R1B after R1A; disjoint locks.
**Non-goals:** Production/query/SQLite/answers/projections/R3/R4/RG/09.
**Invariants:** Closure excludes production/formula, database/replay, grading/oracle rows, R1B; exact Decimal/`null`/order/grade/provenance; sdist <=828000.
**Required tests/checks:** Import guards; 80/R1A vectors; closure/grading drift/inaccessible; production mutation; `just v/vc`; reviewer/CI/merge/exact-main.
**Acceptance:** Declared facts/contracts alone decide results; production mutation cannot affect truth.
**Failure/rollback:** Remove lock; keep R1 blocked.
**Handoff:** SHA/R1A digest/closure/results/gates.
**Cleanup/docs:** Final R1 accounting.
**Suggested commit:** `test: build independent semantic evaluator`
