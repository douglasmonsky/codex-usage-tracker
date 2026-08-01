# CK-12-02 — Run correctness, query, and evidence qualification

**Status:** Blocked on CK-12-01

**Parent:** CK-12 umbrella

**Recommended owner:** `test_engineer correctness-lane`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Run contract, canonical fact, query, projection, selector,
missingness, and privacy gates on the immutable candidate.

**Why:** Semantic correctness needs a lane independent of performance and host
noise.

**Controls:** CK-12 candidate, independent truth, logical/formula/query
contracts.

**Dependencies:** CK-12-01.

**Owned files/interfaces:** Read-only qualification execution and lane evidence;
no candidate edits.

**Produces:** Correctness/privacy lane artifact.

**Independent truth source:** Independent 80-variant evaluator and synthetic
fixtures.

**Consumer seam:** Actual publication/query/evidence/allowance services.

**Parallelism:** May run with CK-12-03/04/05 on identical candidate.

**Non-goals:** Fixing failures, performance claims, host scoring.

**Invariants:** Exact rows/grades/order/selectors, no raw bodies, unsupported
claims fail closed.

**Required tests/checks:** L0-L2 matrix, all plans/variants, mutation/recovery
semantic cases, privacy/static denylists.

**Acceptance:** 100% exact Foundation/Cutover answers and valid evidence with
no privacy or unsupported-field violation.

**Failure/rollback:** Stop lane and retain reproduction; CK-12-06 creates a
narrow owner before any rerun.

**Handoff:** Lane artifact/digest and first failure to CK-12-06.

**Cleanup/docs:** Evidence only; no shared authority edits.

**Suggested commit:** `test: qualify candidate correctness`
