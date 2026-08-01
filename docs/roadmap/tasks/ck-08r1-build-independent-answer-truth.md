# CK-08R1 — Build independent expected-answer truth

**Status:** Blocked on CK-08R0

**Parent:** Corrective prerequisite for CK-09

**Recommended owner:** `default independent-truth`; write-capable Sol-class

**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)

**Central plan:** [REMAINING_EXECUTION_PLAN.md](../REMAINING_EXECUTION_PLAN.md)

**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Calculate all supported expected answers from structural scenario
declarations without production plan assembly or evaluation imports.

**Why:** Two consumers of one production evaluator prove adapter parity, not
independent answer semantics.

**Controls:** CK-07A scenario, formula, operand, selector, valuation, and
comparison contracts.

**Dependencies:** CK-08R0 merged and exact-main verified.

**Owned files/interfaces:** Test-only oracle evaluator, reference adapter,
import denylist and mutation tests, linked CK-07A/CK-08 amendments.

**Produces:** Independent-truth evidence v2 for all 80 variants.

**Independent truth source:** Structural-v2 declarations plus locked formulas;
shared formula definitions are allowed, shared plan assembly is not.

**Consumer seam:** Compare independent rows against database-v1 replay and the
actual runtime query service.

**Parallelism:** May run with CK-08R2/R3, CK-07R1, and CK-QG1. It owns no
production query or publication files.

**Non-goals:** Production storage/query changes, SQLite in the truth lane,
copied expected rows, projections, or grading output as truth.

**Invariants:** Exact Decimal text, NULL, grades, order, selector sequences,
valuation, and no production import of test truth.

**Required tests/checks:** Import denylist, mutation sensitivity, all 80
variants, focused adapters/oracles, `just v`, and `just vc`.

**Acceptance:** 80/80 exact rows and evidence; production evaluator mutation
cannot change truth; canonical-fact mutation breaks consumer parity.

**Failure/rollback:** Record the exact unsupported semantic contract and keep
CK-09 blocked.

**Handoff:** Evidence digest and affected prior-claim requalification map.

**Cleanup/docs:** Preserve old evidence and link its superseding amendment.

**Suggested commit:** `test: add independent answer truth`
