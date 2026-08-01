# CK-10-05 — Integrate the installed surface

**Status:** Blocked on CK-10-02, CK-10-03, and CK-10-04

**Parent:** CK-10 umbrella

**Recommended owner:** `default installed-surface`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Produce a coherent side-by-side wheel/plugin/skill candidate and
qualify CK-10 surface behavior.

**Why:** Separate modules do not prove installed catalog, hashes, versions, and
flows agree.

**Controls:** All CK-10 artifacts and packaging contracts.

**Dependencies:** CK-10-02/03/04 accepted.

**Owned files/interfaces:** Plugin manifest, `.mcp.json`, entrypoint candidate,
version fields, integration tests, CK-10 evidence and authority.

**Produces:** Exact CK-10 bundle manifest.

**Independent truth source:** Synthetic host fixtures and canonical operation
fixtures.

**Consumer seam:** Clean installed CLI/MCP/plugin/skill to application service.

**Parallelism:** Serialized installed-surface lock and final reviewer.

**Non-goals:** Public cutover, replacing default 0.28 entry points, CK-11
harness implementation.

**Invariants:** Side-by-side separate data, no spike imports, exact catalog and
digest coherence, no polling.

**Required tests/checks:** Clean candidate install, two fresh MCP processes,
setup/warm/expansion/evidence flows, bytes/calls, `just v/vc`, CI, exact main.

**Acceptance:** All CK-10 gates pass with one exact bundle.

**Failure/rollback:** Candidate stays disabled and default spike unchanged.

**Handoff:** PR, merged SHA, bundle hashes, CI, residuals, CK-11-01 readiness.

**Cleanup/docs:** Reconcile parent, ledger, index, setup/target contracts.

**Suggested commit:** `feat: integrate agent kernel surface`
