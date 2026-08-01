# CK-09-03 — Implement workflow and tool projections

**Status:** Blocked on CK-09-01 and family admission

**Parent:** CK-09 umbrella

**Recommended owner:** `feature_worker workflow-projections`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement only admitted tool-family, resource, action, and lifecycle
projection families.

**Why:** Workflow semantics have separate identity and mutation rules and need
a bounded owner.

**Controls:** Frozen registry, tool/action/resource logical contracts, and
publication port.

**Dependencies:** CK-09-01 plus explicit family eligibility.

**Owned files/interfaces:** New workflow/tool maintainer modules and tests.

**Produces:** Workflow family equivalence and maintenance evidence.

**Independent truth source:** Canonical lifecycle/resource/state-change facts
and a projection-specific reference aggregation.

**Consumer seam:** Frozen maintainer port to publication-validation reads.

**Parallelism:** May run with CK-09-02/04; no shared integration files.

**Non-goals:** Causal inference, qualitative fields, allowance/evidence
families, or query registry edits.

**Invariants:** Intent, success, completion, and observed mutation stay
separate; open/terminal lifecycle and aliases remain exact.

**Required tests/checks:** Late events, completion, resource aliases,
replacement, bounded dirty keys/fanout/WAL/storage/tail, `just v/vc`.

**Acceptance:** Exact answers and all physical budgets pass.

**Failure/rollback:** Leave family unadmitted and preserve the reproduction.

**Handoff:** Accepted family IDs and evidence digests to CK-09-05.

**Cleanup/docs:** Family evidence only.

**Suggested commit:** `feat: add admitted workflow projections`
