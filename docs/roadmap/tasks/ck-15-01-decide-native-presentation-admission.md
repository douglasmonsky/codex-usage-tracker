# CK-15-01 — Decide native presentation admission

**Status:** Blocked on CK-14-04

**Parent:** CK-15 optional umbrella

**Recommended owner:** `default presentation-decision`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Verify current official host capability and either select a bounded
additive presentation contract or defer with no code.

**Why:** Optional presentation must not grow from an unverified host assumption
into a dashboard or renderer framework.

**Controls:** Qualified clean candidate, official host capability, product
non-goals.

**Dependencies:** CK-14-04 merged and exact-main verified.

**Owned files/interfaces:** Host probe, usefulness rubric, scope decision, and
optional contract proposal; no runtime code.

**Produces:** `selected` or `deferred` presentation decision.

**Independent truth source:** Official host behavior/documentation at task
start and unchanged synthetic result envelopes.

**Consumer seam:** Optional presentation worker and CK-16 release wording.

**Parallelism:** May run with CK-16-01; no shared release files.

**Non-goals:** Dashboard, Evidence Viewer, general layout, custom SQL/formulas,
or required Data Analytics dependency.

**Invariants:** Same rows/selectors/grades, complete text fallback, bounded
bytes/accessibility.

**Required tests/checks:** Capability probe, schema feasibility, usefulness
rubric freeze, response/token/call budget review.

**Acceptance:** Select only a supported, bounded, useful additive contract;
otherwise defer.

**Failure/rollback:** Record deferred/no-code and do not block CK-16.

**Handoff:** Decision digest and exact optional file ownership.

**Cleanup/docs:** Record supported host/version and release dependency.

**Suggested commit:** `docs: decide native presentation scope`
