# CK-02 — Freeze logical contract vectors

**Status:** Completed
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

## Completion evidence

- The physical-independent contract freezes **26 logical entities**, one
  ordered exact identity tuple per entity, and **245 admitted fields**. A
  checked-in synthetic field matrix executes one semantic assertion for every
  field, including basis, missingness, identity participation, ordered
  identity-input consumption, and derived-ID validation.
- The versioned bundle contains **119 unique vectors** in **146,658 bytes**.
  Its canonical bundle digest is
  `f310f9e6dc6e65e8f1944a347b6d3bfbf18fe68f2f8ddcf9eb0d1c81e9396848`.
  Logical IDs use exactly 52 lowercase unpadded base32 digest characters.
- Exact vectors lock nonrecursive publication-ID/artifact-digest derivation,
  zero-to-six-digit timestamp precision, canonical decimal domains,
  result-only grade rejection in canonical missing measurements, joined
  allowance compatibility, and independent cost/credit valuation coverage.
- Focused qualification passed with **37 tests in 0.67 seconds**. Final
  repository qualification passed with **497 tests in 68.58 seconds**, Ruff,
  MyPy, Pyright, scope/manifests/interfaces, frontend checks,
  maintainability, release safety, and `git diff --check`.
- Final review produced **9 findings; 9 were accepted and resolved**.
  Reviewer-token attribution is **pending** because the required strict usage
  command is unavailable; tokens per accepted finding remain pending rather
  than triggering retries.

### Deviations and residual risks

- No production database, parser, query, MCP, or presentation code was added.
  The packet uses pure reference functions and synthetic fixtures exactly as
  scoped.
- The field matrix replaces tag-only completeness as the executable gate.
  Existing `vector_ids` remain as traceability metadata, but contract
  completeness now regenerates and executes the exact matrix.
- Physical implementations in CK-03 onward must prove they reproduce these
  vectors. Adapter-specific source keys, provider rate-card contents, and
  real publication storage remain intentionally unresolved here.
- Independent cost and credit estimates are configured estimates, never
  observed billing truth. Unsupported channels remain null with explicit
  grades and reasons.

**Suggested commit:** `test: freeze agent-kernel logical vectors`
