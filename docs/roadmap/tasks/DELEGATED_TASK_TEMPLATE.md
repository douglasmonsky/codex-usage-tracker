# Delegated Task Template

Copy this template for every new delegable unit. Add the file to
[TASK_PACKETS.md](../TASK_PACKETS.md) and
[REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md) before marking it
Ready.

**Status:** Not started

**Parent:** CK-XX umbrella

**Recommended owner:** `<role> <short-scope>`; use write-capable `default` on
Sol for decision/integration, or the named Luna role for bounded
implementation/qualification. `architect` is read-only advisory support.

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** One outcome.

**Why:** The consumer value or gate this produces.

**Controls:** Exact contracts and predecessor evidence.

**Dependencies:** Exact merged packets and artifacts.

**Owned files/interfaces:** A disjoint write set; identify shared locks.

**Produces:** A versioned artifact or interface with identity/digest.

**Independent truth source:** A source that does not share the implementation
under test.

**Consumer seam:** The real downstream path that must consume the output.

**Parallelism:** What may overlap and what is forbidden.

**Non-goals:** Explicit scope exclusions.

**Invariants:** Semantics, privacy, failure, compatibility, and lifecycle rules.

**Required tests/checks:** Focused then complete checks and measured gates.

**Acceptance:** Observable pass conditions.

**Failure/rollback:** Fail-closed stop rule and recoverable state.

**Handoff:** Exact base/head, PR/CI, evidence digests, residuals, and newly Ready
tasks.

**Cleanup/docs:** Authorities and evidence that must be reconciled.

**Suggested commit:** `type: concise outcome`
