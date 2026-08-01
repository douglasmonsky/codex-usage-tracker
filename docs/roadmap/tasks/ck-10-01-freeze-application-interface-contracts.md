# CK-10-01 — Freeze application and interface contracts

**Status:** Blocked on CK-09-06

**Parent:** CK-10 umbrella

**Recommended owner:** `default application-contracts`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Freeze typed application operations, canonical request/result
envelopes, MCP/CLI mapping, version coherence, and host-wait behavior.

**Why:** Surface workers need one shared contract and must not independently
redesign setup, query, or evidence semantics.

**Controls:** Agent setup/MCP experience, query/evidence, publication, and
product contracts.

**Dependencies:** CK-09-06 merged and exact-main verified.

**Owned files/interfaces:** Application ports, public-internal schemas, catalog
proposal, version/digest rules; no implementation.

**Produces:** Versioned application/interface contract.

**Independent truth source:** Product question/setup contracts and synthetic
request fixtures.

**Consumer seam:** Application service, CLI/MCP adapters, plugin/skill, and
installed harness.

**Parallelism:** Serialized freeze.

**Non-goals:** Implementation, `usage_job_status`, model polling, implicit
refresh, narrative findings, Console, or Data Analytics dependency.

**Invariants:** One canonical result, closed schemas, bounded bytes, query never
refreshes, host waits, version/digest coherence.

**Required tests/checks:** Schema fixtures, catalog counts, copied examples,
scope/release checks, `just v/vc`, final reviewer.

**Acceptance:** Every operation and error is closed, bounded, capability-aware,
and maps to one application seam.

**Failure/rollback:** Keep CK-10 blocked until grouping/semantics are decided.

**Handoff:** Contract digest and exact disjoint ownership for CK-10-02/04.

**Cleanup/docs:** Reconcile setup and target architecture contracts.

**Suggested commit:** `docs: freeze application interface contracts`
