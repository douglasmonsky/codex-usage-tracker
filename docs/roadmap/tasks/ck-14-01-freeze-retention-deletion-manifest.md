# CK-14-01 — Freeze retention and deletion manifest

**Status:** Blocked on CK-13-03

**Parent:** CK-14 umbrella

**Recommended owner:** `default retirement-inventory`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Classify every spike, Console, frontend, Node, test, oracle, release,
configuration, and package path as delete, retain, or port.

**Why:** Parallel deletion is safe only after retained oracles and release
primitives have explicit owners.

**Controls:** CK-13 approval, current filesystem/import/package inventory, spike
disposition history.

**Dependencies:** CK-13-03 with explicit retirement approval.

**Owned files/interfaces:** Final retirement allowlist and retained-oracle map;
no deletion.

**Produces:** Versioned retention/deletion manifest.

**Independent truth source:** AST/import/path/package scans and active
replacement qualification.

**Consumer seam:** Two deletion workers and package/CI integrator.

**Parallelism:** Serialized preparation.

**Non-goals:** Deletion, compatibility shims, replacement UI.

**Invariants:** Every retained item has an owner and validation path; no stale
0.26/0.28 manifest is accepted without reconciliation.

**Required tests/checks:** Filesystem, import, package, workflow, oracle, and
release primitive inventory; `just v/vc`, reviewer.

**Acceptance:** No path or shared ownership is ambiguous.

**Failure/rollback:** Keep all surfaces until missing ownership is resolved.

**Handoff:** Disjoint exact deletion sets to CK-14-02/03.

**Cleanup/docs:** Reconcile retirement/disposition configuration.

**Suggested commit:** `docs: freeze retirement manifest`
