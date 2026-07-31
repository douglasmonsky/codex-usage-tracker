# CK-05 — Implement the selected canonical storage kernel

**Status:** Completed
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

## Execution record

**Status:** Completed
**Evidence:** [canonical-storage-evidence.json](../../decisions/evidence/ck05/canonical-storage-evidence.json)

The clean `codex_usage_tracker.agent_kernel` package now owns the exact
database-v1 DDL, domain and identity primitives, analytical connection policy,
owner-only canonical cache path, and the selected typed fact, occurrence, and
lifecycle repositories. The production implementation imports neither the old
kernel nor CK-04 experimental code and rejects legacy, foreign, or swapped
databases before writer configuration can mutate them.

The selected storage passes the committed CK-02 identity vectors and CK-03
tiny-v1 accounting oracle. The evidence records the exact schema digest and
inventory, connection modes, SQLite integrity checks, canonical occurrence
accounting, compact database bytes, descriptive repository-operation timings,
packaging policy, validation, and final review accounting.

The CK-04 exception is unchanged: current-commit growth repetitions 3 and 4
were waived and the strict v2 aggregate is not claimed. Growth build cost and
SQLite I/O variance remain explicit risks. CK-06 owns bounded ingestion,
streaming and batching beyond the repository seams, queue depth, and RSS.

CK-05's schema and repository implementation are not implicated by the CK-03
question-row mismatch: database-v1 contains no `question_cases` answer table.
Its fixture digests, counts, and accounting evidence must nevertheless be
reissued by
[CK-07A](ck-07a-reconcile-fact-backed-oracles-and-qualify-seams.md) after the
corrected canonical scenario fixture is frozen. A code change is admitted only
if that unchanged consumer replay exposes a concrete storage deficiency.

CK-07A requalified CK-05 storage against all 80 corrected variants without a
storage implementation change. Historical CK-05 evidence remains preserved;
current seam authority is the
[CK-07A evidence](../../decisions/evidence/ck07a/fact-backed-oracle-and-seam-qualification-evidence.json).
