# CK-08R3 — Qualify evidence service scale

**Status:** Blocked on CK-08R3A acceptance, merge, and exact-main verification

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `test_engineer evidence-scale`; Luna

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Prove bounded first/deep pages at both frozen scales.

**Dependencies:** CK-08R3A accepted, merged, and exact-main verified. CK-08R3A
itself depends on accepted CK-08R0.

**Owned files/interfaces:** Evidence tests/workload/artifact; never production.

**Produces:** Evidence-scale v1: SQL, EXPLAIN, rows/bytes/RSS, five p95 samples.

**Independent truth source:** Typed selector/seven-part-order synthetic oracle.

**Consumer seam:** Actual EvidenceService, one query-only snapshot; consume
CK-08R3A's exact blocker identity, which ran no scale/admission.

**Parallelism:** Read-only after CK-08R3A; disjoint from Wave 2.

**Non-goals:** Production fix, projection/backbone/API, index, or new budget.

**Invariants:** Typed provenance, stable late/replacement events, no
gaps/duplicates, <=100 rows, <=16,384 bytes, exact count off.

**Required tests/checks:** Every view/scope/direction, ties/late/replacement/
byte truncation, 100,000 and 1,316,864-call fixtures, first/deep plans and
budgets at both scales, `just v/vc`.

**Acceptance:** All preceding invariants/tests pass at both scales.

**Failure/rollback:** Retain first failure; stop scale/admission and route
physical defects separately. Never weaken gates, create R4, or invent
`evidence_timeline_current`.

**Handoff:** Evidence digest and classification input.

**Cleanup/docs:** CK-08R4 links the result.

**Suggested commit:** `test: qualify evidence service scale`
