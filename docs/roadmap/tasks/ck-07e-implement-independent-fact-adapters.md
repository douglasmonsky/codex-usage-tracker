# CK-07E — Implement independent fact adapters

**Status:** Completed on merge; exact-main verification is recorded in the completion handoff; CK-07A remains 0 / 80 requalified
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Supply the two independently implemented, test-only normalization
paths that CK-07A needs to compare structural-v2 question truth with one
database-v1 publication.

**Why:** Merged CK-07C freezes the pure plan/direct-fact compiler, and merged
CK-07D freezes effective-dated valuation. CK-07A still lacks qualified adapters
that independently turn structural declarations and a query-only database
snapshot into exact `CanonicalFact`, `PlanRequest`, and ordered evidence
inputs. Coupling those truth lanes inside CK-07A would invalidate the required
independence proof.

**Dependencies:** CK-07B, CK-07C, and CK-07D merged; immutable CK-07D authority
`e49531b0775c5c7f1043497042c25a200b447bb7`; retained CK-07A and CK-08
blocker evidence.

**Controls:** `LOGICAL_KERNEL_CONTRACT.md`,
`FORMULA_AND_SELECTOR_CONTRACT.md`, `PLAN_OPERAND_AND_FACT_CONTRACT.md`,
`AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md`, `ADAPTER_CONTRACT.md`,
`PUBLICATION_REFRESH_RECOVERY.md`, `QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`,
`TARGET_ARCHITECTURE.md`, `QUALIFICATION_PLAN.md`, and the CK-07A through
CK-07D packets.

## Frozen interfaces and independence

- `StructuralReferenceFactAdapter` consumes only body-free structural-v2
  declarations, emitted structural facts and source occurrences, a typed
  `PlanRequest`, and merged pure contracts. It cannot access SQLite,
  production query code, scenario outputs, expected answers, grades,
  comparisons, or the database adapter.
- `DatabaseV1FactAdapter` consumes only a caller-owned query-only SQLite
  connection, a typed `PlanRequest`, and merged pure contracts. In one read
  snapshot it selects only explicitly allowlisted database-v1 relations. It
  cannot import the reference adapter, scenario generator or output, oracle
  bundle, Candidate A paths, grading/comparison output, or refresh/write code.
- Both adapters may share only merged schemas/contracts and pure CK-07C/CK-07D
  symbols. Each independently emits `CanonicalFact` rows, the normalized
  `PlanRequest`, and ordered owner-specific evidence references. Required and
  materialized `(role, selector_kind, selector)` triples must match exactly.

## Fact and provenance coverage

Qualification spans calls/tokens/model profiles, sessions/hierarchy/cohorts,
tools/resources/retry stages, state changes, context components, allowance
observations/cycles/intervals, CK-07D valuation/frontiers/unpriced reasons,
publication/head/coverage/delta snapshots, source manifestations/occurrences,
transient structural investigation inputs, and the seven-part total order.
The four CK-07B no-window cases retain owner-specific scope; neither adapter
may fabricate a time window.

All 14 CK-07B selector kinds remain admitted:

```text
allowance_interval allowance_observation call model_profile project
publication rate_card resource session source_manifestation state_change
tool turn window
```

Every reference resolves through its authoritative owner and carries one of
the six typed, non-placeholder provenance kinds. Required/materialized order,
entity existence, and semantic selector identity must remain stable through
clean rebuild, source replacement, and late-event replay. Occurrence
coordinates may change or multiply without changing semantic identity.

## Effective-dated valuation

Both adapters independently materialize the publication-captured immutable
rate-card frontier and derive `valuation_match` through merged CK-07D pure
symbols. Each call selects the greatest matching captured revision whose
`effective_at_us <= call.event_at_us`; effective-time recency wins before
same-time exact-profile versus alias precedence. `fetched_at_us` is
provenance-only, and the selected revision digest participates in valuation
identity. Invalid or missing inputs produce typed unpriced rows, and
configured-estimate coverage excludes them. No call-to-price assignment,
answer cache, or time-blind singular card is persisted or admitted.

## Artifacts

- `tests/agent_kernel/fact_adapters/reference.py`
- `tests/agent_kernel/fact_adapters/database.py`
- `tests/agent_kernel/fact_adapters/support.py`
- `tests/agent_kernel/fact_adapters/test_contracts.py`
- `docs/decisions/evidence/ck07e/independent-fact-adapters-evidence.json`

No production package or database-v1 DDL change is admitted.

**Invariants:** Test-only adapters remain independent and body-free; database
reads remain query-only and snapshot-bound; all selector owners and evidence
references remain typed and ordered; CK-07D effective-time semantics remain
unchanged; CK-07A remains 0 / 80 requalified and CK-08 remains blocked.

**Required tests/checks:**

- Structural and database materialization parity for every permitted
  plan-operand relation and fact family, including `NULL`, empty, ties,
  deterministic order, and owner-specific no-window scope.
- All 14 selector kinds with exact ordered required/materialized triples,
  authoritative entity existence, complete typed provenance, and clean
  rebuild/replacement/late-event stability.
- Effective-time before/exact/after selection, newer-alias versus older-exact
  precedence, same-time exact precedence, missing measurement, immutable
  frontier validation, selected-digest identity, configured-estimate coverage,
  and bounded backdated dirty intervals.
- Import/source allowlists proving evaluator independence and rejection of
  expected/oracle/grading/comparison/body inputs.
- Focused adapter, plan, formula, selector, valuation, schema, storage, and
  publication checks, followed by `just v` and `just vc`.
- Repository-private GitNexus bootstrap and exact compare-based
  `detect_changes` before each commit; one comprehensive read-only final review
  after the diff stabilizes; required CI; merge; exact-main verification.

**Acceptance:**

1. Both adapters independently emit equivalent normalized facts, request, and
   ordered evidence for every required fact family without importing or
   consuming output from the other.
2. Every current plan relation and all 14 selector owners are materially
   represented with exact missingness, deterministic order, real entity
   ownership, and typed non-placeholder provenance.
3. CK-07D valuation selection, frontier, identity, unpriced, coverage, and
   dirty-interval semantics reconcile between structural truth and the
   query-only database snapshot.
4. Clean rebuild, replacement, and late-event replay preserve semantic selector
   identity and normalized parity.
5. Emitted structural JSONL and adapter sources contain no expected/oracle
   rows, grades, grading, comparison results, answer caches, secrets, private
   paths, real Codex content, production query imports, or refresh/write paths.
6. Focused and full local profiles, independent final review, required CI,
   merge, and exact-main post-merge verification pass.
7. CK-07A becomes ready to resume only when durable CK-07E evidence has no
   residual fact-family, selector-owner, provenance, independence, or
   effective-valuation gap. CK-07E claims **0 / 80** CK-07A answer
   comparisons; CK-08 remains blocked.

**Non-goals:** CK-07A expected-row generation or 80-answer comparison,
Candidate A scoring/timing, CK-03 through CK-07 evidence refresh, production
query/evidence code, generic SQL, MCP/setup/CLI/skill, release/tag/publishing,
deployment, Linear mutation, CK-08, CK-09, or CK-15.

**Failure/rollback:** If any fact family, selector owner, independence rule, or
CK-07D valuation contract cannot be implemented inside this test-only
boundary, record the exact blocker, keep CK-07A and CK-08 blocked, and stop.
Before merge, discard the branch. After merge, revert CK-07E as one
prerequisite packet; no database migration is required.

**Cleanup/docs:** Retain the dedicated CK-07E worktree and exact-main
verification worktree. Update the documentation authority, roadmap, packet
ledger, CK-07A resume boundary, qualification plan, scope classifier, and
durable CK-07E evidence in this change.

**Suggested commit:** `test(agent-kernel): qualify independent fact adapters`
