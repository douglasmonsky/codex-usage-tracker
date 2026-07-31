# CK-07D — Implement effective-dated rate-card valuation

**Status:** Completed on merge via PR #385; exact-main verified at `e49531b0775c5c7f1043497042c25a200b447bb7`
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Ensure a configured pricing revision applies only to model calls at
or after its explicit effective time, while preserving canonical call facts
and deterministic current-estimate valuation.

**Why:** CK-07C added a pure valuation relation, but
`compile_current_valuation_matches` accepts one `CurrentRateCard` and applies
that revision to every call. It does not read the call's `event_at_us`, even
though database-v1 already stores both call event time and
`rate_card_revisions.effective_at_us`. Publishing a newly selected card would
therefore reprice all historical calls. The exact reproduction is recorded in
[effective-dated-valuation-gap.json](../../decisions/evidence/ck07d/effective-dated-valuation-gap.json).

**Dependencies:** merged CK-07C at
`dbf98ff4ac971e41442af871e9241c9df20b8ef5`, its plan-operand and valuation
evidence, and the retained CK-07A/CK-08 blocker evidence.

**Controls:** `LOGICAL_KERNEL_CONTRACT.md`,
`PLAN_OPERAND_AND_FACT_CONTRACT.md`,
`AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md`,
`PUBLICATION_REFRESH_RECOVERY.md`,
`QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`,
`SUPPORTED_QUESTION_CONTRACTS.md`, `TARGET_ARCHITECTURE.md`,
`QUALIFICATION_PLAN.md`, and the CK-07/CK-07A/CK-07C packets.

## Frozen valuation semantics

- Valuation is a current configured estimate over immutable canonical calls.
  It is not provider billing truth, historical-as-observed pricing, or a stored
  per-call answer.
- An accepted publication captures an immutable, validated rate-card
  frontier. The frontier identifies the admitted revision lineage and its head
  digest; it is sufficient to reproduce every selected revision without
  consulting mutable configuration or a clock.
- Every cost-bearing revision has an explicit signed UTC-microsecond
  `effective_at_us`, immutable digest, source provenance, validation status,
  model/profile/effort/service-tier match rules, four-class token rates, and
  optional credit rates. `fetched_at_us` is provenance only and must never
  choose the cutover boundary.
- For each call, consider only valid revisions captured by the publication.
  A revision is time-eligible when
  `revision.effective_at_us <= call.event_at_us`. Select the greatest eligible
  effective time whose rules match the call. Adjacent revisions therefore own
  half-open intervals `[effective_at_us, next_effective_at_us)`.
- At one effective time, exact model-profile matching precedes alias matching.
  Multiple matching revisions at the same effective time and precedence are
  ambiguous and fail closed; insertion order, fetch time, and digest order
  cannot break the tie.
- A revision may change pricing for only a subset of models. Calls for
  unchanged models continue searching older eligible revisions rather than
  becoming unpriced or inheriting an unrelated new price.
- A late-ingested historical call selects the revision effective at the call's
  event time. Adding a later-effective revision cannot change the selected
  revision digest or value of an earlier call.
- A deliberately backdated correction changes the current configured estimate
  from its explicit effective time. Reproducing the rate known at ingestion or
  the provider's amount charged would require persisted call-to-revision or
  billing facts and is outside this packet.

## Fail-closed behavior

Missing or malformed call time, missing revision effective time, no
yet-effective matching revision, invalid revision, publication/head mismatch,
missing predecessor, lineage cycle, or ambiguous overlap produces `NULL`
configured cost/credits with a stable typed unpriced reason. It never produces
zero, uses a future revision, falls back to fetch time, or silently selects an
arbitrary card.

`derive_pricing_coverage_v1` counts a call as priced only when its valuation
has a configured-estimate cost grade/value. The mere presence of a typed
unpriced `valuation_match` row does not make the call priced.

## Minimal implementation boundary

- Extend the existing database-v1 rate-card representation only as needed to
  encode and validate one revision lineage/frontier. Prefer an explicit
  predecessor or series identity on `rate_card_revisions`; retain
  `active_rate_card` as the publication-selected head.
- Make `effective_at_us` mandatory for a valid cost-bearing revision and
  validate the complete captured lineage before publication promotion.
- Replace the singular pure-compiler input with the ordered publication
  frontier and select one revision per call using the frozen semantics above.
- Include the selected revision digest in every valuation result and derive
  valuation identity from the call plus that digest.
- Keep `model_calls` unchanged. Do not add a persisted valuation cache,
  call-to-rate assignment, migration, compatibility view, clock read, storage
  read inside the pure compiler, or live pricing fetch in tests.
- Update the schema digest/inventory and preserve rebuild-only compatibility:
  an old database-v1 digest fails closed and rebuilds.
- Correct pricing-coverage derivation so typed unpriced rows remain unpriced.
- Amend the controlling contracts and CK-07A resume authority in the same
  implementation change.

**Invariants:** Canonical calls remain immutable; call event time alone chooses
the eligible pricing interval; fetch time and insertion order never choose a
price; missing or ambiguous inputs remain typed and `NULL`; Decimal and
four-token-class behavior remains exact; all tests and evidence stay synthetic
and body-free.

**Expected owned paths:** `src/codex_usage_tracker/agent_kernel/domain/valuation.py`,
`src/codex_usage_tracker/agent_kernel/domain/plan_derivations_accounting.py`,
the database-v1 schema/repository/publication surfaces, their focused tests,
logical/schema vectors, the controlling architecture and qualification
documents, and CK-07D evidence. Do not broaden into CK-07A scenario repair or
CK-08 query implementation.

**Non-goals:** actual OpenAI price values, web retrieval during runtime or
tests, provider invoice reconciliation, historical-as-known valuation,
persisted per-call prices, rewriting canonical calls, spike/0.28 changes,
migration or compatibility views, CK-07A's 80-case requalification, CK-08,
projections, MCP/CLI/UI, release, deployment, or Linear mutation.

## Required fail-first and acceptance checks

**Required tests/checks:** Implement the twelve fail-first and acceptance checks
below, then run the focused valuation, plan, schema, storage, publication, and
scope suites followed by `just v`, `just vc`, required CI, and exact-main
post-merge verification.

1. Before-boundary, exact-boundary, and after-boundary calls select old, new,
   and new revisions respectively.
2. A late-ingested pre-boundary call selects the old revision, and admitting a
   later-effective revision leaves all earlier-call valuation digests and
   values unchanged.
3. A new revision matching one changed model does not replace the older
   matching revision for unchanged models.
4. Future, invalid, missing-effective-time, missing-call-time, and unmatched
   revisions produce stable typed unpriced results with `NULL` values.
5. Missing predecessor, lineage cycle, publication/head mismatch, and
   equal-effective equal-precedence overlap fail closed before arbitrary
   valuation can be published.
6. Exact-profile precedence over alias remains deterministic at the same
   effective time.
7. Four token classes, reasoning-in-output semantics, Decimal serialization,
   partial rate coverage, and cost/credit missingness remain unchanged.
8. Pricing coverage excludes typed unpriced valuation rows and reports their
   tokens as unpriced.
9. Initial build, ordinary tail, rebuild, replacement, late event, no-change,
   and crash recovery preserve the publication-captured frontier and selected
   revision digests.
10. Focused valuation, plan-operand, pricing-coverage, logical, schema,
    storage, publication, and release-scope tests pass, followed by `just v`
    and `just vc`.
11. A newer eligible alias match beats an older exact-profile match; exact
    profile beats alias only when both matches have the same effective time.
    This proves time selection occurs before same-time match precedence.
12. A deliberately backdated revision changes pure-compiler and published
    valuations only in `[effective_at_us, next_effective_at_us)` for the
    affected match rules, dirties that historical interval, and preserves
    selected digests and values outside it through publication/recovery.

## Implementation and merge record

The implementation and its coupled evidence are recorded in
[effective-dated-valuation-implementation-evidence.json](../../decisions/evidence/ck07d/effective-dated-valuation-implementation-evidence.json).
The local branch now contains the pure frontier compiler, typed fail-closed
reasons, immutable predecessor-chain storage, atomic publication/head
validation, bounded valuation dirty intervals, corrected pricing coverage, and
the CK-05/CK-07/CK-07C focused requalification lane. Historical CK-07C evidence
remains unchanged.

PR #385 passed required CI, merged as
`e49531b0775c5c7f1043497042c25a200b447bb7`, and was verified as exact
`origin/main`. The implementation evidence remains the immutable pre-merge
record; this packet and CK-07E accounting record the merge acceptance. CK-07A
remains zero of 80 variants requalified and CK-08 remains blocked pending the
independent fact-adapter prerequisite.

## Requalification and acceptance

- Requalify CK-05 schema/storage identity and rebuild behavior.
- Requalify CK-07 publication manifest, valuation-only change, no-change/tail,
  rebuild, replacement, late-event, and recovery behavior.
- Requalify CK-07C valuation-relation and plan-operand integration evidence.
- Resume CK-07A only after an independent synthetic boundary evaluator and
  database-v1 replay agree on selected revision digest, configured value,
  grade, missingness, and pricing coverage. CK-08 remains blocked.
- Record exact old/new schema digests, frontier identities, focused/full check
  results, synthetic boundary comparison digests, affected prior-evidence
  links, measurements, review findings, and residual risks.
- Before every commit, run repository bootstrap GitNexus check plus exact
  `detect_changes` against `origin/main`. Run one final comprehensive
  read-only reviewer after the diff is stable.

**Acceptance:** All twelve checks and four requalification lanes above pass; the
implementation contains no time-blind singular-card valuation path; no
historical call is repriced by a later-effective revision; one final reviewer
has no unresolved accepted finding; required CI passes; the PR is merged and
exact `main` is verified.

**Failure/rollback:** If the captured frontier cannot deterministically
reproduce revision selection, if a consumer needs billed or historical-as-known
truth, or if lineage validation needs a broader configuration system, record
the exact residual and keep CK-07A/CK-08 blocked. Before merge, rollback is the
implementation branch. After merge, revert CK-07D as one corrective packet and
rebuild database-v1; do not migrate or reinterpret existing files.

**Cleanup/docs:** Preserve CK-07C evidence as historical truth and link its
requalification result. Update packet status, roadmap accounting, architecture
contracts, qualification authority, schema inventory/digest, and durable
CK-07D implementation evidence together.

**Suggested commit:** `feat(agent-kernel): implement effective-dated valuation`
