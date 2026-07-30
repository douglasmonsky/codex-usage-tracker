# CK-07C — Freeze plan operands and missing canonical facts

**Status:** Completed on merge; CK-07A is ready to resume but remains
unrequalified
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Supply the narrow executable plan-to-operand, direct-fact, and
missing-canonical-fact authority required for CK-07A to independently derive
all 185 answer fields from scenario facts and database-v1 rows.

**Why:** CK-07B correctly froze 45 pure formula operations, 61 catalog formula
uses, 40 answer bindings, 185 answer fields, and owner-dispatched selector
provenance. Its `formula_uses[].operand_rule` remains narrative, so an
independent reference evaluator and database-v1 replay evaluator would still
have to invent how canonical relation rows become formula operands and direct
facts. The retained CK-07A worktree also proved that current structural-v2
scenarios and database-v1 cannot materially represent every required fact.

**Dependencies:** merged CK-07B at
`eec1acf34aa1e30e5415e6b12c95221daf226fff`, retained CK-07A blocker
evidence, and the CK-08 fact-lineage blocker.

**Controls:** `SUPPORTED_QUESTION_CONTRACTS.md`,
`LOGICAL_KERNEL_CONTRACT.md`, `FORMULA_AND_SELECTOR_CONTRACT.md`,
`AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md`,
`QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`, `TARGET_ARCHITECTURE.md`,
`QUALIFICATION_PLAN.md`, and the CK-07A/CK-07B packets.

## Frozen executable surface

- `config/agent-kernel/plan-operand-contract-v1.json`, validated by
  `plan-operand-contract-v1.schema.json`, is the sole plan-to-operand and
  direct-fact binding artifact.
- `codex_usage_tracker.agent_kernel.domain.plan_operands.PlanRequest`,
  `CanonicalFact`, `PlanEvaluation`, `PlanOperandContractError`,
  `compile_plan_operands`, and `evaluate_plan` are the storage-independent
  pure compiler/evaluator surface.
- The artifact contains one record for every catalog question/plan pair,
  exactly 61 formula invocations, exactly 112 direct-fact bindings, and exact
  extraction for all 73 formula-produced fields. It declares typed request,
  selector, publication and capability gates; source relations and fields;
  grouping, total order, NULL and empty behavior; operand derivations; output
  extraction; and internal-only formula results.
- Derivations use a closed opcode vocabulary. Arbitrary expressions, SQL,
  table names, field-name inference, hidden plan-specific Python callbacks,
  clocks, storage access, and answer/oracle/grading/comparison inputs are
  forbidden.
- `bounded_adjacency_v1` means immediate adjacency in the complete gated
  canonical total order. A retained adjacent pair therefore has exactly zero
  intervening events. “Next matching event” is not this v1 operation.

## Missing-fact decisions

- Current valuation remains a deterministic read-side `valuation_match`
  relation over canonical calls, model profiles, the captured publication
  rate-card digest, the validated immutable rate-card revision, and active
  selection. It is not a projection and does not rewrite calls.
- Context components receive the smallest body-free typed database-v1
  relation because no existing row or deterministic join can represent a
  positive `context_component_coverage_v1` operand. It stores structural
  category, observed bytes/count, optional estimator/token estimate, inclusion
  basis, owner IDs, total-order/source-occurrence provenance, measurement
  basis, and publication provenance; it stores no content.
- Existing allowance cycles and intervals are the authoritative pair/cycle
  representation. Publication preparation must preserve typed cycle
  bounds/status and materialize only distinct adjacent compatible observation
  pairs.
- Existing session hierarchy plus late-parent edges is authoritative.
  Cohorts are explicit typed request membership and are never inferred from
  labels.
- Retry stages are a locked deterministic normalization of ordered tool
  operation/resource/lifecycle facts. Structural and investigation feature
  inputs are transient typed relation rows, not generic persisted feature
  blobs or expected answers.
- Existing canonical total-order columns and publication/coverage/delta tables
  are authoritative. Four no-window cases retain CK-07B owner-specific scope
  rules; no synthetic microsecond is permitted.

## Scope

- Add and validate the plan-operand artifact, pure compiler/evaluator, current
  valuation relation, and contract vectors.
- Amend logical/database-v1 implementation only for facts proven absent.
- Add synthetic parity vectors that compare scenario facts and database rows
  at the normalized operand boundary where both sources can materialize the
  same facts.
- Update schema digest/inventory and compatibility authority for any database
  amendment.
- Give CK-07A exact artifact/symbol paths and tests for resumption.

**Non-goals:** CK-07A's 80-case requalification, CK-04 requalification,
production query/evidence code, projections, public MCP/setup/CLI/skill,
Console, generic SQL, narrative analysis, installed harness work, release,
tag, publish, deployment, Linear mutation, CK-08, CK-09, or CK-15.

## Invariants

- Preserve exactly 40 questions, 61 formula uses, 112 direct facts, 73 formula
  outputs, 185 fields, and all 14 selector kinds.
- Reference and database-v1 replay evaluators may share only authoritative
  schemas/contracts and pure symbols. Neither may import the other or consume
  emitted expected, oracle, grading, or comparison output.
- Exact ordered required/materialized role-kind-selector equality,
  owner-dispatched existence, typed non-placeholder provenance, and
  rebuild/replacement/late-event stability remain unchanged.
- Missing operands fail closed. Missing is never rewritten as zero.
- Decimal values serialize as canonical finite decimal text without binary
  float conversion or implicit rounding.
- All fixtures and vectors are synthetic and body-free.

## Required validation

- Contract schema and exact catalog/formula/binding reconciliation.
- Known-answer and negative vectors for every plan/formula use and all 185
  bindings, including NULL, empty, malformed/missing operands, exact Decimal,
  ordering, and ties.
- Scenario-to-operands versus database-rows-to-operands parity for every
  materially representable fact family.
- Focused formula/operand, valuation, logical, schema, adapter, storage,
  publication, selector-provenance, and release-scope checks.
- `just v` and `just vc`.
- Before every commit, repository bootstrap GitNexus check plus exact
  `detect_changes` against `origin/main`.
- One final comprehensive read-only reviewer after the diff is stable.

## Acceptance

1. Every one of the 61 formula uses has executable operands and every one of
   the 185 answer fields has an executable direct or formula-output rule.
2. The pure compiler/evaluator reads no storage or clock and rejects missing,
   malformed, answer, oracle, grading, and comparison inputs.
3. Valuation and context component inputs are materially representable with
   exact missingness and provenance; structural-v2 input families have
   authoritative typed representations.
4. CK-07B selector/provenance invariants and all 14 kinds remain intact.
5. Focused checks, `just v`, `just vc`, final review, required CI, merge, and
   exact-main post-merge verification pass.
6. CK-07A is marked ready only if no residual plan operand or fact
   representation gap remains. CK-07A's 80 variants are not claimed
   requalified by this packet.

**Failure/rollback:** If any plan/direct fact remains heuristic, any required
fact cannot be represented without broader product work, or a selector kind
would need narrowing, record the exact residual and keep CK-07A and CK-08
blocked. Before merge, rollback is this branch. After merge, revert CK-07C as
one contract packet.

**Invariants:** The frozen counts, selector/provenance equality, body-free
privacy boundary, deterministic ordering, and independent-evaluator separation
above are release-blocking.

**Acceptance:** The six acceptance gates above must pass with no residual
operand or canonical-fact representation gap.

**Required tests/checks:** Run the focused operand, valuation, logical,
database, adapter, publication, and selector suites followed by `just v`,
`just vc`, required CI, and exact-main post-merge verification.

**Cleanup/docs:** Retain the dated CK-07C and CK-07A worktrees; update this
packet, the roadmap ledger, architecture contracts, qualification authority, and
durable evidence in the same pull request.

**Suggested commit:** `feat(agent-kernel): freeze CK-07C operand contracts`

## CK-07A resume contract

CK-07A consumes only the exact merged artifact/schema and pure symbols named
above, the unchanged CK-07B formula/selector authorities, and the typed
database-v1 relations accepted by this packet. Its independent reference lane
normalizes scenario declarations to `CanonicalFact` rows. Its independent
database lane selects permitted database-v1 rows in one read snapshot and
normalizes them separately. Both call `evaluate_plan`; neither shares selected
rows, operands, answers, or owner-resolution results.
