# CK-QG1 — Enforce replacement-kernel maintainability

**Status:** Conditional Ready after CK-08R0 merge and exact-main verification

**Parent:** Corrective quality gate for all remaining packets

**Recommended owner:** `refactorer maintainability-ratchet`; Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Make repository validation reject new or worsened complexity in
`agent_kernel` while recording existing debt honestly.

**Why:** The current checker defaults to the frozen spike and does not protect
the replacement implementation.

**Controls:** Repository validation profiles and measured Radon/Xenon output.

**Dependencies:** CK-08R0 merged and exact-main verified.

**Owned files/interfaces:** Maintainability checker, machine-readable baseline,
tests, and validation wiring.

**Produces:** `agent-kernel-maintainability-baseline-v1`.

**Independent truth source:** Normalized machine-readable complexity analysis
over exact source.

**Consumer seam:** `just vp`, `just v`, `just vc`, and later packet CI.

**Parallelism:** May run with other Wave-2 lanes; no production refactor beyond
checker cohesion.

**Non-goals:** Clearing all historical findings or exempting new complexity.

**Invariants:** Spike checks remain through CK-14; improvements shrink the
baseline; new unlisted code meets the active thresholds.

**Required tests/checks:** Baseline match/mismatch/improvement/new-finding
tests, all repository profiles, exact staged GitNexus analysis.

**Acceptance:** Every new/worsened replacement finding fails deterministically
without brittle text exemptions.

**Failure/rollback:** Normalize tool output before enforcement if unstable;
never disable the gate or broadly refactor unrelated code.

**Handoff:** Baseline digest and CI invocation to CK-08RG.

**Cleanup/docs:** Record ownership and retirement behavior for CK-14.

**Suggested commit:** `ci: enforce agent kernel maintainability`
