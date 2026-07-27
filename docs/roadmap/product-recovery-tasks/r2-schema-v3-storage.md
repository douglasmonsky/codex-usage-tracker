# R2 — Define Schema V3 And Compact Storage

## Objective

Approve a compact metadata-first analytical schema that preserves exact
accounting and evidence while removing per-call allowance amplification,
wide-key index amplification, and landing-page scans.

## Depends On

R1.

## Ownership

R2 is the sole owner of:

- analytical and operational schema definitions;
- stable identity and internal-key policy;
- upgrade and rollback state machine;
- allowance interval semantics;
- rollup table contracts;
- schema fixtures, migration tests, and storage budgets.

No parallel task may edit schema files until R2 merges.

## Contract Added First

Add failing schema-v3 contracts for:

- integer internal foreign keys plus stable external selectors;
- four token classes;
- exact copied-row exclusion;
- compact allowance state observations and intervals;
- observation trigger distinct from causal attribution;
- persisted generation-scoped rollups;
- human thread label plus opaque logical selector;
- metadata-only privacy;
- side-by-side build, atomic promotion, and rollback;
- measured database-size ceiling.

## Schema Decisions

- Use analytical schema version 3.
- Build under a new side-by-side cache generation; never mutate the validated
  schema-v2 database in place.
- Keep stable logical selectors as external evidence identities.
- Use compact internal row keys and foreign keys for joins and indexes.
- Keep the optional content store separate and disabled by default.
- Store tool operation and bounded safe target metadata, never raw arguments or
  output.
- Store allowance state only when the exact timestamp snapshot or ordered state
  changes according to the approved interval algorithm.
- Preserve reset boundaries, first and last observations, periodic freshness
  checkpoints, and source provenance.
- Replace causal `source_call` wording with observation-trigger semantics.

## Required Rollups

Generation-scoped persisted rollups cover:

- global four-token and call totals;
- thread and call ranking facts;
- model × effort;
- hour and day token bands;
- configured cost and credit totals with coverage;
- allowance interval facts;
- tool operation summaries.

Rollups are disposable and exactly reproducible from foundational facts. Their
publication is atomic with the generation they summarize.

## Upgrade Contract

- First explicit refresh builds schema v3 beside schema v2.
- Existing readers stay on the validated schema-v2 generation.
- New lines appended during build are caught before promotion.
- Foreign-key, accounting, rollup, privacy, and size checks pass before
  promotion.
- Failed promotion leaves schema v2 active.
- The previous database remains recoverable until explicit maintainer
  deletion.
- No runtime compatibility adapter reads both schemas.

## Performance And Size Proof

Use the R1 production-shaped generator to measure:

- table, index, and total bytes;
- row counts by fact and rollup;
- allowance snapshot and interval reduction;
- join and common-query plans;
- rebuild and rollback cost.

Required: <700 MiB. Stretch: <500 MiB.

## Parallel Execution

R2 is sequential because schema, identity, and migration are shared contracts.
Read-only subagents may audit SQLite layout, allowance semantics, or privacy.
They return recommendations to the R2 owner; they do not edit schema files.

After R2 merges, R3, R4, and the R7 harness lane may work in parallel from the
same recorded schema-contract SHA.

## Validation

- schema and foreign-key tests;
- accounting oracle;
- copied-source reconciliation;
- allowance interval golden tests;
- exact rollup recomputation comparison;
- side-by-side promotion and rollback;
- interrupted migration recovery;
- storage budget;
- privacy scan.

## Acceptance

- No foundational information required by the roadmap is lost.
- Allowance deltas belong to intervals, not final calls.
- Stable selectors survive a clean rebuild.
- Common rollups are generation-consistent.
- The measured size gate passes.
- R3 and R4 have disjoint implementation ownership.

## Handoff

Record the schema-contract SHA, table inventory, index inventory, and approved
upgrade behavior in the ledger. R3 and R4 must use that exact base.
