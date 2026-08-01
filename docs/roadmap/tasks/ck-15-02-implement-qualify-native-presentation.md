# CK-15-02 — Implement and qualify native presentation

**Status:** Blocked unless CK-15-01 selects it

**Parent:** CK-15 optional umbrella

**Recommended owner:** `feature_worker presentation-metadata`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement only selected additive presentation metadata and prove
material usefulness without core regressions.

**Why:** Optional value should be one bounded experiment with automatic
reversion on failure.

**Controls:** CK-15-01 selected contract and immutable canonical result.

**Dependencies:** CK-15-01=`selected`.

**Owned files/interfaces:** Exact selected serialization/interface metadata,
skill guidance, focused tests and A/B evidence.

**Produces:** Qualified presentation metadata contract or clean deferral.

**Independent truth source:** Identical synthetic prompt suite, result oracle,
and closed usefulness rubric.

**Consumer seam:** Official host/Data Analytics handoff with text fallback.

**Parallelism:** May overlap CK-16-02 only with disjoint files; release waits
for its decision if selected.

**Non-goals:** Storage, query, renderer framework, dashboard, canonical schema
changes.

**Invariants:** Facts/selectors/grades unchanged; accessibility, latency, calls,
tokens, and bytes do not regress.

**Required tests/checks:** Schema/render fixtures, fallback, accessibility,
fresh-task A/B, exact result equality, `just v/vc`.

**Acceptance:** Material usefulness gain and every non-regression gate pass.

**Failure/rollback:** Remove all additive code and close as deferred.

**Handoff:** Evidence digest and release inclusion/defer decision.

**Cleanup/docs:** Reconcile optional parent and CK-16 dependency only.

**Suggested commit:** `feat: add bounded presentation metadata`
