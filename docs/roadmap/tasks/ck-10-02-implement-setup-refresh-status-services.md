# CK-10-02 — Implement setup, refresh, and status services

**Status:** Blocked on CK-10-01

**Parent:** CK-10 umbrella

**Recommended owner:** `feature_worker application-services`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Implement the typed application router and host-waited setup,
refresh, repair, and status operations.

**Why:** CLI and MCP must share one use-case implementation.

**Controls:** CK-10-01 and publication/application contracts.

**Dependencies:** CK-10-01 merged and exact-main verified.

**Owned files/interfaces:** `agent_kernel/application/**` and focused
application integration tests.

**Produces:** Reusable application service implementation.

**Independent truth source:** Synthetic source inventory, publication, failure,
and cancellation fixtures.

**Consumer seam:** CLI/MCP adapters and installed skill.

**Parallelism:** May overlap CK-10-04 draft; no shared manifest/interface edits.

**Non-goals:** Transport logic, polling tool, plugin manifests, Console, or
second query implementation.

**Invariants:** Host-waited long work, warm query-first path, explicit refresh,
one operation identity, clean cancellation/failure.

**Required tests/checks:** Recommended/expanded setup, no-change, refresh join,
worker start failure, cancellation, warm reopen, `just v/vc`.

**Acceptance:** Every frozen application operation behaves exactly and returns
the canonical envelope.

**Failure/rollback:** Keep adapters disabled; previous public spike remains.

**Handoff:** Application version and focused evidence to CK-10-03/05.

**Cleanup/docs:** Update application ownership docs only.

**Suggested commit:** `feat: add agent kernel application services`
