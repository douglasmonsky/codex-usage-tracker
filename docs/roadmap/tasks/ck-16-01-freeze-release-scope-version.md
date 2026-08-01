# CK-16-01 — Freeze release scope and version

**Status:** Blocked on CK-14-04

**Parent:** CK-16 umbrella

**Recommended owner:** `default release-scope`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze public product scope, version fields, artifact set, promotion
chain, documentation claims, and approval gates.

**Why:** Documentation and artifact work need one release identity before
parallel preparation.

**Controls:** CK-14 clean candidate, release policy, optional CK-15 decision.

**Dependencies:** CK-14-04 merged and exact-main verified.

**Owned files/interfaces:** Release contract/manifest schema and version
proposal; no docs implementation or publication.

**Produces:** Versioned release-scope authority.

**Independent truth source:** Exact clean artifact manifest and qualification
evidence.

**Consumer seam:** Public docs, build-once workflow, protected publication.

**Parallelism:** May run with CK-15-01; serialized release-contract lock.

**Non-goals:** Publishing, rebuilding artifacts during promotion, unsupported
claims, Console imagery.

**Invariants:** One build, byte-identical promotion, exact tag/version/hash,
ordinary pushes cannot publish.

**Required tests/checks:** Version/catalog/artifact coherence, workflow
preflight, release schema, `just v/vc`, reviewer.

**Acceptance:** Every public claim and byte has an owner, proof source, and
approval path.

**Failure/rollback:** Keep release blocked.

**Handoff:** Release identity and documentation claim allowlist.

**Cleanup/docs:** Reconcile release/roadmap authority.

**Suggested commit:** `docs: freeze clean cutover release`
