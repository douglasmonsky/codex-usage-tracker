# CK-08 — Implement fact-backed query and evidence services

**Status:** Blocked — fact-backed oracle prerequisite missing
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Compile named/typed requests to the selected physical tables and
resolve stable bounded evidence before adding projections.

**Why:** Fact-backed truth is the oracle for every later optimization.

**Controls:** `QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`, CK-01, CK-05–CK-07.
**Dependencies:** CK-07.

**Scope and expected files:**

- `query/contracts.py`, `registry.py`, `compiler.py`, `service.py`;
- `evidence/selectors.py`, `cursors.py`, `service.py`;
- current valuation and allowance read services needed by questions;
- query/evidence tests and plan snapshots.

**Schema changes:** Only indexes explicitly selected by CK-04; no projections
yet.
**API changes:** Internal typed request/result/evidence envelopes.

**Non-goals:** Public MCP, generic SQL, narrative analysis, projection added to
hide a failing plan.

**Invariants:** One read snapshot; keyset cursors; exact counts opt-in; complete
server-side sort; human labels first; four token columns; current valuation
coverage; no refresh/write.

**Tests/benchmarks:** Every Foundation/Cutover fact-backed oracle, cursor
rebuild/replacement/late events, exact count, order ties, unsupported
reframings, EXPLAIN plans, SQL/payload measurements at both scales.

**Acceptance:** Exact answers/evidence pass; selectors stable; result envelope
under budget; every plan reports whether it already meets its class or requires
a CK-09 projection.

**Failure/rollback:** Keep registry entry unimplemented rather than silently
returning incomplete data. No API is public yet.

**Cleanup/docs:** Produce measured projection-admission list.

## Blocking prerequisite found

CK-08 cannot implement or accept the named plans against the unchanged CK-03
question oracles without violating the fact-backed runtime boundary. The
checked-in `Q-ACC-01` boundaries case asks for one exact half-open window and
expects 18 calls and 6,250 uncached-input tokens. Publishing the same synthetic
fixture through the CK-06 adapter and CK-07 writer produces 2 canonical calls
and 1,873 uncached-input tokens in that window.

The CK-04 Candidate A proof does not resolve this mismatch. Its query reads a
candidate-only `question_cases` table populated from `oracle_case` grading
records. The database-v1 contract explicitly forbids that table in the
production package. Adding an equivalent table, reading `oracle_case` records
at runtime, or changing a query to return the frozen expected row would make
the grading truth the answer source instead of deriving the answer from
canonical facts.

The exact inputs, hashes, SQL result, and contract references are recorded in
[`fact-backed-oracle-prerequisite-gap.json`](../../decisions/evidence/ck08/fact-backed-oracle-prerequisite-gap.json).
Before CK-08 can resume, the authority set must freeze Foundation/Cutover
question cases whose expected rows are independently calculated from the
canonical facts emitted for the same typed requests. The replacement must keep
all 21 named plans, 42 variants, grades, formulas, selectors, and limits, and
must prove the oracle without a candidate-only answer table. This packet
remains unchecked; no registry entry, query/evidence implementation,
projection, public API, or CK-09 work is admitted by this blocker record.

**Suggested commits:**

1. `feat: add bounded agent-kernel query compiler`
2. `feat: add stable evidence service`
