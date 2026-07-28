# CK-02 — Freeze logical contract vectors

**Status:** Not started
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Express physical-independent identity, time, missingness, accounting,
lifecycle, hierarchy, allowance, valuation, publication, and selector semantics
as executable vectors.

**Why:** A/C/D cannot be compared if each interprets the domain differently.

**Controls:** `LOGICAL_KERNEL_CONTRACT.md`, `ADAPTER_CONTRACT.md`, CK-01
registry.
**Dependencies:** CK-01.

**Scope and expected files:**

- `config/agent-kernel/logical-contract-v1.json`;
- `tests/agent_kernel/contracts/vectors/*.json`;
- `tests/agent_kernel/contracts/test_identity_vectors.py`;
- `test_time_vectors.py`, `test_accounting_vectors.py`,
  `test_lifecycle_vectors.py`, `test_allowance_vectors.py`,
  `test_selector_vectors.py`;
- minimal pure reference functions under
  `tests/agent_kernel/contracts/reference/`, not production code.

**Schema/API changes:** Locks integer UTC microseconds, identity tuple/version,
four tokens, measurement masks, grades/bases, lifecycle states, operation
enums, resource kinds, allowance compatibility, rate-card coverage,
publication/selector shapes.

**Non-goals:** SQLite DDL, parser, projection, public JSON API.

**Invariants:** Missing never becomes zero; cached/reasoning never
double-count; source copies count once; late parents/events preserve semantic
IDs; intent/success/mutation stay separate.

**Tests/benchmarks:** Exact vectors, collision failure, DST/boundaries/overflow,
stable serialization digest. Pure-vector suite target `<=2 s`.

**Acceptance:** Every logical entity/field has owner, semantics, identity
participation, missing behavior, basis, and vector; every CK-01 required
primitive resolves.

**Failure/rollback:** Change only vectors/docs before physical implementation.
Breaking a locked decision requires a documented decision amendment.

**Cleanup/docs:** Update logical contract and question mappings together.

**Suggested commit:** `test: freeze agent-kernel logical vectors`
