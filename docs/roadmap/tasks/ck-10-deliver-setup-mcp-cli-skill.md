# CK-10 — Deliver agent-led setup, MCP, CLI, and skill

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Make the kernel feel effortless through the installed Codex surface.

**Why:** Millisecond SQL is useless if the agent polls, refreshes unnecessarily,
or needs many discovery queries.

**Controls:** `AGENT_SETUP_AND_MCP_EXPERIENCE.md`, CK-01/CK-07–CK-09.
**Dependencies:** CK-09.

**Scope and expected files:**

- application setup/refresh/query/evidence/status services;
- CLI commands and deterministic JSON codec;
- proposed MCP catalog and closed schemas;
- plugin manifest and usage skill;
- host-wait helper/progress integration;
- interface/plugin/skill contract tests.

**Schema changes:** None beyond operational request hashes/results if already
selected.
**API changes:** New replacement CLI/MCP schemas, initially side-by-side and
not the default public entry point.

**Non-goals:** public model-polled job-status tool, Console, second adapter,
Data Analytics dependency, narrative findings.

**Invariants:** Recommended 30-day question; one host-waited setup; query-first
warm path; no implicit refresh; one canonical structured response; exact
version/digest coherence; bounded schemas/bytes.

**Tests/benchmarks:** setup choices/estimates/results, warm reopen, expansion,
moving tail, compatible operation reuse, worker-start failure, closed schemas,
MCP transport, skill decision tree, copied request examples, response bytes.

**Acceptance:** Fresh raw MCP clients expose intended tools; setup and warm
questions fit call budgets; no polling instruction; skill maps every
Foundation/Cutover prompt to correct plan; CLI and MCP share results.

**Failure/rollback:** New surface stays disabled; spike remains public. Contract
errors are corrected before installed harness.

**Cleanup/docs:** Update MCP experience and machine schemas in one change.

**Suggested commits:**

1. `feat: add agent-led kernel setup`
2. `feat: add bounded MCP and CLI surfaces`
3. `docs: add installed usage skill`
