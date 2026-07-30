# Formula and Selector Provenance Contract

**Status:** CK-07B implementation authority
**Formula family:** `codex-usage-tracker.formula-contract.v1`
**Selector family:** `codex-usage-tracker.selector-provenance.v1`

This contract closes the logical gap found by CK-07A. It defines the executable
meaning of every formula named by the structural-v2 question catalog and the
owner-specific resolution and provenance rules for every declared selector
kind. It amends the question, logical, query/evidence, and qualification
contracts only where stated below. It does not change database-v1 DDL, rebuild
Candidate A, or implement a production query plan.

## Executable formula authority

The canonical registry is
`config/agent-kernel/formula-contract-v1.json`, validated by
`formula-contract-v1.schema.json`. Its pure implementation is
`codex_usage_tracker.agent_kernel.domain.formulas.evaluate_formula`.

The registry contains exactly the 45 formula IDs referenced by
`question-catalog-v1.json`, all 61 question-to-formula uses, and an exact
classification for all 185 answer fields. Each question binding distinguishes
formula-produced fields, direct facts, and formulas used internally for
selection or ordering, so no formula is attached to an unrelated answer
field. The 61 `formula_uses` records additionally lock each formula invocation
to its catalog plan, canonical logical relations, typed request parameters,
output fields, and a rule forbidding answer/oracle/grading inputs. Each formula
record fixes its:

- inputs and canonical normalized fact relations;
- filtering, grouping, ordering, and tie behavior;
- null, invalid, zero-denominator, and empty-domain behavior;
- integer and finite-decimal types, units, and rounding;
- half-open window source; and
- deterministic result shape and executable symbol.

Formula execution receives normalized operands only. It reads neither SQLite,
the clock, a scenario, an oracle row, nor grading output. CK-07A's two
evaluators may share this authority, but each must independently select and
normalize its permitted facts. Neither evaluator may import the other or
consume the other's emitted answer, oracle, grade, or comparison result.

CK-07C supplies the missing executable consumer contract in
`plan-operand-contract-v1.json` and
`codex_usage_tracker.agent_kernel.domain.plan_operands`. Its bindings replace
the narrative `operand_rule` as the authority for converting normalized
relation rows into operands and direct facts; this CK-07B artifact continues
to own formula operation semantics.

The default token formulas are:

```text
total_input_tokens = uncached_input_tokens + cached_input_tokens
total_tokens = total_input_tokens + output_tokens
```

Reasoning tokens remain separate. A missing required token measurement makes
the aggregate `NULL`; an empty eligible domain is exact zero. Finite decimal
results are never implicitly rounded.

## Selector acceptance and comparison

The canonical registry is
`config/agent-kernel/selector-provenance-v1.json`, validated by its paired
schema. All 14 selector kinds already declared by the catalog and logical
contract remain accepted:

```text
allowance_interval  allowance_observation  call  model_profile  project
publication        rate_card              resource  session     source_manifestation
state_change       tool                   turn      window
```

The catalog's `selector_kinds` are a plan allowlist, not an instruction to
materialize every listed kind. Each case must declare an ordered,
role-tagged sequence of required, conditional, and forbidden references.
Repeated kinds are valid when roles differ. The materialized evidence sequence
must equal the required `(role, selector_kind)` sequence exactly.

Every materialized reference must name an existing logical entity and carry
typed, non-placeholder provenance. Allowed provenance kinds are
`source_occurrence`, `derived_boundary_pair`, `configured_artifact`,
`request_derivation`, `publication_commit`, and `source_inventory`.
Set containment, best-effort subsets, fabricated occurrences, and silent
fallback kinds fail closed.

`selector_anchors` is an optimization for kinds stored there, not the universal
selector registry. Resolution dispatches to the authoritative owner named by
the selector-provenance registry. All 14 kinds have an owner rule. Validation
must call that owner's entity resolver; a caller-authored existence boolean is
not evidence. The same logical selector must survive clean
rebuild, source replacement, and late-event replay. Occurrence coordinates may
change or multiply without changing semantic identity. A disclosed alias may
correct an identity, but cannot hide a semantic split or merge.

## Ownership and materialization

### Allowance interval

`allowance` owns `allowance_intervals`. It publishes one row for each pair of
distinct, adjacent, compatible observations and proves it with both boundary
selectors, both sets of real source occurrences, and the compatibility
version. Equal or identical boundaries are a valid empty case and produce no
interval row or interval selector.

### Rate card

`valuation` owns immutable validated `rate_card_revisions` and the selected
`active_rate_card`. A logical rate-card selector resolves by its normalized
digest. Its `configured_artifact` provenance includes source name, fetch time,
validation status, and digest. Missing or invalid active cards leave estimates
`NULL`; they never fall back to another selector kind.

### Window

`evidence` owns the normalized request value. A window selector is a stable
non-persisted logical entity identified by `(start_us, end_us, timezone)` for a
specific parameter role. Its `request_derivation` provenance includes request
digest and role. No database row or synthetic occurrence is required.

### Publication

`publication` owns immutable rows and `publication_head`. A committed
publication selector resolves in the same read snapshot as facts and coverage.
Its `publication_commit` provenance includes operation ID, artifact-manifest
digest, and commit time. Parent publication remains nullable.

### Model profile

`facts/model_calls` owns the observed `(model, reasoning_effort, service_tier)`
tuple in `model_profiles`. The selector resolves to that canonical row and
uses representative canonical calls plus their real occurrences as
`source_occurrence` provenance. Replacing a representative occurrence cannot
change the profile identity.

### Source manifestation

`sources` owns stable lineage rows in `source_manifestations`. The selector
resolves directly from the selected source inventory and uses
`source_inventory` provenance: source ID, content revision, state, and selected
publication. No self-referential JSONL occurrence is required.

Other selector kinds continue to resolve through their existing logical owners
and real source occurrences. CK-07B introduces no DDL migration.

## Four cases without a generic fact window

Scope resolution dispatches by `plan_id` before any generic fact-window rule:

- Q-ALW-02 `allowance_interval_events` resolves the two observation selectors
  and uses `[start.observed_at_us, end.observed_at_us)`. Equal observations or
  times return zero events and both boundary references, with no interval
  selector or synthetic microsecond.
- Q-OPS-01 `latest_publication_delta` resolves `publication_head` and reads the
  latest accepted `publication_deltas` row plus bounded entity and sample rows.
  It has no fact window. A no-change refresh creates no publication, so the
  answer remains the latest accepted publication delta while the operational
  no-change fact is preserved separately.

These rules cover `empty_interval`, `same_time_boundary`, `no_change`, and
`recanonicalized_owner`.

## CK-07A consumption contract

CK-07A resumes from the merged CK-07B commit and consumes exactly:

- `config/agent-kernel/formula-contract-v1.json` and its schema;
- `codex_usage_tracker.agent_kernel.domain.formulas.evaluate_formula`;
- `config/agent-kernel/selector-provenance-v1.json` and its schema;
- `tests.agent_kernel.contracts.reference.selector_provenance.
  validate_evidence_references_v1`; and
- the plan-specific scope rules in this document and the selector registry.

A complete comparison for each of all 80 variants means equal normalized
request digest; a complete answer object including every `NULL`; equal values,
grades, and deterministic order; exact field-to-formula bindings; and exact
ordered `(role, selector_kind, selector, provenance)` references. Every
reference must pass entity-existence, provenance, and
rebuild/replacement/late-event stability checks.

For `validate_evidence_references_v1`, CK-07A builds `owner_rules` directly
from the selector registry and supplies an evaluator-local
`resolve_owner_entity(kind, logical_id)` backed by its own scenario entity map
or database-v1 owner relation. The reference evaluator and replay evaluator
must not share resolver results.

The reference evaluator and database-v1 replay evaluator may share only the
authoritative contracts and pure symbols above. They cannot import one another,
read `oracle_case`/`question_cases`, or consume emitted expected, oracle,
grading, or comparison output.

Prior CK-04 through CK-07 lanes may be carried only when both input bytes and
the named execution path are byte-identical and path-identical. Otherwise
CK-07A reruns the lane and records the changed identity. CK-07B does not itself
requalify CK-03 through CK-07 or admit CK-08.
