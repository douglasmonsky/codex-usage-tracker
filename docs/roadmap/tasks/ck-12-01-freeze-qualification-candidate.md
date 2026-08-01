# CK-12-01 — Freeze the qualification candidate

**Status:** Blocked on CK-11-04

**Parent:** CK-12 umbrella

**Recommended owner:** `default qualification-candidate`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze artifact hashes, fixture digest, catalogs, registry, budgets,
evidence schema, and rerun rules for one immutable candidate.

**Why:** Parallel qualification is valid only when every lane measures the same
bytes and facts.

**Controls:** CK-09 through CK-11 evidence and qualification plan.

**Dependencies:** CK-11-04 merged and exact-main verified.

**Owned files/interfaces:** Candidate manifest, gate ledger, ratchet inputs,
lane evidence schemas; no runtime implementation.

**Produces:** Immutable CK-12 candidate identity.

**Independent truth source:** Accepted predecessor evidence and artifact hashes.

**Consumer seam:** Four parallel qualification lanes and final decision.

**Parallelism:** Serialized freeze; no candidate mutation after lane start.

**Non-goals:** Fixes, gate changes, new questions, UI, branding.

**Invariants:** Identical artifact/fixture/config in every lane; exact catalog
counts; byte ratchets retain at most approved 25% headroom.

**Required tests/checks:** Manifest/schema validation, artifact digest checks,
lane completeness, `just v/vc`, final reviewer.

**Acceptance:** Candidate and all gates are closed, reproducible, and immutable.

**Failure/rollback:** Keep CK-12 blocked; do not launch lanes.

**Handoff:** Candidate digest and independent lane task inputs.

**Cleanup/docs:** Reconcile qualification authority.

**Suggested commit:** `docs: freeze qualification candidate`
