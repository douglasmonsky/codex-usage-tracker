# CK-01 — Make the question catalog executable

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Convert the Markdown question catalog into a validated machine
registry without implementing queries.

**Why:** Questions, not tables, must drive the replacement. Static
reconciliation prevents schema and skill drift.

**Controls:** `SUPPORTED_QUESTION_CONTRACTS.md`,
`QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`.
**Dependencies:** CK-00.

**Scope and expected files:**

- `config/agent-kernel/question-catalog-v1.json`;
- `config/agent-kernel/question-catalog-v1.schema.json`;
- `scripts/check_agent_kernel_contracts.py`;
- `tests/agent_kernel/contracts/test_question_catalog.py`;
- generated compact prompt/plan guidance fixture if needed.

**Schema/API changes:** Adds documentation/config schema only. Registry fields
must cover intent, class/stage, parameters, capabilities, measurements,
logical plan, grades, formulas, coverage, evidence, prohibited claims,
ordering, limits, performance, projections, oracle IDs, and lower-model hints.

**Non-goals:** SQL, physical tables, MCP tools, narrative findings, user
question packs.

**Invariants:**

- every Markdown question ID exists once in JSON and vice versa;
- inference/deferred/unsupported entries cannot name a kernel conclusion field;
- every named plan has one-call and byte budgets;
- every evidence requirement names valid selector kinds;
- Foundation/Cutover stages contain only `N`.

**Tests/benchmarks:** JSON Schema validation, duplicate/reference tests,
question-to-plan/evidence/primitive completeness, deterministic generation,
registry/guidance byte measurement.

**Acceptance:** Forty catalog IDs reconcile; no free-form SQL or raw-content
requirement; all stage/support/prohibited-claim rules pass; generated guidance
is deterministic and under its measured budget.

**Failure/rollback:** Registry remains unconsumed. Resolve contract ambiguity
before CK-02; do not encode guessed fields.

**Cleanup/docs:** Amend catalog and index for any deliberate catalog change.

**Suggested commit:** `docs: make question contracts executable`
