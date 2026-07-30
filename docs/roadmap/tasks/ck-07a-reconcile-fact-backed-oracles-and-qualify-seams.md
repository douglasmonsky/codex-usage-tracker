# CK-07A — Reconcile fact-backed oracles and qualify packet seams

**Status:** Ready to resume after CK-07C merges; not requalified
**Accounting:** [TASK_PACKETS.md](../TASK_PACKETS.md)
**Roadmap:** [AGENT_FIRST_CLEAN_CUTOVER.md](../AGENT_FIRST_CLEAN_CUTOVER.md)

**Goal:** Restore one executable truth chain from synthetic scenario through
canonical database-v1 publication and independently calculated question
answers, then requalify CK-03 through CK-07 before CK-08 resumes.

**Why:** CK-08 proved that the frozen CK-03 question rows and the canonical
facts emitted for the same requests describe different realities. CK-04's
candidate-only `question_cases` query hid that mismatch instead of deriving
answers from permitted facts.

**Controls:** CK-01 through CK-07,
`SUPPORTED_QUESTION_CONTRACTS.md`, `LOGICAL_KERNEL_CONTRACT.md`,
`PHYSICAL_ARCHITECTURE_BAKEOFF.md`,
`AGENT_KERNEL_DATABASE_V1_SCHEMA_CONTRACT.md`, `ADAPTER_CONTRACT.md`,
`PUBLICATION_REFRESH_RECOVERY.md`,
`FORMULA_AND_SELECTOR_CONTRACT.md`,
`QUERY_EVIDENCE_PROJECTION_CONTRACTS.md`, `QUALIFICATION_PLAN.md`, and the
[CK-08 blocker evidence](../../decisions/evidence/ck08/fact-backed-oracle-prerequisite-gap.json).
**Dependencies:** CK-07, CK-07B, and CK-07C merged and verified; CK-08 blocker evidence
merged.

## CK-07B resume authority

Consume `formula-contract-v1.json` and its schema,
`evaluate_formula`, `selector-provenance-v1.json` and its schema, and
`validate_evidence_references_v1` exactly as named by
`FORMULA_AND_SELECTOR_CONTRACT.md`. Complete each of the 80 comparisons over
the full answer including `NULL`, grades and deterministic ordering, all 185
field bindings, and the exact ordered
`(role, selector_kind, selector, provenance)` reference sequence.

The reference and database-v1 replay evaluators may share those contracts and
pure symbols only; neither may import the other or consume emitted oracle,
grading, or comparison output. A CK-04 through CK-07 lane may be carried only
when its input bytes and named execution path are both byte-identical and
path-identical. Otherwise rerun that lane and record the changed identity.

## Frozen seam contracts

The CK-07A implementation must use these exact starting authorities and real
consumer paths. A replacement evidence artifact must record old and new
identities; the old digests below identify the mismatch and are not expected
outputs.

| Seam | Starting producer identity | Required real consumer path | Independent evaluator | Executable replay and comparison | Requalification set |
| --- | --- | --- | --- | --- | --- |
| CK-03 scenario → question truth | `tests/agent_kernel/fixtures/tiny-v1/manifest.json`, revision `agent-kernel-structural-v1`, file SHA-256 `6cb0425f6a6fb755e87b5bbdf1144c7d9eca49c889577c8c9a0ec0961fe4e45e`; `oracle-bundle.json` SHA-256 `9f78b8f87c17ef5e98810be6a4a01f4a13bfc055ac8eb74c9f147a7087d8e41b`; catalog SHA-256 `51f9008297cf9cccd24dcc41b43f0e0285c71af1301090796951ba3367836824` | `tests.agent_kernel.fixtures.generator.generate.generate_fixture` → emitted structural JSONL → `tests.agent_kernel.fixtures.oracles.source_ledger.read_source_ledger` | new `tests.agent_kernel.fixtures.oracles.reference.evaluate_question_case` | `pytest tests/agent_kernel/test_fact_backed_question_oracles.py -q`; compare canonical request digest, complete expected row including NULLs, and selector logical IDs for all 80 variants | CK-03 packet, fixture README, manifest/oracle/tree digests |
| CK-04 fixture → physical correctness | `docs/decisions/evidence/ck04/aggregate-evidence.json` SHA-256 `eba27ee24851fa4919c282e1edec5af7e096cec68fce5435d26866b82b96d3ce`; decision commit `95492032373beeaa700af90b542a0a07f4220c74`; growth repetitions 3 and 4 waived | corrected structural fixture → Candidate A permitted fact tables and plans; `candidate_a.queries.run_question` must no longer read `question_cases` or another expected-answer table | new `tests.agent_kernel.fixtures.oracles.database_replay.evaluate_published_question_case` over the candidate database | `pytest tests/experiments/physical-architecture/candidate_a/test_candidate_a_query_eligibility.py tests/agent_kernel/test_fact_backed_question_oracles.py -q`; compare all 80 rows/selectors, query sources/plans, response bytes, affected timings, selection score, and sensitivity result | CK-04 packet, decision query claim, affected aggregate/scoring evidence; growth waiver remains |
| CK-05 canonical storage | `docs/decisions/evidence/ck05/canonical-storage-evidence.json` SHA-256 `b286907f73621283242af3099834732a2d26f62c6fdc05d36f59e0e5adbe33e1`; merged PR evidence at main before CK-07A | `codex_usage_tracker.agent_kernel.storage.database.initialize_analytical`, typed repositories, `codex_usage_tracker.agent_kernel.storage.database.open_read_only` | `tests.agent_kernel.fixtures.oracles.database_replay.evaluate_published_question_case` over database-v1 | `pytest tests/agent_kernel/storage tests/agent_kernel/test_fact_backed_question_oracles.py -q`; compare schema digest/inventory, identities, canonical counts, occurrence accounting, and all 80 replay rows | CK-05 packet/evidence and storage measurements |
| CK-06 source → proposed changes | `docs/decisions/evidence/ck06/codex-adapter-ingestion-evidence.json` SHA-256 `b45d88ceb799037090f06b79761168dbb7fba4554ba9e44a6582fc3fe94cb1cf`; merged CK-06 evidence | `codex_usage_tracker.agent_kernel.adapters.codex_jsonl.ingest.ingest` on the corrected emitted source files | scenario declarations plus `tests.agent_kernel.fixtures.oracles.reference.evaluate_question_case` | `pytest tests/agent_kernel/adapters tests/agent_kernel/test_fact_backed_question_oracles.py -q`; compare typed proposed facts, capabilities, cursors, privacy, strict counts, and prove grading metadata produces no proposed fact | CK-06 packet/evidence, ingestion counts/timings |
| CK-07 proposed changes → publication | `docs/decisions/evidence/ck07/publication-refresh-recovery-evidence.json` SHA-256 `36eb76ca286b3448037857b701caab9371afc704a22bc479523149e70aca41eb`; merged CK-07 main `7ff3eaa268def98dfbff0693160211ffb0c2cedc` | `codex_usage_tracker.agent_kernel.publication.writer.prepare_write_set_from_changes` → `codex_usage_tracker.agent_kernel.publication.writer.PublicationWriter.publish` → `codex_usage_tracker.agent_kernel.storage.database.open_read_only` on the committed database-v1 publication | `tests.agent_kernel.fixtures.oracles.database_replay.evaluate_published_question_case` | `pytest tests/agent_kernel/publication tests/agent_kernel/test_fact_backed_question_oracles.py -q`; compare all 80 rows and occurrence selectors after initial build, rebuild, replacement, and late event, plus unchanged recovery/tail results | CK-07 packet/evidence, publication counts/timings, CK-08 unblock gate |

Every command runs with `.venv/bin/python -m` from the exact worktree. The
final evidence records the exact merged dependency SHA used for each row.

## Frozen correction formats

- The corrected fixture revision is `agent-kernel-structural-v2` under
  `tests/agent_kernel/fixtures/tiny-v2/`. The historical `tiny-v1` artifacts
  remain evidence only and are not runtime or qualification inputs after
  CK-07A.
- `question-scenarios.json` is outside `sources/` and has schema
  `codex-usage-tracker.synthetic-question-scenarios.v1`. Its top level is
  `schema`, `fixture_revision`, and ordered `cases`. Each case contains
  `oracle_id`, `question_id`, `variant`, normalized typed `request`, ordered
  canonical structural record declarations, required selector kinds, and the
  question-contract digest. It contains no expected row.
- Emitted source JSONL contains only adapter-ingestible structural events.
  `oracle_case`, expected rows, answer grades, and grading metadata are absent.
- `oracles.reference.evaluate_question_case` consumes the scenario declaration,
  locked catalog/formulas, and serialized occurrence map. It produces the
  expected row and selectors without SQLite or production code.
- `oracles.database_replay.evaluate_published_question_case` consumes only a
  read-only Candidate A or database-v1 connection plus the normalized request.
  It cannot import the reference evaluator, oracle bundle, or scenario expected
  output. It is test-only and cannot be imported by
  `src/codex_usage_tracker/agent_kernel/`.
- The regenerated oracle bundle uses
  `codex-usage-tracker.synthetic-oracle-bundle.v2`. Its expected rows come only
  from `oracles.reference.evaluate_question_case`.
- CK-07A evidence uses
  `codex-usage-tracker.ck07a-fact-backed-oracle-and-seam-qualification-evidence.v1`
  and records every seam-table identity, command, result, comparison digest,
  measurement, requalified evidence path, and residual risk.

**Scope and expected files:**

- freeze one scenario declaration, expected-row, selector, and seam-evidence
  format before parallel implementation;
- change the CK-03 generator/oracle modules so every question variant emits
  canonical typed facts for its exact typed request;
- calculate expected rows with an independent reference evaluator over those
  scenario facts, never production SQL or copied grading output;
- move `oracle_case` and equivalent grading metadata outside the runtime source
  stream, or prove the adapter rejects it without creating canonical facts;
- replace CK-04's `question_cases` answer proof with fact-backed qualification
  over permitted tables, rerun affected correctness/planner/payload/timing and
  aggregate score/sensitivity evidence, and preserve the recorded growth
  waiver;
- replay CK-05 storage, CK-06 adapter/ingestion, and CK-07
  publication/recovery acceptance against the corrected fixture;
- regenerate committed tiny fixture bytes, manifests, oracle bundle, exact
  digests, strict counts, and affected measurements;
- add
  `docs/decisions/evidence/ck07a/fact-backed-oracle-and-seam-qualification-evidence.json`;
- amend CK-03 through CK-07 packet/evidence records by linking the CK-07A
  requalification result rather than deleting their historical evidence.

**Schema/API changes:** Synthetic scenario/oracle formats may receive a new
version. No production database-v1 table, public MCP/CLI/skill schema, or
projection is admitted. A targeted CK-05–CK-07 implementation correction is
allowed only when an executable replay proves a real deficiency in the
existing owned boundary and the evidence names it exactly.

**Non-goals:** CK-08 query/evidence implementation, CK-09 projections, public
MCP/setup/CLI/skill, Console, generic SQL, narrative analysis, real Codex logs,
frozen 0.28 imports, local tracker databases, release/tag/publish/deploy, or
Linear mutation.

**Invariants:**

- keep all 40 catalog questions, 21 Foundation/Cutover named plans, 42
  Foundation/Cutover variants, IDs, grades, formulas, limits, ordering, and
  prohibited claims unless a separately recorded product-contract conflict
  forces a stop;
- correct the unified oracle generator for all 80 variants so one bundle
  cannot retain mixed truth-lineage classes;
- one scenario declaration emits canonical facts; an independent evaluator
  derives expected rows; the actual downstream consumer derives the same rows;
- reference and production paths may share locked formulas and typed contracts
  but never computed answer rows;
- every required selector resolves to an actual database-v1 entity and source
  occurrence coordinate;
- mutating grading metadata cannot change a consumer result; mutating canonical
  facts changes the consumer result and breaks oracle equivalence;
- no `question_cases`, `oracle_case` runtime read, answer cache, projection,
  generic SQL surface, refresh/write query path, or spike dependency;
- synthetic structural fixtures only; no raw bodies, secrets, private paths,
  or local databases.

**Required tests/checks:**

- consume the exact merged CK-07C
  `plan-operand-contract-v1.json` and paired schema through
  `compile_plan_operands` and `evaluate_plan`; the reference and database-v1
  lanes independently normalize permitted relation rows and may not share
  selection code, operands, answers, owner-resolution results, or comparison
  output;
- fail-first reproduction of the frozen `Q-ACC-01` mismatch;
- all 80 question variants reconcile scenario facts to independent expected
  rows and replay through CK-06, CK-07, and database-v1;
- exact request windows, missingness, four token columns, valuation/rate-card,
  allowance compatibility, hierarchy, lifecycle, ties, and selector
  coordinates;
- grading-metadata and canonical-fact mutation tests;
- CK-04 all-variant correctness, query-plan/table allowlist, response payload,
  affected timing, score, and sensitivity rerun proving no expected-answer
  table; a CK-04 lane may be carried forward only when the evidence proves its
  input digest and execution path are unchanged by CK-07A;
- unchanged CK-05 repository/identity/accounting checks;
- unchanged CK-06 discovery/cursor/normalization/privacy checks;
- unchanged CK-07 no-change/tail/rebuild/replacement/late-event/crash checks;
- deterministic fixture generation across supported Python versions;
- focused tests first, then `just v`; run `just vc` because committed fixture
  assets and build membership/digests change;
- before each commit, GitNexus check plus exact staged `detect_changes` against
  `origin/main`.

**Measurements:** Record exact old/new fixture bytes and digests, catalog and
variant counts, canonical row counts, per-variant reconciliation results,
selector-coordinate counts, fixture generation time, CK-05 storage and CK-06
ingestion counts, CK-07 publication/tail measurements, SQL sources/plans for
the fact-backed proof, response payloads where applicable, privacy scan,
review findings, reviewer token status, and the unchanged CK-04 growth waiver.
Byte ratchets allow at most 25% headroom; exact counts remain strict.

**Acceptance:**

1. All 80 expected rows are independently derived from canonical scenario
   facts and replay exactly through the real CK-06/CK-07/database-v1 path.
2. The fact-backed proof contains no candidate-only or runtime expected-answer
   table and no oracle/grading input in the consumer path.
3. Every required selector resolves to a real canonical entity and occurrence
   coordinate and remains stable across rebuild, replacement, and late event.
4. CK-04 affected correctness and scoring evidence is recomputed against the
   corrected fixture; any carried lane proves byte-identical inputs and an
   unchanged execution path. CK-05–CK-07 acceptance passes unchanged, or any
   narrowly necessary correction is explicitly evidenced, owned, and
   requalified.
5. CK-03–CK-07 historical evidence remains preserved and links one canonical
   CK-07A requalification artifact with exact hashes and results.
6. One final comprehensive read-only reviewer has no unresolved accepted
   finding; required CI passes; the PR is merged and exact `main` is verified.
7. Only after all prior items pass may CK-08 change from blocked to ready.

**Failure/rollback:** If a locked product/logical contract cannot be
materialized as canonical facts, record the exact conflicting question,
formula, or missing physical prerequisite and stop. Do not change expected
rows to match incidental fixture output, add an answer table, weaken grades or
limits, admit a projection, or begin CK-08. Before merge, rollback is the
packet branch; after merge, revert the corrective packet as one unit and keep
CK-08 blocked.

**Cleanup/docs:** Update the qualification claim class, fixture README,
affected packet/evidence links, roadmap ledger, and current-boundary index.
Retain the CK-08 blocker artifact as historical reproduction evidence. Record
the merged SHA and create a separate CK-08 task only after exact-main
verification.

**Parallelism:** The primary integrator first freezes the shared scenario,
expected-row, selector, and seam-evidence schemas. Then these lanes may proceed
in disjoint files:

- scenario/canonical-fact generator and independent reference evaluator;
- CK-04 fact-backed proof replacement;
- CK-05–CK-07 replay harness and evidence refresh.

No lane independently changes shared schemas, the question catalog, the
ledger, or the canonical CK-07A evidence format.

**Suggested commits:**

1. `test: freeze fact-backed question seam contracts`
2. `fix: derive question oracles from canonical scenarios`
3. `test: replace candidate answer-table qualification`
4. `test: requalify canonical ingestion and publication seams`
5. `docs: record CK-07A seam qualification evidence`
