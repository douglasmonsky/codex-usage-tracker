# CK-09-01 — Freeze the residual projection registry

**Status:** Blocked on CK-08RG

**Parent:** CK-09 umbrella

**Recommended owner:** `default projection-registry`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Admit only CK-08R4-proven projections and freeze their metadata,
physical ownership, dirty keys, maintenance port, and budgets.

**Why:** A provisional plan classification cannot justify persistent write,
storage, WAL, fanout, and recovery cost.

**Controls:** `projection-admission-v2`, database-v1, publication, and query
contracts.

**Dependencies:** CK-08RG merged and exact-main verified.

**Owned files/interfaces:** Projection registry/schema, analytical DDL
amendment, publication maintainer port, validation-plan metadata.

**Produces:** Versioned projection registry and family eligibility list.

**Independent truth source:** Corrected fact-backed evaluator and CK-08R4
measurements.

**Consumer seam:** Family maintainers, publication writer, and named-plan
compiler binding.

**Parallelism:** Serialized freeze; no family implementation starts first.

**Non-goals:** Implementing projections, speculative consumers, event
backbones, or generic aggregates.

**Invariants:** Current-only, exact fact equivalence, bounded dirty updates,
removable last-consumer projections, no full-tail rebuild.

**Required tests/checks:** Schema/registry validation, consumer and budget
completeness, scope/release checks, `just v/vc`, final read-only reviewer.

**Acceptance:** Every admitted projection has a measured consumer, physical
shape, update/delete semantics, dirty keys, and hard budgets.

**Failure/rollback:** Keep the candidate unadmitted and CK-09 blocked.

**Handoff:** Eligible family tasks and immutable registry digest.

**Cleanup/docs:** Reconcile physical decision, query contract, packet, ledger.

**Suggested commit:** `docs: freeze residual projection registry`
