# CK-13-01 — Freeze the cutover and rollback drill

**Status:** Blocked on CK-12-06

**Parent:** CK-13 umbrella

**Recommended owner:** `default cutover-manifest`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze the qualified candidate manifest, entry-point changes,
separate database identity, side-by-side drill, rollback release, and deletion
approval conditions.

**Why:** Cutover must select proven bytes without combining preparation,
mutation, rollback, and deletion.

**Controls:** CK-12 evidence, cutover gate, package and rollback contracts.

**Dependencies:** CK-12-06 merged and exact-main verified.

**Owned files/interfaces:** Cutover manifest/evidence schema and exact change
allowlist; no runtime or entry-point edits.

**Produces:** Immutable cutover/rollback drill v1.

**Independent truth source:** CK-12 artifacts and installed synthetic oracles.

**Consumer seam:** Entry-point worker and cutover verifier.

**Parallelism:** Serialized preparation.

**Non-goals:** Cutover, deletion, migration, dual-write, compatibility views,
or public release.

**Invariants:** Separate databases, untouched reinstallable 0.28 rollback,
exact candidate hashes, no spike fallback hidden in replacement.

**Required tests/checks:** Manifest/hash validation, isolated install/catalog
probe, rollback preflight, `just v/vc`, reviewer.

**Acceptance:** Every cutover and rollback step, postcondition, and stop rule is
decision-complete.

**Failure/rollback:** Keep default entry points unchanged.

**Handoff:** Exact allowlist and manifest digest to CK-13-02.

**Cleanup/docs:** Reconcile cutover authority.

**Suggested commit:** `docs: freeze cutover rollback drill`
