# CK-07B — Freeze formula and provenance contract

**Status:** Completed on merge via PR #383 — exact-main verification is recorded
in the completion handoff
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Supply the narrow executable formula, selector, provenance, and scope
decision required for CK-07A to evaluate all 80 structural-v2 variants.

**Why:** CK-07A stopped correctly after proving that 45 formula IDs had no
executable authority, selector ownership was underspecified, allowance and
publication edge cases were ambiguous, and four requests had no generic fact
window.

**Dependencies:** merged CK-07, admitted CK-07A, and CK-07A's retained blocker
evidence.
**Controls:** `SUPPORTED_QUESTION_CONTRACTS.md`,
`LOGICAL_KERNEL_CONTRACT.md`,
`AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md`,
`QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`,
`QUALIFICATION_PLAN.md`, and
`FORMULA_AND_SELECTOR_CONTRACT.md`.

## Scope

- Freeze exactly 45 executable formula definitions, 61 catalog uses, 185
  answer-field bindings, exact per-use canonical-relation/request gates, and
  pure contract symbols.
- Preserve all 14 declared selector kinds and define owner-specific resolution
  plus evaluator-local entity resolvers without a database migration.
- Define exact ordered role/kind comparison, entity existence,
  non-placeholder provenance, and lifecycle stability gates.
- Define allowance interval, rate card, window, publication, model profile,
  source manifestation, and four no-window ownership/materialization rules.
- Give CK-07A exact consumption files, comparison completeness, evaluator
  independence, and carry-forward rules.

**Non-goals:**

Candidate A rebuild, database-v1 DDL migration, CK-03–CK-07 requalification,
CK-08 query/evidence implementation, CK-09 projections, public MCP/CLI/skill,
generic SQL, real logs/databases, release, tag, deployment, or Linear changes.

**Invariants:**

- all 45 formula IDs, 61 catalog uses, 40 questions, and 185 answer fields
  reconcile exactly;
- all 14 declared selector kinds remain accepted and resolve through their
  authoritative owner without fallback;
- reference and database-v1 replay evaluators remain independent;
- only synthetic structural fixtures may be used; and
- CK-07A and CK-08 remain incomplete and blocked respectively until CK-07A
  executes its qualification.

**Acceptance:**

1. Formula registry, schema, implementation, and synthetic vectors reconcile
   exactly to all 45 catalog IDs, 61 uses, and 185 fields.
2. Materialized selector references equal the required ordered role/kind
   sequence; every reference proves entity existence, typed provenance, and
   lifecycle stability.
3. All 14 declared selector kinds remain accepted through authoritative owner
   dispatch. `selector_anchors` is not treated as a universal registry, and no
   fallback or DDL migration is implied.
4. Q-ALW-02 and Q-OPS-01 plan-specific scope rules cover the four blocked
   variants without inventing a persisted window or publication.
5. CK-07A resume instructions are deterministic and evaluator independence is
   executable.
6. Focused contracts, `just v`, `just vc`, final review, required CI, merge,
   and exact-main verification pass.

**Required tests/checks:**

- focused formula, selector-provenance, question-catalog, lifecycle, and
  integration-scope contract tests;
- repository bootstrap and private GitNexus impact/detect-changes checks;
- `just v` and `just vc`;
- one final read-only review after the diff is stable;
- required pull-request CI and exact-main post-merge verification.

**Failure/rollback:**

If a formula remains undefined, an accepted selector cannot prove its owner or
provenance without broader migration, or the independent comparison contract
cannot execute, keep CK-07A and CK-08 blocked and record the exact residual
gap. Revert CK-07B as one contract packet; do not partially narrow selectors,
invent fallback evidence, or mutate database-v1.

**Cleanup/docs:**

Retain the dedicated CK-07B worktree and evidence. Update the documentation
authority, logical/query/qualification contracts, roadmap, ledger, CK-07A
resume packet, and physical-decision residual risk. Do not delete retained
worktrees or historical CK-04–CK-07 evidence.

**Suggested commit:** `feat: freeze CK-07B formula and provenance contract`

## Durable evidence

The completion record is
`docs/decisions/evidence/ck07b/formula-and-provenance-contract-evidence.json`.
It records artifact identities, exact counts, the no-narrowing decision,
validation, review accounting, PR/merge identity, and residual risks. CK-07A
remains unqualified until it executes its full seam replay.
