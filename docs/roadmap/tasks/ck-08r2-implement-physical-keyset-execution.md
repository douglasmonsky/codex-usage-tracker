# CK-08R2 — Implement bounded physical keyset execution

**Status:** Blocked on CK-08R0

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `default physical-paging`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Execute ordering, keyset predicates, and `LIMIT page_size + 1` before
Python materialization for every direct runtime plan.

**Why:** Slicing a fully evaluated result produces bounded responses but not
bounded deep-page work.

**Controls:** Frozen page-executor contract, plan operands, ordering, cursor,
query-only, and database-v1 contracts.

**Dependencies:** CK-08R0 merged and exact-main verified.

**Owned files/interfaces:** Query contracts, compiler, registry, service, and
focused query/cursor tests under the query physical lock.

**Produces:** Versioned page-execution seam and runtime plan evidence.

**Independent truth source:** R0-frozen structural paging/order vectors plus
direct SQL order and EXPLAIN assertions. CK-08R1 semantic comparison is
consumed later by CK-08R4, not by this parallel implementation lane.

**Consumer seam:** `QueryService` on one query-only snapshot.

**Parallelism:** May run with non-query Wave-2 lanes. No projection or shared
architecture edits.

**Non-goals:** Generic SQL, arbitrary fragments, new projections, complete
result sorting in Python, or public interface work.

**Invariants:** Stable signed cursor bindings, total order, no gaps/duplicates,
exact-count opt-in, fail-closed unknown plans, one read snapshot.

**Required tests/checks:** First/deep pages, ties, tamper/replacement/stale
cursors, count opt-in, query-only denial, EXPLAIN shapes, scale, `just v/vc`.

**Acceptance:** Runtime never calls full `evaluate_plan`; page work is
proportional; accepted direct plans meet correctness, payload, and latency.

**Failure/rollback:** Leave unsupported plans unimplemented and record the
exact index/physical gap; do not add a projection.

**Handoff:** Physical executor version, supported direct-plan list, plans and
measurements.

**Cleanup/docs:** Update query contracts and linked CK-08 evidence amendment.

**Suggested commit:** `feat: execute bounded query pages`
