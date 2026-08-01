# CK-09-06 — Integrate and qualify projections

**Status:** Blocked on CK-09-05

**Parent:** CK-09 umbrella

**Recommended owner:** `default projection-integration`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Integrate accepted maintainers into publication and close CK-09 with
exact equivalence and physical evidence.

**Why:** Isolated family modules must survive actual publication, recovery,
artifact, and query lifecycle.

**Controls:** All CK-09 evidence, publication/recovery, storage, query, and
qualification contracts.

**Dependencies:** CK-09-05 and every admitted family lane.

**Owned files/interfaces:** Shared publication call sites, DDL digest, registry,
integration tests, evidence aggregate, parent/ledger status.

**Produces:** Canonical CK-09 qualification evidence and exact-main handoff.

**Independent truth source:** Independent answers and mutation/recovery fixture
matrix.

**Consumer seam:** Publication writer, artifacts, query/evidence/allowance
services.

**Parallelism:** Serialized integration and one final reviewer.

**Non-goals:** Public surfaces, CK-10 implementation, gate waivers.

**Invariants:** Prior publication readable, no full-tail rebuild, bounded
ordinary tails, exact storage/WAL/fanout attribution.

**Required tests/checks:** All named plans/variants, every mutation/recovery
mode, scale, storage/WAL/payload, `just v/vc`, hosted CI, exact-main checks.

**Acceptance:** Every admitted consumer passes all gates; direct plans remain
correct; all plans classified; no unresolved review finding.

**Failure/rollback:** Keep CK-09 blocked and remove failed admission/binding.

**Handoff:** PR, merged SHA, CI, evidence digest, final registry and CK-10-01
readiness.

**Cleanup/docs:** Reconcile parent packet, roadmap, ledger, index, contracts.

**Suggested commit:** `feat: integrate qualified projections`
