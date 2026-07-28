# CK-05 — Implement the selected canonical storage kernel

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Create the clean production root, database identity, domain types,
selected DDL/indexes, connection policy, and canonical repositories.

**Why:** All later behavior needs one isolated, tested physical foundation.

**Controls:** Physical decision, `LOGICAL_KERNEL_CONTRACT.md`,
`TARGET_ARCHITECTURE.md`.
**Dependencies:** CK-04.

**Scope and expected files:**

- `src/codex_usage_tracker/agent_kernel/domain/**`;
- `storage/database.py`, `schema.py`, selected fact/occurrence/lifecycle
  repositories;
- owner-only cache-path resolver for `agent-usage-kernel-v1.sqlite3`;
- `tests/agent_kernel/storage/**`;
- import-isolation and old-database rejection ratchets.

**Schema changes:** Creates database-v1 physical schema and versions exactly as
selected.
**API changes:** Internal typed repository ports only.

**Non-goals:** Codex parsing, publication worker, projections, MCP, migration,
compatibility views.

**Invariants:** No old imports/database opens; integer UTC; NULL missing; four
tokens; stable identity/collision checks; parameterized SQL; owner-only files;
physical query compilation, no compatibility views.

**Tests/benchmarks:** DDL digest, connection/read/write modes, foreign keys,
quick/integrity checks, identity vectors, canonical occurrence accounting,
database bytes and baseline repository operations.

**Acceptance:** CK-02 vectors and CK-03 tiny accounting oracle pass on selected
storage; exact schema/index inventory matches decision; zero runtime
dependencies beyond approved package policy.

**Failure/rollback:** Delete only the new database path/artifacts. Spike files
remain untouched. Schema drift returns to CK-04 decision amendment.

**Cleanup/docs:** Update physical decision only for measured corrections; record
schema ownership.

**Suggested commits:**

1. `feat: add isolated agent-kernel domain`
2. `feat: add selected database-v1 storage`
