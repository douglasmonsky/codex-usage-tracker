# CK-09-04 — Implement allowance and evidence projections

**Status:** Blocked on CK-09-01 and family admission

**Parent:** CK-09 umbrella

**Recommended owner:** `feature_worker allowance-projections`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement only explicitly admitted allowance interval or evidence
timeline families.

**Why:** These streams have distinct interval/order and selector semantics and
must not be inferred from other rollups.

**Controls:** Frozen registry, allowance interval, selector/provenance,
evidence cursor, and publication contracts.

**Dependencies:** CK-09-01 plus explicit family eligibility.

**Owned files/interfaces:** New allowance/evidence maintainer modules and tests.

**Produces:** Family equivalence and maintenance evidence.

**Independent truth source:** Exact observations, interval evaluator, and typed
evidence-order oracle.

**Consumer seam:** Frozen maintainer port to allowance/evidence read services.

**Parallelism:** May run with CK-09-02/03; no shared registry or service edits.

**Non-goals:** Inventing evidence projection after CK-08R3 passed direct reads,
raw bodies, qualitative conclusions, or public APIs.

**Invariants:** Half-open intervals, repeat/reset boundaries, typed provenance,
seven-part evidence order, stable replacement/late events.

**Required tests/checks:** Equal-time boundaries, incompatible intervals,
replacement, late events, fanout/storage/WAL/tail, `just v/vc`.

**Acceptance:** Exact equivalence and every family hard budget pass.

**Failure/rollback:** Leave family unadmitted; direct service remains only if
it meets its contract.

**Handoff:** Accepted family IDs and evidence digests to CK-09-05.

**Cleanup/docs:** Family evidence only.

**Suggested commit:** `feat: add admitted allowance projections`
