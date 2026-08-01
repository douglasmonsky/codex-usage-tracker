# CK-10 — Deliver setup, MCP, CLI, and skill

**Status:** Blocked on CK-09-06; umbrella only

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Expose the qualified kernel through one typed application service and
coherent CLI/MCP/plugin/skill bundle.

**Dependencies:** CK-09-06. Child sequence: CK-10-01; CK-10-02 and bounded
CK-10-04; CK-10-03; CK-10-05.

**Non-goals:** This umbrella is never delegated directly; no Console, polling
tool, implicit refresh, narrative findings, or second implementation.

**Invariants:** Host-waited work, query-first warm path, closed schemas, one
canonical result, exact versions/digests, bounded calls/bytes.

**Required tests/checks:** Child gates plus clean bundle install, fresh
processes, complete setup/query/evidence flows, CI/review/exact-main.

**Acceptance:** CK-10-05 accepts one exact side-by-side bundle.

**Failure/rollback:** Candidate remains disabled and public 0.28 unchanged.

**Cleanup/docs:** Reconcile setup, target architecture, roadmap, ledger, index.

**Suggested commit:** `feat: deliver agent kernel interfaces`
