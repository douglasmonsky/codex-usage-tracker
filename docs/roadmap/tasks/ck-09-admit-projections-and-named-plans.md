# CK-09 — Admit projections and complete named plans

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Add only measured current projections required for Foundation and
Cutover presets and bind optimized plans to them.

**Why:** Common answers must be fast without rebuilding a broad derived-state
system.

**Controls:** CK-08 admission report,
`QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`.
**Dependencies:** CK-08.

**Scope and expected files:**

- `publication/projections.py` and per-family maintainers;
- projection registry/versions/dependencies;
- optimized compiler modules;
- complete Foundation/Cutover plan implementations;
- projection/query/performance tests.

**Schema changes:** Only projections named in the CK-09 admission artifact.
Each has consumers, dirty keys, validation, storage/WAL/fanout budgets.
**API changes:** Plan registry marks optimized compiler/version.

**Non-goals:** dashboard aggregates, speculative future projections, historical
generation copies, inference fields.

**Invariants:** Current-only; exact fact-backed equivalence; bounded dirty
updates; rate-card dependence isolated; no full tail rebuild; projection can be
removed when last consumer disappears.

**Tests/benchmarks:** Fact/projection equivalence, all mutation types, one-call/
tool tails, hierarchy/late parent, lifecycle completion, valuation-only, source
replacement, storage attribution, named-plan SQL/MCP/payload gates.

**Acceptance:** All Foundation/Cutover question oracles and hard budgets pass;
projection DB/WAL and tail costs within ratchets; every plan normally needs one
query call.

**Failure/rollback:** Remove failing projection and use fact plan only if it
meets contract; otherwise return to physical decision rather than broadening
write amplification.

**Cleanup/docs:** Freeze admitted projection table and measured consumer
rationale.

**Parallelism:** Disjoint projection families may run in parallel after registry
and publication port freeze; one owner integrates writer call sites.

**Suggested commits:**

1. `feat: add measured current projections`
2. `perf: bind optimized named question plans`
