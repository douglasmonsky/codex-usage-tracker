# CK-10-03 — Implement CLI and MCP adapters

**Status:** Blocked on CK-10-02

**Parent:** CK-10 umbrella

**Recommended owner:** `feature_worker cli-mcp-adapters`; Luna-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Expose the frozen operations through deterministic CLI JSON and
closed MCP schemas using only the application service.

**Why:** Both transports need exact identity without duplicate business logic.

**Controls:** CK-10-01/02 and MCP/CLI contract.

**Dependencies:** CK-10-02 merged and exact-main verified.

**Owned files/interfaces:** `agent_kernel/interfaces/cli/**`,
`agent_kernel/interfaces/mcp/**`, codecs and transport tests; manifests remain
integrator-owned.

**Produces:** CLI/MCP adapters and catalog candidate.

**Independent truth source:** Canonical application serialization fixtures.

**Consumer seam:** Raw CLI/MCP clients to application result.

**Parallelism:** One bounded lane; no plugin/skill or shared manifest edits.

**Non-goals:** SQL, hidden calculations, implicit refresh, polling, Console,
or alternate result schemas.

**Invariants:** Unknown fields fail closed, bounded bytes, no refresh-on-query,
coherent versions, deterministic output.

**Required tests/checks:** Transport schemas, catalog exposure, CLI/MCP result
identity, errors, payloads, fresh process smoke, `just v/vc`.

**Acceptance:** Intended operations only; exact application equality; no
polling or second implementation.

**Failure/rollback:** Adapters stay unselected.

**Handoff:** Catalog/schema digests and smoke evidence to CK-10-05.

**Cleanup/docs:** Interface docs and generated schemas.

**Suggested commit:** `feat: add bounded cli and mcp adapters`
