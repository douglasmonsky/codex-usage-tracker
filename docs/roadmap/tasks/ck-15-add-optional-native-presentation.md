# CK-15 — Add optional native presentation

**Status:** Blocked on CK-14-04; optional umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Decide, then optionally implement, a bounded additive native
presentation handoff.

**Dependencies:** CK-14-04. Child sequence: CK-15-01; CK-15-02 only if selected.

**Non-goals:** This umbrella is never delegated directly; no dashboard,
renderer framework, storage/query changes, or required presentation dependency.

**Invariants:** Canonical rows/selectors/grades unchanged; full text fallback;
no latency/call/token/byte regression.

**Required tests/checks:** Host capability, schema/fallback/accessibility,
fresh-task A/B when selected.

**Acceptance:** Selected implementation passes all gates or branch closes
deferred with no code.

**Failure/rollback:** Remove additive code and do not block CK-16.

**Cleanup/docs:** Record supported host/version and release status.

**Suggested commit:** `feat: qualify optional presentation`
