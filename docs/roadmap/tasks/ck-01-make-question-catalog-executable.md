# CK-01 — Make the question catalog executable

**Status:** Completed
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

## Completion evidence

- The executable registry contains all **40** authoritative question IDs
  exactly once. The catalog is **84,923 bytes**, its JSON Schema is
  **10,211 bytes**, and its deterministic compact guidance projection is
  **14,459 / 16,384 bytes**.
- Schema, reference, support/stage, evidence-selector, answer-dependency,
  prohibited-claim, raw/SQL-input, and Markdown reconciliation checks pass.
  All physical compiler IDs remain `null`; CK-01 implements no query or
  physical plan.
- Focused qualification passed with **36 tests**. The final bounded
  repository qualification passed with **473 tests**, Ruff, MyPy, Pyright,
  scope/manifests/interfaces, frontend checks, maintainability, release
  safety, and `git diff --check`.
- Final review produced **5 findings; 5 were accepted and resolved**.
  Reviewer-token attribution is **pending** because the installed Usage
  Tracker CLI does not expose the expected `strict` command; tokens per
  accepted finding therefore remain pending rather than triggering retries.

### Deviations and residual risks

- No catalog intent, support class, stage, or evidence-class assignment was
  deliberately changed. The generated compact guidance fixture was included
  as the packet's allowed optional artifact.
- The registry remains deliberately unconsumed and repository-only in CK-01.
  Later packets must implement and qualify compilers, packaging/runtime
  loading, synthetic oracles, and plan performance before these contracts
  become product behavior.
- Cross-field dependency validation currently covers the admitted
  `following_tokens` answer. Future answer fields with hidden capability,
  measurement, primitive, or coverage dependencies must add an equivalent
  fail-closed rule when introduced.
- No runtime latency, CPU, or database-storage claim applies to this
  documentation/config-only packet; the byte measurements above are the
  relevant packet measurements.

**Suggested commit:** `docs: make question contracts executable`
