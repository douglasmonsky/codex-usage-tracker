# CK-15 — Add optional native presentation and Data Analytics handoff

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Improve presentation only after the clean MVP is proven, using
official host primitives and bounded results.

**Why:** Custom visualization should not delay or complicate the core.

**Controls:** Product direction, result envelope, current official Codex
capabilities verified at task start.
**Dependencies:** CK-14; non-blocking for CK-16 unless explicitly selected.

**Scope:** Presentation hints for a deliberately small canonical set; Data
Analytics handoff with semantic grades/metric definitions; optional native
metric/ranked/time-series/comparison blocks if officially supported.

**Schema/API changes:** Additive presentation metadata only.
**Non-goals:** Dashboard, Evidence Viewer, Live Watch, general layout system,
Data Analytics dependency, Claude implementation.

**Invariants:** Same exact rows/selectors; text fallback complete; accessibility
and byte budgets; no custom SQL/layout formulas.

**Tests/benchmarks:** Host support probe, schema/render fixtures, fallback,
accessibility, response/model-token impact, fresh-task usefulness A/B.

**Acceptance:** Presentation materially improves the closed usefulness rubric
without latency/call/token regression; otherwise defer with no runtime code.

**Failure/rollback:** Remove additive presentation hints; core answer unchanged.

**Cleanup/docs:** Record supported host/version and future seams.

**Suggested commit:** `feat: add bounded native analysis handoff`
