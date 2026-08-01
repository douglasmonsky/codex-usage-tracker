# CK-14-03 — Delete Console, frontend, and Node

**Status:** Blocked on CK-14-01

**Parent:** CK-14 umbrella

**Recommended owner:** `worker frontend-deletion`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Remove only manifest-approved Console routes/assets/tests/scripts,
frontend sources, and Node toolchain files.

**Why:** The replacement has no dashboard; retaining these surfaces adds
maintenance and package weight.

**Controls:** CK-14-01 deletion set.

**Dependencies:** CK-14-01 merged and exact-main verified.

**Owned files/interfaces:** Exact Console/frontend/Node deletion paths;
package/CI manifests remain integrator-owned.

**Produces:** Frontend/Console/Node absence evidence.

**Independent truth source:** Retirement manifest and package/path scans.

**Consumer seam:** Replacement CLI/MCP/skill installed bundle.

**Parallelism:** May run with CK-14-02 from the same base.

**Non-goals:** Replacement UI, runtime deletion, package/CI integration.

**Invariants:** No required CK-10 through CK-12 path depends on deleted assets.

**Required tests/checks:** Route/static/Node scans, replacement surface tests,
distribution member preview, `just v/vc`.

**Acceptance:** No Console/frontend/Node surface remains and replacement stays
complete.

**Failure/rollback:** Revert the deletion lane; do not build a replacement UI.

**Handoff:** Deletion diff and absence evidence to CK-14-04.

**Cleanup/docs:** Integrator owns final manifests.

**Suggested commit:** `refactor: remove console and frontend`
