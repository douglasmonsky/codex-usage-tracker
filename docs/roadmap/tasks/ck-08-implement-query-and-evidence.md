# CK-08 — Implement fact-backed query and evidence services

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Compile named/typed requests to the selected physical tables and
resolve stable bounded evidence before adding projections.

**Why:** Fact-backed truth is the oracle for every later optimization.

**Controls:** `QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`, CK-01, CK-05–CK-07.
**Dependencies:** CK-07.

**Scope and expected files:**

- `query/contracts.py`, `registry.py`, `compiler.py`, `service.py`;
- `evidence/selectors.py`, `cursors.py`, `service.py`;
- current valuation and allowance read services needed by questions;
- query/evidence tests and plan snapshots.

**Schema changes:** Only indexes explicitly selected by CK-04; no projections
yet.
**API changes:** Internal typed request/result/evidence envelopes.

**Non-goals:** Public MCP, generic SQL, narrative analysis, projection added to
hide a failing plan.

**Invariants:** One read snapshot; keyset cursors; exact counts opt-in; complete
server-side sort; human labels first; four token columns; current valuation
coverage; no refresh/write.

**Tests/benchmarks:** Every Foundation/Cutover fact-backed oracle, cursor
rebuild/replacement/late events, exact count, order ties, unsupported
reframings, EXPLAIN plans, SQL/payload measurements at both scales.

**Acceptance:** Exact answers/evidence pass; selectors stable; result envelope
under budget; every plan reports whether it already meets its class or requires
a CK-09 projection.

**Failure/rollback:** Keep registry entry unimplemented rather than silently
returning incomplete data. No API is public yet.

**Cleanup/docs:** Produce measured projection-admission list.

**Suggested commits:**

1. `feat: add bounded agent-kernel query compiler`
2. `feat: add stable evidence service`
