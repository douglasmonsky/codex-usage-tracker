# Plan Operand and Canonical Fact Contract

**Status:** CK-07C implementation authority
**Contract family:** `codex-usage-tracker.plan-operand-contract.v1`

This contract closes the remaining executable gap between the CK-07B formula
operations and the canonical facts used by CK-07A. It defines how every named
plan turns typed request parameters and normalized canonical relation rows
into direct answer facts and formula operands. It also fixes the smallest
canonical representations for facts that the retained CK-07A replay proved
absent.

It does not implement a production query service, perform CK-07A's 80-case
requalification, admit a projection, or change the public MCP/CLI/skill
surface.

## Executable authority

The machine-readable authority is
`config/agent-kernel/plan-operand-contract-v1.json`, validated by its paired
JSON Schema. It references the exact question catalog and CK-07B formula
contract and reconciles:

- 40 question/plan entries;
- 61 formula uses;
- 112 direct-fact answer bindings;
- 73 formula-output answer bindings; and
- all 185 catalog answer fields.

Each plan record fixes:

- exact allowed logical relations and required row fields;
- typed required and optional request parameters;
- publication, capability, selector, and scope gates;
- half-open request or plan-specific no-window scope;
- grouping keys and complete deterministic input/result order;
- direct-fact source rules;
- every formula invocation's operand names and derivations;
- NULL, unavailable, empty-domain, and malformed behavior;
- formula-output extraction; and
- the consumer of every internal-only formula.

The derivation vocabulary is closed by the schema. It is deliberately smaller
than the CK-08 query grammar and cannot express SQL, table names, joins,
arbitrary functions, user expressions, or hidden callbacks. Output field names
never choose a source rule.

## Pure compiler and evaluator

The pure implementation is
`codex_usage_tracker.agent_kernel.domain.plan_operands`. Its public boundary is:

```text
PlanRequest
CanonicalFact
PlanEvaluation
PlanOperandContractError
compile_plan_operands(contract, request, facts)
evaluate_plan(contract, request, facts, formula_evaluator=evaluate_formula)
```

The compiler validates the artifact identity, exact plan and request shape,
permitted relations/fields, gates, grouping, ordering, cardinality, and
missingness before producing formula invocations and direct facts. The
evaluator invokes CK-07B's `evaluate_formula`, extracts declared output paths,
assembles every answer field, and retains declared internal results.

Neither function opens storage, reads a clock, resolves a source file, imports
an evaluator, or accepts an expected answer, oracle, grade, comparison result,
or grading row. Unknown relations, fields, request keys, opcodes, output paths,
and duplicate group identities fail closed. A formula failure cannot yield a
partial answer.

Exact finite decimals remain `Decimal` in memory and serialize as canonical
finite decimal strings. Binary floats and implicit rounding are forbidden.

## Request, scope, and order

Windows are signed UTC microseconds with half-open `[start_us, end_us)`
semantics and an explicit timezone when the catalog requires it. Optional
absence is distinct from explicit `NULL`.

The four cases without a generic fact window retain CK-07B's rules:

- Q-ALW-02 uses the two named allowance observations and
  `[start.observed_at_us, end.observed_at_us)`;
- Q-OPS-01 uses `publication_head` and the latest accepted publication delta.
- Q-OPS-02 requires a host-captured signed UTC-microsecond `as_of_us` request
  and compares it with the publication's observed-through time; the compiler
  does not read a clock.

Equal allowance boundaries return zero events with both boundary references.
They do not create an interval selector or a synthetic microsecond. A
no-change operation creates no publication and leaves the latest accepted
publication delta unchanged.

All event ordering uses:

```text
(
  event_at_us IS NULL,
  event_at_us,
  source_rank,
  source_order,
  event_kind_order,
  logical_id,
  transition_rank
)
```

Missing coordinates never fall back to arrival, list, or SQLite row order.

`bounded_adjacency_v1` is immediate adjacency in the complete eligible event
stream after request, publication, capability, selector, and scope gates.
Only after complete total ordering may a plan retain declared adjacent
left/right kinds. The v1 result therefore reports exactly zero intervening
events. Finding the next matching event across intervening activity would be
a different, versioned operation.

## Current valuation relation

`valuation_match` is a deterministic current-only logical relation. It is
derived from:

- canonical call token measurements and model-profile ownership;
- the captured publication's rate-card digest;
- the matching immutable, validated rate-card revision; and
- active rate-card selection for that same publication.

`codex_usage_tracker.agent_kernel.domain.valuation` supplies the pure typed
relation compiler. It performs exact Decimal arithmetic over the four token
classes, preserves the `reasoning_in_output` rule, and returns match basis,
cost/credit estimates, rated and missing token fields, coverage numerators and
denominators, explicit unpriced reasons, and configured-estimate grades.

Missing, invalid, unmatched, or partial rate cards create typed unpriced rows
with `NULL` estimates. They never create zero cost and never fall back to a
different card. Calls are immutable; this relation is not a projection or an
expected-answer cache.

## Context components

Positive `context_component_coverage_v1` operands cannot be reconstructed from
calls, occurrences, or grading metadata. Database-v1 therefore adds the
smallest typed `context_components` relation.

A component contains only:

- stable component, session, turn, and optional call ownership;
- a fixed structural category;
- observed UTF-8 byte count and/or event count;
- optional total observed context bytes for the same owner/inclusion basis,
  required before unattributed bytes may be computed;
- optional estimator identity and exact estimated tokens;
- inclusion basis (`observed_in_source`, `selected_by_host`,
  `known_included_in_call`, or `inclusion_unknown`);
- measurement mask and basis;
- complete total-order and source-occurrence provenance; and
- first/last publication provenance.

It contains no prompt, response, reasoning, command, patch, file, message, or
tool-output body. Observed source content is not proof that a call included it.
When the capability is absent, the plan returns its declared unavailable
outcome rather than an invented empty component.

## Structural input representations

The plan artifact resolves plan grain rather than leaving it to either
evaluator. In particular, top-session results are session-grained with
plan-wide concentration repeated on each selected row; cache-reuse and
cached-replay candidates are call-grained; context trajectories are
session/context-epoch grained; token acceleration is session-grained; first
calls without a predecessor are excluded from jump rows; and profile
transitions are one row per changed adjacent pair.

Explicit cohort requests have exactly `left` and `right` arrays of session
IDs. Family mode is `project` or `root_session` for project-family plans and
`root` or `direct_parent` for delegation plans. Cohorts, family ownership, and
candidate identities are never inferred from labels.

### Allowance boundaries and cycles

`allowance_limits`, `allowance_cycles`, `allowance_observations`, and
`allowance_intervals` remain authoritative. Publication preparation preserves
cycle bounds and completion status. It materializes one interval only for two
distinct adjacent compatible observations with equal provider, limit, plan,
window kind, cycle/reset identity, and nondecreasing observed time.

Equal-time distinct observations may form a zero-width interval. An identical
selector, reset/plan/limit change, or incompatible pair forms no interval.
Only positive compatible deltas are ratio eligible.

### Hierarchy and cohorts

`sessions` and `late_parent_edges` own hierarchy. Root, parent, depth, and
relationship basis are explicit, and late discovery changes no usage identity
or activity time. Cohort membership is a typed request input with explicit
members and roles. Labels, path similarity, session length, and emitted
answers cannot create a cohort.

### Retry stages and feature inputs

Retry stages are a deterministic normalization of canonical ordered tool
operation, resource, and lifecycle facts into the fixed sequence vocabulary
used by `retry_sequence_matcher_v1`. Stable event IDs and one resource are
required for a match. Read/search/inspect operations form `inspect`; a
write/edit/execute/test operation forms `attempt`; a failed attempt forms
`failure`; the next inspect and attempt for the same resource form
`reinspect` and `retry`. No free-form stage blob is persisted.

Structural workflow and investigation candidates use typed transient counts,
coverage, baselines, and representative selectors derived from canonical
calls, turns, tools, resources, lifecycle, and state changes. The database
does not persist `skill_candidate`, `waste`, `productivity`, a generic feature
blob, or a grading result.

Their fixed candidate signature is semantic operation, resource kind, and
write intent. Their admitted feature vocabulary is call, turn, tool,
failure, mutation, sequence, and four-token counts/sums plus explicit
coverage counts. Weekly-review and side-by-side plans assemble fixed named
maps from those same derivations; they never accept a source-authored
`features`, `baseline`, `section`, or answer object.

### Publication snapshots

One read snapshot supplies `publication_head`, the committed publication,
source/capability coverage, entity counts, the latest accepted delta and
bounded delta samples, active rate-card identity, and all selected facts.
Writer-internal prior-state objects are not query/replay publication facts.

## Evaluator independence and CK-07A handoff

CK-07A's reference evaluator converts one structural-v2 scenario declaration
into `CanonicalFact` rows. Its database-v1 evaluator independently selects
permitted rows from one query-only SQLite snapshot and normalizes those rows.

The evaluators may share:

- the logical, formula, selector-provenance, and plan-operand artifacts and
  their schema parsers;
- immutable pure value types;
- `compile_plan_operands`, `evaluate_plan`, `evaluate_formula`, and the pure
  valuation relation compiler.

They may not share:

- SQLite or scenario relation-selection code;
- owner-resolution results;
- precompiled operands or direct slots;
- answer, oracle, grading, or comparison output; or
- emitted expected rows.

CK-07A compares normalized request digest; every answer value including
`NULL`; grades; deterministic order; all 185 field bindings; and the exact
ordered role-kind-selector-provenance sequence. This packet makes that replay
executable but does not claim that any of the 80 variants has passed.

## Exact CK-07A resume surface

CK-07A must validate `config/agent-kernel/plan-operand-contract-v1.json`
against `config/agent-kernel/plan-operand-contract-v1.schema.json`. Its shared
pure symbols are:

- `FactCoordinates`, `CanonicalFact`, `PlanRequest`, `FormulaInvocation`,
  `PlanGroup`, `PlanMaterialization`, `PlanEvaluation`, and
  `PlanOperandContractError`;
- `compile_plan_operands` and `evaluate_plan`;
- `CurrentRateCard`, `CurrentValuationMatch`, and
  `compile_current_valuation_matches`;
- CK-07B's `evaluate_formula`.

The CK-07C source paths that create or amend executable behavior are:

- `src/codex_usage_tracker/agent_kernel/domain/plan_operands.py`;
- `src/codex_usage_tracker/agent_kernel/domain/plan_derivations_accounting.py`;
- `src/codex_usage_tracker/agent_kernel/domain/plan_derivations_structural.py`;
- `src/codex_usage_tracker/agent_kernel/domain/valuation.py`;
- `src/codex_usage_tracker/agent_kernel/adapters/contracts.py`;
- `src/codex_usage_tracker/agent_kernel/adapters/codex_jsonl/normalize.py`;
- `src/codex_usage_tracker/agent_kernel/publication/preparation.py`;
- `src/codex_usage_tracker/agent_kernel/publication/writer.py`;
- `src/codex_usage_tracker/agent_kernel/storage/analytical.sql`,
  `repositories.py`, and `schema.py`.

Before CK-07A resumes its own 80-case requalification, it must run:

```text
pytest -q tests/agent_kernel/contracts/test_plan_operand_contract.py
pytest -q tests/agent_kernel/contracts/test_plan_derivations_accounting.py
pytest -q tests/agent_kernel/contracts/test_plan_derivations_structural.py
pytest -q tests/agent_kernel/contracts/test_current_valuation_relation.py
pytest -q tests/agent_kernel/contracts/test_formula_contract.py
pytest -q tests/agent_kernel/contracts/test_selector_provenance_contract.py
pytest -q tests/agent_kernel/contracts/test_database_v1_schema_contract.py
pytest -q tests/agent_kernel/adapters tests/agent_kernel/storage tests/agent_kernel/publication
```

The two evaluators may share only those validated artifacts and pure symbols.
Neither may import the other or consume emitted answer, oracle, grading, or
comparison rows.
