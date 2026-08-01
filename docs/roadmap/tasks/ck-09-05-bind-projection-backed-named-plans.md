# CK-09-05 — Bind projection-backed named plans

**Status:** Blocked on accepted CK-09-02, CK-09-03, and CK-09-04 lanes

**Parent:** CK-09 umbrella

**Recommended owner:** `default projection-bindings`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Bind only accepted projection consumers into bounded named-plan
compilers while preserving sufficient direct plans.

**Why:** Family maintainers do not prove the actual runtime consumer path.

**Controls:** Frozen projection registry, query page executor, result and cursor
contracts.

**Dependencies:** All eligible family lanes accepted on exact main.

**Owned files/interfaces:** Query registry/compiler/service bindings and
focused projection-backed query tests under the query lock.

**Produces:** Versioned plan-to-projection bindings.

**Independent truth source:** Independent answer truth and direct fact-backed
qualification seam.

**Consumer seam:** Actual `QueryService` on one snapshot.

**Parallelism:** Serialized query integration.

**Non-goals:** New projections, broad fallback, generic SQL, or shared writer
integration.

**Invariants:** Complete SQL order and keyset bounds precede materialization;
missingness, grades, selectors, and bytes remain exact.

**Required tests/checks:** Every bound plan/variant, cursor behavior, direct
fallback classifications, EXPLAIN, payload and latency, `just v/vc`.

**Acceptance:** Each optimized plan names compiler/version/projection and meets
all exact result and physical gates.

**Failure/rollback:** Remove the failing binding; do not retain a partial or
full-materialization fallback.

**Handoff:** Binding digest and complete plan classification to CK-09-06.

**Cleanup/docs:** Integrator-owned query evidence amendment.

**Suggested commit:** `feat: bind projection backed plans`
